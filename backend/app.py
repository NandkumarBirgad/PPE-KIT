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

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Enable CORS for all routes and frontend origins
    CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

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

    from flask import send_from_directory
    @app.route("/uploads/<path:filename>", methods=["GET"])
    def serve_upload(filename):
        return send_from_directory(Config.UPLOAD_FOLDER, filename)

    @app.route("/", methods=["GET"])
    def root():
        return jsonify({
            "name": "AI-Based PPE Kit Compliance Monitoring System API",
            "version": "2.4.0",
            "engine": "Python Flask + Ultralytics YOLOv8",
            "status": "Operational",
            "storage": "Cloudinary Active (Cloud: ddiyh7wmr)",
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
    app = create_app()
    print(f"🚀 PPE Monitoring Flask API Server starting on http://{Config.HOST}:{Config.PORT}")
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
