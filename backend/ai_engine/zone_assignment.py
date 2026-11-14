import time
import math
import threading
from typing import List, Dict, Any, Tuple, Optional
from config import Config

def compute_worker_bottom_center_anchor(bbox: List[Any], img_shape: Tuple[int, int]) -> Tuple[float, float]:
    """
    Computes normalized (x, y) coordinates for a worker's bottom-center anchor.
    Formula:
      anchor_x = (x1 + x2) / 2.0
      anchor_y = y1 + 0.95 * (y2 - y1)
    Normalized:
      norm_x = anchor_x / frame_width
      norm_y = anchor_y / frame_height
    Clamped strictly to [0.0, 1.0].
    """
    if not bbox or len(bbox) < 4:
        return 0.5, 0.5

    x1, y1, x2, y2 = [float(c) for c in bbox[:4]]
    h = max(1, int(img_shape[0]))
    w = max(1, int(img_shape[1]))

    anchor_x = (x1 + x2) / 2.0
    anchor_y = y1 + 0.95 * (y2 - y1)

    norm_x = max(0.0, min(1.0, anchor_x / float(w)))
    norm_y = max(0.0, min(1.0, anchor_y / float(h)))

    return norm_x, norm_y

def is_point_on_segment(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
    eps: float = 1e-5
) -> bool:
    """
    Checks if point (px, py) lies within epsilon distance of segment (ax, ay) -> (bx, by).
    """
    abx = bx - ax
    aby = by - ay
    l2 = abx * abx + aby * aby

    if l2 < 1e-12:
        dx = px - ax
        dy = py - ay
        return (dx * dx + dy * dy) <= (eps * eps)

    # Projection factor t
    apx = px - ax
    apy = py - ay
    t = (apx * abx + apy * aby) / l2
    t_clamped = max(0.0, min(1.0, t))

    closest_x = ax + t_clamped * abx
    closest_y = ay + t_clamped * aby

    dx = px - closest_x
    dy = py - closest_y
    return (dx * dx + dy * dy) <= (eps * eps)

def is_point_on_polygon_boundary(
    px: float,
    py: float,
    vertices: List[Tuple[float, float]],
    eps: float = 1e-5
) -> bool:
    """
    Checks if point (px, py) lies within epsilon distance of any polygon edge.
    """
    n = len(vertices)
    if n < 2:
        return False

    for i in range(n):
        ax, ay = vertices[i]
        bx, by = vertices[(i + 1) % n]
        if is_point_on_segment(px, py, ax, ay, bx, by, eps=eps):
            return True

    return False

def is_point_in_polygon_ray_casting(
    px: float,
    py: float,
    vertices: List[Tuple[float, float]]
) -> bool:
    """
    Ray-casting algorithm (crossing number test) for point-in-polygon.
    Returns True if (px, py) is strictly inside the polygon.
    """
    inside = False
    n = len(vertices)
    if n < 3:
        return False

    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]

        # Check if horizontal ray at y = py crosses edge (x1, y1) -> (x2, y2)
        if (y1 > py) != (y2 > py):
            x_int = (x2 - x1) * (py - y1) / (y2 - y1) + x1
            if px < x_int:
                inside = not inside

    return inside

