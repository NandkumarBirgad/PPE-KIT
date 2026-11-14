import os
import math
from dotenv import load_dotenv

load_dotenv()

def validate_temporal_durations(resolution_sec_val, max_gap_sec_val):
    """
    Validates and enforces:
      0 < max_compliance_observation_gap_sec < resolution_confirmation_duration_sec
    using a 0.2-second safety margin where mathematically valid.

    1. Resolves and validates resolution_confirmation_duration_sec first.
    2. Computes the maximum allowable observation gap:
       - Where mathematically valid (resolution_duration > 0.4s), applies a 0.2s safety margin:
         max_allowed_gap = resolution_duration - 0.2s
       - For very small resolution durations (<= 0.4s, e.g. 0.2s or 0.1s), subtracting 0.2s would
         yield <= 0 or an invalid margin. It smoothly transitions to a proportional safety margin:
         max_allowed_gap = resolution_duration * 0.5
    3. Resolves and bounds max_compliance_observation_gap_sec:
       - Fallback default is min(1.5s, max_allowed_gap).
       - Valid candidate is clamped to at most max_allowed_gap.
       - Guarantees 0 < max_gap < resolution_duration under all inputs.
    """
    # 1. Validate resolution confirmation duration (default: 2.0s)
    try:
        r_val = float(resolution_sec_val)
        res_dur = r_val if (math.isfinite(r_val) and r_val > 0.0) else 2.0
    except (ValueError, TypeError):
        res_dur = 2.0

    # 2. Compute max allowable gap with 0.2s safety margin where mathematically valid
    max_allowed_gap = max(res_dur * 0.5, res_dur - 0.2)
    safe_default_gap = min(1.5, max_allowed_gap)

    # 3. Validate max compliance observation gap (default: 1.5s, clamped to max_allowed_gap)
    try:
        g_val = float(max_gap_sec_val)
        if math.isfinite(g_val) and g_val > 0.0:
            max_gap = min(g_val, max_allowed_gap)
        else:
            max_gap = safe_default_gap
    except (ValueError, TypeError):
        max_gap = safe_default_gap

    # 4. Final sanity assurance: must be strictly positive and strictly less than resolution duration
    if max_gap <= 0.0 or max_gap >= res_dur:
        max_gap = res_dur * 0.5

    return res_dur, max_gap

KNOWN_DEFAULT_SECRETS = {
    "ppe_compliance_jwt_secret_key_2026_enterprise",
    "secret",
    "jwt_secret",
    "default",
    "changeme",
    "change_me",
    "123456",
}

def validate_production_config(cfg=None):
    """
    Milestone M3.3: Validates production security configuration:
    - Flask DEBUG must be False in production.
    - JWT_SECRET must be non-empty, non-default, and at least 32 characters.
    """
    c = cfg or Config
    env = getattr(c, "ENV", "development").lower()
    is_prod = getattr(c, "IS_PRODUCTION", env in ["production", "prod"])
    if not is_prod:
        return True

    debug_val = getattr(c, "DEBUG", False)
    if debug_val is True:
        raise ValueError("Security violation: Production mode cannot run with Flask DEBUG enabled")

    jwt_secret = getattr(c, "JWT_SECRET", "")
    if not jwt_secret or jwt_secret in KNOWN_DEFAULT_SECRETS or len(jwt_secret) < 32:
        raise ValueError(
            "Security violation: Production mode requires a strong, non-default JWT_SECRET of at least 32 characters"
        )

    return True

