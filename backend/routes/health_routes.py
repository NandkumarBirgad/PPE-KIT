import datetime
from flask import Blueprint, jsonify
from database import get_status
from ai_engine.ppe_model import get_model_status

health_bp = Blueprint("health_bp", __name__)

@health_bp.route("/health", methods=["GET"])
@health_bp.route("/api/health", methods=["GET"])
def health_check():
    ai_status = get_model_status()
    db_connected = get_status()

    return jsonify({
        "status": "healthy",
        "service": "PPE Compliance Monitoring System (Python Flask API)",
        "version": "2.4.0",
        "database_connected": db_connected,
        "ai_engine": ai_status,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }), 200