def evaluate_single_frame_zone(
    norm_x: float,
    norm_y: float,
    camera_zones: List[Dict[str, Any]],
    boundary_eps: float = 1e-5
) -> Tuple[str, Optional[str], Optional[str], str]:
    """
    Evaluates a single normalized point against a camera's configured zone polygons.

    Returns:
      (status, zone_id, zone_name, explanation)
      where status is 'ASSIGNED', 'UNASSIGNED', or 'UNCERTAIN'
    """
    if not camera_zones:
        return "UNASSIGNED", None, None, "No camera zones configured"

    matched_zones = []
    hit_boundary = False

    for idx, z in enumerate(camera_zones):
        poly_raw = z.get("polygon")
        if not poly_raw or not isinstance(poly_raw, list) or len(poly_raw) < 3:
            # Invalid polygon configuration: log and treat as invalid
            return "UNCERTAIN", None, None, f"Camera zone at index {idx} has invalid polygon configuration"

        vertices = []
        for v in poly_raw:
            if isinstance(v, dict):
                vertices.append((float(v["x"]), float(v["y"])))
            elif isinstance(v, (list, tuple)) and len(v) >= 2:
                vertices.append((float(v[0]), float(v[1])))

        if len(vertices) < 3:
            return "UNCERTAIN", None, None, f"Camera zone at index {idx} has fewer than 3 valid vertices"

        # 1. Boundary check
        if is_point_on_polygon_boundary(norm_x, norm_y, vertices, eps=boundary_eps):
            hit_boundary = True

        # 2. Interior check
        elif is_point_in_polygon_ray_casting(norm_x, norm_y, vertices):
            matched_zones.append(z)

    # Rule: Boundary hit returns UNCERTAIN
    if hit_boundary:
        return "UNCERTAIN", None, None, "Worker anchor lies on polygon boundary"

    # Rule: No matching polygon returns UNASSIGNED
    if not matched_zones:
        return "UNASSIGNED", None, None, "Outside all configured zone polygons"

    # Rule: Multiple matching polygons resolved by priority (higher integer = higher precedence)
    matched_zones.sort(key=lambda item: int(item.get("priority", 1)), reverse=True)
    top_priority = int(matched_zones[0].get("priority", 1))

    # Check for equal top priority tie
    top_matches = [m for m in matched_zones if int(m.get("priority", 1)) == top_priority]
    if len(top_matches) > 1:
        tied_names = ", ".join(m.get("zoneName", m.get("zoneId", "Unknown")) for m in top_matches)
        return "UNCERTAIN", None, None, f"Overlapping zones with equal priority ({top_priority}): {tied_names}"

    # Exactly one highest priority winner
    winner = top_matches[0]
    zid = str(winner.get("zoneId"))
    zname = winner.get("zoneName", "Monitored Zone")
    return "ASSIGNED", zid, zname, f"Assigned to {zname} (priority {top_priority})"

class TrackSpatialState:
    """
    Maintains spatial assignment and debounced transition state for a single track.
    Requires 3 consecutive observations of a new candidate zone before committing a transition.
    """
    def __init__(self, track_id: int):
        self.track_id = int(track_id)
        self.committed_zone_id: Optional[str] = None
        self.committed_zone_name: Optional[str] = None
        self.committed_status: str = "UNASSIGNED"

        self.pending_candidate_id: Optional[str] = None
        self.pending_candidate_name: Optional[str] = None
        self.pending_candidate_status: str = "UNASSIGNED"
        self.consecutive_observations: int = 0
        self.last_seen_timestamp: float = time.monotonic()

    def update(
        self,
        candidate_status: str,
        candidate_zone_id: Optional[str],
        candidate_zone_name: Optional[str],
        debounce_frames: int = 3,
        timestamp: Optional[float] = None
    ) -> Tuple[str, Optional[str], Optional[str], str]:
        """
        Updates tracking state with a single-frame candidate evaluation.
        Returns:
          (reported_status, reported_zone_id, reported_zone_name, confidence_explanation)
        """
        now = timestamp if timestamp is not None else time.monotonic()
        self.last_seen_timestamp = now
        threshold = max(1, int(debounce_frames))

        # 1. Ambiguous / Uncertain candidate: expose uncertainty directly
        if candidate_status == "UNCERTAIN":
            return (
                "UNCERTAIN",
                self.committed_zone_id,
                self.committed_zone_name,
                "Spatial position is ambiguous (boundary or overlapping equal-priority zones)"
            )

        # 2. Candidate matches current committed state: stable observation
        if candidate_zone_id == self.committed_zone_id and candidate_status == self.committed_status:
            self.pending_candidate_id = None
            self.pending_candidate_name = None
            self.pending_candidate_status = "UNASSIGNED"
            self.consecutive_observations = 0
            explanation = (
                f"Confidently assigned to {self.committed_zone_name}"
                if self.committed_status == "ASSIGNED"
                else "Unassigned (outside all zones)"
            )
            return self.committed_status, self.committed_zone_id, self.committed_zone_name, explanation

        # 3. Candidate is different from current committed state
        if candidate_zone_id == self.pending_candidate_id and candidate_status == self.pending_candidate_status:
            self.consecutive_observations += 1
        else:
            # Candidate changed: reset observation accumulator
            self.pending_candidate_id = candidate_zone_id
            self.pending_candidate_name = candidate_zone_name
            self.pending_candidate_status = candidate_status
            self.consecutive_observations = 1

        # Check if transition threshold is reached
        if self.consecutive_observations >= threshold:
            # Commit the transition!
            self.committed_zone_id = candidate_zone_id
            self.committed_zone_name = candidate_zone_name
            self.committed_status = candidate_status

            self.pending_candidate_id = None
            self.pending_candidate_name = None
            self.pending_candidate_status = "UNASSIGNED"
            self.consecutive_observations = 0

            explanation = (
                f"Committed transition to {self.committed_zone_name} ({threshold}/{threshold} observations)"
                if self.committed_status == "ASSIGNED"
                else f"Committed transition to unassigned ({threshold}/{threshold} observations)"
            )
            return self.committed_status, self.committed_zone_id, self.committed_zone_name, explanation

        # Transition pending: preserve current committed zone while candidate accumulates
        target_name = candidate_zone_name or "unassigned"
        current_name = self.committed_zone_name or "unassigned"
        explanation = (
            f"Preserving {current_name}, pending transition to {target_name} "
            f"({self.consecutive_observations}/{threshold} observations)"
        )
        return self.committed_status, self.committed_zone_id, self.committed_zone_name, explanation

