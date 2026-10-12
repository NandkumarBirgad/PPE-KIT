import os
import cv2
import numpy as np
import base64
from ultralytics import YOLO
from config import Config

_ppe_model = None
_person_model = None
_model_loaded = False
_model_info = {"type": "Dual YOLOv8 (PPE + Person Detection)", "classes": [], "device": "CPU"}

def get_yolo_models():
    global _ppe_model, _person_model, _model_loaded, _model_info
    if _ppe_model is None:
        model_path = Config.MODEL_PATH
        os.makedirs(os.path.dirname(model_path) if os.path.dirname(model_path) else "models", exist_ok=True)

        try:
            # 1. Load PPE Model
            if os.path.exists(model_path):
                print(f"🤖 Loading specialized PPE YOLO model: {model_path}")
                _ppe_model = YOLO(model_path)
            else:
                print("🤖 Loading base YOLOv8 model for PPE...")
                _ppe_model = YOLO("yolov8n.pt")

            # 2. Load Person Detector
            print("🤖 Loading Person Detector (yolov8n.pt)...")
            _person_model = YOLO("yolov8n.pt")

            _model_loaded = True
            _model_info["classes"] = list(_ppe_model.names.values()) if hasattr(_ppe_model, 'names') else []
            print(f"✅ AI Ensemble Active. PPE Classes: {_model_info['classes']}")
        except Exception as e:
            print(f"⚠️ Failed to load YOLO ensemble: {e}")
            _model_loaded = False

    return _ppe_model, _person_model

def get_yolo_model():
    ppe_m, _ = get_yolo_models()
    return ppe_m

def get_model_status():
    return {
        "loaded": _model_loaded,
        "type": _model_info["type"],
        "device": _model_info["device"],
        "classes_count": len(_model_info["classes"]),
        "model_path": Config.MODEL_PATH
    }

def decode_image(image_input):
    """Decodes base64 string, byte buffer, or file storage to an OpenCV BGR numpy array."""
    if isinstance(image_input, str):
        if image_input.startswith("data:image"):
            image_input = image_input.split(",")[1]
        img_bytes = base64.b64decode(image_input)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    elif hasattr(image_input, "read"):
        img_bytes = image_input.read()
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    elif isinstance(image_input, np.ndarray):
        return image_input
    return None

def encode_image_to_base64(cv2_img):
    """Encodes an OpenCV image to base64 JPEG string."""
    _, buffer = cv2.imencode('.jpg', cv2_img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    return base64.b64encode(buffer).decode('utf-8')

def detect_ppe_in_frame(img, confidence_threshold=0.35):
    """
    Runs dual inference on OpenCV BGR image:
    1. Detects Persons via person detector
    2. Detects PPE items (Helmet, Vest, Goggles, Gloves, Mask, Boots) via specialized PPE model
    Returns: (annotated_image, detected_objects, persons)
    """
    ppe_model, person_model = get_yolo_models()
    if ppe_model is None or img is None:
        return img, [], []

    h, w = img.shape[:2]
    annotated = img.copy()

    detected_objects = []
    persons = []

    # Map class name aliases to canonical labels
    ppe_aliases = {
        "helmet": "helmet", "hard hat": "helmet", "hardhat": "helmet", "safety helmet": "helmet", "head": "helmet",
        "vest": "vest", "safety vest": "vest", "reflective vest": "vest", "jacket": "vest",
        "goggles": "goggles", "glasses": "goggles", "safety glasses": "goggles", "eye wear": "goggles",
        "gloves": "gloves", "glove": "gloves", "safety gloves": "gloves",
        "mask": "mask", "face mask": "mask", "respirator": "mask",
        "boots": "boots", "shoes": "boots", "safety_shoe": "boots", "safety boots": "boots", "footwear": "boots"
    }

    # 1. Run Person Detection
    if person_model is not None:
        person_results = person_model(img, classes=[0], conf=confidence_threshold, verbose=False)
        if person_results and len(person_results) > 0:
            for box in person_results[0].boxes:
                conf = float(box.conf[0].item())
                xyxy = [int(x) for x in box.xyxy[0].tolist()]
                persons.append({
                    "bbox": xyxy,
                    "confidence": conf,
                    "worn_ppe": [],
                    "missing_ppe": [],
                    "compliant": False
                })

    # 2. Run PPE Model Detection
    ppe_results = ppe_model(img, conf=confidence_threshold, verbose=False)
    if ppe_results and len(ppe_results) > 0:
        for box in ppe_results[0].boxes:
            cls_id = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            xyxy = [int(x) for x in box.xyxy[0].tolist()]
            raw_name = ppe_model.names.get(cls_id, f"class_{cls_id}").lower()

            if raw_name == "person":
                if not any(p["bbox"] == xyxy for p in persons):
                    persons.append({
                        "bbox": xyxy,
                        "confidence": conf,
                        "worn_ppe": [],
                        "missing_ppe": [],
                        "compliant": False
                    })
                continue

            # Canonical mapping
            matched_ppe = None
            for alias, canonical in ppe_aliases.items():
                if alias in raw_name:
                    matched_ppe = canonical
                    break

            label = matched_ppe if matched_ppe else raw_name
            detected_objects.append({
                "class": label,
                "name": label,
                "confidence": conf,
                "bbox": xyxy
            })

    # 3. Supplemental Heuristic Visual Analyzer for Person Crops (Color & Geometry)
    for person in persons:
        px1, py1, px2, py2 = person["bbox"]
        pw = px2 - px1
        ph = py2 - py1
        if pw <= 15 or ph <= 15:
            continue

        head_y2 = min(py1 + int(ph * 0.28), h)
        head_crop = img[max(py1, 0):head_y2, max(px1, 0):min(px2, w)]

        torso_y1 = head_y2
        torso_y2 = min(py1 + int(ph * 0.65), h)
        torso_crop = img[max(torso_y1, 0):torso_y2, max(px1, 0):min(px2, w)]

        # Check for safety helmet color signatures (yellow, white, orange, red)
        if head_crop.size > 0:
            hsv_head = cv2.cvtColor(head_crop, cv2.COLOR_BGR2HSV)
            yellow_mask = cv2.inRange(hsv_head, np.array([15, 80, 80]), np.array([35, 255, 255]))
            orange_mask = cv2.inRange(hsv_head, np.array([5, 120, 100]), np.array([18, 255, 255]))
            white_mask = cv2.inRange(hsv_head, np.array([0, 0, 190]), np.array([180, 25, 255]))
            combined_helmet = cv2.bitwise_or(yellow_mask, cv2.bitwise_or(orange_mask, white_mask))
            ratio_helmet = np.sum(combined_helmet > 0) / (head_crop.shape[0] * head_crop.shape[1] + 1e-5)

            has_helmet = any(d["class"] == "helmet" and d["bbox"][1] < head_y2 for d in detected_objects)
            if ratio_helmet > 0.16 and not has_helmet:
                detected_objects.append({
                    "class": "helmet",
                    "name": "helmet",
                    "confidence": min(0.72 + float(ratio_helmet * 0.4), 0.96),
                    "bbox": [px1 + int(pw * 0.1), py1, px2 - int(pw * 0.1), head_y2]
                })

        # Check for safety vest color signatures (fluorescent lime/yellow, neon orange)
        if torso_crop.size > 0:
            hsv_torso = cv2.cvtColor(torso_crop, cv2.COLOR_BGR2HSV)
            hi_vis_mask = cv2.inRange(hsv_torso, np.array([22, 100, 100]), np.array([45, 255, 255]))
            hi_vis_orange = cv2.inRange(hsv_torso, np.array([8, 120, 120]), np.array([20, 255, 255]))
            combined_vest = cv2.bitwise_or(hi_vis_mask, hi_vis_orange)
            ratio_vest = np.sum(combined_vest > 0) / (torso_crop.shape[0] * torso_crop.shape[1] + 1e-5)

            has_vest = any(d["class"] == "vest" for d in detected_objects)
            if ratio_vest > 0.15 and not has_vest:
                detected_objects.append({
                    "class": "vest",
                    "name": "vest",
                    "confidence": min(0.75 + float(ratio_vest * 0.35), 0.95),
                    "bbox": [px1, torso_y1, px2, torso_y2]
                })

    return annotated, detected_objects, persons
