import time
import os
import json
import datetime
import tempfile
import uuid
import threading
from typing import Optional, Any
import numpy as np
import cv2
from flask import Blueprint, request, jsonify
from database import (
    is_mongo_connected, 
    get_detections_col, 
    mem_detections,
    get_zones_col,
    mem_zones,
    get_notifications_col,
    mem_notifications
)
from ai_engine.ppe_model import decode_image, encode_image_to_base64, detect_ppe_in_frame
from ai_engine.compliance import evaluate_compliance, draw_compliance_annotations, reset_session_temporal
from ai_engine.temporal_compliance import sanitize_timestamp
from ai_engine.tracker import get_session_tracker, reset_session_tracker
from auth import (
    token_required,
    supervisor_required,
    super_admin_required,
    strict_token_required,
    dev_fallback_allowed
)
from config import Config
from storage import upload_evidence_image, is_cloudinary_enabled
from alerts import dispatch_violation_alert
from ai_engine.camera_health import (
    record_camera_frame_success,
    record_camera_frame_failure,
    record_camera_video_completed
)

detection_bp = Blueprint("detection_bp", __name__)
_mem_incident_lock = threading.Lock()

# Thread-safe session tracking ownership registry (M3.3)
_session_owners = {}
_session_owners_lock = threading.Lock()

def register_session_owner(session_id: str, user_id: str):
    if not session_id or not user_id:
        return
    with _session_owners_lock:
        _session_owners[session_id] = str(user_id)

def get_session_owner(session_id: str) -> Optional[str]:
    with _session_owners_lock:
        return _session_owners.get(session_id)

def clear_session_owner(session_id: str):
    with _session_owners_lock:
        _session_owners.pop(session_id, None)

ALLOWED_VIDEO_EXTENSIONS = {"mp4", "avi", "mov", "mkv", "webm"}

def validate_uploaded_video(video_file) -> tuple[bool, str, str]:
    """
    Milestone M3.3: Strict video upload security validation:
    - Verifies presence of filename and allowed video extension.
    - Rejects empty uploads (0 bytes) and oversized uploads exceeding MAX_CONTENT_LENGTH.
    - Deep container decoding and verification is handled securely via OpenCV VideoCapture.
    """
    if not video_file or not video_file.filename:
        return False, "Video file is required", ""

    filename = video_file.filename.strip()
    if "." not in filename:
        return False, "Video file missing extension", ""

    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        return False, f"Unsupported video format: .{ext}. Allowed extensions: mp4, avi, mov, mkv, webm", ""

    try:
        video_file.seek(0, os.SEEK_END)
        size = video_file.tell()
        video_file.seek(0)
    except Exception:
        size = 0

    if size == 0:
        return False, "Uploaded video file is empty (0 bytes)", ""

    max_bytes = getattr(Config, "MAX_CONTENT_LENGTH", 100 * 1024 * 1024)
    if size > max_bytes:
        return False, f"Video file size exceeds maximum limit of {max_bytes // (1024 * 1024)}MB", ""

    return True, "", ext

def persist_confirmed_incident(incident_doc: dict) -> tuple[dict, bool]:
    """
    M2.2B.4H: Idempotently persists a confirmed incident episode to the database.
    Prevents duplicate records across frames, retries, and network replays using stable episode_id.
    Returns: (persisted_doc, is_new_insert)
    """
    episode_id = incident_doc.get("episode_id")
    if not episode_id:
        episode_id = f"ep_{uuid.uuid4().hex[:12]}"
        incident_doc["episode_id"] = episode_id

    # Normalize fields for downstream compatibility
    incident_doc.setdefault("complianceStatus", "VIOLATION")
    incident_doc.setdefault("reviewStatus", "PENDING")
    incident_doc.setdefault("reviewerNotes", "")
    if "timestamp" not in incident_doc:
        incident_doc["timestamp"] = datetime.datetime.now(datetime.timezone.utc)
    if "createdAt" not in incident_doc:
        incident_doc["createdAt"] = datetime.datetime.now(datetime.timezone.utc)

    if is_mongo_connected:
        try:
            col = get_detections_col()
            if col is not None:
                try:
                    col.create_index("episode_id", unique=True, sparse=True)
                except Exception:
                    pass

                res = col.update_one(
                    {"episode_id": episode_id},
                    {"$setOnInsert": incident_doc},
                    upsert=True
                )
                if res.upserted_id is not None:
                    incident_doc["_id"] = str(res.upserted_id)
                    return incident_doc, True
                else:
                    existing = col.find_one({"episode_id": episode_id})
                    if existing:
                        incident_doc["_id"] = str(existing.get("_id"))
                    return incident_doc, False
        except Exception as e:
            try:
                col = get_detections_col()
                if col is not None:
                    existing = col.find_one({"episode_id": episode_id})
                    if existing:
                        incident_doc["_id"] = str(existing.get("_id"))
                        return incident_doc, False
            except Exception:
                pass

    # In-memory fallback
    with _mem_incident_lock:
        existing = next((d for d in mem_detections if d.get("episode_id") == episode_id), None)
        if existing:
            incident_doc["_id"] = str(existing.get("_id"))
            return incident_doc, False
        else:
            incident_doc["_id"] = "det_" + str(int(time.time() * 1000)) + "_" + uuid.uuid4().hex[:4]
            mem_detections.insert(0, incident_doc)
            return incident_doc, True

def _parse_strict_track_id(val: Any) -> tuple[Optional[int], Optional[str]]:
    """
    M2.2B.5C-F.4: Strictly validates and parses a track ID:
    - Rejects booleans (isinstance(val, bool)).
    - Rejects all float values, including whole-number floats like 1.0 (isinstance(val, float)).
    - Rejects non-numeric objects (None, dict, list).
    - Accepts genuine integers (e.g. 1, 0).
    - Accepts strictly integer-formatted numeric strings (e.g. "1", "0").
    """
    if val is None:
        return None, "Track ID cannot be None"

    if isinstance(val, bool):
        return None, f"Track ID cannot be boolean: {val!r}"

    if isinstance(val, float):
        return None, f"Track ID cannot be float: {val!r}"

    if isinstance(val, int):
        return val, None

    if isinstance(val, str):
        s = val.strip()
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            return int(s), None
        return None, f"Track ID string must be strictly integer-formatted, got {val!r}"

    return None, f"Track ID must be integer or integer string, got {type(val).__name__}"


def _extract_and_validate_candidate_identity(candidate: dict) -> tuple[Optional[dict], Optional[str]]:
    """
    M2.2B.5C-F.2 / M2.2B.5C-F.3: Validates that a resolution candidate dictionary contains all
    mandatory identity fields with valid types before any lookup or mutation occurs.
    Returns: (identity_dict, error_message)
    """
    if not isinstance(candidate, dict):
        return None, "Candidate must be a dictionary"

    episode_id = candidate.get("episode_id")
    if not episode_id or not isinstance(episode_id, str) or not episode_id.strip():
        return None, "Candidate missing or empty 'episode_id'"

    session_id = candidate.get("session_id")
    if session_id is None or not str(session_id).strip():
        return None, "Candidate missing or empty 'session_id'"

    track_id = candidate.get("track_id")
    track_id_int, track_err = _parse_strict_track_id(track_id)
    if track_id_int is None:
        return None, f"Candidate track_id invalid: {track_err}"

    ppe_category = candidate.get("ppe_category")
    if not ppe_category or not isinstance(ppe_category, str) or not ppe_category.strip():
        return None, "Candidate missing or empty 'ppe_category'"

    from ai_engine.compliance import normalize_ppe_class
    canonical_ppe = normalize_ppe_class(ppe_category)

    zone_id = candidate.get("zone_id")
    cand_zone_id = str(zone_id).strip() if zone_id else None

    return {
        "episode_id": episode_id.strip(),
        "session_id": str(session_id).strip(),
        "track_id": track_id_int,
        "zone_id": cand_zone_id,
        "ppe_category": ppe_category.strip(),
        "canonical_ppe": canonical_ppe
    }, None


