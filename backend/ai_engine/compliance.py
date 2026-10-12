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

def evaluate_compliance(persons, detected_objects, required_ppe, confidence_threshold=0.35):
    """
    Evaluates compliance against required zone PPE.
    Returns:
    - compliance_status: 'COMPLIANT' | 'VIOLATION' | 'UNCERTAIN'
    - missing_ppe: list of missing items
    - evaluated_persons: list of persons with individual compliance status
    """
    required_set = set([r.lower() for r in (required_ppe or ['helmet', 'vest'])])

    if not persons:
        # If no person detected, check if any PPE detected in empty scene
        if not detected_objects:
            return "UNCERTAIN", [], []
        # Fallback evaluation based on detected objects
        detected_set = set([d["class"].lower() for d in detected_objects])
        missing = list(required_set - detected_set)
        status = "COMPLIANT" if len(missing) == 0 else "VIOLATION"
        return status, missing, []

    # Associate PPE items with individual persons
    persons = associate_ppe_with_persons(persons, detected_objects)

    frame_violations = []
    frame_uncertain = False
    all_missing_set = set()

    for person in persons:
        worn_set = set([w.lower() for w in person["worn_ppe"]])
        missing = list(required_set - worn_set)
        person["missing_ppe"] = missing

        # Check uncertainty (e.g. low person confidence or partial body crop)
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
            status_text = f"WORKER #{i+1}: COMPLIANT"
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
        banner_w = max(len(status_text) * 10 + 15, 140)
        cv2.rectangle(output, (x1, max(y1 - 26, 0)), (x1 + banner_w, y1), color, -1)
        cv2.putText(output, status_text, (x1 + 6, max(y1 - 8, 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 2, cv2.LINE_AA)

    return output
