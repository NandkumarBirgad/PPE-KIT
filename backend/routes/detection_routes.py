import time
import os
import json
import datetime
import tempfile
import cv2
from flask import Blueprint, request, jsonify
from database import (
    is_mongo_connected, 
    get_detections_col, 
    mem_detections,
    get_zones_col,
    mem_zones,
    get_notifications_col,
    mem_notifications
)
from ai_engine.ppe_model import decode_image, encode_image_to_base64, detect_ppe_in_frame
from ai_engine.compliance import evaluate_compliance, draw_compliance_annotations
from auth import token_required

detection_bp = Blueprint("detection_bp", __name__)

@detection_bp.route("/detect", methods=["POST"])
@detection_bp.route("/api/detect", methods=["POST"])
def detect_image():
    start_time = time.time()
    
    # 1. Parse Image Input (multipart file or json base64)
    img = None
    required_ppe = ['helmet', 'vest']
    zone_name = "Live Camera"
    conf_thresh = 0.35

    if request.is_json:
        data = request.get_json() or {}
        img_b64 = data.get("image")
        img = decode_image(img_b64)
        required_ppe = data.get("required_ppe", required_ppe)
        zone_name = data.get("zone_name", zone_name)
        conf_thresh = float(data.get("confidence_threshold", conf_thresh))
    elif "file" in request.files:
        file_obj = request.files["file"]
        img = decode_image(file_obj)
        if "required_ppe" in request.form:
            try:
                required_ppe = json.loads(request.form["required_ppe"])
            except Exception:
                pass
        zone_name = request.form.get("zone_name", zone_name)
        conf_thresh = float(request.form.get("confidence_threshold", conf_thresh))

    if img is None:
        return jsonify({"message": "Invalid or missing image payload"}), 400

    # 2. Run YOLO Inference
    raw_annotated, detected_objects, persons = detect_ppe_in_frame(img, confidence_threshold=conf_thresh)

    # 3. Compliance Evaluation with Person Association
    compliance_status, missing_ppe, evaluated_persons = evaluate_compliance(
        persons, detected_objects, required_ppe, confidence_threshold=conf_thresh
    )

    # 4. Draw HUD Visual Annotations
    final_annotated = draw_compliance_annotations(
        img, evaluated_persons, detected_objects, compliance_status
    )
    annotated_b64 = encode_image_to_base64(final_annotated)
    latency_ms = int((time.time() - start_time) * 1000)

    return jsonify({
        "compliance_status": compliance_status,
        "missing_ppe": missing_ppe,
        "detected_classes": detected_objects,
        "persons": evaluated_persons,
        "annotated_image": annotated_b64,
        "latency_ms": latency_ms,
        "zone_name": zone_name
    }), 200