def _match_candidate_with_incident_identity(cand_identity: dict, incident_doc: dict) -> tuple[bool, Optional[str]]:
    """
    M2.2B.5C-F.2 / M2.2B.5C-F.3: Verifies that stored incident document identity strictly matches the candidate:
    - episode_id exact match
    - session_id exact match
    - track_id strict integer equivalence without silent float truncation
    - PPE category present in stored missingPPE (or ppe_category)
    - zone_id match (Zone B compliance cannot resolve Zone A incident)
    Returns: (is_matched, mismatch_reason)
    """
    if not isinstance(incident_doc, dict):
        return False, "Stored incident is not a dictionary"

    # 1. Episode ID exact match
    doc_episode = str(incident_doc.get("episode_id") or "").strip()
    if doc_episode != cand_identity["episode_id"]:
        return False, f"Episode ID mismatch (stored='{doc_episode}', cand='{cand_identity['episode_id']}')"

    # 2. Session ID exact match
    doc_session = str(incident_doc.get("session_id") or "").strip()
    if doc_session != cand_identity["session_id"]:
        return False, f"Session ID mismatch (stored='{doc_session}', cand='{cand_identity['session_id']}')"

    # 3. Track ID strict equivalence (no silent float truncation)
    doc_track = incident_doc.get("track_id")
    doc_track_int, doc_track_err = _parse_strict_track_id(doc_track)
    if doc_track_int is None:
        return False, f"Stored incident track_id invalid: {doc_track_err}"
    if doc_track_int != cand_identity["track_id"]:
        return False, f"Track ID mismatch (stored={doc_track_int}, cand={cand_identity['track_id']})"

    # 4. PPE category match in missingPPE (or ppe_category)
    from ai_engine.compliance import normalize_ppe_class
    cand_ppe = cand_identity["canonical_ppe"]
    doc_missing = incident_doc.get("missingPPE")
    doc_ppes = []
    if isinstance(doc_missing, (list, tuple)):
        for item in doc_missing:
            if item:
                doc_ppes.append(normalize_ppe_class(str(item)))
    elif doc_missing:
        doc_ppes.append(normalize_ppe_class(str(doc_missing)))

    extra_cat = incident_doc.get("ppe_category") or incident_doc.get("ppeCategory")
    if extra_cat:
        doc_ppes.append(normalize_ppe_class(str(extra_cat)))

    if cand_ppe not in doc_ppes:
        return False, f"PPE category mismatch (candidate '{cand_ppe}' not in stored missingPPE {doc_ppes})"

    # 5. Zone ID match (Zone B compliance cannot resolve Zone A incident)
    cand_zone = cand_identity.get("zone_id")
    doc_zone = incident_doc.get("zoneId")
    cand_z_str = str(cand_zone).strip() if cand_zone else None
    doc_z_str = str(doc_zone).strip() if doc_zone else None
    if cand_z_str != doc_z_str:
        return False, f"Zone ID mismatch (stored='{doc_zone}', cand='{cand_zone}')"

    return True, None


def resolve_confirmed_incident(candidate: dict) -> tuple[Optional[dict], bool]:
    """
    M2.2B.5C: Idempotently updates an existing incident record in MongoDB (or memory fallback)
    to mark it as automatically resolved upon verified continuous compliance.

    Requirements (M2.2B.5C / M2.2B.5C-F.2):
    1. Validate candidate contains all required identity fields (episode_id, session_id, track_id, ppe_category).
    2. Defense-in-depth identity validation: match candidate session_id, track_id, and PPE category against stored incident.
    3. Update only an existing incident using exact candidate['episode_id']; never insert a second incident.
    4. Only resolve an incident in an Open state (reviewStatus not in RESOLVED, REJECTED, APPROVED, FALSE_POSITIVE).
    5. Persist status=RESOLVED, resolution_type=AUTOMATIC_COMPLIANCE, timestamp, reason, duration, identifiers.
    6. Append a lifecycle_history entry with actor SYSTEM.
    7. Preserve original creation time, timestamps, episode_id, evidence images.
    8. Return (document, is_new_transition).
       - (doc, True) if newly resolved.
       - (doc, False) if already resolved (idempotent no-op).
       - (None, False) if not found, DB failure, or candidate identity mismatch (allows retry).
    """
    cand_identity, validation_err = _extract_and_validate_candidate_identity(candidate)
    if not cand_identity:
        print(f"Incident auto-resolution rejected: {validation_err}")
        return None, False

    episode_id = cand_identity["episode_id"]
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    verified_dur = float(candidate.get("verified_compliance_duration_sec", 2.0))
    reason = f"Continuous verified compliance maintained for {verified_dur:.1f}s"
    cand_ts = candidate.get("candidate_timestamp")

    history_entry = {
        "state": "RESOLVED",
        "resolution_type": "AUTOMATIC_COMPLIANCE",
        "actor": "SYSTEM",
        "timestamp": now_utc,
        "reason": reason,
        "verified_compliance_duration_sec": verified_dur,
        "session_id": cand_identity["session_id"],
        "track_id": cand_identity["track_id"],
        "worker_id": candidate.get("worker_id"),
        "ppe_category": cand_identity["ppe_category"]
    }

    update_payload = {
        "$set": {
            "status": "RESOLVED",
            "reviewStatus": "RESOLVED",
            "resolution_type": "AUTOMATIC_COMPLIANCE",
            "resolutionType": "AUTOMATIC_COMPLIANCE",
            "resolved_at": now_utc,
            "resolvedAt": now_utc,
            "resolution_timestamp": cand_ts,
            "resolution_reason": reason,
            "resolutionReason": reason,
            "verified_compliance_duration_sec": verified_dur,
            "resolved_worker_id": candidate.get("worker_id"),
            "resolved_track_id": cand_identity["track_id"],
            "resolved_ppe_category": cand_identity["ppe_category"],
            "resolved_session_id": cand_identity["session_id"],
            "updatedAt": now_utc
        },
        "$push": {
            "lifecycle_history": history_entry
        }
    }

    cand_ppe = cand_identity["canonical_ppe"]
    raw_ppe = cand_identity["ppe_category"]
    ppe_variants = list({
        cand_ppe,
        cand_ppe.capitalize(),
        cand_ppe.upper(),
        raw_ppe,
        raw_ppe.lower(),
        raw_ppe.capitalize()
    })
    if cand_ppe == "helmet":
        ppe_variants.extend(["Safety Helmet", "safety helmet", "Hard Hat", "hard hat", "hardhat"])
    elif cand_ppe == "vest":
        ppe_variants.extend(["Safety Vest", "safety vest", "reflective vest", "Reflective Vest", "jacket"])
    elif cand_ppe == "boots":
        ppe_variants.extend(["Safety Boots", "safety boots", "safety_shoe", "Safety Shoe", "shoes", "boot", "footwear"])
    elif cand_ppe == "goggles":
        ppe_variants.extend(["Safety Glasses", "safety glasses", "glasses", "eye wear"])

    filter_query = {
        "episode_id": episode_id,
        "session_id": cand_identity["session_id"],
        "track_id": {"$in": [cand_identity["track_id"], str(cand_identity["track_id"])]},
        "$or": [
            {"missingPPE": {"$in": ppe_variants}},
            {"ppe_category": {"$in": ppe_variants}}
        ],
        "reviewStatus": {"$nin": ["RESOLVED", "REJECTED", "APPROVED", "FALSE_POSITIVE"]},
        "status": {"$ne": "RESOLVED"}
    }
    if cand_identity.get("zone_id"):
        filter_query["zoneId"] = cand_identity["zone_id"]
    else:
        filter_query["zoneId"] = {"$in": [None, ""]}

    if is_mongo_connected:
        try:
            col = get_detections_col()
            if col is not None:
                res = col.update_one(filter_query, update_payload)
                if res.modified_count > 0:
                    doc = col.find_one({"episode_id": episode_id})
                    if doc:
                        doc["_id"] = str(doc["_id"])
                    return doc, True
                else:
                    existing = col.find_one({"episode_id": episode_id})
                    if existing:
                        existing["_id"] = str(existing.get("_id"))
                        # Verify identity on existing document before checking terminal states
                        matched, mismatch_reason = _match_candidate_with_incident_identity(cand_identity, existing)
                        if not matched:
                            print(f"Incident auto-resolution rejected: candidate identity mismatch for episode '{episode_id}' ({mismatch_reason})")
                            return None, False

                        # If already resolved, acknowledge idempotently
                        if existing.get("status") == "RESOLVED" or existing.get("reviewStatus") == "RESOLVED":
                            return existing, False
                        # If rejected / approved / false positive: cannot auto-resolve
                        if existing.get("reviewStatus") in ["REJECTED", "APPROVED", "FALSE_POSITIVE"]:
                            return existing, False
                    return None, False
        except Exception as e:
            print(f"MongoDB incident auto-resolution notice: {e}")
            return None, False

    # In-memory fallback
    with _mem_incident_lock:
        existing = next((d for d in mem_detections if d.get("episode_id") == episode_id), None)
        if not existing:
            return None, False

        # Validate identity against stored incident document
        matched, mismatch_reason = _match_candidate_with_incident_identity(cand_identity, existing)
        if not matched:
            print(f"Incident auto-resolution rejected (in-memory): candidate identity mismatch for episode '{episode_id}' ({mismatch_reason})")
            return None, False

        if existing.get("status") == "RESOLVED" or existing.get("reviewStatus") == "RESOLVED":
            return existing, False

        if existing.get("reviewStatus") in ["REJECTED", "APPROVED", "FALSE_POSITIVE"]:
            return existing, False

        for k, v in update_payload["$set"].items():
            existing[k] = v
        existing.setdefault("lifecycle_history", []).append(history_entry)
        return existing, True


