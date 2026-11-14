import time
import datetime
from typing import Optional, Dict, Any
from database import (
    is_mongo_connected,
    get_cameras_col,
    mem_cameras,
    get_system_settings
)
from routes.event_routes import broadcast_event

HEALTH_STATUS_ONLINE = "ONLINE"
HEALTH_STATUS_WARNING = "WARNING"
HEALTH_STATUS_OFFLINE = "OFFLINE"
HEALTH_STATUS_DEGRADED = "DEGRADED"
HEALTH_STATUS_COMPLETED = "COMPLETED"

VALID_HEALTH_STATUSES = {
    HEALTH_STATUS_ONLINE,
    HEALTH_STATUS_WARNING,
    HEALTH_STATUS_OFFLINE,
    HEALTH_STATUS_DEGRADED,
    HEALTH_STATUS_COMPLETED
}

def _to_iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    try:
        return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).isoformat()
    except Exception:
        return None

def _find_camera_doc(camera_id: str) -> Optional[Dict[str, Any]]:
    if not camera_id:
        return None
    cam_str = str(camera_id)
    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_cameras_col()
            if col is not None:
                doc = col.find_one({"$or": [{"_id": ObjectId(cam_str)}, {"_id": cam_str}]})
                if doc:
                    return doc
        except Exception:
            pass

    for c in mem_cameras:
        if str(c.get("_id")) == cam_str:
            return c
    return None

def _persist_camera_health_update(camera_id: str, updates: Dict[str, Any]) -> None:
    if not camera_id or not updates:
        return
    cam_str = str(camera_id)

    if is_mongo_connected:
        try:
            from bson import ObjectId
            col = get_cameras_col()
            if col is not None:
                col.update_one(
                    {"$or": [{"_id": ObjectId(cam_str)}, {"_id": cam_str}]},
                    {"$set": updates}
                )
        except Exception:
            pass

    for i, c in enumerate(mem_cameras):
        if str(c.get("_id")) == cam_str:
            mem_cameras[i].update(updates)
            break

