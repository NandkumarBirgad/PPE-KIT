import time
import datetime
from flask import Blueprint, request, jsonify
from database import is_mongo_connected, get_cameras_col, mem_cameras, get_zones_col, mem_zones
from auth import token_required, super_admin_required
from ai_engine.zone_geometry import validate_camera_zone_mappings
from ai_engine.camera_health import (
    evaluate_camera_health,
    record_camera_frame_success,
    record_camera_frame_failure,
    HEALTH_STATUS_ONLINE,
    HEALTH_STATUS_OFFLINE
)

camera_bp = Blueprint("camera_bp", __name__)

@camera_bp.route("/api/cameras", methods=["GET"])
def get_cameras():
    zone_id = request.args.get("zoneId")
    status = request.args.get("status")

    res = []
    if is_mongo_connected:
        try:
            col = get_cameras_col()
            docs = list(col.find({}).sort("created_at", -1))
            for d in docs:
                d["_id"] = str(d["_id"])
                d["zones"] = d.get("zones", [])
                evaluated = evaluate_camera_health(d)
                res.append(evaluated)
        except Exception:
            pass

    if not res:
        # In-memory fallback
        for c in mem_cameras:
            copy_c = dict(c, zones=c.get("zones", []))
            evaluated = evaluate_camera_health(copy_c)
            res.append(evaluated)

    if zone_id:
        res = [c for c in res if str(c.get("zoneId")) == str(zone_id)]
    if status:
        res = [c for c in res if c.get("status") == status]

    return jsonify(res), 200

@camera_bp.route("/api/cameras/<id>", methods=["GET"])
def get_camera_by_id(id):
    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_cameras_col()
            d = col.find_one({"_id": ObjectId(id)})
            if not d:
                d = col.find_one({"_id": str(id)})
            if d:
                d["_id"] = str(d["_id"])
                d["zones"] = d.get("zones", [])
                return jsonify(evaluate_camera_health(d)), 200
        except Exception:
            pass

    found = next((c for c in mem_cameras if str(c.get("_id")) == str(id)), None)
    if not found:
        return jsonify({"message": "Camera not found"}), 404
    copy_found = dict(found, zones=found.get("zones", []))
    return jsonify(evaluate_camera_health(copy_found)), 200

@camera_bp.route("/api/cameras", methods=["POST"])
@token_required
@super_admin_required
def create_camera():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"message": "Camera name is required"}), 400

    zone_id = data.get("zoneId", "zone_01")
    zone_name = data.get("zoneName", "General Facility Zone")

    # Sync zone name if zone exists
    zone = next((z for z in mem_zones if str(z.get("_id")) == str(zone_id)), None)
    if zone:
        zone_name = zone.get("name", zone_name)

    raw_zones = data.get("zones")
    validated_zones = []
    if raw_zones is not None:
        valid, err_msg, validated_zones = validate_camera_zone_mappings(raw_zones)
        if not valid:
            return jsonify({"message": err_msg}), 400

    new_cam = {
        "name": name,
        "zoneId": str(zone_id),
        "zoneName": zone_name,
        "status": data.get("status", "ONLINE"),
        "sourceType": data.get("sourceType", "webcam"),
        "streamUrl": data.get("streamUrl", ""),
        "resolution": data.get("resolution", "1080p HD"),
        "fps": int(data.get("fps", 25)),
        "location": data.get("location", "Facility Deck"),
        "zones": validated_zones,
        "active": data.get("active", True),
        "created_at": datetime.datetime.now(datetime.timezone.utc)
    }

    if is_mongo_connected:
        try:
            col = get_cameras_col()
            res = col.insert_one(new_cam)
            new_cam["_id"] = str(res.inserted_id)
            return jsonify(new_cam), 201
        except Exception:
            pass

    new_cam["_id"] = "cam_" + str(int(time.time() * 1000))
    mem_cameras.insert(0, new_cam)
    return jsonify(new_cam), 201

