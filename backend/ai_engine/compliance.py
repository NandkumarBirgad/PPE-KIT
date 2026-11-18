import cv2
import numpy as np
import time
from config import Config
from ai_engine.temporal_compliance import (
    TemporalState,
    TrackPPEState,
    SessionTemporalTracker,
    get_session_temporal_tracker,
    reset_session_temporal,
    sanitize_timestamp
)

CANONICAL_PPE_REGION_MAP = {
    "helmet": "head",
    "vest": "torso",
    "goggles": "face",
    "boots": "feet"
}

CANONICAL_PPE_ORDER = getattr(Config, "CANONICAL_PPE_ORDER", ["helmet", "vest", "goggles", "boots"])

def normalize_ppe_class(raw_class):
    """
    Maps aliases and casing variations to canonical 4 PPE classes.
    """
    if not raw_class:
        return ""
    c = str(raw_class).lower().strip()
    if c in CANONICAL_PPE_REGION_MAP:
        return c
    for alias, canonical in [
        ("hard hat", "helmet"), ("safety helmet", "helmet"), ("hardhat", "helmet"),
        ("safety vest", "vest"), ("reflective vest", "vest"), ("jacket", "vest"),
        ("safety glasses", "goggles"), ("glasses", "goggles"), ("eye wear", "goggles"),
        ("safety boots", "boots"), ("safety_shoe", "boots"), ("shoes", "boots"), ("footwear", "boots"), ("boot", "boots")
    ]:
        if alias in c:
            return canonical
    return c

def sort_canonical_ppe(ppe_list):
    """
    Sorts a collection of PPE class strings deterministically:
    ['helmet', 'vest', 'goggles', 'boots'] followed by any non-canonical items.
    """
    order_map = {cls: idx for idx, cls in enumerate(CANONICAL_PPE_ORDER)}
    unique_items = list(dict.fromkeys(ppe_list))
    return sorted(unique_items, key=lambda x: order_map.get(x.lower(), 99))

def compute_box_intersection_ratio(box_inner, box_outer):
    """
    Computes what percentage of box_inner's area is inside box_outer.
    box: [x1, y1, x2, y2]
    """
    if not box_inner or not box_outer or len(box_inner) < 4 or len(box_outer) < 4:
        return 0.0

    ix1 = max(box_inner[0], box_outer[0])
    iy1 = max(box_inner[1], box_outer[1])
    ix2 = min(box_inner[2], box_outer[2])
    iy2 = min(box_inner[3], box_outer[3])

    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    intersection_area = (ix2 - ix1) * (iy2 - iy1)
    inner_area = (box_inner[2] - box_inner[0]) * (box_inner[3] - box_inner[1])

    if inner_area <= 0:
        return 0.0
    return intersection_area / inner_area

def compute_person_anatomical_regions(person_box, img_shape=None, region_config=None):
    """
    Constructs anatomical sub-bounding boxes for a person.
    Initial geometric proportions:
      - Head: 0-25%
      - Face: 10-30%, central 60% width
      - Torso: 25-70%
      - Feet: 75-100%
    Clipped to image boundaries if img_shape is provided.
    Invalid or zero-area input boxes return empty dict.
    """
    if not person_box or len(person_box) < 4:
        return {}

    px1, py1, px2, py2 = [float(c) for c in person_box[:4]]
    pw = px2 - px1
    ph = py2 - py1

    if pw <= 0 or ph <= 0:
        return {}

    head_r = getattr(Config, "PPE_REGION_HEAD_RATIO", (0.0, 0.25))
    face_r = getattr(Config, "PPE_REGION_FACE_RATIO", (0.10, 0.30, 0.20, 0.80))
    torso_r = getattr(Config, "PPE_REGION_TORSO_RATIO", (0.25, 0.70))
    feet_r = getattr(Config, "PPE_REGION_FEET_RATIO", (0.75, 1.0))

    if region_config:
        head_r = region_config.get("head", head_r)
        face_r = region_config.get("face", face_r)
        torso_r = region_config.get("torso", torso_r)
        feet_r = region_config.get("feet", feet_r)

    raw_regions = {
        "head": [
            px1,
            py1 + ph * head_r[0],
            px2,
            py1 + ph * head_r[1]
        ],
        "face": [
            px1 + pw * face_r[2],
            py1 + ph * face_r[0],
            px1 + pw * face_r[3],
            py1 + ph * face_r[1]
        ],
        "torso": [
            px1,
            py1 + ph * torso_r[0],
            px2,
            py1 + ph * torso_r[1]
        ],
        "feet": [
            px1,
            py1 + ph * feet_r[0],
            px2,
            py1 + ph * feet_r[1]
        ]
    }

    max_x = img_shape[1] if (img_shape and len(img_shape) >= 2 and img_shape[1] is not None) else float("inf")
    max_y = img_shape[0] if (img_shape and len(img_shape) >= 2 and img_shape[0] is not None) else float("inf")

    clipped_regions = {}
    for region_name, (rx1, ry1, rx2, ry2) in raw_regions.items():
        cx1 = max(0, min(int(round(rx1)), int(max_x))) if max_x != float("inf") else max(0, int(round(rx1)))
        cy1 = max(0, min(int(round(ry1)), int(max_y))) if max_y != float("inf") else max(0, int(round(ry1)))
        cx2 = max(0, min(int(round(rx2)), int(max_x))) if max_x != float("inf") else max(0, int(round(rx2)))
        cy2 = max(0, min(int(round(ry2)), int(max_y))) if max_y != float("inf") else max(0, int(round(ry2)))

        if cx2 > cx1 and cy2 > cy1:
            clipped_regions[region_name] = [cx1, cy1, cx2, cy2]
        else:
            clipped_regions[region_name] = [cx1, cy1, cx1, cy1]

    return clipped_regions