def evaluate_camera_health(
    camera_doc: Dict[str, Any],
    current_time: Optional[float] = None,
    settings: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Evaluates current camera health based on elapsed time since last_frame_time,
    consecutive failures, or video completion status.
    Deterministic, thread-safe, and avoids background polling threads.
    """
    if not camera_doc:
        return {}

    cam = dict(camera_doc)
    now = current_time if current_time is not None else time.time()
    cfg = settings or get_system_settings()

    warning_threshold = float(cfg.get("camera_warning_timeout_sec", 5.0))
    offline_threshold = float(cfg.get("camera_offline_timeout_sec", 15.0))
    degraded_limit = int(cfg.get("camera_degraded_failures", 3))

    current_status = cam.get("status", HEALTH_STATUS_ONLINE)
    last_frame_ts = cam.get("last_frame_time")
    consecutive_fails = int(cam.get("consecutive_failures") or 0)

    # 1. COMPLETED status: uploaded video reached normal end; remains completed until new frame
    if current_status == HEALTH_STATUS_COMPLETED:
        cam.setdefault("status_reason", "Uploaded video inspection completed normally")
        return cam

    # 2. DEGRADED status: sustained processing failures
    if current_status == HEALTH_STATUS_DEGRADED or consecutive_fails >= degraded_limit:
        cam["status"] = HEALTH_STATUS_DEGRADED
        cam.setdefault("status_reason", f"Degraded: {consecutive_fails} consecutive processing failures")
        return cam

    # 3. Dynamic timeout evaluation based on last_frame_time
    if last_frame_ts is not None:
        try:
            elapsed = max(0.0, now - float(last_frame_ts))
        except (ValueError, TypeError):
            elapsed = 0.0

        if elapsed >= offline_threshold:
            new_status = HEALTH_STATUS_OFFLINE
            reason = f"No frames received for {elapsed:.1f}s (offline threshold: {offline_threshold:.1f}s)"
        elif elapsed >= warning_threshold:
            new_status = HEALTH_STATUS_WARNING
            reason = f"No frames received for {elapsed:.1f}s (warning threshold: {warning_threshold:.1f}s)"
        else:
            new_status = HEALTH_STATUS_ONLINE
            reason = "Frames are being received and processed normally"

        if new_status != current_status:
            cam["status"] = new_status
            cam["last_transition_time"] = now
            cam["last_transition_time_iso"] = _to_iso(now)
            cam["status_reason"] = reason
            _persist_camera_health_update(str(cam.get("_id")), {
                "status": new_status,
                "last_transition_time": now,
                "last_transition_time_iso": _to_iso(now),
                "status_reason": reason
            })
            broadcast_event("CAMERA_STATUS_CHANGED", {
                "cameraId": str(cam.get("_id")),
                "cameraName": cam.get("name"),
                "status": new_status,
                "reason": reason,
                "lastFrameTime": cam.get("last_frame_time_iso")
            })
        else:
            cam["status_reason"] = reason
    else:
        # Camera without recorded frame activity preserves configured status
        cam.setdefault("status_reason", "Camera registered and awaiting stream frames")

    return cam

def record_camera_frame_success(
    camera_id: str,
    timestamp: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """
    Called upon successful frame decoding and inference.
    Transitions camera to ONLINE if it was WARNING, OFFLINE, DEGRADED, or COMPLETED.
    Resets failure counters and updates last_frame_time.
    """
    if not camera_id:
        return None
    now = timestamp if timestamp is not None else time.time()
    cam = _find_camera_doc(camera_id)
    if not cam:
        return None

    prev_status = cam.get("status")
    updates = {
        "last_frame_time": now,
        "last_frame_time_iso": _to_iso(now),
        "consecutive_failures": 0,
        "error_details": None,
        "status": HEALTH_STATUS_ONLINE,
        "status_reason": "Frames are being received and processed normally"
    }

    status_changed = prev_status != HEALTH_STATUS_ONLINE
    if status_changed:
        updates["last_transition_time"] = now
        updates["last_transition_time_iso"] = _to_iso(now)

    _persist_camera_health_update(camera_id, updates)

    if status_changed:
        broadcast_event("CAMERA_STATUS_CHANGED", {
            "cameraId": str(camera_id),
            "cameraName": cam.get("name"),
            "status": HEALTH_STATUS_ONLINE,
            "reason": updates["status_reason"],
            "lastFrameTime": updates["last_frame_time_iso"]
        })

    cam.update(updates)
    return cam

def record_camera_frame_failure(
    camera_id: str,
    error_message: str = "Frame processing failure",
    timestamp: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """
    Records an ingestion or processing failure (e.g. corrupt image payload, decode error).
    Increments consecutive failure count. Transitions to DEGRADED when threshold reached.
    Camera failures NEVER generate PPE violations.
    """
    if not camera_id:
        return None
    now = timestamp if timestamp is not None else time.time()
    cam = _find_camera_doc(camera_id)
    if not cam:
        return None

    cfg = get_system_settings()
    degraded_limit = int(cfg.get("camera_degraded_failures", 3))

    fails = int(cam.get("consecutive_failures") or 0) + 1
    prev_status = cam.get("status")

    updates = {
        "consecutive_failures": fails,
        "error_details": str(error_message),
        "last_failure_time": now,
        "last_failure_time_iso": _to_iso(now)
    }

    if fails >= degraded_limit:
        updates["status"] = HEALTH_STATUS_DEGRADED
        updates["status_reason"] = f"Degraded: {fails} consecutive processing failures ({error_message})"
        if prev_status != HEALTH_STATUS_DEGRADED:
            updates["last_transition_time"] = now
            updates["last_transition_time_iso"] = _to_iso(now)
            broadcast_event("CAMERA_STATUS_CHANGED", {
                "cameraId": str(camera_id),
                "cameraName": cam.get("name"),
                "status": HEALTH_STATUS_DEGRADED,
                "reason": updates["status_reason"],
                "errorDetails": str(error_message)
            })

    _persist_camera_health_update(camera_id, updates)
    cam.update(updates)
    return cam

def record_camera_video_completed(
    camera_id: str,
    reason: str = "Uploaded video inspection completed normally",
    timestamp: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """
    Transitions camera to COMPLETED upon natural end of uploaded video playback.
    Distinguishes completed video from camera disconnection or failure.
    """
    if not camera_id:
        return None
    now = timestamp if timestamp is not None else time.time()
    cam = _find_camera_doc(camera_id)
    if not cam:
        return None

    updates = {
        "status": HEALTH_STATUS_COMPLETED,
        "status_reason": reason,
        "error_details": None,
        "consecutive_failures": 0,
        "last_transition_time": now,
        "last_transition_time_iso": _to_iso(now)
    }

    _persist_camera_health_update(camera_id, updates)
    broadcast_event("CAMERA_STATUS_CHANGED", {
        "cameraId": str(camera_id),
        "cameraName": cam.get("name"),
        "status": HEALTH_STATUS_COMPLETED,
        "reason": reason
    })

    cam.update(updates)
    return cam