@camera_bp.route("/api/cameras/<id>", methods=["PATCH"])
@token_required
@super_admin_required
def update_camera(id):
    data = request.get_json() or {}

    if "zones" in data:
        raw_zones = data.get("zones")
        valid, err_msg, validated_zones = validate_camera_zone_mappings(raw_zones)
        if not valid:
            return jsonify({"message": err_msg}), 400
        data["zones"] = validated_zones

    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_cameras_col()
            col.update_one({"$or": [{"_id": ObjectId(id)}, {"_id": str(id)}]}, {"$set": data})
            updated = col.find_one({"$or": [{"_id": ObjectId(id)}, {"_id": str(id)}]})
            if updated:
                updated["_id"] = str(updated["_id"])
                updated["zones"] = updated.get("zones", [])
                return jsonify(updated), 200
        except Exception:
            pass

    for i, c in enumerate(mem_cameras):
        if str(c.get("_id")) == str(id):
            mem_cameras[i] = {**c, **data}
            mem_cameras[i]["zones"] = mem_cameras[i].get("zones", [])
            return jsonify(mem_cameras[i]), 200

    return jsonify({"message": "Camera not found"}), 404

@camera_bp.route("/api/cameras/<id>", methods=["DELETE"])
@token_required
@super_admin_required
def delete_camera(id):
    global mem_cameras
    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_cameras_col()
            col.delete_one({"$or": [{"_id": ObjectId(id)}, {"_id": str(id)}]})
            return jsonify({"message": "Camera deleted successfully"}), 200
        except Exception:
            pass

    mem_cameras = [c for c in mem_cameras if str(c.get("_id")) != str(id)]
    return jsonify({"message": "Camera deleted successfully"}), 200

@camera_bp.route("/api/cameras/<id>/zones", methods=["GET"])
def get_camera_zones(id):
    cam = None
    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_cameras_col()
            cam = col.find_one({"$or": [{"_id": ObjectId(id)}, {"_id": str(id)}]})
        except Exception:
            pass
    if not cam:
        cam = next((c for c in mem_cameras if str(c.get("_id")) == str(id)), None)

    if not cam:
        return jsonify({"message": "Camera not found"}), 404

    return jsonify(cam.get("zones", [])), 200

@camera_bp.route("/api/cameras/<id>/zones", methods=["PUT", "PATCH"])
@token_required
@super_admin_required
def update_camera_zones(id):
    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"message": "Invalid or missing JSON payload"}), 400

    raw_zones = body.get("zones") if isinstance(body, dict) and "zones" in body else body

    valid, err_msg, validated_zones = validate_camera_zone_mappings(raw_zones)
    if not valid:
        return jsonify({"message": err_msg}), 400

    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_cameras_col()
            res = col.update_one(
                {"$or": [{"_id": ObjectId(id)}, {"_id": str(id)}]},
                {"$set": {"zones": validated_zones}}
            )
            if res.matched_count > 0:
                updated = col.find_one({"$or": [{"_id": ObjectId(id)}, {"_id": str(id)}]})
                if updated:
                    updated["_id"] = str(updated["_id"])
                    updated["zones"] = updated.get("zones", [])
                    return jsonify(updated), 200
        except Exception:
            pass

    for i, c in enumerate(mem_cameras):
        if str(c.get("_id")) == str(id):
            mem_cameras[i]["zones"] = validated_zones
            return jsonify(mem_cameras[i]), 200

    return jsonify({"message": "Camera not found"}), 404

