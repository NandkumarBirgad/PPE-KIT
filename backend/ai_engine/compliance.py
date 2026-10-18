import cv2
import numpy as np

def compute_box_intersection_ratio(box_inner, box_outer):
    """
    Computes what percentage of box_inner's area is inside box_outer.
    box: [x1, y1, x2, y2]
    """
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

def associate_ppe_with_persons(persons, detected_objects):
    """
    Associates each detected PPE item with the appropriate person based on
    spatial overlap and vertical position relative to the worker's bounding box.
    """
    for person in persons:
        person["worn_ppe"] = []
        p_box = person["bbox"]

        for obj in detected_objects:
            obj_box = obj["bbox"]
            obj_cls = obj["class"]

            # Calculate overlap with this person
            ratio = compute_box_intersection_ratio(obj_box, p_box)

            # Association threshold: > 40% of PPE object must be contained in person's bbox
            # Or horizontal alignment check
            obj_center_x = (obj_box[0] + obj_box[2]) / 2
            obj_center_y = (obj_box[1] + obj_box[3]) / 2

            is_inside_x = p_box[0] <= obj_center_x <= p_box[2]
            is_inside_y = p_box[1] - 20 <= obj_center_y <= p_box[3] + 20

            if ratio >= 0.40 or (is_inside_x and is_inside_y):
                if obj_cls not in person["worn_ppe"]:
                    person["worn_ppe"].append(obj_cls)

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

def detect_scanned_body_parts(person_box, img_shape=None, worn_ppe=None):
    """
    Determines which anatomical body regions are actually scanned / visible
    within the camera frame for a given person bounding box.
    Returns: dict with boolean flags and list of scanned regions.
    """
    worn_ppe = [w.lower() for w in (worn_ppe or [])]
    px1, py1, px2, py2 = person_box
    pw = max(px2 - px1, 1)
    ph = max(py2 - py1, 1)
    aspect_ratio = ph / float(pw)

    img_h = img_shape[0] if img_shape else max(py2 + 20, 480)
    img_w = img_shape[1] if img_shape else max(px2 + 20, 640)

    # 1. Head: Is the upper portion of the person inside the frame?
    # Visible unless person starts very low down (e.g. only legs/knees in frame)
    is_head_scanned = (py1 < img_h * 0.65) and (ph >= 35) or any("helm" in w or "hat" in w for w in worn_ppe)

    # 2. Face: Visible if head is scanned and enough vertical resolution
    is_face_scanned = is_head_scanned and (ph >= 50)

    # 3. Torso: Visible if person extends below head region
    is_torso_scanned = (ph >= 60 and py2 > py1 + int(ph * 0.30)) or any("vest" in w or "jacket" in w for w in worn_ppe)

    # 4. Feet / Lower Body (Boots / Shoes):
    # Feet are NOT scanned if:
    # - Bounding box is cut off at the bottom edge of the camera view (py2 near bottom edge)
    # - Aspect ratio is waist-up / half-body / seated (ph / pw < 2.1 and py2 >= img_h * 0.60)
    # - Box height is small relative to frame height and positioned at bottom
    has_boots_detected = any(b in worn_ppe for b in ["boots", "shoes", "safety boots", "footwear", "safety_shoe"])

    is_cut_off_at_bottom = py2 >= (img_h - 25)
    is_half_body_ratio = (aspect_ratio < 2.1) and (py2 >= img_h * 0.60)

    if has_boots_detected:
        is_feet_scanned = True
    elif is_cut_off_at_bottom or is_half_body_ratio:
        is_feet_scanned = False
    else:
        # Full body standing in frame with visible clearance above the bottom edge
        is_feet_scanned = (aspect_ratio >= 2.0) and (py2 < img_h - 35)

    # 5. Hands:
    has_gloves_detected = any("glov" in w for w in worn_ppe)
    if has_gloves_detected:
        is_hands_scanned = True
    elif is_cut_off_at_bottom or (px1 <= 15) or (px2 >= img_w - 15):
        # Hands/wrists cut off by frame boundaries
        is_hands_scanned = False
    else:
        is_hands_scanned = (aspect_ratio >= 2.0) and (ph >= 120)

    scanned_regions = []
    if is_head_scanned: scanned_regions.append("head")
    if is_face_scanned: scanned_regions.append("face")
    if is_torso_scanned: scanned_regions.append("torso")
    if is_feet_scanned: scanned_regions.append("feet")
    if is_hands_scanned: scanned_regions.append("hands")

    return {
        "head": is_head_scanned,
        "face": is_face_scanned,
        "torso": is_torso_scanned,
        "feet": is_feet_scanned,
        "hands": is_hands_scanned,
        "scanned_regions": scanned_regions
    }