class SessionSpatialZoneResolver:
    """
    Session-scoped, thread-safe spatial zone resolver maintaining track-level stabilization.
    """
    def __init__(self, session_id: str, debounce_frames: int = 3):
        self.session_id = str(session_id)
        self.debounce_frames = max(1, int(debounce_frames))
        self._tracks: Dict[int, TrackSpatialState] = {}
        self._lock = threading.RLock()
        self.last_accessed = time.monotonic()

    def resolve_track(
        self,
        track_id: int,
        candidate_status: str,
        candidate_zone_id: Optional[str],
        candidate_zone_name: Optional[str],
        timestamp: Optional[float] = None
    ) -> Tuple[str, Optional[str], Optional[str], str]:
        with self._lock:
            self.last_accessed = time.monotonic()
            tid = int(track_id)
            if tid not in self._tracks:
                self._tracks[tid] = TrackSpatialState(tid)
            state = self._tracks[tid]
            return state.update(
                candidate_status,
                candidate_zone_id,
                candidate_zone_name,
                debounce_frames=self.debounce_frames,
                timestamp=timestamp
            )

    def reset(self):
        with self._lock:
            self._tracks.clear()
            self.last_accessed = time.monotonic()

    def track_count(self) -> int:
        with self._lock:
            return len(self._tracks)

# Global Session Registry for Spatial Resolvers
_session_spatial_resolvers: Dict[str, SessionSpatialZoneResolver] = {}
_session_lock = threading.RLock()

def get_session_spatial_resolver(
    session_id: str,
    debounce_frames: Optional[int] = None
) -> SessionSpatialZoneResolver:
    """
    Retrieves or creates a thread-safe SessionSpatialZoneResolver for the given session_id.
    """
    with _session_lock:
        sid = str(session_id or "default_spatial_session").strip()
        threshold = (
            debounce_frames
            if debounce_frames is not None
            else getattr(Config, "ZONE_ASSIGNMENT_DEBOUNCE_FRAMES", 3)
        )
        if sid not in _session_spatial_resolvers:
            _session_spatial_resolvers[sid] = SessionSpatialZoneResolver(sid, debounce_frames=threshold)
        return _session_spatial_resolvers[sid]

def reset_session_spatial_zones(session_id: str) -> None:
    """Clears spatial tracking state for a specific monitoring session."""
    with _session_lock:
        sid = str(session_id).strip()
        if sid in _session_spatial_resolvers:
            _session_spatial_resolvers[sid].reset()

def purge_expired_spatial_sessions(max_age_sec: float = 300.0) -> int:
    """
    Removes spatial resolvers inactive for longer than max_age_sec.
    Returns the count of purged sessions.
    """
    with _session_lock:
        now = time.monotonic()
        to_purge = [
            sid for sid, res in _session_spatial_resolvers.items()
            if (now - res.last_accessed) > max_age_sec
        ]
        for sid in to_purge:
            del _session_spatial_resolvers[sid]
        return len(to_purge)

