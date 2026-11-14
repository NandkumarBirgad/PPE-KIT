import datetime
from flask import Blueprint, request, jsonify
from database import get_system_settings, update_system_settings
from auth import token_required, strict_token_required, super_admin_required
from ai_engine.compliance import normalize_ppe_class

settings_bp = Blueprint("settings_bp", __name__)

VALID_PPE_CATEGORIES = {"helmet", "vest", "boots", "safety_shoe", "goggles", "gloves", "mask"}

def validate_settings_payload(data: dict) -> tuple[bool, str, dict]:
    """
    Validates settings update payload:
    - default_required_ppe: list of valid normalized PPE classes
    - confidence_threshold: float 0.1 <= val <= 1.0
    - violation_confirmation_duration_sec: float/int 0.5 <= val <= 60.0
    - incident_auto_resolution_duration_sec: float/int 0.5 <= val <= 60.0
    - video_sampling_interval_ms: int 100 <= val <= 10000
    - alert_cooldown_sec: int 0 <= val <= 120
    - camera_warning_timeout_sec: float/int 1.0 <= val <= 120.0
    - camera_offline_timeout_sec: float/int val > warning and val <= 300.0
    - camera_degraded_failures: int 1 <= val <= 20
    - floor_buzzer_enabled: bool
    - sound_enabled: bool
    """
    if not isinstance(data, dict):
        return False, "Payload must be a JSON object", {}

    validated = {}

    if "factory_name" in data:
        fn = str(data["factory_name"]).strip()
        if not fn or len(fn) > 120:
            return False, "Factory name must be between 1 and 120 characters", {}
        validated["factory_name"] = fn

    if "default_required_ppe" in data:
        raw_ppe = data["default_required_ppe"]
        if not isinstance(raw_ppe, list):
            return False, "default_required_ppe must be a list of PPE category strings", {}
        norm_list = []
        for item in raw_ppe:
            if not isinstance(item, str):
                return False, f"Invalid PPE category type: {type(item).__name__}", {}
            norm = normalize_ppe_class(item)
            if not norm or norm not in VALID_PPE_CATEGORIES:
                return False, f"Unrecognized or unsupported PPE category: '{item}'", {}
            if norm not in norm_list:
                norm_list.append(norm)
        validated["default_required_ppe"] = norm_list

    if "confidence_threshold" in data:
        try:
            val = float(data["confidence_threshold"])
            if not (0.1 <= val <= 1.0):
                return False, "confidence_threshold must be between 0.10 and 1.00", {}
            validated["confidence_threshold"] = round(val, 2)
        except (ValueError, TypeError):
            return False, "confidence_threshold must be a numeric value", {}

    if "violation_confirmation_duration_sec" in data:
        try:
            val = float(data["violation_confirmation_duration_sec"])
            if not (0.5 <= val <= 60.0):
                return False, "violation_confirmation_duration_sec must be between 0.5s and 60.0s", {}
            validated["violation_confirmation_duration_sec"] = round(val, 1)
        except (ValueError, TypeError):
            return False, "violation_confirmation_duration_sec must be a numeric value", {}

    if "incident_auto_resolution_duration_sec" in data:
        try:
            val = float(data["incident_auto_resolution_duration_sec"])
            if not (0.5 <= val <= 60.0):
                return False, "incident_auto_resolution_duration_sec must be between 0.5s and 60.0s", {}
            validated["incident_auto_resolution_duration_sec"] = round(val, 1)
        except (ValueError, TypeError):
            return False, "incident_auto_resolution_duration_sec must be a numeric value", {}

    if "video_sampling_interval_ms" in data:
        try:
            val = int(data["video_sampling_interval_ms"])
            if not (100 <= val <= 10000):
                return False, "video_sampling_interval_ms must be an integer between 100ms and 10,000ms", {}
            validated["video_sampling_interval_ms"] = val
        except (ValueError, TypeError):
            return False, "video_sampling_interval_ms must be an integer", {}

    if "alert_cooldown_sec" in data:
        try:
            val = int(data["alert_cooldown_sec"])
            if not (0 <= val <= 120):
                return False, "alert_cooldown_sec must be an integer between 0s and 120s", {}
            validated["alert_cooldown_sec"] = val
        except (ValueError, TypeError):
            return False, "alert_cooldown_sec must be an integer", {}

    if "camera_warning_timeout_sec" in data:
        try:
            val = float(data["camera_warning_timeout_sec"])
            if not (1.0 <= val <= 120.0):
                return False, "camera_warning_timeout_sec must be between 1.0s and 120.0s", {}
            validated["camera_warning_timeout_sec"] = round(val, 1)
        except (ValueError, TypeError):
            return False, "camera_warning_timeout_sec must be a numeric value", {}

    if "camera_offline_timeout_sec" in data:
        try:
            val = float(data["camera_offline_timeout_sec"])
            warn_val = validated.get("camera_warning_timeout_sec", get_system_settings().get("camera_warning_timeout_sec", 5.0))
            if val <= warn_val:
                return False, f"camera_offline_timeout_sec ({val}s) must be strictly greater than warning timeout ({warn_val}s)", {}
            if val > 300.0:
                return False, "camera_offline_timeout_sec must not exceed 300.0s", {}
            validated["camera_offline_timeout_sec"] = round(val, 1)
        except (ValueError, TypeError):
            return False, "camera_offline_timeout_sec must be a numeric value", {}

    if "camera_degraded_failures" in data:
        try:
            val = int(data["camera_degraded_failures"])
            if not (1 <= val <= 20):
                return False, "camera_degraded_failures must be an integer between 1 and 20", {}
            validated["camera_degraded_failures"] = val
        except (ValueError, TypeError):
            return False, "camera_degraded_failures must be an integer", {}

    if "floor_buzzer_enabled" in data:
        if not isinstance(data["floor_buzzer_enabled"], bool):
            return False, "floor_buzzer_enabled must be a boolean", {}
        validated["floor_buzzer_enabled"] = bool(data["floor_buzzer_enabled"])

    if "sound_enabled" in data:
        if not isinstance(data["sound_enabled"], bool):
            return False, "sound_enabled must be a boolean", {}
        validated["sound_enabled"] = bool(data["sound_enabled"])

    return True, "", validated

@settings_bp.route("/api/settings", methods=["GET"])
@strict_token_required
def get_settings():
    """
    Returns the authoritative system settings.
    Accessible to authenticated users (Administrator and Zone Supervisor).
    """
    settings = get_system_settings()
    return jsonify(settings), 200

@settings_bp.route("/api/settings", methods=["PUT", "PATCH"])
@strict_token_required
@super_admin_required
def update_settings():
    """
    Updates authoritative system settings.
    Requires Administrator privileges (SUPER_ADMIN).
    Supervisors receive 403 Forbidden via super_admin_required.
    """
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"message": "Invalid JSON body or missing request payload"}), 400

    valid, err_msg, validated_data = validate_settings_payload(payload)
    if not valid:
        return jsonify({"message": err_msg}), 400

    if not validated_data:
        return jsonify({"message": "No valid settings fields provided for update"}), 400

    curr_user = getattr(request, "current_user", {})
    validated_data["updated_by"] = curr_user.get("email") or curr_user.get("name") or "Administrator"

    try:
        updated = update_system_settings(validated_data)
        return jsonify({
            "message": "System configuration updated successfully",
            "settings": updated
        }), 200
    except Exception as e:
        return jsonify({"message": f"Failed to persist configuration: {str(e)}"}), 500
