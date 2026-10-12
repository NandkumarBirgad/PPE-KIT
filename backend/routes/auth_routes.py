from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash
from database import is_mongo_connected, get_users_col, mem_users
from auth import generate_token, token_required

auth_bp = Blueprint("auth_bp", __name__)

@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"message": "Email and password are required"}), 400

    # 1. Hardcoded quick demo accounts fallback for rock-solid instant demo
    if email == "admin@ppe.com" and password == "Admin@123":
        token = generate_token("usr_admin", "admin", "admin@ppe.com")
        return jsonify({
            "token": token,
            "user": {
                "id": "usr_admin",
                "name": "System Safety Administrator",
                "email": "admin@ppe.com",
                "role": "admin"
            }
        }), 200

    if email == "reviewer@ppe.com" and password == "Reviewer@123":
        token = generate_token("usr_reviewer", "reviewer", "reviewer@ppe.com")
        return jsonify({
            "token": token,
            "user": {
                "id": "usr_reviewer",
                "name": "Compliance Inspector Dave",
                "email": "reviewer@ppe.com",
                "role": "reviewer"
            }
        }), 200

    # 2. Database lookup
    user = None
    if is_mongo_connected:
        users_col = get_users_col()
        if users_col is not None:
            user = users_col.find_one({"email": email})
    else:
        user = next((u for u in mem_users if u.get("email") == email), None)

    if not user or not user.get("active", True):
        return jsonify({"message": "Invalid credentials or inactive account"}), 401

    if not check_password_hash(user.get("password_hash", ""), password):
        return jsonify({"message": "Invalid credentials"}), 401

    user_id = str(user.get("_id"))
    token = generate_token(user_id, user.get("role", "reviewer"), user.get("email"))

    return jsonify({
        "token": token,
        "user": {
            "id": user_id,
            "name": user.get("name", "User"),
            "email": user.get("email"),
            "role": user.get("role", "reviewer")
        }
    }), 200

@auth_bp.route("/api/auth/me", methods=["GET"])
@token_required
def get_me():
    curr = request.current_user
    user = None
    if is_mongo_connected:
        users_col = get_users_col()
        from bson import ObjectId
        try:
            user = users_col.find_one({"_id": ObjectId(curr["id"])})
        except Exception:
            user = users_col.find_one({"email": curr["email"]})
    else:
        user = next((u for u in mem_users if str(u.get("_id")) == curr["id"] or u.get("email") == curr["email"]), None)

    if not user:
        return jsonify({
            "user": {
                "id": curr["id"],
                "name": "System User",
                "email": curr["email"],
                "role": curr["role"]
            }
        }), 200

    return jsonify({
        "user": {
            "id": str(user.get("_id")),
            "name": user.get("name"),
            "email": user.get("email"),
            "role": user.get("role")
        }
    }), 200

@auth_bp.route("/api/auth/logout", methods=["POST"])
def logout():
    return jsonify({"message": "Logged out successfully"}), 200