def assign_persons_spatial_zones(
    persons: List[Dict[str, Any]],
    camera_doc: Optional[Dict[str, Any]],
    img_shape: Tuple[int, int],
    session_id: Optional[str] = None,
    timestamp: Optional[float] = None,
    debounce_frames: Optional[int] = None,
    boundary_eps: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Assigns camera-specific spatial zones to tracked persons.

    1. Computes bottom-center anchor: (anchor_x, anchor_y).
    2. Evaluates point-in-polygon against camera's configured polygons.
    3. If polygons configured and session active: applies temporal debounce stabilization.
    4. If camera has no polygons configured: falls back to camera-level default zone.
    5. Returns enriched persons list with:
       - zone_id
       - zone_name
       - zone_assignment_status ('ASSIGNED' | 'UNASSIGNED' | 'UNCERTAIN')
       - zone_assignment_confidence (explanation string)
       - zone_anchor: {'x': norm_x, 'y': norm_y}
    """
    if not persons:
        return []

    eps = boundary_eps if boundary_eps is not None else getattr(Config, "ZONE_BOUNDARY_EPSILON", 1e-5)
    threshold = (
        debounce_frames
        if debounce_frames is not None
        else getattr(Config, "ZONE_ASSIGNMENT_DEBOUNCE_FRAMES", 3)
    )

    cam = camera_doc or {}
    configured_zones = cam.get("zones", [])

    # Legacy fallback when camera has no polygons configured
    has_polygons = bool(configured_zones and isinstance(configured_zones, list) and len(configured_zones) > 0)
    default_camera_zone_id = str(cam.get("zoneId")) if cam.get("zoneId") else None
    default_camera_zone_name = cam.get("zoneName", "General Facility Zone") if default_camera_zone_id else None

    resolver = get_session_spatial_resolver(session_id, debounce_frames=threshold) if session_id else None

    for person in persons:
        bbox = person.get("bbox")
        norm_x, norm_y = compute_worker_bottom_center_anchor(bbox, img_shape)
        person["zone_anchor"] = {"x": round(norm_x, 6), "y": round(norm_y, 6)}

        if not has_polygons:
            # Legacy camera behavior: camera-level default zone
            person["zone_id"] = default_camera_zone_id
            person["zone_name"] = default_camera_zone_name
            person["zone_assignment_status"] = "ASSIGNED" if default_camera_zone_id else "UNASSIGNED"
            person["zone_assignment_confidence"] = "Camera-level default zone (no polygons configured)"
            continue

        # Evaluate single-frame candidate against configured polygons
        cand_status, cand_zid, cand_zname, explanation = evaluate_single_frame_zone(
            norm_x, norm_y, configured_zones, boundary_eps=eps
        )

        track_id = person.get("track_id")
        if resolver is not None and track_id is not None:
            # Apply 3-observation temporal stabilization
            rep_status, rep_zid, rep_zname, conf_text = resolver.resolve_track(
                track_id, cand_status, cand_zid, cand_zname, timestamp=timestamp
            )
            person["zone_id"] = rep_zid
            person["zone_name"] = rep_zname
            person["zone_assignment_status"] = rep_status
            person["zone_assignment_confidence"] = conf_text
        else:
            # Non-tracked or stateless single-frame evaluation
            person["zone_id"] = cand_zid
            person["zone_name"] = cand_zname
            person["zone_assignment_status"] = cand_status
            person["zone_assignment_confidence"] = explanation

    return persons


def lookup_zone(zone_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Looks up a zone document from MongoDB or mem_zones fallback.
    Matches by _id (string or ObjectId) or by zone code (case-insensitive).
    """
    if not zone_id:
        return None
    zid = str(zone_id).strip()
    if not zid:
        return None

    try:
        from database import is_mongo_connected, get_zones_col, mem_zones
    except ImportError:
        return None

    if is_mongo_connected:
        try:
            col = get_zones_col()
            if col is not None:
                d = col.find_one({"_id": zid})
                if not d:
                    try:
                        from bson import ObjectId
                        if ObjectId.is_valid(zid):
                            d = col.find_one({"_id": ObjectId(zid)})
                    except Exception:
                        pass
                if not d:
                    d = col.find_one({"code": zid})
                if not d:
                    import re
                    d = col.find_one({"code": re.compile(f"^{re.escape(zid)}$", re.IGNORECASE)})
                if d:
                    d["_id"] = str(d["_id"])
                    return d
        except Exception:
            pass

    found = next(
        (z for z in mem_zones if str(z.get("_id")) == zid or str(z.get("code", "")).strip().lower() == zid.lower()),
        None
    )
    if found:
        return dict(found)
    return None


def get_authoritative_zone_ppe(zone_id: Optional[str]) -> Optional[List[str]]:
    """
    Retrieves and validates authoritative required PPE categories for a zone.
    Supported canonical categories: 'helmet', 'vest', 'boots', 'goggles'.
    Normalizes aliases (e.g. 'safety_shoe' -> 'boots', 'hard hat' -> 'helmet').
    Returns sorted list of canonical categories, or None if zone is not found or policy is invalid.
    """
    zone_doc = lookup_zone(zone_id)
    if not zone_doc:
        return None

    raw_ppe = zone_doc.get("requiredPPE")
    if raw_ppe is None or not isinstance(raw_ppe, (list, tuple)):
        return None

    from ai_engine.compliance import normalize_ppe_class, sort_canonical_ppe, CANONICAL_PPE_REGION_MAP
    canonical_set = set(CANONICAL_PPE_REGION_MAP.keys())  # {'helmet', 'vest', 'goggles', 'boots'}

    normalized = []
    for item in raw_ppe:
        c = normalize_ppe_class(item)
        if c in canonical_set and c not in normalized:
            normalized.append(c)

    return sort_canonical_ppe(normalized)


def lookup_camera(camera_id: Optional[str] = None, zone_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Looks up a camera document from MongoDB or mem_cameras fallback.
    - If camera_id is provided:
        * Checks MongoDB and mem_cameras for exact camera_id match.
        * Special-case "uploaded_video": returns unzoned video file camera config.
        * If camera_id is unknown/invalid, returns an unconfigured camera config with zones: []
          (NEVER silently selects cam_01 or inherits cam_01's polygons!).
    - If camera_id is missing and zone_id is provided:
        * Matches camera by zoneId in MongoDB or mem_cameras.
        * If not found, returns unconfigured camera for that zone with zones: [].
    - If both camera_id and zone_id are missing/None:
        * Returns default live camera config with zones: [] (no polygons inherited!).
    """
    try:
        from database import is_mongo_connected, get_cameras_col, mem_cameras
    except ImportError:
        return {
            "_id": "webcam_main",
            "name": "Primary Live Camera",
            "zoneId": "zone_01",
            "zoneName": "Heavy Assembly Bay 01",
            "sourceType": "webcam",
            "zones": []
        }

    # 1. By camera_id
    if camera_id is not None and str(camera_id).strip():
        cid = str(camera_id).strip()
        if cid == "uploaded_video":
            return {
                "_id": "uploaded_video",
                "name": "Uploaded Video Inspection",
                "zoneId": None,
                "zoneName": "Video Upload",
                "sourceType": "video_file",
                "zones": []
            }

        if is_mongo_connected:
            try:
                col = get_cameras_col()
                if col is not None:
                    d = col.find_one({"_id": cid})
                    if not d:
                        try:
                            from bson import ObjectId
                            if ObjectId.is_valid(cid):
                                d = col.find_one({"_id": ObjectId(cid)})
                        except Exception:
                            pass
                    if d:
                        d["_id"] = str(d["_id"])
                        return d
            except Exception:
                pass

        found = next((c for c in mem_cameras if str(c.get("_id")) == cid), None)
        if found:
            return dict(found)

        # Explicit camera_id requested but NOT FOUND in database/memory:
        # Strictly return unconfigured camera with empty zones.
        # NEVER silently fall through to cam_01 or inherit another camera's polygons!
        return {
            "_id": cid,
            "name": f"Unknown Camera ({cid})",
            "zoneId": None,
            "zoneName": "Unconfigured Camera",
            "sourceType": "unknown",
            "zones": [],
            "is_unknown": True
        }

    # 2. By zone_id (when camera_id was omitted)
    if zone_id is not None and str(zone_id).strip():
        zid = str(zone_id).strip()
        if is_mongo_connected:
            try:
                col = get_cameras_col()
                if col is not None:
                    d = col.find_one({"zoneId": zid})
                    if d:
                        d["_id"] = str(d["_id"])
                        return d
            except Exception:
                pass

        found = next((c for c in mem_cameras if str(c.get("zoneId")) == zid), None)
        if found:
            return dict(found)

        return {
            "_id": f"cam_{zid}",
            "name": f"Camera for Zone {zid}",
            "zoneId": zid,
            "zoneName": f"Zone {zid}",
            "sourceType": "webcam",
            "zones": []
        }

    # 3. Missing camera_id and missing zone_id:
    # Default live camera / webcam configuration without polygon inheritance
    return {
        "_id": "webcam_main",
        "name": "Primary Live Camera",
        "zoneId": "zone_01",
        "zoneName": "Heavy Assembly Bay 01",
        "sourceType": "webcam",
        "zones": []
    }
