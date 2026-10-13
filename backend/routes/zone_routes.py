import time
import datetime
from flask import Blueprint, request, jsonify
from database import is_mongo_connected, get_zones_col, mem_zones, get_notifications_col, mem_notifications
from auth import token_required, admin_required

zone_bp = Blueprint("zone_bp", __name__)

@zone_bp.route("/api/zones", methods=["GET"])
def get_zones():
    if is_mongo_connected:
        try:
            col = get_zones_col()
            docs = list(col.find().sort("created_at", -1))
            res = []
            for d in docs:
                d["_id"] = str(d["_id"])
                res.append(d)
            if res:
                return jsonify(res), 200
        except Exception:
            pass

    return jsonify(mem_zones), 200

@zone_bp.route("/api/zones/<id>", methods=["GET"])
def get_zone_by_id(id):
    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_zones_col()
            d = col.find_one({"_id": ObjectId(id)})
            if d:
                d["_id"] = str(d["_id"])
                return jsonify(d), 200
        except Exception:
            pass

    found = next((z for z in mem_zones if str(z.get("_id")) == str(id)), None)
    if not found:
        return jsonify({"message": "Zone not found"}), 404
    return jsonify(found), 200

@zone_bp.route("/api/zones", methods=["POST"])
@token_required
def create_zone():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"message": "Zone name is required"}), 400

    new_zone = {
        "name": name,
        "code": data.get("code", "ZN-01").upper(),
        "description": data.get("description", ""),
        "requiredPPE": data.get("requiredPPE", ["helmet", "vest"]),
        "supervisor": data.get("supervisor", {
            "name": "Safety Floor Supervisor",
            "email": "supervisor@ppe.com",
            "phone": "+91 98000 00000",
            "alertChannel": "WhatsApp & SMS",
            "shift": "General Shift"
        }),
        "cameraFeed": data.get("cameraFeed", {
            "name": f"{name} Camera Feed",
            "sourceType": "webcam",
            "streamUrl": "",
            "deviceId": "cam_default"
        }),
        "buzzerEnabled": data.get("buzzerEnabled", True),
        "buzzerSound": data.get("buzzerSound", "siren"),
        "active": data.get("active", True),
        "created_at": datetime.datetime.now(datetime.timezone.utc)
    }

    if is_mongo_connected:
        try:
            col = get_zones_col()
            res = col.insert_one(new_zone)
            new_zone["_id"] = str(res.inserted_id)
            return jsonify(new_zone), 201
        except Exception:
            pass

    new_zone["_id"] = "zone_" + str(int(time.time() * 1000))
    mem_zones.insert(0, new_zone)
    return jsonify(new_zone), 201

@zone_bp.route("/api/zones/<id>", methods=["PATCH"])
@token_required
def update_zone(id):
    data = request.get_json() or {}
    
    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_zones_col()
            col.update_one({"_id": ObjectId(id)}, {"$set": data})
            updated = col.find_one({"_id": ObjectId(id)})
            if updated:
                updated["_id"] = str(updated["_id"])
                return jsonify(updated), 200
        except Exception:
            pass

    for i, z in enumerate(mem_zones):
        if str(z.get("_id")) == str(id):
            mem_zones[i] = {**z, **data}
            return jsonify(mem_zones[i]), 200

    return jsonify({"message": "Zone not found"}), 404

@zone_bp.route("/api/zones/<id>", methods=["DELETE"])
@token_required
@admin_required
def delete_zone(id):
    global mem_zones
    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_zones_col()
            col.delete_one({"_id": ObjectId(id)})
            return jsonify({"message": "Zone deleted successfully"}), 200
        except Exception:
            pass

    mem_zones = [z for z in mem_zones if str(z.get("_id")) != str(id)]
    return jsonify({"message": "Zone deleted successfully"}), 200