class Config:
    ENV = os.environ.get("FLASK_ENV", os.environ.get("ENV", "development")).lower()
    IS_PRODUCTION = ENV in ["production", "prod"]
    PORT = int(os.environ.get("PORT", 5000))
    HOST = os.environ.get("HOST", "0.0.0.0")
    DEBUG = (os.environ.get("DEBUG", "False" if IS_PRODUCTION else "True").lower() == "true") and not IS_PRODUCTION
    ENFORCE_STRICT_AUTH = os.environ.get("ENFORCE_STRICT_AUTH", "False").lower() == "true"
    
    # MongoDB
    MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/ppe_compliance")
    DB_NAME = os.environ.get("DB_NAME", "ppe_compliance")
    
    # JWT
    JWT_SECRET = os.environ.get("JWT_SECRET", "ppe_compliance_jwt_secret_key_2026_enterprise")
    JWT_EXPIRES_HOURS = int(os.environ.get("JWT_EXPIRES_HOURS", 168)) # 7 days
    
    # CORS Origins (Explicit allowed origins replacing wildcard)
    DEFAULT_CORS_ORIGINS = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5000",
        "http://127.0.0.1:5000",
    ]
    _env_origins = os.environ.get("ALLOWED_ORIGINS", "")
    if _env_origins:
        ALLOWED_ORIGINS = [o.strip() for o in _env_origins.split(",") if o.strip()]
    else:
        ALLOWED_ORIGINS = DEFAULT_CORS_ORIGINS

    # AI Engine
    BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
    _env_model_path = os.environ.get("MODEL_PATH", "models/ppe_best.pt")
    MODEL_PATH = _env_model_path if os.path.isabs(_env_model_path) else os.path.join(BACKEND_DIR, _env_model_path)
    _env_person_model_path = os.environ.get("PERSON_MODEL_PATH", "yolov8n.pt")
    PERSON_MODEL_PATH = _env_person_model_path if os.path.isabs(_env_person_model_path) else os.path.join(BACKEND_DIR, _env_person_model_path)
    DEFAULT_CONFIDENCE = float(os.environ.get("DEFAULT_CONFIDENCE", 0.35))
    
    # Uploads & Video Security (100 MB limit)
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
    EVIDENCE_FOLDER = os.path.join(UPLOAD_FOLDER, "evidence")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 100 * 1024 * 1024))
    ALLOWED_VIDEO_EXTENSIONS = {"mp4", "avi", "mov", "mkv", "webm"}

    # Cloudinary Cloud Storage
    CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
    CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "")
    CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")

    # External Alerting (Email & Webhook)
    SMTP_SERVER = os.environ.get("SMTP_SERVER", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    ALERT_EMAIL_FROM = os.environ.get("ALERT_EMAIL_FROM", "alerts@ppe-safety.internal")
    ALERT_WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL", "")

    # Anonymous Worker Tracking Configuration
    TRACKER_IOU_THRESHOLD = max(0.05, min(0.95, float(os.environ.get("TRACKER_IOU_THRESHOLD", 0.30))))
    TRACKER_CENTROID_THRESHOLD = max(0.01, min(1.0, float(os.environ.get("TRACKER_CENTROID_THRESHOLD", 0.15)))) # 15% of frame diagonal
    TRACKER_RECOVERY_TIMEOUT_SEC = max(0.5, float(os.environ.get("TRACKER_RECOVERY_TIMEOUT_SEC", 3.0)))
    TRACKER_SESSION_PURGE_TIMEOUT_SEC = max(10.0, float(os.environ.get("TRACKER_SESSION_PURGE_TIMEOUT_SEC", 300.0)))
    TRACKER_AMBIGUITY_MARGIN = max(0.01, min(0.5, float(os.environ.get("TRACKER_AMBIGUITY_MARGIN", 0.08))))

    # PPE Association Configuration
    PPE_ASSOCIATION_MIN_SCORE = max(0.05, min(0.95, float(os.environ.get("PPE_ASSOCIATION_MIN_SCORE", 0.35))))
    PPE_ASSOCIATION_AMBIGUITY_MARGIN = max(0.01, min(0.5, float(os.environ.get("PPE_ASSOCIATION_AMBIGUITY_MARGIN", 0.08))))
    PPE_REGION_HEAD_RATIO = (0.0, 0.25)
    PPE_REGION_FACE_RATIO = (0.10, 0.30, 0.20, 0.80)  # y1_ratio, y2_ratio, x1_ratio, x2_ratio
    PPE_REGION_TORSO_RATIO = (0.25, 0.70)
    PPE_REGION_FEET_RATIO = (0.75, 1.0)
    CANONICAL_PPE_ORDER = ["helmet", "vest", "goggles", "boots"]

    # Visibility Assessment Configuration
    VISIBILITY_EDGE_MARGIN_TOP = int(os.environ.get("VISIBILITY_EDGE_MARGIN_TOP", 10))
    VISIBILITY_EDGE_MARGIN_BOTTOM = int(os.environ.get("VISIBILITY_EDGE_MARGIN_BOTTOM", 25))
    VISIBILITY_EDGE_MARGIN_SIDES = int(os.environ.get("VISIBILITY_EDGE_MARGIN_SIDES", 10))
    VISIBILITY_MIN_PERSON_HEIGHT = int(os.environ.get("VISIBILITY_MIN_PERSON_HEIGHT", 40))
    VISIBILITY_MIN_FACE_HEIGHT = int(os.environ.get("VISIBILITY_MIN_FACE_HEIGHT", 80))
    VISIBILITY_MIN_FEET_HEIGHT = int(os.environ.get("VISIBILITY_MIN_FEET_HEIGHT", 120))

    # HSV Heuristic Configuration
    ENABLE_HSV_HEURISTICS = os.environ.get("ENABLE_HSV_HEURISTICS", "True").lower() == "true"

    # Temporal Compliance Configuration
    VIOLATION_CONFIRMATION_DURATION_SEC = max(0.1, float(os.environ.get("VIOLATION_CONFIRMATION_DURATION_SEC", 3.0)))
    # Verified compliance resolution and observation gap validation (M2.2B.5B.1.1)
    _env_res_dur = os.environ.get("RESOLUTION_CONFIRMATION_DURATION_SEC", 2.0)
    _env_max_gap = os.environ.get("MAX_COMPLIANCE_OBSERVATION_GAP_SEC", 1.5)
    RESOLUTION_CONFIRMATION_DURATION_SEC, MAX_COMPLIANCE_OBSERVATION_GAP_SEC = validate_temporal_durations(
        _env_res_dur, _env_max_gap
    )

    # Spatial Zone Assignment Configuration
    ZONE_ASSIGNMENT_DEBOUNCE_FRAMES = max(1, int(os.environ.get("ZONE_ASSIGNMENT_DEBOUNCE_FRAMES", 3)))
    ZONE_BOUNDARY_EPSILON = max(1e-9, float(os.environ.get("ZONE_BOUNDARY_EPSILON", 1e-5)))

