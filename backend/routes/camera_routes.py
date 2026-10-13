import time
import datetime
from flask import Blueprint, request, jsonify
from database import is_mongo_connected, get_cameras_col, mem_cameras, get_zones_col, mem_zones
from auth import token_required, super_admin_required

camera_bp = Blueprint("camera_bp", __name__)

@camera_bp.route("/api/cameras", methods=["GET"])
def get_cameras():
    zone_id = request.args.get("zoneId")
    status = request.args.get("status")

    if is_mongo_connected:
        try:
            col = get_cameras_col()
            query = {}
            if zone_id:
                query["zoneId"] = zone_id
            if status:
                query["status"] = status
            docs = list(col.find(query).sort("created_at", -1))
            res = []
            for d in docs:
                d["_id"] = str(d["_id"])
                res.append(d)
            if res:
                return jsonify(res), 200
        except Exception:
            pass

    # In-memory fallback
    res = list(mem_cameras)
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
                return jsonify(d), 200
        except Exception:
            pass

    found = next((c for c in mem_cameras if str(c.get("_id")) == str(id)), None)
    if not found:
        return jsonify({"message": "Camera not found"}), 404
    return jsonify(found), 200

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

    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_cameras_col()
            col.update_one({"$or": [{"_id": ObjectId(id)}, {"_id": str(id)}]}, {"$set": data})
            updated = col.find_one({"$or": [{"_id": ObjectId(id)}, {"_id": str(id)}]})
            if updated:
                updated["_id"] = str(updated["_id"])
                return jsonify(updated), 200
        except Exception:
            pass

    for i, c in enumerate(mem_cameras):
        if str(c.get("_id")) == str(id):
            mem_cameras[i] = {**c, **data}
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

@camera_bp.route("/api/cameras/<id>/toggle-status", methods=["POST"])
@token_required
def toggle_camera_status(id):
    for i, c in enumerate(mem_cameras):
        if str(c.get("_id")) == str(id):
            new_status = "OFFLINE" if c.get("status") == "ONLINE" else "ONLINE"
            mem_cameras[i]["status"] = new_status
            if is_mongo_connected:
                try:
                    from bson import ObjectId
                    col = get_cameras_col()
                    col.update_one({"$or": [{"_id": ObjectId(id)}, {"_id": str(id)}]}, {"$set": {"status": new_status}})
                except Exception:
                    pass
            return jsonify({"message": f"Camera is now {new_status}", "camera": mem_cameras[i]}), 200

    return jsonify({"message": "Camera not found"}), 404
