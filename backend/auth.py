import datetime
from functools import wraps
import jwt
from flask import request, jsonify
from werkzeug.security import check_password_hash
from config import Config
from database import is_mongo_connected, get_users_col, mem_users

def normalize_role(role_str):
    if not role_str:
        return ""
    r = str(role_str).strip().upper()
    if not r:
        return ""
    if r in ["SUPER_ADMIN", "ADMIN"]:
        return "SUPER_ADMIN"
    if r in ["ZONE_SUPERVISOR", "SUPERVISOR"]:
        return "ZONE_SUPERVISOR"
    if r == "REVIEWER":
        return "REVIEWER"
    return r

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
            # Enforce authentication strictly by default. Dev fallback is permitted only on routes explicitly marked with _allow_dev_fallback outside production
            if not getattr(f, "_allow_dev_fallback", False) or Config.IS_PRODUCTION or Config.ENFORCE_STRICT_AUTH:
                return jsonify({"message": "Authentication token missing"}), 401

            # In development/test mode without strict auth, provide a fallback operator identity
            request.current_user = {
                "id": "usr_dev_default",
                "role": "ZONE_SUPERVISOR",
                "email": "dev@ppe.com",
                "name": "Development Operator",
                "assignedZoneId": "zone_01",
                "assignedZoneName": "Heavy Assembly Bay 01"
            }
            return f(*args, **kwargs)

        payload = decode_token(token)
        if not payload:
            return jsonify({"message": "Invalid or expired session token"}), 401

        request.current_user = payload
        return f(*args, **kwargs)
    return decorated

def dev_fallback_allowed(f):
    """Marks an inference or ingestion endpoint to permit development operator fallback outside production."""
    f._allow_dev_fallback = True
    return f

def strict_token_required(f):
    """Decorator for sensitive endpoints requiring strict authentication across all environments."""
    f._allow_dev_fallback = False
    return token_required(f)

def super_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not hasattr(request, "current_user") or normalize_role(request.current_user.get("role")) != "SUPER_ADMIN":
            return jsonify({"message": "Super Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated

def supervisor_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        allowed = ["ZONE_SUPERVISOR", "SUPER_ADMIN"]
        if not hasattr(request, "current_user") or normalize_role(request.current_user.get("role")) not in allowed:
            return jsonify({"message": "Zone Supervisor privilege required"}), 403
        return f(*args, **kwargs)
    return decorated

# Backward compatibility alias
admin_required = super_admin_required