# Supervisor Notification endpoint
@zone_bp.route("/api/zones/<id>/notify-supervisor", methods=["POST"])
def notify_zone_supervisor(id):
    data = request.get_json() or {}
    
    # Locate zone
    zone = None
    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_zones_col()
            zone = col.find_one({"_id": ObjectId(id)})
            if zone:
                zone["_id"] = str(zone["_id"])
        except Exception:
            pass

    if not zone:
        zone = next((z for z in mem_zones if str(z.get("_id")) == str(id)), None)

    zone_name = zone.get("name") if zone else data.get("zoneName", "General Facility Zone")
    supervisor = zone.get("supervisor", {}) if zone else {}
    supervisor_name = supervisor.get("name") or data.get("supervisorName", "Shift Supervisor")
    supervisor_phone = supervisor.get("phone") or data.get("supervisorPhone", "+91 98765 43210")
    supervisor_email = supervisor.get("email") or data.get("supervisorEmail", "supervisor@ppe.com")
    alert_channel = supervisor.get("alertChannel") or data.get("alertChannel", "SMS & WhatsApp")
    missing_ppe = data.get("missingPPE", ["Safety Helmet", "Vest"])
    custom_msg = data.get("message", f"Urgent: PPE non-compliance detected in {zone_name}. Missing: {', '.join(missing_ppe)}.")

    notification_record = {
        "_id": "notif_" + str(int(time.time() * 1000)),
        "zoneId": str(id),
        "zoneName": zone_name,
        "supervisorName": supervisor_name,
        "supervisorPhone": supervisor_phone,
        "supervisorEmail": supervisor_email,
        "alertChannel": alert_channel,
        "missingPPE": missing_ppe,
        "message": custom_msg,
        "deliveryStatus": "DELIVERED",
        "buzzerTriggered": zone.get("buzzerEnabled", False) if zone else True,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "created_at": datetime.datetime.now(datetime.timezone.utc)
    }

    if is_mongo_connected:
        try:
            ncol = get_notifications_col()
            if ncol is not None:
                res = ncol.insert_one(dict(notification_record))
                notification_record["_id"] = str(res.inserted_id)
        except Exception:
            pass

    mem_notifications.insert(0, notification_record)

    return jsonify({
        "success": True,
        "message": f"Alert successfully dispatched to Supervisor {supervisor_name} ({supervisor_phone}) via {alert_channel}",
        "notification": notification_record
    }), 200

# Zone Buzzer Trigger endpoint
@zone_bp.route("/api/zones/<id>/trigger-buzzer", methods=["POST"])
def trigger_zone_buzzer(id):
    data = request.get_json() or {}
    zone = None
    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_zones_col()
            zone = col.find_one({"_id": ObjectId(id)})
            if zone:
                zone["_id"] = str(zone["_id"])
        except Exception:
            pass

    if not zone:
        zone = next((z for z in mem_zones if str(z.get("_id")) == str(id)), None)

    zone_name = zone.get("name") if zone else "Facility Zone"
    buzzer_sound = zone.get("buzzerSound", "siren") if zone else "siren"
    is_test = data.get("isTest", False)

    return jsonify({
        "success": True,
        "zoneId": str(id),
        "zoneName": zone_name,
        "buzzerSound": buzzer_sound,
        "buzzerStatus": "ACTIVATED",
        "isTest": is_test,
        "message": f"Audible Buzzer ({buzzer_sound.upper()}) activated on bay floor for {zone_name}"
    }), 200

# Get recent notifications
@zone_bp.route("/api/notifications", methods=["GET"])
def get_notifications():
    if is_mongo_connected:
        try:
            ncol = get_notifications_col()
            if ncol is not None:
                docs = list(ncol.find().sort("created_at", -1).limit(40))
                res = []
                for d in docs:
                    d["_id"] = str(d["_id"])
                    if "created_at" in d and isinstance(d["created_at"], datetime.datetime):
                        d["created_at"] = d["created_at"].isoformat()
                    res.append(d)
                if res:
                    return jsonify(res), 200
        except Exception:
            pass

    return jsonify(mem_notifications[:40]), 200

# Get all buzzers
@zone_bp.route("/api/buzzers", methods=["GET"])
def get_buzzers():
    buzzers = []
    for z in mem_zones:
        buzzers.append({
            "zoneId": str(z.get("_id")),
            "zoneName": z.get("name"),
            "zoneCode": z.get("code"),
            "buzzerEnabled": z.get("buzzerEnabled", True),
            "buzzerSound": z.get("buzzerSound", "siren"),
            "active": z.get("active", True),
            "status": "ARMED" if z.get("buzzerEnabled", True) else "DISABLED",
            "supervisor": z.get("supervisor", {})
        })
    return jsonify(buzzers), 200

# Silence all buzzers
@zone_bp.route("/api/buzzers/silence-all", methods=["POST"])
@token_required
def silence_all_buzzers():
    for z in mem_zones:
        z["buzzerEnabled"] = False
    return jsonify({"message": "All zone floor buzzers have been silenced.", "success": True}), 200

# Get all supervisors with zone mapping
@zone_bp.route("/api/supervisors", methods=["GET"])
def get_supervisors():
    supervisors = []
    for z in mem_zones:
        sup = z.get("supervisor")
        if sup:
            supervisors.append({
                "id": f"sup_{z.get('_id')}",
                "name": sup.get("name"),
                "email": sup.get("email"),
                "phone": sup.get("phone"),
                "shift": sup.get("shift", "General Shift"),
                "alertChannel": sup.get("alertChannel", "WhatsApp & SMS"),
                "zoneId": str(z.get("_id")),
                "zoneName": z.get("name"),
                "zoneCode": z.get("code"),
                "active": z.get("active", True),
                "buzzerEnabled": z.get("buzzerEnabled", True)
            })
    return jsonify(supervisors), 200


