import sys
import os

# Safe UTF-8 console output for Windows cmd/powershell
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from flask import Flask, jsonify
from flask_cors import CORS
from config import Config
from database import init_db
from ai_engine.ppe_model import get_yolo_model

# Blueprint imports
from routes.health_routes import health_bp
from routes.auth_routes import auth_bp
from routes.detection_routes import detection_bp
from routes.dashboard_routes import dashboard_bp
from routes.zone_routes import zone_bp
from routes.user_routes import user_bp
from routes.report_routes import report_bp
from routes.camera_routes import camera_bp
from routes.event_routes import event_bp
from routes.settings_routes import settings_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Configure explicit CORS allowed origins (replacing permissive wildcard)
    CORS(app, resources={r"/*": {"origins": Config.ALLOWED_ORIGINS}}, supports_credentials=True)

    # Initialize Database & Seeds
    init_db()

    # Pre-warm YOLO model in background thread or initialization
    try:
        get_yolo_model()
    except Exception as e:
        print(f"⚠️ YOLO pre-warm notice: {e}")

    # Register Blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(detection_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(zone_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(camera_bp)
    app.register_blueprint(event_bp)
    app.register_blueprint(settings_bp)

    from flask import send_from_directory
    from auth import token_required, strict_token_required, supervisor_required

    @app.route("/uploads/<path:filename>", methods=["GET"])
    @strict_token_required
    @supervisor_required
    def serve_upload(filename):
        """
        Milestone M3.3: Authenticated and path-traversal-protected evidence retrieval.
        Accessible to authorized plant personnel (Supervisors and Administrators).
        """
        safe_base = os.path.abspath(Config.UPLOAD_FOLDER)
        requested_path = os.path.abspath(os.path.join(safe_base, filename))

        # Enforce strict path traversal barrier
        try:
            common = os.path.commonpath([safe_base, requested_path])
        except ValueError:
            return jsonify({"message": "Invalid file path"}), 400

        if common != safe_base:
            return jsonify({"message": "Access denied: Path traversal detected"}), 403

        if not os.path.exists(requested_path) or not os.path.isfile(requested_path):
            return jsonify({"message": "Evidence file not found"}), 404

        dir_path, base_name = os.path.split(requested_path)
        return send_from_directory(dir_path, base_name)

    @app.route("/", methods=["GET"])
    def root():
        return jsonify({
            "name": "AI-Based PPE Kit Compliance Monitoring System API",
            "version": "2.4.0",
            "engine": "Python Flask + Ultralytics YOLOv8",
            "status": "Operational",
            "storage": "Cloudinary Storage" if Config.CLOUDINARY_CLOUD_NAME else "Local Resilient Storage",
            "endpoints": [
                "/api/health",
                "/api/auth/login",
                "/api/detect",
                "/api/detect-video",
                "/api/detections",
                "/api/dashboard/summary",
                "/api/zones",
                "/api/reports/summary"
            ]
        }), 200

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"message": "Resource not found"}), 404

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"message": "Internal server error"}), 500

    return app

if __name__ == "__main__":
    from config import validate_production_config
    validate_production_config(Config)
    app = create_app()
    print(f"🚀 PPE Monitoring Flask API Server starting on http://{Config.HOST}:{Config.PORT}")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
