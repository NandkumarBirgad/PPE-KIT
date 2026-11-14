from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash
from database import is_mongo_connected, get_users_col, mem_users
from auth import generate_token, token_required

auth_bp = Blueprint("auth_bp", __name__)

EMAIL_ALIASES = {
    "admin": "admin@ppe.com",
    "admin@admin.com": "admin@ppe.com",
    "superadmin@ppe.com": "admin@ppe.com",
    "supervisor": "supervisor@ppe.com",
    "vikram.patil@ppe.com": "supervisor@ppe.com",
    "vikram@ppe.com": "supervisor@ppe.com",
    "pooja": "pooja@ppe.com",
    "pooja.kulkarni@ppe.com": "pooja@ppe.com",
    "reviewer": "reviewer@ppe.com",
}

@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    """
    Milestone M3.3: Production-hardened authentication endpoint.
    Verifies user credentials strictly against cryptographically hashed passwords.
    All hardcoded plaintext password bypasses and static test keys have been removed.
    """
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    password = str(data.get("password", "")).strip()

    if not email or not password:
        return jsonify({"message": "Workstation email and password are required"}), 400

    lookup_email = EMAIL_ALIASES.get(email, email)

    # Database and resilient in-memory lookup
    user = None
    if is_mongo_connected:
        try:
            users_col = get_users_col()
            if users_col is not None:
                user = users_col.find_one({"email": lookup_email})
        except Exception:
            pass

    if not user:
        user = next((u for u in mem_users if u.get("email", "").lower() == lookup_email), None)

    if not user or not user.get("active", True):
        return jsonify({"message": "Invalid workstation credentials or inactive account"}), 401

    stored_hash = user.get("password_hash", "")
    if not stored_hash or not check_password_hash(stored_hash, password):
        return jsonify({"message": "Invalid workstation security key or password"}), 401

    user_id = str(user.get("_id"))
    raw_role = user.get("role", "ZONE_SUPERVISOR")
    norm_role = "SUPER_ADMIN" if str(raw_role).upper() in ["SUPER_ADMIN", "ADMIN"] else "ZONE_SUPERVISOR"
    assigned_zone_id = user.get("assignedZoneId", "zone_01" if norm_role == "ZONE_SUPERVISOR" else None)
    assigned_zone_name = user.get("assignedZoneName", "Monitored Safety Zone" if norm_role == "ZONE_SUPERVISOR" else None)

    token = generate_token(
        user_id, 
        norm_role, 
        user.get("email"), 
        assigned_zone_id, 
        assigned_zone_name, 
        name=user.get("name", "User")
    )

    return jsonify({
        "token": token,
        "user": {
            "id": user_id,
            "name": user.get("name", "User"),
            "email": user.get("email"),
            "role": norm_role,
            "assignedZoneId": assigned_zone_id,
            "assignedZoneName": assigned_zone_name
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

    norm_role = "SUPER_ADMIN" if str(curr.get("role")).upper() in ["SUPER_ADMIN", "ADMIN"] else "ZONE_SUPERVISOR"

    if not user:
        return jsonify({
            "user": {
                "id": curr["id"],
                "name": curr.get("name", "System User"),
                "email": curr["email"],
                "role": norm_role,
                "assignedZoneId": curr.get("assignedZoneId"),
                "assignedZoneName": curr.get("assignedZoneName")
            }
        }), 200

    db_role = user.get("role", norm_role)
    clean_role = "SUPER_ADMIN" if str(db_role).upper() in ["SUPER_ADMIN", "ADMIN"] else "ZONE_SUPERVISOR"

    return jsonify({
        "user": {
            "id": str(user.get("_id")),
            "name": user.get("name"),
            "email": user.get("email"),
            "role": clean_role,
            "assignedZoneId": user.get("assignedZoneId", curr.get("assignedZoneId")),
            "assignedZoneName": user.get("assignedZoneName", curr.get("assignedZoneName"))
        }
    }), 200

@auth_bp.route("/api/auth/logout", methods=["POST"])
def logout():
    return jsonify({"message": "Logged out successfully"}), 200