@camera_bp.route("/api/cameras/<id>/toggle-status", methods=["POST"])
@token_required
@super_admin_required
def toggle_camera_status(id):
    now = time.time()
    now_iso = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).isoformat()
    for i, c in enumerate(mem_cameras):
        if str(c.get("_id")) == str(id):
            new_status = "OFFLINE" if c.get("status") == "ONLINE" else "ONLINE"
            reason = f"Manually toggled {new_status} by operator"
            updates = {
                "status": new_status,
                "last_transition_time": now,
                "last_transition_time_iso": now_iso,
                "status_reason": reason
            }
            mem_cameras[i].update(updates)
            if is_mongo_connected:
                try:
                    from bson import ObjectId
                    col = get_cameras_col()
                    col.update_one({"$or": [{"_id": ObjectId(id)}, {"_id": str(id)}]}, {"$set": updates})
                except Exception:
                    pass
            return jsonify({"message": f"Camera is now {new_status}", "camera": mem_cameras[i]}), 200

    return jsonify({"message": "Camera not found"}), 404

@camera_bp.route("/api/cameras/<id>/test-connection", methods=["POST"])
@token_required
def test_camera_connection(id):
    cam = None
    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_cameras_col()
            cam = col.find_one({"$or": [{"_id": ObjectId(id)}, {"_id": str(id)}]})
        except Exception:
            pass
    if not cam:
        cam = next((c for c in mem_cameras if str(c.get("_id")) == str(id)), None)

    if not cam:
        return jsonify({"message": "Camera not found"}), 404

    stream_url = (cam.get("streamUrl") or "").strip()
    source_type = cam.get("sourceType", "webcam")

    if source_type == "webcam" or not stream_url:
        return jsonify({
            "success": True, 
            "online": True,
            "message": "Local Browser Webcam channel active and responsive."
        }), 200

    import cv2
    try:
        cap = cv2.VideoCapture(stream_url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        ret, frame = cap.read()
        cap.release()
        if ret and frame is not None:
            return jsonify({
                "success": True,
                "online": True,
                "resolution": f"{frame.shape[1]}x{frame.shape[0]}",
                "message": f"RTSP / IP Stream verified! Resolution: {frame.shape[1]}x{frame.shape[0]}"
            }), 200
        else:
            return jsonify({
                "success": False,
                "online": False,
                "message": f"Unable to fetch video frame from stream target: {stream_url}"
            }), 200
    except Exception as e:
        return jsonify({
            "success": False,
            "online": False,
            "message": f"Stream connection exception: {str(e)}"
        }), 200

@camera_bp.route("/api/cameras/<id>/analyze", methods=["POST"])
@token_required
def analyze_camera_feed(id):
    """
    Captures live frame directly from an IP/RTSP camera URL on server,
    runs dual YOLO inference, verifies zone compliance, and auto-logs violations.
    """
    cam = None
    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_cameras_col()
            cam = col.find_one({"$or": [{"_id": ObjectId(id)}, {"_id": str(id)}]})
        except Exception:
            pass
    if not cam:
        cam = next((c for c in mem_cameras if str(c.get("_id")) == str(id)), None)

    if not cam:
        return jsonify({"message": "Camera not found"}), 404

    # Fetch corresponding Zone PPE requirements
    zone_id = cam.get("zoneId")
    zone = next((z for z in mem_zones if str(z.get("_id")) == str(zone_id)), None)
    required_ppe = zone.get("requiredPPE", ["helmet", "vest"]) if zone else ["helmet", "vest"]
    zone_name = zone.get("name", cam.get("zoneName", "General Facility Zone")) if zone else cam.get("zoneName", "General Facility Zone")

    stream_url = (cam.get("streamUrl") or "").strip()
    if not stream_url or stream_url == "webcam":
        return jsonify({"message": "Camera is configured for client-side webcam. Use /api/detect."}), 400

    import cv2
    from ai_engine.ppe_model import detect_ppe_in_frame, encode_image_to_base64
    from ai_engine.compliance import evaluate_compliance, draw_compliance_annotations
    from storage import upload_evidence_image
    from alerts import dispatch_violation_alert
    from database import get_detections_col, mem_detections

    try:
        cap = cv2.VideoCapture(stream_url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            record_camera_frame_failure(str(id), "Failed to read live frame from IP camera.")
            return jsonify({"message": "Failed to read live frame from IP camera."}), 502

        fh, fw = frame.shape[:2]
        cam_session_id = f"cam_{id}"
        now_ts = time.time()
        _, detected_objects, persons = detect_ppe_in_frame(
            frame, confidence_threshold=0.35, session_id=cam_session_id, timestamp=now_ts
        )
        record_camera_frame_success(str(id), timestamp=now_ts)
        compliance_status, missing_ppe, evaluated_persons = evaluate_compliance(
            persons, detected_objects, required_ppe, confidence_threshold=0.35, img_shape=(fh, fw),
            session_id=cam_session_id, timestamp=now_ts
        )

        annotated = draw_compliance_annotations(frame, evaluated_persons, detected_objects, compliance_status)
        annotated_b64 = encode_image_to_base64(annotated)

        # If newly confirmed violation detected, record forensic snapshot and dispatch alert
        image_url = None
        has_new_confirmed = any(p.get("new_confirmed_violations") for p in evaluated_persons)
        if compliance_status == "VIOLATION" and has_new_confirmed:
            from routes.detection_routes import persist_confirmed_incident
            from routes.event_routes import broadcast_event

            try:
                image_url = upload_evidence_image(annotated_b64, folder="ppe_violations")
            except Exception:
                image_url = None

            raw_evidence_ref = image_url or (f"data:image/jpeg;base64,{annotated_b64}" if annotated_b64 else None)

            for person in evaluated_persons:
                track_id = person.get("track_id")
                worker_id = person.get("worker_id", f"W-{track_id:03d}" if track_id else None)
                temporal_state = person.get("temporal_state", {})

                for new_cat in person.get("new_confirmed_violations", []):
                    st_dict = temporal_state.get(new_cat, {})
                    episode_id = st_dict.get("episode_id")
                    if not episode_id:
                        continue

                    event_doc = {
                        "episode_id": episode_id,
                        "worker_id": worker_id,
                        "track_id": int(track_id) if track_id is not None else 1,
                        "personId": worker_id or "Worker #1",
                        "workerTag": f"{worker_id} (Track #{track_id})" if worker_id else "Worker #1",
                        "session_id": str(cam_session_id),
                        "zoneId": str(zone_id),
                        "zoneName": zone_name,
                        "cameraId": str(id),
                        "cameraName": cam.get("name"),
                        "sourceType": "rtsp",
                        "timestamp": datetime.datetime.now(datetime.timezone.utc),
                        "detectedClasses": [d["class"] for d in detected_objects],
                        "missingPPE": [new_cat],
                        "complianceStatus": "VIOLATION",
                        "personCount": len(persons),
                        "reviewStatus": "PENDING",
                        "reviewerNotes": "",
                        "first_missing_timestamp": st_dict.get("first_missing_timestamp"),
                        "confirmed_timestamp": st_dict.get("confirmed_timestamp"),
                        "imageUrl": image_url,
                        "evidenceImageReference": raw_evidence_ref,
                        "createdAt": datetime.datetime.now(datetime.timezone.utc)
                    }

                    saved_doc, is_new_insert = persist_confirmed_incident(event_doc)
                    if is_new_insert:
                        broadcast_event("VIOLATION_DETECTED", {
                            "event": saved_doc
                        })

        # M2.2B.5C: Automatic Incident Resolution for RTSP camera stream
        from routes.detection_routes import process_resolution_candidates
        from ai_engine.temporal_compliance import get_session_temporal_tracker
        cam_tracker = get_session_temporal_tracker(cam_session_id)
        process_resolution_candidates(cam_tracker, cam_session_id)

        return jsonify({
            "camera": cam.get("name"),
            "complianceStatus": compliance_status,
            "missingPPE": missing_ppe,
            "personCount": len(persons),
            "annotatedImage": f"data:image/jpeg;base64,{annotated_b64}",
            "imageUrl": image_url
        }), 200

    except Exception as e:
        return jsonify({"message": f"Server-side analysis error: {str(e)}"}), 500