def process_resolution_candidates(tracker, session_id: str) -> list[dict]:
    """
    M2.2B.5C: Consumes verified-compliance resolution candidates from the tracker,
    persists resolution in MongoDB/memory, broadcasts SSE events,
    and acknowledges the candidate only after successful persistence.
    """
    if tracker is None or not session_id:
        return []

    candidates = tracker.get_resolution_candidates()
    if not candidates:
        return []

    resolved_list = []
    for cand in candidates:
        cand_session = cand.get("session_id")
        if cand_session and str(cand_session) != str(session_id):
            continue

        episode_id = cand.get("episode_id")
        if not episode_id:
            continue

        resolved_doc, is_new_resolution = resolve_confirmed_incident(cand)
        if resolved_doc is not None:
            # Acknowledge in tracker
            tracker.acknowledge_resolution(episode_id)

            if is_new_resolution:
                from routes.event_routes import broadcast_event
                broadcast_event("INCIDENT_RESOLVED", {
                    "event": resolved_doc,
                    "resolution": cand
                })
                resolved_list.append(resolved_doc)

    return resolved_list

@detection_bp.route("/detect", methods=["POST"])
@detection_bp.route("/api/detect", methods=["POST"])
@token_required
@supervisor_required
@dev_fallback_allowed
def detect_image():
    start_time = time.time()
    
    # 1. Parse Image Input (multipart file or json base64)
    img = None
    required_ppe = ['helmet', 'vest']
    zone_name = "Live Camera"
    conf_thresh = 0.35
    session_id = None

    zone_id = None
    camera_id = None
    if request.is_json:
        data = request.get_json(silent=True) or {}
        img_b64 = data.get("image")
        img = decode_image(img_b64)
        required_ppe = data.get("required_ppe", required_ppe)
        zone_name = data.get("zone_name", zone_name)
        zone_id = data.get("zone_id") or data.get("zoneId")
        camera_id = data.get("camera_id") or data.get("cameraId")
        try:
            conf_thresh = float(data.get("confidence_threshold", conf_thresh))
        except (ValueError, TypeError):
            conf_thresh = 0.35
        session_id = data.get("session_id")
        timestamp = data.get("timestamp")
    elif "file" in request.files:
        file_obj = request.files["file"]
        img = decode_image(file_obj)
        if "required_ppe" in request.form:
            try:
                required_ppe = json.loads(request.form["required_ppe"])
            except Exception:
                pass
        zone_name = request.form.get("zone_name", zone_name)
        zone_id = request.form.get("zone_id") or request.form.get("zoneId")
        camera_id = request.form.get("camera_id") or request.form.get("cameraId")
        try:
            conf_thresh = float(request.form.get("confidence_threshold", conf_thresh))
        except (ValueError, TypeError):
            conf_thresh = 0.35
        session_id = request.form.get("session_id")
        timestamp = request.form.get("timestamp")
    else:
        timestamp = request.args.get("timestamp")
        zone_id = request.args.get("zone_id") or request.args.get("zoneId")
        camera_id = request.args.get("camera_id") or request.args.get("cameraId")

    if not session_id:
        session_id = request.args.get("session_id")

    curr_user = getattr(request, "current_user", {})
    if session_id and curr_user.get("id"):
        register_session_owner(session_id, curr_user.get("id"))

    if img is None:
        if camera_id:
            record_camera_frame_failure(str(camera_id), "Invalid or missing image payload")
        return jsonify({"message": "Invalid or missing image payload"}), 400

    # Sanitize timestamp: non-numeric, NaN, inf, or negative values resolve to None safely without raising 500
    valid_timestamp = sanitize_timestamp(timestamp)

    h, w = img.shape[:2]
    # 2. Run YOLO Inference with Session-Scoped Anonymous Worker Tracking
    raw_annotated, detected_objects, persons = detect_ppe_in_frame(
        img, confidence_threshold=conf_thresh, session_id=session_id, timestamp=valid_timestamp
    )

    # 2.5 Spatial Zone Resolution & Authoritative Policy Retrieval
    from ai_engine.zone_assignment import (
        assign_persons_spatial_zones,
        get_authoritative_zone_ppe,
        lookup_camera
    )
    from ai_engine.compliance import normalize_ppe_class, CANONICAL_PPE_REGION_MAP

    camera_doc = lookup_camera(camera_id=camera_id, zone_id=zone_id)
    has_camera_polygons = bool(camera_doc and camera_doc.get("zones"))

    if camera_id:
        record_camera_frame_success(str(camera_id))
    elif camera_doc and camera_doc.get("_id") and str(camera_doc.get("_id")) != "uploaded_video":
        record_camera_frame_success(str(camera_doc.get("_id")))

    # Assign camera-specific spatial zones to tracked persons
    persons = assign_persons_spatial_zones(
        persons, camera_doc, img_shape=(h, w), session_id=session_id, timestamp=valid_timestamp
    )

    # Retrieve and apply authoritative zone PPE policies per worker
    for person in persons:
        z_status = person.get("zone_assignment_status", "UNASSIGNED")
        p_zid = person.get("zone_id")

        if has_camera_polygons:
            # Modern polygon-configured camera: authoritative zone policy takes absolute precedence
            if z_status == "ASSIGNED" and p_zid:
                auth_policy = get_authoritative_zone_ppe(p_zid)
                if auth_policy is not None:
                    person["zone_policy_valid"] = True
                    person["required_ppe"] = auth_policy
                else:
                    # Configured polygon zone has invalid or missing database policy
                    person["zone_policy_valid"] = False
                    person["uncertain"] = True
                    person["uncertain_reason"] = "INVALID_ZONE_POLICY"
                    person["required_ppe"] = []
            elif z_status == "UNASSIGNED":
                person["zone_policy_valid"] = True
                person["uncertain"] = True
                person["uncertain_reason"] = "NO_MONITORED_ZONE"
                person["required_ppe"] = []
            elif z_status == "UNCERTAIN":
                person["zone_policy_valid"] = True
                person["uncertain"] = True
                person["uncertain_reason"] = person.get("uncertain_reason") or "ZONE_BOUNDARY_AMBIGUITY"
                person["required_ppe"] = []
        else:
            # Legacy camera without polygons: retain previous camera-level behavior
            # Respects caller-supplied required_ppe or falls back to camera zone policy
            person["zone_policy_valid"] = True
            if required_ppe:
                person["required_ppe"] = [
                    normalize_ppe_class(r) for r in required_ppe
                    if normalize_ppe_class(r) in CANONICAL_PPE_REGION_MAP
                ]
            elif p_zid:
                person["required_ppe"] = get_authoritative_zone_ppe(p_zid) or ['helmet', 'vest']
            else:
                person["required_ppe"] = ['helmet', 'vest']

    # 3. Compliance Evaluation with Body Scan Awareness & Temporal Confirmation
    compliance_status, missing_ppe, evaluated_persons = evaluate_compliance(
        persons, detected_objects, required_ppe, confidence_threshold=conf_thresh, img_shape=(h, w),
        session_id=session_id, timestamp=valid_timestamp
    )

    # 4. Draw HUD Visual Annotations
    final_annotated = draw_compliance_annotations(
        img, evaluated_persons, detected_objects, compliance_status
    )
    annotated_b64 = encode_image_to_base64(final_annotated)
    latency_ms = int((time.time() - start_time) * 1000)

    # 5. M2.2B.4H: Automatic Live Incident Persistence for newly confirmed violation episodes
    new_confirmed_incidents = []
    if session_id and compliance_status == "VIOLATION":
        for person in evaluated_persons:
            track_id = person.get("track_id")
            if track_id is None:
                continue
            worker_id = person.get("worker_id", f"W-{track_id:03d}")
            temporal_state = person.get("temporal_state", {})

            for new_cat in person.get("new_confirmed_violations", []):
                st_dict = temporal_state.get(new_cat, {})
                episode_id = st_dict.get("episode_id")
                if not episode_id:
                    continue

                # Upload evidence snapshot for this confirmed episode
                image_url = None
                try:
                    uploaded = upload_evidence_image(annotated_b64, folder="ppe_violations")
                    if uploaded and isinstance(uploaded, str) and (
                        uploaded.startswith("http://") or uploaded.startswith("https://") or uploaded.startswith("/")
                    ):
                        image_url = uploaded
                except Exception as e:
                    print("Snapshot evidence upload notice:", e)
                    image_url = None

                raw_evidence_ref = image_url
                if not raw_evidence_ref and annotated_b64:
                    if isinstance(annotated_b64, str) and annotated_b64.strip():
                        clean_b64 = annotated_b64.strip()
                        raw_evidence_ref = (
                            clean_b64 if clean_b64.startswith("data:image/")
                            else f"data:image/jpeg;base64,{clean_b64}"
                        )
                    else:
                        raw_evidence_ref = None

                p_zid = str(person.get("zone_id") or zone_id or (camera_doc.get("zoneId") if camera_doc else "zone_01"))
                p_zname = person.get("zone_name") or zone_name or (camera_doc.get("zoneName") if camera_doc else "General Facility Zone")
                p_cam_id = str(camera_doc.get("_id")) if camera_doc and camera_doc.get("_id") else (str(camera_id) if camera_id else "webcam_main")
                p_cam_name = camera_doc.get("name") if camera_doc else "Primary Live Camera"
                p_cam_src = camera_doc.get("sourceType", "webcam") if camera_doc else "webcam"

                incident_doc = {
                    "episode_id": episode_id,
                    "worker_id": worker_id,
                    "track_id": int(track_id),
                    "personId": worker_id,
                    "workerTag": f"{worker_id} (Track #{track_id})",
                    "session_id": str(session_id),
                    "zoneId": p_zid,
                    "zoneName": p_zname,
                    "cameraId": p_cam_id,
                    "cameraName": p_cam_name,
                    "sourceType": p_cam_src,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc),
                    "detectedClasses": detected_objects,
                    "confidenceScores": [d.get("confidence", 0.0) for d in detected_objects],
                    "missingPPE": [new_cat],
                    "complianceStatus": "VIOLATION",
                    "personCount": len(evaluated_persons),
                    "reviewStatus": "PENDING",
                    "reviewerNotes": "",
                    "first_missing_timestamp": st_dict.get("first_missing_timestamp"),
                    "confirmed_timestamp": st_dict.get("confirmed_timestamp"),
                    "imageUrl": image_url,
                    "evidenceImageReference": raw_evidence_ref,
                    "processingMetadata": {
                        "latencyMs": latency_ms,
                        "accumulated_missing_sec": st_dict.get("accumulated_missing_sec", 3.0),
                        "model": "YOLOv8"
                    },
                    "createdAt": datetime.datetime.now(datetime.timezone.utc)
                }

                saved_doc, is_new_insert = persist_confirmed_incident(incident_doc)
                if is_new_insert:
                    from routes.event_routes import broadcast_event
                    broadcast_event("VIOLATION_DETECTED", {
                        "event": saved_doc
                    })
                    new_confirmed_incidents.append(saved_doc)

    # 6. M2.2B.5C: Automatic Incident Resolution for verified compliance candidates
    new_resolved_incidents = []
    if session_id:
        from ai_engine.temporal_compliance import get_session_temporal_tracker
        tracker = get_session_temporal_tracker(session_id)
        new_resolved_incidents = process_resolution_candidates(tracker, session_id)

    return jsonify({
        "compliance_status": compliance_status,
        "missing_ppe": missing_ppe,
        "detected_classes": detected_objects,
        "persons": evaluated_persons,
        "annotated_image": annotated_b64,
        "latency_ms": latency_ms,
        "zone_name": zone_name,
        "new_confirmed_incidents": new_confirmed_incidents,
        "new_resolved_incidents": new_resolved_incidents
    }), 200