@detection_bp.route("/detect-video", methods=["POST"])
@detection_bp.route("/api/detect-video", methods=["POST"])
def detect_video():
    if "file" not in request.files:
        return jsonify({"message": "Video file is required"}), 400

    video_file = request.files["file"]
    required_ppe = ['helmet', 'vest']
    if "required_ppe" in request.form:
        try:
            required_ppe = json.loads(request.form["required_ppe"])
        except Exception:
            pass

    # Save to temporary file
    temp_fd, temp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(temp_fd)
    video_file.save(temp_path)

    try:
        cap = cv2.VideoCapture(temp_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        frame_interval = int(max(fps * 0.8, 1)) # sample ~1 frame every 0.8 second

        total_frames_processed = 0
        total_violations_found = 0
        frame_results = []
        overall_missing = set()
        overall_detected = []
        last_annotated_b64 = None

        frame_count = 0
        while cap.isOpened() and total_frames_processed < 40:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_count % frame_interval == 0:
                _, detected_objects, persons = detect_ppe_in_frame(frame, confidence_threshold=0.35)
                comp_status, missing_ppe, evaluated_persons = evaluate_compliance(
                    persons, detected_objects, required_ppe
                )

                if comp_status == "VIOLATION":
                    total_violations_found += 1
                    for m in missing_ppe:
                        overall_missing.add(m)

                for d in detected_objects:
                    if not any(od["name"] == d["name"] for od in overall_detected):
                        overall_detected.append(d)

                annotated_img = draw_compliance_annotations(frame, evaluated_persons, detected_objects, comp_status)
                last_annotated_b64 = encode_image_to_base64(annotated_img)

                frame_results.append({
                    "frame_idx": total_frames_processed + 1,
                    "timestamp_sec": round(frame_count / fps, 1),
                    "compliance_status": comp_status,
                    "missing_ppe": missing_ppe,
                    "persons_count": len(evaluated_persons)
                })
                total_frames_processed += 1

            frame_count += 1

        cap.release()

        overall_status = "VIOLATION" if total_violations_found > 0 else "COMPLIANT" if total_frames_processed > 0 else "UNCERTAIN"

        return jsonify({
            "overall_compliance_status": overall_status,
            "overall_missing_ppe": list(overall_missing),
            "overall_detected_classes": overall_detected,
            "total_frames_processed": total_frames_processed,
            "total_violations_found": total_violations_found,
            "annotated_image": last_annotated_b64,
            "frame_breakdown": frame_results
        }), 200

    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

@detection_bp.route("/api/detections", methods=["GET"])
def get_detections():
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 10))
    skip = (page - 1) * limit

    compliance_status = request.args.get("complianceStatus")
    review_status = request.args.get("reviewStatus")
    search = request.args.get("search", "").strip().lower()

    if is_mongo_connected:
        col = get_detections_col()
        query = {}
        if compliance_status:
            query["complianceStatus"] = compliance_status
        if review_status:
            query["reviewStatus"] = review_status
        if search:
            query["$or"] = [
                {"zoneName": {"$regex": search, "$options": "i"}},
                {"missingPPE": {"$in": [search]}}
            ]

        try:
            total_count = col.count_documents(query)
            cursor = col.find(query).sort("createdAt", -1).skip(skip).limit(limit)
            events = []
            for doc in cursor:
                doc["_id"] = str(doc["_id"])
                events.append(doc)

            return jsonify({
                "events": events,
                "page": page,
                "totalPages": max(1, (total_count + limit - 1) // limit),
                "totalCount": total_count
            }), 200
        except Exception as e:
            pass

    # In-memory fallback
    filtered = list(mem_detections)
    if compliance_status:
        filtered = [e for e in filtered if e.get("complianceStatus") == compliance_status]
    if review_status:
        filtered = [e for e in filtered if e.get("reviewStatus") == review_status]
    if search:
        filtered = [e for e in filtered if search in e.get("zoneName", "").lower() or any(search in m.lower() for m in e.get("missingPPE", []))]

    total_count = len(filtered)
    events = filtered[skip:skip + limit]

    return jsonify({
        "events": events,
        "page": page,
        "totalPages": max(1, (total_count + limit - 1) // limit),
        "totalCount": total_count
    }), 200

@detection_bp.route("/api/detections", methods=["POST"])
def create_detection():
    data = request.get_json() or {}
    compliance_status = data.get("complianceStatus")
    if not compliance_status:
        return jsonify({"message": "complianceStatus is required"}), 400

    zone_id = data.get("zoneId")
    zone_name = data.get("zoneName", "General Monitored Zone")
    missing_ppe = data.get("missingPPE", [])

    event_doc = {
        "zoneId": zone_id,
        "zoneName": zone_name,
        "cameraId": data.get("cameraId", "cam_01"),
        "cameraName": data.get("cameraName", "Primary Camera Feed"),
        "sourceType": data.get("sourceType", "webcam"),
        "timestamp": datetime.datetime.now(datetime.timezone.utc),
        "detectedClasses": data.get("detectedClasses", []),
        "confidenceScores": data.get("confidenceScores", []),
        "missingPPE": missing_ppe,
        "complianceStatus": compliance_status,
        "personCount": int(data.get("personCount", 1)),
        "reviewStatus": "PENDING",
        "reviewerNotes": "",
        "evidenceImageReference": data.get("evidenceImageBase64"),
        "processingMetadata": data.get("processingMetadata", {}),
        "createdAt": datetime.datetime.now(datetime.timezone.utc)
    }

    # Automatically trigger supervisor alert record if violation
    supervisor_alert = None
    if compliance_status == "VIOLATION" and zone_id:
        zone = None
        if is_mongo_connected:
            try:
                from bson import ObjectId
                col = get_zones_col()
                zone = col.find_one({"_id": ObjectId(zone_id)})
            except Exception:
                pass
        if not zone:
            zone = next((z for z in mem_zones if str(z.get("_id")) == str(zone_id)), None)

        if zone and zone.get("supervisor"):
            sup = zone["supervisor"]
            supervisor_alert = {
                "_id": "notif_" + str(int(time.time() * 1000)),
                "zoneId": str(zone_id),
                "zoneName": zone.get("name", zone_name),
                "supervisorName": sup.get("name", "Shift Supervisor"),
                "supervisorPhone": sup.get("phone", "+91 98000 00000"),
                "supervisorEmail": sup.get("email", "supervisor@ppe.com"),
                "alertChannel": sup.get("alertChannel", "SMS & WhatsApp"),
                "missingPPE": missing_ppe,
                "message": f"Violation detected in {zone.get('name', zone_name)}. Missing PPE: {', '.join(missing_ppe) if missing_ppe else 'Mandatory Gear'}",
                "deliveryStatus": "DELIVERED",
                "buzzerTriggered": zone.get("buzzerEnabled", True),
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "created_at": datetime.datetime.now(datetime.timezone.utc)
            }
            if is_mongo_connected:
                try:
                    ncol = get_notifications_col()
                    if ncol is not None:
                        ncol.insert_one(dict(supervisor_alert))
                except Exception:
                    pass
            mem_notifications.insert(0, supervisor_alert)

    if is_mongo_connected:
        try:
            col = get_detections_col()
            res = col.insert_one(event_doc)
            event_doc["_id"] = str(res.inserted_id)
            return jsonify({
                "message": "Event recorded", 
                "event": event_doc,
                "supervisorAlert": supervisor_alert
            }), 201
        except Exception as e:
            pass

    event_doc["_id"] = "det_" + str(int(time.time() * 1000))
    mem_detections.insert(0, event_doc)
    return jsonify({
        "message": "Event recorded", 
        "event": event_doc,
        "supervisorAlert": supervisor_alert
    }), 201

@detection_bp.route("/api/detections/<id>/review", methods=["PATCH"])
@token_required
def update_review(id):
    data = request.get_json() or {}
    review_status = data.get("reviewStatus")
    reviewer_notes = data.get("reviewerNotes")

    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_detections_col()
            update_fields = {}
            if review_status:
                update_fields["reviewStatus"] = review_status
            if reviewer_notes is not None:
                update_fields["reviewerNotes"] = reviewer_notes

            col.update_one({"_id": ObjectId(id)}, {"$set": update_fields})
            return jsonify({"message": "Review status updated"}), 200
        except Exception:
            pass

    # In-memory
    for e in mem_detections:
        if str(e.get("_id")) == str(id):
            if review_status:
                e["reviewStatus"] = review_status
            if reviewer_notes is not None:
                e["reviewerNotes"] = reviewer_notes
            return jsonify({"message": "Review status updated", "event": e}), 200

    return jsonify({"message": "Event not found"}), 404
