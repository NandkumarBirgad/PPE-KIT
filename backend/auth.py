import datetime
from functools import wraps
import jwt
from flask import request, jsonify
from werkzeug.security import check_password_hash
from config import Config
from database import is_mongo_connected, get_users_col, mem_users

def normalize_role(role_str):
    if not role_str:
        return "ZONE_SUPERVISOR"
    r = str(role_str).strip().upper()
    if r in ["SUPER_ADMIN", "ADMIN"]:
        return "SUPER_ADMIN"
    return "ZONE_SUPERVISOR"

def generate_token(user_id, role, email, assigned_zone_id=None, assigned_zone_name=None, name=None):
    norm_role = normalize_role(role)
    payload = {
        "id": str(user_id),
        "role": norm_role,
        "email": email,
        "name": name,
        "assignedZoneId": assigned_zone_id,
        "assignedZoneName": assigned_zone_name,
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=Config.JWT_EXPIRES_HOURS),
        "iat": datetime.datetime.now(datetime.timezone.utc),
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm="HS256")

def decode_token(token):
    try:
        return jwt.decode(token, Config.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

        if not token:
            return jsonify({"message": "Authentication token missing"}), 401

        payload = decode_token(token)
        if not payload:
            return jsonify({"message": "Invalid or expired session token"}), 401

        request.current_user = payload
        return f(*args, **kwargs)
    return decorated

def super_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not hasattr(request, "current_user") or request.current_user.get("role") not in ["SUPER_ADMIN", "admin"]:
            return jsonify({"message": "Super Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated

def supervisor_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        allowed = ["ZONE_SUPERVISOR", "SUPER_ADMIN", "admin", "supervisor", "reviewer"]
        if not hasattr(request, "current_user") or request.current_user.get("role") not in allowed:
            return jsonify({"message": "Zone Supervisor privilege required"}), 403
        return f(*args, **kwargs)
    return decorated

# Backward compatibility alias
admin_required = super_admin_required

