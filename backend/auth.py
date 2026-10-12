import datetime
from functools import wraps
import jwt
from flask import request, jsonify
from werkzeug.security import check_password_hash
from config import Config
from database import is_mongo_connected, get_users_col, mem_users

def generate_token(user_id, role, email):
    payload = {
        "id": str(user_id),
        "role": role,
        "email": email,
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

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not hasattr(request, "current_user") or request.current_user.get("role") != "admin":
            return jsonify({"message": "Administrative privilege required"}), 403
        return f(*args, **kwargs)
    return decorated