@detection_bp.route("/detect-video", methods=["POST"])
@detection_bp.route("/api/detect-video", methods=["POST"])
@token_required
@supervisor_required
@dev_fallback_allowed
def detect_video():
    """
    Milestone M3.1: Uploaded Video Demonstration Workflow & Spatial Zone Integration.
    Processes uploaded factory inspection videos across chronological frames:
    - Supports explicit camera profile association (evaluates spatial polygon zones).
    - Preserves unzoned monitoring when no camera profile is specified.
    - Applies temporal compliance state machine and authoritative zone PPE policies.
    - Persists newly confirmed violation episodes and verifies continuous compliance auto-resolutions.
    - Cleans up isolated session trackers and temporary files on success, cancellation, or failure.
    """
    if "file" not in request.files:
        return jsonify({"message": "Video file is required"}), 400

    video_file = request.files["file"]
    valid, err_msg, ext = validate_uploaded_video(video_file)
    if not valid:
        return jsonify({"message": err_msg}), 400

    from database import get_system_settings
    sys_settings = get_system_settings()
    default_ppe = list(sys_settings.get("default_required_ppe") or ["helmet", "vest", "boots"])

    required_ppe = None
    if "required_ppe" in request.form:
        try:
            parsed = json.loads(request.form["required_ppe"])
            if isinstance(parsed, list) and len(parsed) > 0:
                required_ppe = parsed
        except Exception:
            pass
    if required_ppe is None:
        required_ppe = default_ppe

    camera_id = request.form.get("cameraId") or request.form.get("camera_id")
    zone_id = request.form.get("zoneId") or request.form.get("zone_id")
    conf_thresh = float(request.form.get("confidence_threshold", 0.35))
    conf_dur = float(request.form.get("confirmation_duration_sec", 3.0))
    sample_interval_sec = float(request.form.get("sample_interval_sec", 0.8))
    max_frames = min(int(request.form.get("max_frames", 60)), 120)

    from ai_engine.zone_assignment import (
        assign_persons_spatial_zones,
        get_authoritative_zone_ppe,
        lookup_camera,
        reset_session_spatial_zones
    )
    from ai_engine.compliance import normalize_ppe_class, CANONICAL_PPE_REGION_MAP

    # Resolve camera configuration: explicit camera ID uses its profile; missing ID is unzoned
    if camera_id and str(camera_id).strip():
        camera_doc = lookup_camera(camera_id=str(camera_id).strip(), zone_id=zone_id)
    else:
        # Explicit unzoned mode - zero polygons inherited!
        camera_doc = lookup_camera(camera_id="uploaded_video")

    has_camera_polygons = bool(camera_doc and camera_doc.get("zones"))
    camera_id_str = str(camera_doc.get("_id", "uploaded_video"))
    camera_name_str = str(camera_doc.get("name", "Uploaded Video Inspection"))

    # Save to temporary file securely
    temp_fd, temp_path = tempfile.mkstemp(prefix="ppe_vid_", suffix=f".{ext}")
    os.close(temp_fd)
    video_file.save(temp_path)
    video_session_id = f"video_{uuid.uuid4().hex[:8]}"

    curr_user = getattr(request, "current_user", {})
    if curr_user.get("id"):
        register_session_owner(video_session_id, curr_user.get("id"))

    try:
        cap = cv2.VideoCapture(temp_path)
        if not cap.isOpened():
            if camera_id and camera_id_str != "uploaded_video":
                record_camera_frame_failure(camera_id_str, "Unsupported or corrupted video file")
            return jsonify({"message": "Unsupported or corrupted video file"}), 400

        fps = cap.get(cv2.CAP_PROP_FPS)
        if not fps or fps <= 0 or np.isnan(fps):
            fps = 25.0

        frame_interval = int(max(round(fps * sample_interval_sec), 1))

        total_frames_processed = 0
        confirmed_video_episodes = set()
        resolved_video_episodes = set()
        persisted_incidents_list = []
        frame_results = []
        overall_missing = set()
        overall_detected = []
        last_annotated_b64 = None

        frame_count = 0
        while cap.isOpened() and total_frames_processed < max_frames:
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            if frame_count % frame_interval == 0:
                fh, fw = frame.shape[:2]
                timestamp_sec = round(frame_count / fps, 3)

                # 1. Anonymous Worker Tracking & PPE Detection
                _, detected_objects, persons = detect_ppe_in_frame(
                    frame, confidence_threshold=conf_thresh, session_id=video_session_id, timestamp=timestamp_sec
                )
                if camera_id and camera_id_str != "uploaded_video":
                    record_camera_frame_success(camera_id_str)

                # 2. Spatial Zone Resolution
                persons = assign_persons_spatial_zones(
                    persons, camera_doc, img_shape=(fh, fw), session_id=video_session_id, timestamp=timestamp_sec
                )

                # 3. Retrieve and Apply Authoritative Zone PPE Policies
                for person in persons:
                    z_status = person.get("zone_assignment_status", "UNASSIGNED")
                    p_zid = person.get("zone_id")

                    if has_camera_polygons:
                        if z_status == "ASSIGNED" and p_zid:
                            auth_policy = get_authoritative_zone_ppe(p_zid)
                            if auth_policy is not None:
                                person["zone_policy_valid"] = True
                                person["required_ppe"] = auth_policy
                                person["uncertain"] = False
                                person["uncertain_reason"] = None
                            else:
                                person["zone_policy_valid"] = False
                                person["uncertain"] = True
                                person["uncertain_reason"] = "INVALID_ZONE_POLICY"
                                person["required_ppe"] = []
                        elif z_status == "UNASSIGNED":
                            person["zone_policy_valid"] = True
                            person["uncertain"] = True
                            person["uncertain_reason"] = "NO_MONITORED_ZONE"
                            person["required_ppe"] = []
                        elif z_status == "UNCERTAIN":
                            person["zone_policy_valid"] = True
                            person["uncertain"] = True
                            person["uncertain_reason"] = person.get("uncertain_reason") or "ZONE_BOUNDARY_AMBIGUITY"
                            person["required_ppe"] = []
                    else:
                        person["zone_assignment_status"] = "ASSIGNED"
                        person["zone_policy_valid"] = True
                        if required_ppe:
                            person["required_ppe"] = [
                                normalize_ppe_class(r) for r in required_ppe
                                if normalize_ppe_class(r) in CANONICAL_PPE_REGION_MAP
                            ]
                        elif p_zid:
                            person["required_ppe"] = get_authoritative_zone_ppe(p_zid) or default_ppe
                        else:
                            person["required_ppe"] = default_ppe

                # 4. Compliance Evaluation with Body Part Scanning & Temporal Confirmation
                comp_status, missing_ppe, evaluated_persons = evaluate_compliance(
                    persons, detected_objects, required_ppe, confidence_threshold=conf_thresh,
                    img_shape=(fh, fw), session_id=video_session_id, timestamp=timestamp_sec,
                    confirmation_duration_sec=conf_dur
                )

                # Draw Visual Annotations
                annotated_img = draw_compliance_annotations(frame, evaluated_persons, detected_objects, comp_status)
                frame_annotated_b64 = encode_image_to_base64(annotated_img)
                last_annotated_b64 = frame_annotated_b64

                # 5. Persist Newly Confirmed Violation Incidents
                frame_new_violations = []
                for p in evaluated_persons:
                    track_id = p.get("track_id")
                    worker_id = p.get("worker_id", f"W-{track_id:03d}" if track_id else "Worker #1")
                    temporal_state = p.get("temporal_state", {})
                    p_zid = p.get("zone_id") if has_camera_polygons else camera_doc.get("zoneId")
                    p_zname = p.get("zone_name") if has_camera_polygons else camera_doc.get("zoneName", "Video Upload")

                    for cat in p.get("new_confirmed_violations", []):
                        st_dict = temporal_state.get(cat, {})
                        ep_id = st_dict.get("episode_id")
                        if ep_id and ep_id not in confirmed_video_episodes:
                            confirmed_video_episodes.add(ep_id)
                            vid_incident = {
                                "episode_id": ep_id,
                                "worker_id": worker_id,
                                "track_id": int(track_id) if track_id is not None else 1,
                                "personId": worker_id,
                                "workerTag": f"{worker_id} (Track #{track_id})" if track_id is not None else worker_id,
                                "session_id": str(video_session_id),
                                "zoneId": p_zid,
                                "zoneName": p_zname,
                                "cameraId": camera_id_str,
                                "cameraName": camera_name_str,
                                "sourceType": "video_file",
                                "timestamp": datetime.datetime.now(datetime.timezone.utc),
                                "detectedClasses": detected_objects,
                                "confidenceScores": [d.get("confidence", 0.0) for d in detected_objects],
                                "missingPPE": [cat],
                                "complianceStatus": "VIOLATION",
                                "personCount": len(evaluated_persons),
                                "reviewStatus": "PENDING",
                                "status": "OPEN",
                                "reviewerNotes": "",
                                "first_missing_timestamp": st_dict.get("first_missing_timestamp"),
                                "confirmed_timestamp": st_dict.get("confirmed_timestamp"),
                                "imageUrl": None,
                                "evidenceImageReference": frame_annotated_b64,
                                "processingMetadata": {
                                    "video_timestamp_sec": timestamp_sec,
                                    "accumulated_missing_sec": st_dict.get("accumulated_missing_sec", conf_dur),
                                    "model": "YOLOv8",
                                    "camera_id": camera_id_str,
                                    "has_camera_polygons": has_camera_polygons
                                },
                                "createdAt": datetime.datetime.now(datetime.timezone.utc)
                            }
                            persist_confirmed_incident(vid_incident)
                            persisted_incidents_list.append(vid_incident)
                            frame_new_violations.append({
                                "worker_id": worker_id,
                                "track_id": track_id,
                                "missing_ppe": cat,
                                "zone_id": p_zid,
                                "zone_name": p_zname,
                                "episode_id": ep_id
                            })

                # 6. Automatic Resolution of Video Episodes upon Continuous Compliance
                from ai_engine.temporal_compliance import get_session_temporal_tracker
                vid_tracker = get_session_temporal_tracker(video_session_id)
                resolved_in_frame = process_resolution_candidates(vid_tracker, video_session_id)
                frame_new_resolutions = []
                for r in resolved_in_frame:
                    r_epid = r.get("episode_id")
                    if r_epid:
                        resolved_video_episodes.add(r_epid)
                        frame_new_resolutions.append(r)

                if comp_status == "VIOLATION":
                    for m in missing_ppe:
                        overall_missing.add(m)

                for d in detected_objects:
                    if not any(od["name"] == d["name"] for od in overall_detected):
                        overall_detected.append(d)

                frame_results.append({
                    "frame_idx": total_frames_processed + 1,
                    "timestamp_sec": timestamp_sec,
                    "compliance_status": comp_status,
                    "missing_ppe": missing_ppe,
                    "persons_count": len(evaluated_persons),
                    "annotated_image": frame_annotated_b64,
                    "new_confirmed_violations": frame_new_violations,
                    "new_resolved_violations": frame_new_resolutions,
                    "persons": [
                        {
                            "worker_id": p.get("worker_id"),
                            "track_id": p.get("track_id"),
                            "zone_id": p.get("zone_id"),
                            "zone_name": p.get("zone_name"),
                            "compliant": p.get("compliant"),
                            "uncertain": p.get("uncertain"),
                            "uncertain_reason": p.get("uncertain_reason"),
                            "missing_ppe": p.get("missing_ppe", [])
                        }
                        for p in evaluated_persons
                    ]
                })
                total_frames_processed += 1

            frame_count += 1

        cap.release()
        if camera_id and camera_id_str != "uploaded_video":
            record_camera_video_completed(camera_id_str, "Uploaded video inspection completed normally")

        total_violations_found = len(confirmed_video_episodes)
        total_resolutions_found = len(resolved_video_episodes)
        overall_status = "VIOLATION" if total_violations_found > 0 else "COMPLIANT" if total_frames_processed > 0 else "UNCERTAIN"

        return jsonify({
            "overall_compliance_status": overall_status,
            "overall_missing_ppe": list(overall_missing),
            "overall_detected_classes": overall_detected,
            "total_frames_processed": total_frames_processed,
            "total_violations_found": total_violations_found,
            "total_resolutions_found": total_resolutions_found,
            "resolved_video_episodes": list(resolved_video_episodes),
            "persisted_incidents": persisted_incidents_list,
            "annotated_image": last_annotated_b64,
            "frame_breakdown": frame_results,
            "camera_profile": {
                "_id": camera_id_str,
                "name": camera_name_str,
                "has_camera_polygons": has_camera_polygons,
                "zones": camera_doc.get("zones", [])
            }
        }), 200

    finally:
        reset_session_tracker(video_session_id)
        reset_session_temporal(video_session_id)
        reset_session_spatial_zones(video_session_id)
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