def evaluate_compliance(persons, detected_objects, required_ppe, confidence_threshold=0.35, img_shape=None):
    """
    Evaluates compliance against required zone PPE ONLY for body parts
    that are actually scanned / visible in the camera frame.
    Returns:
    - compliance_status: 'COMPLIANT' | 'VIOLATION' | 'UNCERTAIN'
    - missing_ppe: list of missing items
    - evaluated_persons: list of persons with individual compliance status
    """
    raw_required = [r.lower() for r in (required_ppe or ['helmet', 'vest'])]

    if not persons:
        # If no person detected, check if any PPE detected in empty scene
        if not detected_objects:
            return "UNCERTAIN", [], []
        # Fallback evaluation based on detected objects
        detected_set = set([d["class"].lower() for d in detected_objects])
        missing = [r for r in raw_required if r not in detected_set]
        status = "COMPLIANT" if len(missing) == 0 else "VIOLATION"
        return status, missing, []

    # Associate PPE items with individual persons
    persons = associate_ppe_with_persons(persons, detected_objects)

    frame_violations = []
    frame_uncertain = False
    all_missing_set = set()

    for person in persons:
        p_box = person["bbox"]
        worn_set = set([w.lower() for w in person["worn_ppe"]])

        # 1. Determine which body parts are actually scanned in the camera
        body_scan = detect_scanned_body_parts(p_box, img_shape=img_shape, worn_ppe=person["worn_ppe"])
        scanned_regions = body_scan["scanned_regions"]

        # 2. Filter required PPE to ONLY items corresponding to scanned body parts!
        applicable_required = []
        ignored_unscanned_ppe = []

        for req in raw_required:
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

        # 3. Calculate missing items ONLY from applicable scanned required items!
        missing = [req for req in applicable_required if req not in worn_set]
        person["missing_ppe"] = missing
        person["scanned_body_parts"] = scanned_regions
        person["applicable_required_ppe"] = applicable_required
        person["ignored_unscanned_ppe"] = ignored_unscanned_ppe

        # 4. Check uncertainty (e.g. low person confidence or partial body crop)
        if person.get("confidence", 1.0) < confidence_threshold + 0.05:
            person["compliant"] = False
            person["uncertain"] = True
            frame_uncertain = True
        elif len(missing) == 0:
            person["compliant"] = True
            person["uncertain"] = False
        else:
            person["compliant"] = False
            person["uncertain"] = False
            frame_violations.append(person)
            for m in missing:
                all_missing_set.add(m)

    if len(frame_violations) > 0:
        compliance_status = "VIOLATION"
    elif frame_uncertain:
        compliance_status = "UNCERTAIN"
    else:
        compliance_status = "COMPLIANT"

    return compliance_status, list(all_missing_set), persons

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

        if is_compliant:
            color = (0, 220, 100) # Emerald Green
            scanned_parts = p.get("scanned_body_parts", [])
            scanned_label = "+".join(scanned_parts).upper() if scanned_parts else "SCANNED"
            status_text = f"WORKER #{i+1}: COMPLIANT ({scanned_label})"
        elif is_uncertain:
            color = (0, 190, 255) # Amber
            status_text = f"WORKER #{i+1}: UNCERTAIN"
        else:
            color = (50, 50, 240) # Crimson Red
            missing_str = ", ".join(p.get("missing_ppe", []))
            status_text = f"VIOLATION: MISSING {missing_str.upper()}"

        # Draw thick rounded-style bounding box
        cv2.rectangle(output, (x1, y1), (x2, y2), color, 3)

        # Header banner
        banner_w = max(len(status_text) * 10 + 15, 150)
        cv2.rectangle(output, (x1, max(y1 - 26, 0)), (x1 + banner_w, y1), color, -1)
        cv2.putText(output, status_text, (x1 + 6, max(y1 - 8, 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (255, 255, 255), 2, cv2.LINE_AA)

    return output
