import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    PORT = int(os.environ.get("PORT", 5000))
    HOST = os.environ.get("HOST", "0.0.0.0")
    DEBUG = os.environ.get("DEBUG", "True").lower() == "true"
    
    # MongoDB
    MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/ppe_compliance")
    DB_NAME = os.environ.get("DB_NAME", "ppe_compliance")
    
    # JWT
    JWT_SECRET = os.environ.get("JWT_SECRET", "ppe_compliance_jwt_secret_key_2026_enterprise")
    JWT_EXPIRES_HOURS = int(os.environ.get("JWT_EXPIRES_HOURS", 168)) # 7 days
    
    # AI Engine
    MODEL_PATH = os.environ.get("MODEL_PATH", "models/ppe_best.pt")
    DEFAULT_CONFIDENCE = float(os.environ.get("DEFAULT_CONFIDENCE", 0.35))
    
    # Uploads
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
    EVIDENCE_FOLDER = os.path.join(UPLOAD_FOLDER, "evidence")
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB
