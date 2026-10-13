import time
import datetime
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash
from database import is_mongo_connected, get_users_col, mem_users
from auth import token_required, admin_required

user_bp = Blueprint("user_bp", __name__)

@user_bp.route("/api/users", methods=["GET"])
@token_required
@admin_required
def get_users():
    if is_mongo_connected:
        try:
            col = get_users_col()
            users = list(col.find({}, {"password_hash": 0}).sort("created_at", -1))
            res = []
            for u in users:
                u["_id"] = str(u["_id"])
                res.append(u)
            if res:
                return jsonify(res), 200
        except Exception:
            pass

    safe_mem = []
    for u in mem_users:
        u_copy = dict(u)
        u_copy.pop("password_hash", None)
        safe_mem.append(u_copy)
    return jsonify(safe_mem), 200

@user_bp.route("/api/users", methods=["POST"])
@token_required
@admin_required
def create_user():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    raw_role = data.get("role", "ZONE_SUPERVISOR")
    norm_role = "SUPER_ADMIN" if str(raw_role).upper() in ["SUPER_ADMIN", "ADMIN"] else "ZONE_SUPERVISOR"

    new_user = {
        "name": name,
        "email": email,
        "password_hash": generate_password_hash(password),
        "role": norm_role,
        "assignedZoneId": data.get("assignedZoneId"),
        "assignedZoneName": data.get("assignedZoneName"),
        "phone": data.get("phone", ""),
        "shift": data.get("shift", "General Shift"),
        "active": True,
        "created_at": datetime.datetime.now(datetime.timezone.utc)
    }

    if is_mongo_connected:
        try:
            col = get_users_col()
            if col.find_one({"email": email}):
                return jsonify({"message": "Email already exists"}), 400
            res = col.insert_one(new_user)
            new_user["_id"] = str(res.inserted_id)
            new_user.pop("password_hash", None)
            return jsonify(new_user), 201
        except Exception:
            pass

    if any(u.get("email") == email for u in mem_users):
        return jsonify({"message": "Email already exists"}), 400

    new_user["_id"] = "usr_" + str(int(time.time() * 1000))
    mem_users.append(new_user)
    ret_copy = dict(new_user)
    ret_copy.pop("password_hash", None)
    return jsonify(ret_copy), 201

@user_bp.route("/api/users/<id>", methods=["PATCH"])
@token_required
@admin_required
def update_user(id):
    data = request.get_json() or {}
    update_data = {}
    if "name" in data: update_data["name"] = data["name"]
    if "role" in data: 
        update_data["role"] = "SUPER_ADMIN" if str(data["role"]).upper() in ["SUPER_ADMIN", "ADMIN"] else "ZONE_SUPERVISOR"
    if "active" in data: update_data["active"] = data["active"]
    if "assignedZoneId" in data: update_data["assignedZoneId"] = data["assignedZoneId"]
    if "assignedZoneName" in data: update_data["assignedZoneName"] = data["assignedZoneName"]
    if "phone" in data: update_data["phone"] = data["phone"]
    if "shift" in data: update_data["shift"] = data["shift"]

    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_users_col()
            col.update_one({"_id": ObjectId(id)}, {"$set": update_data})
            u = col.find_one({"_id": ObjectId(id)}, {"password_hash": 0})
            if u:
                u["_id"] = str(u["_id"])
                return jsonify(u), 200
        except Exception:
            pass

    for i, u in enumerate(mem_users):
        if str(u.get("_id")) == str(id):
            mem_users[i] = {**u, **update_data}
            ret = dict(mem_users[i])
            ret.pop("password_hash", None)
            return jsonify(ret), 200

    return jsonify({"message": "User not found"}), 404

@user_bp.route("/api/users/<id>", methods=["DELETE"])
@token_required
@admin_required
def delete_user(id):
    global mem_users
    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_users_col()
            col.delete_one({"_id": ObjectId(id)})
            return jsonify({"message": "User deleted"}), 200
        except Exception:
            pass

    mem_users = [u for u in mem_users if str(u.get("_id")) != str(id)]
    return jsonify({"message": "User deleted"}), 200