@detection_bp.route("/api/extract-video-frame", methods=["POST"])
@token_required
@supervisor_required
@dev_fallback_allowed
def extract_video_frame():
    """
    Milestone M3.1: Extracts a representative reference frame from an uploaded video
    for polygon safety zone calibration in the visual editor.
    """
    if "file" not in request.files:
        return jsonify({"message": "Video file is required"}), 400

    video_file = request.files["file"]
    valid, err_msg, ext = validate_uploaded_video(video_file)
    if not valid:
        return jsonify({"message": err_msg}), 400

    target_sec = float(request.form.get("timestamp_sec", 1.0))

    temp_fd, temp_path = tempfile.mkstemp(prefix="ppe_frame_extract_", suffix=f".{ext}")
    os.close(temp_fd)
    video_file.save(temp_path)

    cap = None
    try:
        cap = cv2.VideoCapture(temp_path)
        if not cap.isOpened():
            return jsonify({"message": "Unsupported or corrupted video file"}), 400

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration_sec = round(total_frames / fps, 2) if total_frames > 0 and fps > 0 else 0.0

        target_frame_num = int(min(max(0, target_sec * fps), max(0, total_frames - 1)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_num)

        ret, frame = cap.read()
        if not ret or frame is None:
            # Fallback to frame 0
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()

        if not ret or frame is None:
            return jsonify({"message": "Could not read any frames from video"}), 400

        fh, fw = frame.shape[:2]
        frame_b64 = encode_image_to_base64(frame)

        return jsonify({
            "frame_image": f"data:image/jpeg;base64,{frame_b64}",
            "width": fw,
            "height": fh,
            "fps": round(float(fps), 2),
            "total_frames": total_frames,
            "duration_sec": duration_sec,
            "extracted_timestamp_sec": round(target_frame_num / fps, 3)
        }), 200

    finally:
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

@detection_bp.route("/api/tracker/reset", methods=["POST"])
@strict_token_required
def reset_tracker_endpoint():
    """Explicitly resets and frees an active tracking session."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id") or request.form.get("session_id")
    if not session_id:
        return jsonify({"message": "session_id is required"}), 400

    curr_user = getattr(request, "current_user", {})
    curr_user_id = str(curr_user.get("id", ""))
    curr_role = str(curr_user.get("role", "")).upper()

    owner_id = get_session_owner(session_id)
    if owner_id and owner_id != curr_user_id and curr_role not in ["SUPER_ADMIN", "ADMIN"]:
        return jsonify({"message": "Forbidden: Cannot reset another user's tracking session"}), 403

    reset_session_tracker(session_id)
    reset_session_temporal(session_id)
    from ai_engine.zone_assignment import reset_session_spatial_zones
    reset_session_spatial_zones(session_id)
    clear_session_owner(session_id)
    return jsonify({"message": f"Tracker session {session_id} reset successfully"}), 200


CANONICAL_LIFECYCLE_STATES = {"OPEN", "ACKNOWLEDGED", "RESOLVED"}


def get_canonical_state(doc: dict) -> str:
    """
    Returns the canonical lifecycle state: 'OPEN', 'ACKNOWLEDGED', or 'RESOLVED'.
    Handles both modern 'status' and legacy 'reviewStatus'.
    """
    if not isinstance(doc, dict):
        return "OPEN"
    status = str(doc.get("status") or "").strip().upper()
    if status in CANONICAL_LIFECYCLE_STATES:
        return status

    # Fallback to legacy reviewStatus
    review_status = str(doc.get("reviewStatus") or "").strip().upper()
    if review_status in ["RESOLVED", "APPROVED", "REJECTED", "FALSE_POSITIVE"]:
        return "RESOLVED"
    if review_status in ["REVIEWED", "ACKNOWLEDGED"]:
        return "ACKNOWLEDGED"

    return "OPEN"


def build_canonical_status_mongo_filter(canonical_status: str) -> dict:
    """
    M2.2B.5E.1: Builds a MongoDB query filter for canonical lifecycle states:
    'OPEN', 'ACKNOWLEDGED', 'RESOLVED'.
    Guarantees valid modern 'status' takes strict precedence over legacy 'reviewStatus'.
    """
    status_upper = str(canonical_status or "").strip().upper()
    if status_upper == "OPEN":
        return {
            "$or": [
                {"status": "OPEN"},
                {
                    "status": {"$nin": ["OPEN", "ACKNOWLEDGED", "RESOLVED"]},
                    "reviewStatus": {
                        "$nin": [
                            "RESOLVED", "APPROVED", "REJECTED", "FALSE_POSITIVE",
                            "REVIEWED", "ACKNOWLEDGED"
                        ]
                    }
                }
            ]
        }
    elif status_upper == "ACKNOWLEDGED":
        return {
            "$or": [
                {"status": "ACKNOWLEDGED"},
                {
                    "status": {"$nin": ["OPEN", "ACKNOWLEDGED", "RESOLVED"]},
                    "reviewStatus": {"$in": ["REVIEWED", "ACKNOWLEDGED"]}
                }
            ]
        }
    elif status_upper == "RESOLVED":
        return {
            "$or": [
                {"status": "RESOLVED"},
                {
                    "status": {"$nin": ["OPEN", "ACKNOWLEDGED", "RESOLVED"]},
                    "reviewStatus": {"$in": ["RESOLVED", "APPROVED", "REJECTED", "FALSE_POSITIVE"]}
                }
            ]
        }
    else:
        # Invalid canonical status safely matches nothing
        return {"_id": {"$exists": False}}


@detection_bp.route("/api/detections", methods=["GET"])
def get_detections():
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 10))
    skip = (page - 1) * limit

    compliance_status = request.args.get("complianceStatus")
    status_param = request.args.get("status")
    review_status = request.args.get("reviewStatus")
    search = request.args.get("search", "").strip().lower()

    canonical_status_upper = (
        str(status_param).strip().upper()
        if status_param is not None and str(status_param).strip()
        else None
    )

    if is_mongo_connected:
        col = get_detections_col()
        and_conditions = []
        if compliance_status:
            and_conditions.append({"complianceStatus": compliance_status})

        if canonical_status_upper is not None:
            and_conditions.append(build_canonical_status_mongo_filter(canonical_status_upper))
        elif review_status:
            and_conditions.append({"reviewStatus": review_status})

        if search:
            and_conditions.append({
                "$or": [
                    {"zoneName": {"$regex": search, "$options": "i"}},
                    {"missingPPE": {"$in": [search]}}
                ]
            })

        if len(and_conditions) == 1:
            query = and_conditions[0]
        elif len(and_conditions) > 1:
            query = {"$and": and_conditions}
        else:
            query = {}

        try:
            total_count = col.count_documents(query)
            cursor = col.find(query).sort("createdAt", -1).skip(skip).limit(limit)
            events = []
            for doc in cursor:
                doc["_id"] = str(doc["_id"])
                events.append(doc)

            return jsonify({
                "events": events,
                "page": page,
                "totalPages": max(1, (total_count + limit - 1) // limit),
                "totalCount": total_count
            }), 200
        except Exception as e:
            pass

    # In-memory fallback
    filtered = list(mem_detections)
    if compliance_status:
        filtered = [e for e in filtered if e.get("complianceStatus") == compliance_status]

    if canonical_status_upper is not None:
        if canonical_status_upper in CANONICAL_LIFECYCLE_STATES:
            filtered = [e for e in filtered if get_canonical_state(e) == canonical_status_upper]
        else:
            filtered = []
    elif review_status:
        filtered = [e for e in filtered if e.get("reviewStatus") == review_status]

    if search:
        filtered = [e for e in filtered if search in e.get("zoneName", "").lower() or any(search in m.lower() for m in e.get("missingPPE", []))]

    total_count = len(filtered)
    events = filtered[skip:skip + limit]

    return jsonify({
        "events": events,
        "page": page,
        "totalPages": max(1, (total_count + limit - 1) // limit),
        "totalCount": total_count
    }), 200

@detection_bp.route("/api/detections", methods=["POST"])
@token_required
@supervisor_required
@dev_fallback_allowed
def create_detection():
    data = request.get_json() or {}
    compliance_status = data.get("complianceStatus")
    if not compliance_status:
        return jsonify({"message": "complianceStatus is required"}), 400

    zone_id = data.get("zoneId")
    zone_name = data.get("zoneName", "General Monitored Zone")
    missing_ppe = data.get("missingPPE", [])

    # Upload evidence snapshot to Cloudinary cloud storage
    raw_evidence = data.get("evidenceImageBase64")
    image_url = None
    if raw_evidence:
        try:
            image_url = upload_evidence_image(raw_evidence, folder="ppe_violations")
        except Exception as e:
            print("Evidence upload warning:", e)
            image_url = raw_evidence

    event_doc = {
        "zoneId": zone_id,
        "zoneName": zone_name,
        "cameraId": data.get("cameraId", "cam_01"),
        "cameraName": data.get("cameraName", "Primary Camera Feed"),
        "sourceType": data.get("sourceType", "webcam"),
        "timestamp": datetime.datetime.now(datetime.timezone.utc),
        "detectedClasses": data.get("detectedClasses", []),
        "confidenceScores": data.get("confidenceScores", []),
        "missingPPE": missing_ppe,
        "complianceStatus": compliance_status,
        "personCount": int(data.get("personCount", 1)),
        "reviewStatus": "PENDING",
        "reviewerNotes": "",
        "imageUrl": image_url,
        "evidenceImageReference": image_url or raw_evidence,
        "processingMetadata": data.get("processingMetadata", {}),
        "createdAt": datetime.datetime.now(datetime.timezone.utc)
    }

    # Automatically trigger supervisor alert record if violation
    supervisor_alert = None
    if compliance_status == "VIOLATION" and zone_id:
        zone = None
        if is_mongo_connected:
            try:
                from bson import ObjectId
                col = get_zones_col()
                zone = col.find_one({"_id": ObjectId(zone_id)})
            except Exception:
                pass
        if not zone:
            zone = next((z for z in mem_zones if str(z.get("_id")) == str(zone_id)), None)

        if zone and zone.get("supervisor"):
            sup = zone["supervisor"]
            supervisor_alert = {
                "_id": "notif_" + str(int(time.time() * 1000)),
                "zoneId": str(zone_id),
                "zoneName": zone.get("name", zone_name),
                "supervisorName": sup.get("name", "Shift Supervisor"),
                "supervisorPhone": sup.get("phone", "+91 98000 00000"),
                "supervisorEmail": sup.get("email", "supervisor@ppe.com"),
                "alertChannel": sup.get("alertChannel", "SMS & WhatsApp"),
                "missingPPE": missing_ppe,
                "message": f"Violation detected in {zone.get('name', zone_name)}. Missing PPE: {', '.join(missing_ppe) if missing_ppe else 'Mandatory Gear'}",
                "deliveryStatus": "DELIVERED",
                "buzzerTriggered": zone.get("buzzerEnabled", True),
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "created_at": datetime.datetime.now(datetime.timezone.utc)
            }
            if is_mongo_connected:
                try:
                    ncol = get_notifications_col()
                    if ncol is not None:
                        ncol.insert_one(dict(supervisor_alert))
                except Exception:
                    pass
            mem_notifications.insert(0, supervisor_alert)

    if is_mongo_connected:
        try:
            col = get_detections_col()
            res = col.insert_one(event_doc)
            event_doc["_id"] = str(res.inserted_id)
            if compliance_status == "VIOLATION":
                dispatch_violation_alert(event_doc, supervisor_alert)
            return jsonify({
                "message": "Event recorded", 
                "event": event_doc,
                "supervisorAlert": supervisor_alert
            }), 201
        except Exception as e:
            pass

    event_doc["_id"] = "det_" + str(int(time.time() * 1000))
    mem_detections.insert(0, event_doc)
    if compliance_status == "VIOLATION":
        dispatch_violation_alert(event_doc, supervisor_alert)
    return jsonify({
        "message": "Event recorded", 
        "event": event_doc,
        "supervisorAlert": supervisor_alert
    }), 201

ALLOWED_LIFECYCLE_ROLES = {
    "SUPER_ADMIN", "ADMIN", "ZONE_SUPERVISOR", "SUPERVISOR",
    "super_admin", "admin", "zone_supervisor", "supervisor"
}


def _parse_lifecycle_request(data: dict) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    M2.2B.5D: Parses and validates requested lifecycle action.
    Returns: (target_state, resolution_type, reason, error_message)
    target_state: "ACKNOWLEDGED" | "RESOLVED"
    resolution_type: "MANUAL" | "FALSE_POSITIVE" | None
    """
    if not isinstance(data, dict):
        return None, None, None, "Request body must be a JSON object"

    # Extract reason/notes from various candidate fields
    raw_reason = data.get("reason")
    if raw_reason is None:
        raw_reason = data.get("reviewerNotes")
    if raw_reason is None:
        raw_reason = data.get("reviewNotes")
    if raw_reason is None:
        raw_reason = data.get("notes")
    reason = str(raw_reason).strip() if raw_reason is not None else ""

    action = str(data.get("action") or "").strip().upper()
    target_state = str(data.get("status") or data.get("state") or "").strip().upper()
    review_status = str(data.get("reviewStatus") or "").strip().upper()
    res_type_override = str(data.get("resolution_type") or data.get("resolutionType") or "").strip().upper()

    # 1. False-Positive resolution
    if (
        action in ["FALSE_POSITIVE", "DISMISS_FALSE_POSITIVE", "REJECT", "REJECTED"]
        or res_type_override == "FALSE_POSITIVE"
        or review_status in ["FALSE_POSITIVE", "REJECTED"]
    ):
        if not reason:
            return None, None, None, "Resolution reason is required and cannot be empty"
        return "RESOLVED", "FALSE_POSITIVE", reason, None

    # 2. Normal manual resolution
    if (
        action in ["RESOLVE", "RESOLVED"]
        or target_state == "RESOLVED"
        or review_status in ["RESOLVED", "APPROVED"]
    ):
        if not reason:
            return None, None, None, "Resolution reason is required and cannot be empty"
        res_type = "FALSE_POSITIVE" if res_type_override == "FALSE_POSITIVE" else "MANUAL"
        return "RESOLVED", res_type, reason, None

    # 3. Acknowledgement
    if (
        action in ["ACKNOWLEDGE", "ACKNOWLEDGED"]
        or target_state == "ACKNOWLEDGED"
        or review_status in ["REVIEWED", "ACKNOWLEDGED"]
    ):
        return "ACKNOWLEDGED", None, reason if reason else None, None

    return None, None, None, "Invalid or unrecognized lifecycle action. Supported actions: ACKNOWLEDGE, RESOLVE, FALSE_POSITIVE (or target states: ACKNOWLEDGED, RESOLVED)"


def _build_incident_lookup_filter(incident_id: str) -> dict:
    """Builds MongoDB query filter accepting ObjectId, custom string ID, or episode_id."""
    from bson import ObjectId
    s_id = str(incident_id).strip()
    if ObjectId.is_valid(s_id):
        return {"$or": [{"_id": ObjectId(s_id)}, {"_id": s_id}, {"episode_id": s_id}]}
    return {"$or": [{"_id": s_id}, {"episode_id": s_id}]}


def _broadcast_lifecycle_event(action_name: str, doc: dict):
    try:
        from routes.event_routes import broadcast_event
        if action_name in ["RESOLVE", "RESOLVE_FALSE_POSITIVE"]:
            broadcast_event("INCIDENT_RESOLVED", {"event": doc})
        elif action_name == "ACKNOWLEDGE":
            broadcast_event("INCIDENT_ACKNOWLEDGED", {"event": doc})
    except Exception:
        pass


def transition_incident_lifecycle(incident_id: str, data: dict, current_user: dict) -> tuple[Optional[dict], int, str]:
    """
    M2.2B.5D: Manually transitions an incident lifecycle with strict RBAC, validation,
    atomic concurrency handling, and audit history logging.
    Returns: (updated_doc, http_status_code, message)
    """
    if not incident_id or not str(incident_id).strip():
        return None, 400, "Incident ID is required"

    actor_role = current_user.get("role")
    if not actor_role or actor_role not in ALLOWED_LIFECYCLE_ROLES:
        return None, 403, "Administrator or Supervisor role required to perform lifecycle actions"

    actor_id = str(current_user.get("id") or current_user.get("email") or "unknown_user")

    target_state, resolution_type, reason, err_msg = _parse_lifecycle_request(data)
    if err_msg:
        return None, 400, err_msg

    if target_state == "ACKNOWLEDGED":
        action_name = "ACKNOWLEDGE"
    elif resolution_type == "FALSE_POSITIVE":
        action_name = "RESOLVE_FALSE_POSITIVE"
    else:
        action_name = "RESOLVE"

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    set_fields = {
        "status": target_state,
        "updatedAt": now_utc
    }

    if target_state == "ACKNOWLEDGED":
        set_fields["reviewStatus"] = "REVIEWED"
        set_fields["acknowledged_at"] = now_utc
        set_fields["acknowledgedAt"] = now_utc
        set_fields["acknowledged_by"] = actor_id
        set_fields["acknowledged_by_role"] = actor_role
        if reason:
            set_fields["reviewerNotes"] = reason
            set_fields["acknowledgement_notes"] = reason
    elif target_state == "RESOLVED":
        set_fields["reviewStatus"] = "FALSE_POSITIVE" if resolution_type == "FALSE_POSITIVE" else "RESOLVED"
        set_fields["resolution_type"] = resolution_type
        set_fields["resolutionType"] = resolution_type
        set_fields["resolved_at"] = now_utc
        set_fields["resolvedAt"] = now_utc
        set_fields["resolved_by"] = actor_id
        set_fields["resolved_by_role"] = actor_role
        set_fields["resolution_reason"] = reason
        set_fields["resolutionReason"] = reason
        set_fields["reviewerNotes"] = reason

    history_entry = {
        "previous_state": None,
        "new_state": target_state,
        "state": target_state,
        "action": action_name,
        "actor_id": str(actor_id),
        "actor_role": str(actor_role),
        "actor": f"{actor_role}:{actor_id}",
        "timestamp": now_utc,
        "reason": reason if reason else None,
        "resolution_type": resolution_type
    }

    if is_mongo_connected:
        try:
            col = get_detections_col()
            if col is not None:
                lookup_query = _build_incident_lookup_filter(incident_id)
                existing = col.find_one(lookup_query)
                if not existing:
                    return None, 404, "Incident not found"

                prev_state = get_canonical_state(existing)

                if target_state == "ACKNOWLEDGED":
                    if prev_state == "ACKNOWLEDGED":
                        existing["_id"] = str(existing.get("_id"))
                        return existing, 200, "Incident already acknowledged"
                    if prev_state == "RESOLVED":
                        return None, 409, "Cannot acknowledge an already resolved incident"
                    if prev_state != "OPEN":
                        return None, 400, f"Cannot acknowledge incident from state {prev_state}"
                    atomic_filter = {
                        **lookup_query,
                        "status": {"$in": ["OPEN", None]},
                        "reviewStatus": {"$nin": ["RESOLVED", "APPROVED", "REJECTED", "FALSE_POSITIVE", "REVIEWED", "ACKNOWLEDGED"]}
                    }

                elif target_state == "RESOLVED":
                    if prev_state == "RESOLVED":
                        return None, 409, "Incident is already resolved"
                    atomic_filter = {
                        **lookup_query,
                        "status": {"$nin": ["RESOLVED"]},
                        "reviewStatus": {"$nin": ["RESOLVED", "APPROVED", "REJECTED", "FALSE_POSITIVE"]}
                    }

                history_entry["previous_state"] = prev_state
                update_op = {
                    "$set": set_fields,
                    "$push": {"lifecycle_history": history_entry}
                }

                res = col.update_one(atomic_filter, update_op)
                if res.modified_count > 0:
                    updated = col.find_one(lookup_query)
                    if updated:
                        updated["_id"] = str(updated.get("_id"))
                        _broadcast_lifecycle_event(action_name, updated)
                        return updated, 200, f"Incident {target_state.lower()} successfully"
                else:
                    latest = col.find_one(lookup_query)
                    if latest:
                        latest["_id"] = str(latest.get("_id"))
                        latest_state = get_canonical_state(latest)
                        if target_state == "ACKNOWLEDGED" and latest_state == "ACKNOWLEDGED":
                            return latest, 200, "Incident already acknowledged"
                        if latest_state == "RESOLVED":
                            return None, 409, "Incident is already resolved"
                    return None, 409, "Concurrent conflicting update detected; please retry"

        except Exception as e:
            print(f"MongoDB incident lifecycle transition notice: {e}")
            return None, 500, f"Database error: {str(e)}"

    # In-memory fallback
    with _mem_incident_lock:
        s_id = str(incident_id).strip()
        existing = next(
            (e for e in mem_detections if str(e.get("_id")) == s_id or str(e.get("episode_id")) == s_id),
            None
        )
        if not existing:
            return None, 404, "Incident not found"

        prev_state = get_canonical_state(existing)

        if target_state == "ACKNOWLEDGED":
            if prev_state == "ACKNOWLEDGED":
                return existing, 200, "Incident already acknowledged"
            if prev_state == "RESOLVED":
                return None, 409, "Cannot acknowledge an already resolved incident"
            if prev_state != "OPEN":
                return None, 400, f"Cannot acknowledge incident from state {prev_state}"

        elif target_state == "RESOLVED":
            if prev_state == "RESOLVED":
                return None, 409, "Incident is already resolved"

        history_entry["previous_state"] = prev_state
        for k, v in set_fields.items():
            existing[k] = v
        existing.setdefault("lifecycle_history", []).append(history_entry)

        _broadcast_lifecycle_event(action_name, existing)
        return existing, 200, f"Incident {target_state.lower()} successfully"


@detection_bp.route("/api/detections/<id>/review", methods=["PATCH", "POST"])
@detection_bp.route("/api/detections/<id>/lifecycle", methods=["PATCH", "POST"])
@detection_bp.route("/api/incidents/<id>/review", methods=["PATCH", "POST"])
@detection_bp.route("/api/incidents/<id>/lifecycle", methods=["PATCH", "POST"])
@token_required
def update_review(id):
    data = request.get_json() or {}
    current_user = getattr(request, "current_user", {})

    updated_doc, status_code, message = transition_incident_lifecycle(id, data, current_user)
    if updated_doc is not None:
        return jsonify({
            "message": message,
            "status": updated_doc.get("status"),
            "reviewStatus": updated_doc.get("reviewStatus"),
            "event": updated_doc
        }), status_code

    return jsonify({"message": message}), status_code