def max_weight_bipartite_matching(cost_matrix):
    """
    Pure Python global maximum weight bipartite matching (Hungarian / Jonker-Volgenant style).
    cost_matrix: N x M list of lists (non-negative weights).
    Returns: list of (row_idx, col_idx) optimal pairs maximizing sum of weights.
    Runs in O(V^3) time without external dependencies.
    """
    n = len(cost_matrix)
    if n == 0:
        return []
    m = len(cost_matrix[0])
    if m == 0:
        return []

    dim = max(n, m)
    u = [0.0] * (dim + 1)
    v = [0.0] * (dim + 1)
    p = [0] * (dim + 1)
    way = [0] * (dim + 1)

    max_val = max(max(row) for row in cost_matrix) if any(cost_matrix) else 1.0
    cost = [[0.0] * (dim + 1) for _ in range(dim + 1)]
    for i in range(dim):
        for j in range(dim):
            if i < n and j < m:
                cost[i + 1][j + 1] = max_val - cost_matrix[i][j]
            else:
                cost[i + 1][j + 1] = max_val

    for i in range(1, dim + 1):
        p[0] = i
        j0 = 0
        minv = [float('inf')] * (dim + 1)
        used = [False] * (dim + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = float('inf')
            j1 = 0
            for j in range(1, dim + 1):
                if not used[j]:
                    cur = cost[i0][j] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(dim + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break

    ans = []
    for j in range(1, m + 1):
        if p[j] != 0 and p[j] <= n:
            i = p[j] - 1
            j_orig = j - 1
            ans.append((i, j_orig))
    return ans

def associate_ppe_with_persons(persons, detected_objects, img_shape=None, min_score=None, ambiguity_margin=None):
    """
    Exclusive, body-region-aware PPE-to-worker association engine.
    - Constructs anatomical sub-boxes for each tracked worker.
    - For each canonical PPE class independently:
      * Maps PPE class to target body region.
      * Computes containment score matrix between eligible detections and workers' regions.
      * Solves global maximum weight bipartite matching (1-to-1).
      * Rejects candidates failing min score or falling within ambiguity margin.
    - Appends structured evidence to person["ppe_associations"].
    - Populates person["worn_ppe"] strictly with valid genuine YOLO associations.
    """
    min_score = min_score if min_score is not None else getattr(Config, "PPE_ASSOCIATION_MIN_SCORE", 0.35)
    ambiguity_margin = ambiguity_margin if ambiguity_margin is not None else getattr(Config, "PPE_ASSOCIATION_AMBIGUITY_MARGIN", 0.08)

    if not persons:
        return persons

    if detected_objects is None or len(detected_objects) == 0:
        for person in persons:
            if "worn_ppe" not in person:
                person["worn_ppe"] = []
            if "ppe_associations" not in person:
                person["ppe_associations"] = []
        return persons

    for person in persons:
        person["worn_ppe"] = []
        person["ppe_associations"] = []

    # 1. Compute anatomical regions for each person
    person_regions = [
        compute_person_anatomical_regions(p.get("bbox", []), img_shape=img_shape)
        for p in persons
    ]

    # 2. Iterate each canonical class independently
    num_persons = len(persons)
    for canonical_cls in CANONICAL_PPE_ORDER:
        target_region = CANONICAL_PPE_REGION_MAP.get(canonical_cls)
        if not target_region:
            continue

        # Collect detections matching this canonical class
        class_detections = [
            obj for obj in detected_objects
            if normalize_ppe_class(obj.get("class", "")) == canonical_cls
        ]

        if not class_detections:
            continue

        # Separate genuine YOLO detections from synthetic/heuristic detections
        genuine_detections = [
            d for d in class_detections
            if (not d.get("is_synthetic", False)) and d.get("source") == "yolo"
        ]
        synthetic_detections = [
            d for d in class_detections
            if d.get("is_synthetic", False) or d.get("source") != "yolo"
        ]

        def _solve_class_assignment(candidates):
            """
            Solves 1-to-1 bipartite assignment with global alternative ambiguity check
            for a candidate set of detections against all persons.
            """
            if not candidates or num_persons == 0:
                return []

            num_dets = len(candidates)
            score_matrix = [[0.0] * num_dets for _ in range(num_persons)]

            for i, p in enumerate(persons):
                p_box = p.get("bbox", [])
                if len(p_box) < 4:
                    continue
                pw = p_box[2] - p_box[0]
                region_box = person_regions[i].get(target_region)
                if not region_box or (region_box[2] <= region_box[0] or region_box[3] <= region_box[1]):
                    continue

                for j, det in enumerate(candidates):
                    d_box = det.get("bbox", [])
                    if len(d_box) < 4:
                        continue

                    containment = compute_box_intersection_ratio(d_box, region_box)
                    d_center_x = (d_box[0] + d_box[2]) / 2.0
                    is_aligned_x = (p_box[0] - 0.25 * pw) <= d_center_x <= (p_box[2] + 0.25 * pw)

                    if containment >= min_score and is_aligned_x:
                        score_matrix[i][j] = float(containment)

            eligible_matrix = [
                [score_matrix[i][j] if score_matrix[i][j] >= min_score else 0.0 for j in range(num_dets)]
                for i in range(num_persons)
            ]

            raw_matches = max_weight_bipartite_matching(eligible_matrix)
            valid_matches = [(w, d) for w, d in raw_matches if eligible_matrix[w][d] >= min_score]
            total_optimal = sum(eligible_matrix[w][d] for w, d in valid_matches)

            accepted = []
            for w_idx, d_idx in valid_matches:
                score = eligible_matrix[w_idx][d_idx]

                # Global Alternative Ambiguity Evaluation
                alt_matrix = [row[:] for row in eligible_matrix]
                alt_matrix[w_idx][d_idx] = 0.0

                alt_matches = max_weight_bipartite_matching(alt_matrix)
                alt_valid = [(aw, ad) for aw, ad in alt_matches if alt_matrix[aw][ad] >= min_score]
                total_alt = sum(alt_matrix[aw][ad] for aw, ad in alt_valid)

                global_delta = total_optimal - total_alt
                if global_delta < ambiguity_margin:
                    # Ambiguous alternative global assignment exists within margin: reject
                    continue

                accepted.append((w_idx, d_idx, score))

            return accepted

        # 1. Authoritative assignment: genuine YOLO detections ONLY
        genuine_matches = _solve_class_assignment(genuine_detections)
        authoritative_matched_workers = set()

        for w_idx, d_idx, score in genuine_matches:
            matched_det = genuine_detections[d_idx]
            worker = persons[w_idx]
            worker_id = worker.get("worker_id", f"W-{w_idx+1:03d}")

            evidence = {
                "ppe_class": canonical_cls,
                "name": matched_det.get("name", canonical_cls),
                "confidence": round(float(matched_det.get("confidence", 0.0)), 4),
                "bbox": [int(c) for c in matched_det["bbox"]],
                "detection_source": "yolo",
                "is_synthetic": False,
                "assigned_worker_id": worker_id,
                "matched_region": target_region,
                "region_bbox": [int(c) for c in person_regions[w_idx].get(target_region, [])],
                "association_score": round(float(score), 4),
                "is_valid_wear": True
            }
            worker["ppe_associations"].append(evidence)
            if canonical_cls not in worker["worn_ppe"]:
                worker["worn_ppe"].append(canonical_cls)
            authoritative_matched_workers.add(w_idx)

        # 2. Diagnostic assignment: synthetic/heuristic detections (never authoritative)
        if synthetic_detections:
            synthetic_matches = _solve_class_assignment(synthetic_detections)
            for w_idx, d_idx, score in synthetic_matches:
                matched_det = synthetic_detections[d_idx]
                worker = persons[w_idx]
                worker_id = worker.get("worker_id", f"W-{w_idx+1:03d}")
                det_source = matched_det.get("source", "hsv")

                evidence = {
                    "ppe_class": canonical_cls,
                    "name": matched_det.get("name", canonical_cls),
                    "confidence": round(float(matched_det.get("confidence", 0.0)), 4),
                    "bbox": [int(c) for c in matched_det["bbox"]],
                    "detection_source": det_source,
                    "is_synthetic": True,
                    "assigned_worker_id": worker_id,
                    "matched_region": target_region,
                    "region_bbox": [int(c) for c in person_regions[w_idx].get(target_region, [])],
                    "association_score": round(float(score), 4),
                    "is_valid_wear": False  # Synthetic evidence is strictly non-authoritative
                }
                worker["ppe_associations"].append(evidence)
                # CRITICAL: worker["worn_ppe"] is NEVER populated from synthetic evidence!

    for person in persons:
        person["worn_ppe"] = sort_canonical_ppe(person["worn_ppe"])

    return persons


PPE_BODY_MAPPING = {
    "helmet": "head",
    "hard hat": "head",
    "hardhat": "head",
    "safety helmet": "head",
    "mask": "face",
    "face mask": "face",
    "respirator": "face",
    "goggles": "face",
    "glasses": "face",
    "safety glasses": "face",
    "eye wear": "face",
    "vest": "torso",
    "safety vest": "torso",
    "reflective vest": "torso",
    "jacket": "torso",
    "boots": "feet",
    "shoes": "feet",
    "safety boots": "feet",
    "safety_shoe": "feet",
    "footwear": "feet",
    "gloves": "hands",
    "glove": "hands",
    "safety gloves": "hands"
}

def detect_scanned_body_parts(person_box, img_shape=None, worn_ppe=None, occluded_regions=None):
    """
    Independent body-region visibility assessment.
    Visibility is determined EXCLUSIVELY from:
      - person bounding box coordinates
      - image boundaries and clipping margins
      - anatomical aspect ratio and resolution
      - physical occlusion markers / barriers
    NEVER uses PPE detections to establish region observability.

    Returns:
      dict with:
        - head: bool
        - face: bool
        - torso: bool
        - feet: bool
        - hands: bool
        - scanned_regions: list[str] (observable regions)
        - visibility_details: dict of region -> {status, bbox, reason, is_scanned}
    """
    if not person_box or len(person_box) < 4:
        return {
            "head": False, "face": False, "torso": False, "feet": False, "hands": False,
            "scanned_regions": [],
            "visibility_details": {}
        }

    px1, py1, px2, py2 = [float(c) for c in person_box[:4]]
    pw = px2 - px1
    ph = py2 - py1

    img_h = int(img_shape[0]) if (img_shape and len(img_shape) >= 2 and img_shape[0]) else max(int(py2 + 20), 480)
    img_w = int(img_shape[1]) if (img_shape and len(img_shape) >= 2 and img_shape[1]) else max(int(px2 + 20), 640)

    if pw <= 0 or ph <= 0:
        return {
            "head": False, "face": False, "torso": False, "feet": False, "hands": False,
            "scanned_regions": [],
            "visibility_details": {
                r: {"status": "unobservable", "reason": "invalid_bounding_box", "is_scanned": False}
                for r in ["head", "face", "torso", "feet", "hands"]
            }
        }

    aspect_ratio = ph / float(pw)

    margin_top = getattr(Config, "VISIBILITY_EDGE_MARGIN_TOP", 10)
    margin_bottom = getattr(Config, "VISIBILITY_EDGE_MARGIN_BOTTOM", 25)
    margin_sides = getattr(Config, "VISIBILITY_EDGE_MARGIN_SIDES", 10)
    min_person_h = getattr(Config, "VISIBILITY_MIN_PERSON_HEIGHT", 40)
    min_face_h = getattr(Config, "VISIBILITY_MIN_FACE_HEIGHT", 80)
    min_feet_h = getattr(Config, "VISIBILITY_MIN_FEET_HEIGHT", 120)

    # Lateral clipping checks
    is_clipped_left = (px1 <= 0)
    is_partially_clipped_left = (0 < px1 <= margin_sides)
    is_clipped_right = (px2 >= img_w)
    is_partially_clipped_right = (img_w - margin_sides <= px2 < img_w)
    is_severely_clipped_lateral = is_clipped_left or is_clipped_right

    occluded_set = set(str(r).lower().strip() for r in (occluded_regions or []))

    # 1. HEAD ASSESSMENT
    head_box = [max(0, int(px1)), max(0, int(py1)), min(img_w, int(px2)), min(img_h, int(py1 + 0.25 * ph))]
    if "head" in occluded_set or "helmet" in occluded_set:
        head_status = "unobservable"
        head_reason = "head_occluded_by_object"
        is_head_scanned = False
    elif py1 < 0:
        head_status = "unobservable"
        head_reason = "head_cut_off_at_top_boundary"
        is_head_scanned = False
    elif py1 <= margin_top:
        head_status = "partially_observable"
        head_reason = "head_touches_top_edge"
        is_head_scanned = False
    elif py1 >= img_h * 0.65:
        head_status = "unobservable"
        head_reason = "head_outside_frame_bottom"
        is_head_scanned = False
    elif ph < min_person_h:
        head_status = "uncertain"
        head_reason = "insufficient_resolution"
        is_head_scanned = False
    elif is_severely_clipped_lateral:
        head_status = "partially_observable"
        head_reason = "head_clipped_laterally"
        is_head_scanned = False
    else:
        head_status = "observable"
        head_reason = "fully_in_frame"
        is_head_scanned = True

    head_details = {
        "status": head_status,
        "reason": head_reason,
        "is_scanned": is_head_scanned,
        "bbox": head_box
    }

    # 2. FACE ASSESSMENT
    face_box = [
        max(0, int(px1 + 0.20 * pw)),
        max(0, int(py1 + 0.10 * ph)),
        min(img_w, int(px1 + 0.80 * pw)),
        min(img_h, int(py1 + 0.30 * ph))
    ]
    if "face" in occluded_set or "goggles" in occluded_set:
        face_status = "unobservable"
        face_reason = "face_occluded_by_object"
        is_face_scanned = False
    elif not is_head_scanned:
        face_status = "unobservable" if head_status == "unobservable" else "uncertain"
        face_reason = "head_not_observable"
        is_face_scanned = False
    elif ph < min_face_h or pw < 30:
        face_status = "uncertain"
        face_reason = "insufficient_face_resolution"
        is_face_scanned = False
    elif is_severely_clipped_lateral or is_partially_clipped_left or is_partially_clipped_right:
        face_status = "partially_observable"
        face_reason = "face_clipped_laterally"
        is_face_scanned = False
    else:
        face_status = "observable"
        face_reason = "fully_in_frame"
        is_face_scanned = True

    face_details = {
        "status": face_status,
        "reason": face_reason,
        "is_scanned": is_face_scanned,
        "bbox": face_box
    }

    # 3. TORSO ASSESSMENT
    torso_y1 = py1 + 0.25 * ph
    torso_y2 = py1 + 0.70 * ph
    torso_box = [max(0, int(px1)), max(0, int(torso_y1)), min(img_w, int(px2)), min(img_h, int(torso_y2))]
    if "torso" in occluded_set or "vest" in occluded_set:
        torso_status = "unobservable"
        torso_reason = "torso_covered_by_object"
        is_torso_scanned = False
    elif torso_y1 >= img_h or torso_y2 <= 0:
        torso_status = "unobservable"
        torso_reason = "torso_outside_frame"
        is_torso_scanned = False
    elif torso_y1 < 0 or py1 < -margin_top:
        torso_status = "partially_observable"
        torso_reason = "torso_clipped_at_top"
        is_torso_scanned = False
    elif torso_y2 >= img_h:
        torso_status = "partially_observable"
        torso_reason = "torso_clipped_at_bottom"
        is_torso_scanned = False
    elif ph < 50:
        torso_status = "uncertain"
        torso_reason = "insufficient_torso_resolution"
        is_torso_scanned = False
    elif is_severely_clipped_lateral:
        torso_status = "partially_observable"
        torso_reason = "torso_clipped_laterally"
        is_torso_scanned = False
    else:
        torso_status = "observable"
        torso_reason = "fully_in_frame"
        is_torso_scanned = True

    torso_details = {
        "status": torso_status,
        "reason": torso_reason,
        "is_scanned": is_torso_scanned,
        "bbox": torso_box
    }

    # 4. FEET ASSESSMENT
    feet_y1 = py1 + 0.75 * ph
    feet_y2 = py2
    feet_box = [max(0, int(px1)), max(0, int(feet_y1)), min(img_w, int(px2)), min(img_h, int(feet_y2))]
    is_cut_off_at_bottom = (py2 >= img_h - margin_bottom)
    # Human standing aspect ratio is typically 2.2 - 3.5. An aspect ratio < 1.85 indicates half-body / lower body occluded
    is_half_body = (aspect_ratio < 1.85) or ((aspect_ratio < 2.0) and (py2 >= img_h * 0.55))

    if "feet" in occluded_set or "boots" in occluded_set:
        feet_status = "unobservable"
        feet_reason = "feet_hidden_behind_object"
        is_feet_scanned = False
    elif is_cut_off_at_bottom:
        feet_status = "unobservable"
        feet_reason = "feet_cut_off_at_bottom_boundary"
        is_feet_scanned = False
    elif is_half_body:
        feet_status = "unobservable"
        feet_reason = "half_body_framing"
        is_feet_scanned = False
    elif feet_y1 >= img_h:
        feet_status = "unobservable"
        feet_reason = "feet_outside_frame"
        is_feet_scanned = False
    elif ph < min_feet_h:
        feet_status = "uncertain"
        feet_reason = "insufficient_feet_resolution"
        is_feet_scanned = False
    elif (feet_y2 - feet_y1) < 25 or pw < 30:
        feet_status = "uncertain"
        feet_reason = "insufficient_feet_resolution"
        is_feet_scanned = False
    elif is_severely_clipped_lateral:
        feet_status = "partially_observable"
        feet_reason = "feet_clipped_laterally"
        is_feet_scanned = False
    else:
        feet_status = "observable"
        feet_reason = "fully_in_frame"
        is_feet_scanned = True

    feet_details = {
        "status": feet_status,
        "reason": feet_reason,
        "is_scanned": is_feet_scanned,
        "bbox": feet_box
    }

    # 5. HANDS (Conservative geometric check)
    is_hands_scanned = is_torso_scanned and (ph >= 120) and not is_severely_clipped_lateral
    hands_details = {
        "status": "observable" if is_hands_scanned else "uncertain",
        "reason": "fully_in_frame" if is_hands_scanned else "insufficient_resolution_or_clipped",
        "is_scanned": is_hands_scanned,
        "bbox": [max(0, int(px1)), max(0, int(torso_y1)), min(img_w, int(px2)), min(img_h, int(torso_y2))]
    }

    scanned_regions = []
    if is_head_scanned: scanned_regions.append("head")
    if is_face_scanned: scanned_regions.append("face")
    if is_torso_scanned: scanned_regions.append("torso")
    if is_feet_scanned: scanned_regions.append("feet")
    if is_hands_scanned: scanned_regions.append("hands")

    visibility_details = {
        "head": head_details,
        "face": face_details,
        "torso": torso_details,
        "feet": feet_details,
        "hands": hands_details
    }

    return {
        "head": is_head_scanned,
        "face": is_face_scanned,
        "torso": is_torso_scanned,
        "feet": is_feet_scanned,
        "hands": is_hands_scanned,
        "scanned_regions": scanned_regions,
        "visibility_details": visibility_details
    }


def evaluate_compliance(
    persons,
    detected_objects,
    required_ppe,
    confidence_threshold=0.35,
    img_shape=None,
    session_id=None,
    timestamp=None,
    temporal_tracker=None,
    confirmation_duration_sec=None
):
    """
    Evaluates compliance against required zone PPE ONLY for body parts
    that are actually scanned / visible in the camera frame.
    When a tracking session is active, applies temporal violation confirmation
    (default: 3.0s observable missing threshold) to smooth transient detector misses.

    Returns:
    - compliance_status: 'COMPLIANT' | 'VIOLATION' | 'UNCERTAIN'
    - missing_ppe: list of confirmed missing items across the frame
    - evaluated_persons: list of persons with individual compliance status
    """
    raw_required = [r.lower() for r in (required_ppe or ['helmet', 'vest'])]

    if not persons:
        # Empty scene: with no workers present in the monitored area, compliance
        # cannot be evaluated or violated. Loose equipment or background objects
        # must never be classified as worker compliance or worker violations.
        return "UNCERTAIN", [], []

    # Associate PPE items with individual persons
    persons = associate_ppe_with_persons(persons, detected_objects, img_shape=img_shape)

    tracker = None
    if temporal_tracker is not None:
        tracker = temporal_tracker
    elif session_id is not None:
        tracker = get_session_temporal_tracker(
            session_id,
            confirmation_duration_sec=confirmation_duration_sec
        )

    # Sanitize and resolve one consistent timestamp for the entire evaluation
    valid_ts = sanitize_timestamp(timestamp)
    if tracker is not None:
        resolved_ts = tracker.resolve_timestamp(valid_ts)
    else:
        resolved_ts = valid_ts if valid_ts is not None else time.monotonic()

    frame_violations = []
    frame_uncertain = False
    all_missing_set = set()

    for person in persons:
        p_box = person["bbox"]
        worn_set = set([w.lower() for w in person["worn_ppe"]])

        # Collect explicit occlusions and other worker boxes
        occluded = list(person.get("occluded_regions") or [])
        for k, reg in [("torso_occluded", "torso"), ("feet_occluded", "feet"), ("head_occluded", "head"), ("face_occluded", "face")]:
            if person.get(k) and reg not in occluded:
                occluded.append(reg)

        # 1. Determine which body parts are actually scanned in the camera (independent of PPE detections)
        body_scan = detect_scanned_body_parts(
            p_box,
            img_shape=img_shape,
            occluded_regions=occluded
        )
        scanned_regions = body_scan["scanned_regions"]
        vis_details = body_scan.get("visibility_details", {})
        person["body_region_visibility"] = vis_details
        person["scanned_body_parts"] = scanned_regions

        # 2. Worker required PPE: zone policy takes precedence
        z_status = person.get("zone_assignment_status", "ASSIGNED")
        policy_valid = person.get("zone_policy_valid", True)

        if z_status == "UNASSIGNED":
            worker_required = []
            is_worker_uncertain = True
            person["uncertain"] = True
            person["compliant"] = False
            person["uncertain_reason"] = "NO_MONITORED_ZONE"
        elif z_status == "UNCERTAIN":
            worker_required = []
            is_worker_uncertain = True
            person["uncertain"] = True
            person["compliant"] = False
            person["uncertain_reason"] = person.get("uncertain_reason") or "ZONE_BOUNDARY_AMBIGUITY"
        elif not policy_valid:
            worker_required = []
            is_worker_uncertain = True
            person["uncertain"] = True
            person["compliant"] = False
            person["uncertain_reason"] = person.get("uncertain_reason") or "INVALID_ZONE_POLICY"
        elif person.get("required_ppe") is not None:
            worker_required = [normalize_ppe_class(r) for r in person.get("required_ppe")]
            is_worker_uncertain = bool(person.get("is_uncertain") or (person.get("uncertain") and not person.get("temporal_state")))
        else:
            worker_required = raw_required
            is_worker_uncertain = bool(person.get("is_uncertain") or (person.get("uncertain") and not person.get("temporal_state")))

        # 3. Filter required PPE to ONLY items corresponding to scanned body parts!
        applicable_required = []
        ignored_unscanned_ppe = []

        for req in worker_required:
            req_region = PPE_BODY_MAPPING.get(req)
            if not req_region:
                if any(b in req for b in ['boot', 'shoe']): req_region = 'feet'
                elif any(v in req for v in ['vest', 'jacket']): req_region = 'torso'
                elif any(h in req for h in ['helm', 'hat']): req_region = 'head'
                elif any(g in req for g in ['glov']): req_region = 'hands'
                elif any(f in req for f in ['gogg', 'glass', 'mask']): req_region = 'face'
                else: req_region = 'torso'

            if req_region in scanned_regions:
                applicable_required.append(req)
            else:
                ignored_unscanned_ppe.append(req)

        # 4. Calculate instantaneous missing items
        instant_missing = [req for req in applicable_required if req not in worn_set]
        instant_missing = sort_canonical_ppe(instant_missing)
        person["scanned_body_parts"] = scanned_regions
        person["applicable_required_ppe"] = applicable_required
        person["ignored_unscanned_ppe"] = ignored_unscanned_ppe
        person["instant_missing_ppe"] = instant_missing

        # 5. Check uncertainty (low detection confidence, partial body framing, or zone uncertainty)
        is_uncertain = (person.get("confidence", 1.0) < confidence_threshold + 0.05) or is_worker_uncertain

        # 6. Temporal Compliance State Machine
        track_id = person.get("track_id")
        zone_id = person.get("zone_id")
        if tracker is not None and track_id is not None:
            ts = resolved_ts
            confirmed_missing = []
            pending_missing = []
            new_confirmed_violations = []
            temporal_state_dict = {}

            if z_status in ("UNASSIGNED", "UNCERTAIN") or not policy_valid:
                tracker.pause_track_pending(track_id, timestamp=ts)
            else:
                for req in applicable_required:
                    canonical_cls = normalize_ppe_class(req)
                    req_region = PPE_BODY_MAPPING.get(canonical_cls, "torso")
                    reg_info = vis_details.get(req_region, {})
                    is_observable = (req_region in scanned_regions) and (reg_info.get("status") == "observable") and (not is_uncertain)
                    is_worn = (canonical_cls in worn_set)

                    st = tracker.update_worker_ppe(
                        track_id=track_id,
                        ppe_category=canonical_cls,
                        is_worn=is_worn,
                        is_observable=is_observable,
                        is_required=True,
                        is_uncertain=is_uncertain,
                        timestamp=ts,
                        zone_id=zone_id
                    )
                    temporal_state_dict[canonical_cls] = st.to_dict()

                    if st.state == TemporalState.CONFIRMED:
                        confirmed_missing.append(canonical_cls)
                        if st.is_new_confirmation:
                            new_confirmed_violations.append(canonical_cls)
                    elif st.state == TemporalState.PENDING:
                        pending_missing.append(canonical_cls)

                # Process all required PPE whose body part was unscanned/unobservable
                for req in ignored_unscanned_ppe:
                    canonical_cls = normalize_ppe_class(req)
                    is_worn = (canonical_cls in worn_set)

                    st = tracker.update_worker_ppe(
                        track_id=track_id,
                        ppe_category=canonical_cls,
                        is_worn=is_worn,
                        is_observable=False, # Body part is unobservable!
                        is_required=True,
                        is_uncertain=True,
                        timestamp=ts,
                        zone_id=zone_id
                    )
                    temporal_state_dict[canonical_cls] = st.to_dict()

                    # Existing confirmed violations are not automatically erased by temporary occlusion
                    if st.state == TemporalState.CONFIRMED:
                        confirmed_missing.append(canonical_cls)

            person["missing_ppe"] = sort_canonical_ppe(confirmed_missing)
            person["pending_missing_ppe"] = sort_canonical_ppe(pending_missing)
            person["new_confirmed_violations"] = sort_canonical_ppe(new_confirmed_violations)
            person["temporal_state"] = temporal_state_dict

            unscanned_unworn = [r for r in ignored_unscanned_ppe if normalize_ppe_class(r) not in worn_set]

            if is_uncertain:
                person["compliant"] = False
                person["uncertain"] = True
                frame_uncertain = True
            elif len(confirmed_missing) > 0:
                person["compliant"] = False
                person["uncertain"] = False
                frame_violations.append(person)
                for m in confirmed_missing:
                    all_missing_set.add(m)
            elif len(unscanned_unworn) > 0:
                person["compliant"] = False
                person["uncertain"] = True
                first_unscanned_reg = PPE_BODY_MAPPING.get(normalize_ppe_class(unscanned_unworn[0]), "REGION")
                if not person.get("uncertain_reason"):
                    person["uncertain_reason"] = f"UNOBSERVABLE_{first_unscanned_reg.upper()}"
                frame_uncertain = True
            elif len(pending_missing) > 0:
                person["compliant"] = True
                person["uncertain"] = False
            else:
                person["compliant"] = True
                person["uncertain"] = False
        else:
            # Fallback for static single-frame evaluation without active session tracking
            person["missing_ppe"] = instant_missing
            person["pending_missing_ppe"] = []
            person["new_confirmed_violations"] = instant_missing
            person["temporal_state"] = {}

            if is_uncertain:
                person["compliant"] = False
                person["uncertain"] = True
                frame_uncertain = True
            elif len(instant_missing) == 0:
                person["compliant"] = True
                person["uncertain"] = False
            else:
                person["compliant"] = False
                person["uncertain"] = False
                frame_violations.append(person)
                for m in instant_missing:
                    all_missing_set.add(m)

    if tracker is not None:
        active_ids = {int(p["track_id"]) for p in persons if p.get("track_id") is not None}
        tracker.mark_frame_tracks(active_ids, timestamp=resolved_ts)
        tracker.prune_expired_tracks(resolved_ts, active_track_ids=active_ids)

    if len(frame_violations) > 0:
        compliance_status = "VIOLATION"
    elif frame_uncertain:
        compliance_status = "UNCERTAIN"
    else:
        compliance_status = "COMPLIANT"

    return compliance_status, sort_canonical_ppe(list(all_missing_set)), persons

def draw_compliance_annotations(img, persons, detected_objects, compliance_status):
    """
    Renders professional bounding boxes and HUD labels on the image:
    - Persons: Green (Compliant), Red (Violation), Amber (Uncertain)
    - Shows scanned body regions on compliant tags
    - Detected PPE items: Cyan / Green boxes with label tag
    """
    output = img.copy()

    # Draw detected PPE gear boxes
    for obj in detected_objects:
        x1, y1, x2, y2 = obj["bbox"]
        label = f"{obj['name'].upper()} {int(obj['confidence'] * 100)}%"

        # Cyan bounding box for PPE
        cv2.rectangle(output, (x1, y1), (x2, y2), (255, 230, 0), 2)
        # Label tag background
        cv2.rectangle(output, (x1, max(y1 - 20, 0)), (x1 + len(label) * 9 + 10, y1), (255, 230, 0), -1)
        cv2.putText(output, label, (x1 + 4, max(y1 - 5, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

    # Draw Person bounding boxes with compliance status
    for i, p in enumerate(persons):
        x1, y1, x2, y2 = p["bbox"]
        is_compliant = p.get("compliant", False)
        is_uncertain = p.get("uncertain", False)
        worker_id = p.get("worker_id", f"W-{i+1:03d}")
        zname = p.get("zone_name")
        zlabel = f" [{zname}]" if zname else ""

        if is_compliant:
            color = (0, 220, 100) # Emerald Green
            scanned_parts = p.get("scanned_body_parts", [])
            scanned_label = "+".join(scanned_parts).upper() if scanned_parts else "SCANNED"
            status_text = f"{worker_id}: COMPLIANT{zlabel} ({scanned_label})"
        elif is_uncertain:
            color = (0, 190, 255) # Amber
            ureason = p.get("uncertain_reason")
            ureason_str = f" [{ureason}]" if ureason else ""
            status_text = f"{worker_id}: UNCERTAIN{ureason_str}{zlabel}"
        else:
            color = (50, 50, 240) # Crimson Red
            missing_str = ", ".join(p.get("missing_ppe", []))
            status_text = f"{worker_id}: MISSING {missing_str.upper()}{zlabel}"

        # Draw thick rounded-style bounding box
        cv2.rectangle(output, (x1, y1), (x2, y2), color, 3)

        # Header banner
        banner_w = max(len(status_text) * 10 + 15, 150)
        cv2.rectangle(output, (x1, max(y1 - 26, 0)), (x1 + banner_w, y1), color, -1)
        cv2.putText(output, status_text, (x1 + 6, max(y1 - 8, 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (255, 255, 255), 2, cv2.LINE_AA)

    return output
