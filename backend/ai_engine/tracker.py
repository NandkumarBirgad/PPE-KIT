"""
Anonymous Worker Tracker Module
===============================
Provides session-scoped, anonymous worker identification (W-001, W-002, ...)
using a lightweight IoU + predicted-centroid tracking architecture.

Design Principles:
- CPU-only execution with zero external C-dependencies (pure Python + NumPy).
- True time-based track recovery (monotonic/presentation timestamp elapsed time).
- Ambiguity-aware matching (refuses to force associations on near-ties).
- Normalized spatial thresholds (scale-invariant across 640x480, 1280x720, etc.).
- Thread-safe session tracker registry providing complete camera/session isolation.
"""

import time
import threading
import numpy as np

def compute_box_iou(box_a, box_b):
    """
    Computes Intersection-over-Union (IoU) of two bounding boxes.
    Format: [x1, y1, x2, y2]
    """
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])

    inter_w = max(0, x2 - x1)
    inter_h = max(0, y2 - y1)
    inter_area = inter_w * inter_h

    area_a = max(0, box_a[2] - box_a[0]) * max(0, box_a[3] - box_a[1])
    area_b = max(0, box_b[2] - box_b[0]) * max(0, box_b[3] - box_b[1])
    union_area = area_a + area_b - inter_area

    if union_area <= 0:
        return 0.0
    return float(inter_area) / float(union_area)

def compute_box_centroid(box):
    """Returns the (cx, cy) center coordinates of a bounding box."""
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)

class TrackState:
    ACTIVE = "ACTIVE"
    LOST = "LOST"
    REMOVED = "REMOVED"

class Track:
    """
    Represents an individual worker's anonymous spatial track over time.
    """
    def __init__(self, track_id: int, bbox: list, conf: float, timestamp: float):
        self.id = track_id
        self.worker_id = f"W-{track_id:03d}"
        self.bbox = [int(v) for v in bbox]
        self.prev_bbox = [int(v) for v in bbox]
        self.conf = float(conf)
        self.state = TrackState.ACTIVE
        self.created_at = float(timestamp)
        self.last_seen = float(timestamp)
        self.hits = 1
        self.age = 1
        self.velocity = (0.0, 0.0) # (dx/dt, dy/dt) in pixels/sec
        self.centroid = compute_box_centroid(self.bbox)

    def update(self, bbox: list, conf: float, timestamp: float):
        """Updates track state with a newly associated detection."""
        dt = max(float(timestamp) - self.last_seen, 1e-4)
        new_centroid = compute_box_centroid(bbox)

        # Calculate instantaneous velocity
        inst_vx = (new_centroid[0] - self.centroid[0]) / dt
        inst_vy = (new_centroid[1] - self.centroid[1]) / dt

        # Damped exponential moving average for smooth velocity prediction
        alpha = 0.35
        self.velocity = (
            (1.0 - alpha) * self.velocity[0] + alpha * inst_vx,
            (1.0 - alpha) * self.velocity[1] + alpha * inst_vy
        )

        self.prev_bbox = list(self.bbox)
        self.bbox = [int(v) for v in bbox]
        self.centroid = new_centroid
        self.conf = float(conf)
        self.last_seen = float(timestamp)
        self.state = TrackState.ACTIVE
        self.hits += 1
        self.age += 1

    def predict_centroid(self, timestamp: float) -> tuple:
        """
        Predicts worker position forward in time using estimated velocity.
        Clamps forward projection to a maximum horizon of 1.0s to prevent drift.
        """
        dt = max(0.0, float(timestamp) - self.last_seen)
        horizon = min(dt, 1.0)
        return (
            self.centroid[0] + self.velocity[0] * horizon,
            self.centroid[1] + self.velocity[1] * horizon
        )

    def mark_lost(self):
        """Marks track as temporarily lost/unmatched."""
        self.state = TrackState.LOST
        self.age += 1

    def to_dict(self) -> dict:
        return {
            "track_id": self.id,
            "worker_id": self.worker_id,
            "bbox": self.bbox,
            "confidence": self.conf,
            "state": self.state,
            "hits": self.hits,
            "age": self.age,
            "created_at": self.created_at,
            "last_seen": self.last_seen
        }

class LightweightIoUTracker:
    """
    Lightweight IoU + Centroid Distance Tracker.
    Maintains session-scoped anonymous worker IDs across video frames.
    """
    def __init__(
        self,
        iou_threshold: float = 0.30,
        centroid_threshold: float = 0.15,
        recovery_timeout_sec: float = 3.0,
        ambiguity_margin: float = 0.08
    ):
        self.iou_threshold = max(0.05, min(0.95, float(iou_threshold)))
        self.centroid_threshold = max(0.01, min(1.0, float(centroid_threshold)))
        self.recovery_timeout_sec = max(0.5, float(recovery_timeout_sec))
        self.ambiguity_margin = max(0.01, min(0.5, float(ambiguity_margin)))

        self.tracks = []
        self.next_id = 1
        self.last_timestamp = None
        self._lock = threading.RLock()

    def reset(self):
        """Resets tracker state and restarts ID counter at 1."""
        with self._lock:
            self.tracks = []
            self.next_id = 1
            self.last_timestamp = None

    def update(self, detections: list, timestamp: float, img_shape: tuple = None) -> list:
        with self._lock:
            return self._update_internal(detections, timestamp, img_shape=img_shape)

    def _update_internal(self, detections: list, timestamp: float, img_shape: tuple = None) -> list:
        """
        Updates the tracker with detections from the current frame.

        Parameters:
        - detections: list of dicts with 'bbox' [x1, y1, x2, y2] and 'confidence' float
        - timestamp: float seconds (presentation timestamp or monotonic clock)
        - img_shape: optional (height, width) for scale-normalized distance matching

        Returns:
        - list of matched person dicts augmented with 'worker_id', 'track_id', etc.
        """
        ts = float(timestamp)

        # Guard against non-monotonic clock or timestamp jumps (e.g. video loop or time shift)
        if self.last_timestamp is not None and ts < self.last_timestamp - 0.5:
            # Timestamp jumped backwards: adjust track last_seen offsets
            delta = self.last_timestamp - ts
            for t in self.tracks:
                t.last_seen = max(0.0, t.last_seen - delta)
                t.created_at = max(0.0, t.created_at - delta)
        self.last_timestamp = ts

        # Determine scale-normalized centroid distance threshold
        if img_shape and img_shape[0] > 0 and img_shape[1] > 0:
            diag = np.hypot(img_shape[0], img_shape[1])
            effective_dist_thresh = self.centroid_threshold * diag
        else:
            # Default reference diagonal for 720p: hypot(720, 1280) ≈ 1468.6 px -> 0.15 * 1468.6 ≈ 220 px
            effective_dist_thresh = self.centroid_threshold * 1468.6

        # Step 1: Age existing tracks and prune tracks that exceeded recovery timeout
        surviving_tracks = []
        for t in self.tracks:
            elapsed = ts - t.last_seen
            if elapsed <= self.recovery_timeout_sec:
                surviving_tracks.append(t)
            else:
                t.state = TrackState.REMOVED
        self.tracks = surviving_tracks

        matched_tracks = set()
        matched_detections = set()

        # Step 2: Primary Association — Active Tracks with High IoU
        active_tracks = [t for t in self.tracks if t.state == TrackState.ACTIVE]

        if len(active_tracks) > 0 and len(detections) > 0:
            # Build IoU cost matrix
            iou_matrix = np.zeros((len(active_tracks), len(detections)), dtype=np.float32)
            for t_idx, t in enumerate(active_tracks):
                for d_idx, d in enumerate(detections):
                    iou_matrix[t_idx, d_idx] = compute_box_iou(t.bbox, d["bbox"])

            # Greedy one-to-one matching with ambiguity resolution
            while True:
                max_val = float(np.max(iou_matrix)) if iou_matrix.size > 0 else 0.0
                if max_val < self.iou_threshold:
                    break

                t_idx, d_idx = np.unravel_index(np.argmax(iou_matrix), iou_matrix.shape)

                # Check for ambiguity: does another detection have a near-identical IoU with this track?
                row_vals = sorted(iou_matrix[t_idx, :], reverse=True)
                is_ambiguous_det = False
                if len(row_vals) > 1 and row_vals[1] >= self.iou_threshold:
                    if (row_vals[0] - row_vals[1]) < self.ambiguity_margin:
                        is_ambiguous_det = True

                # Does another track have a near-identical IoU with this detection?
                col_vals = sorted(iou_matrix[:, d_idx], reverse=True)
                is_ambiguous_track = False
                if len(col_vals) > 1 and col_vals[1] >= self.iou_threshold:
                    if (col_vals[0] - col_vals[1]) < self.ambiguity_margin:
                        is_ambiguous_track = True

                if not is_ambiguous_det and not is_ambiguous_track:
                    track = active_tracks[t_idx]
                    det = detections[d_idx]
                    track.update(det["bbox"], det["confidence"], ts)
                    matched_tracks.add(track.id)
                    matched_detections.add(d_idx)

                # Nullify row and column in cost matrix so neither is matched again
                iou_matrix[t_idx, :] = -1.0
                iou_matrix[:, d_idx] = -1.0

        # Step 3: Secondary Association — Lost Tracks Recovery using IoU + Centroid Distance
        unmatched_dets = [i for i in range(len(detections)) if i not in matched_detections]
        candidate_lost_tracks = [t for t in self.tracks if t.id not in matched_tracks]

        if len(candidate_lost_tracks) > 0 and len(unmatched_dets) > 0:
            score_matrix = np.zeros((len(candidate_lost_tracks), len(unmatched_dets)), dtype=np.float32)

            for t_idx, t in enumerate(candidate_lost_tracks):
                pred_c = t.predict_centroid(ts)
                for u_idx, d_idx in enumerate(unmatched_dets):
                    det = detections[d_idx]
                    d_c = compute_box_centroid(det["bbox"])
                    dist = float(np.hypot(d_c[0] - pred_c[0], d_c[1] - pred_c[1]))
                    iou = compute_box_iou(t.bbox, det["bbox"])

                    if dist <= effective_dist_thresh or iou >= 0.15:
                        norm_dist_score = max(0.0, 1.0 - (dist / effective_dist_thresh))
                        score_matrix[t_idx, u_idx] = (0.60 * iou) + (0.40 * norm_dist_score)
                    else:
                        score_matrix[t_idx, u_idx] = 0.0

            # Match secondary candidates
            while True:
                max_score = float(np.max(score_matrix)) if score_matrix.size > 0 else 0.0
                # Secondary recovery threshold
                if max_score < 0.25:
                    break

                t_idx, u_idx = np.unravel_index(np.argmax(score_matrix), score_matrix.shape)
                d_idx = unmatched_dets[u_idx]

                # Ambiguity guard on secondary matching
                row_vals = sorted(score_matrix[t_idx, :], reverse=True)
                is_ambig_secondary = False
                if len(row_vals) > 1 and row_vals[1] >= 0.25:
                    if (row_vals[0] - row_vals[1]) < self.ambiguity_margin:
                        is_ambig_secondary = True

                col_vals = sorted(score_matrix[:, u_idx], reverse=True)
                if len(col_vals) > 1 and col_vals[1] >= 0.25:
                    if (col_vals[0] - col_vals[1]) < self.ambiguity_margin:
                        is_ambig_secondary = True

                if not is_ambig_secondary:
                    track = candidate_lost_tracks[t_idx]
                    det = detections[d_idx]
                    track.update(det["bbox"], det["confidence"], ts)
                    matched_tracks.add(track.id)
                    matched_detections.add(d_idx)

                score_matrix[t_idx, :] = -1.0
                score_matrix[:, u_idx] = -1.0

        # Step 4: Mark remaining unmatched tracks as LOST
        for t in self.tracks:
            if t.id not in matched_tracks:
                t.mark_lost()

        # Step 5: Initialize brand new tracks for remaining unmatched detections
        # NEVER reuse an existing ID within the same session
        for d_idx in range(len(detections)):
            if d_idx not in matched_detections:
                det = detections[d_idx]
                new_track = Track(self.next_id, det["bbox"], det["confidence"], ts)
                self.next_id += 1
                self.tracks.append(new_track)

        # Step 6: Map worker_id and track information into detection output
        # Build lookup from matching bbox or track assignment
        assigned_outputs = []
        for t in self.tracks:
            if t.state == TrackState.ACTIVE:
                # Find corresponding original detection index if matched
                assigned_outputs.append({
                    "track_id": t.id,
                    "worker_id": t.worker_id,
                    "bbox": t.bbox,
                    "confidence": t.conf,
                    "state": t.state,
                    "hits": t.hits,
                    "age": t.age
                })

        return assigned_outputs

# =====================================================================
# THREAD-SAFE SESSION TRACKER REGISTRY
# =====================================================================
class SessionTrackerManager:
    """
    Manages isolated tracker instances per camera/monitoring session.
    Provides thread safety and automatic TTL-based stale session cleanup.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._sessions = {} # session_id -> {"tracker": LightweightIoUTracker, "last_accessed": float}

    def get_tracker(
        self,
        session_id: str,
        iou_threshold: float = 0.30,
        centroid_threshold: float = 0.15,
        recovery_timeout_sec: float = 3.0,
        ambiguity_margin: float = 0.08
    ) -> LightweightIoUTracker:
        """
        Retrieves or creates an isolated tracker instance for the given session_id.
        """
        key = str(session_id or "default_session").strip()
        now = time.monotonic()
        with self._lock:
            if key not in self._sessions:
                self._sessions[key] = {
                    "tracker": LightweightIoUTracker(
                        iou_threshold=iou_threshold,
                        centroid_threshold=centroid_threshold,
                        recovery_timeout_sec=recovery_timeout_sec,
                        ambiguity_margin=ambiguity_margin
                    ),
                    "last_accessed": now
                }
            else:
                self._sessions[key]["last_accessed"] = now
            return self._sessions[key]["tracker"]

    def reset_tracker(self, session_id: str):
        """
        Explicitly removes and frees a session tracker instance.
        """
        key = str(session_id or "default_session").strip()
        with self._lock:
            if key in self._sessions:
                self._sessions[key]["tracker"].reset()
                del self._sessions[key]

    def cleanup_stale_sessions(self, ttl_seconds: float = 300.0) -> int:
        """
        Purges sessions that have been inactive for more than ttl_seconds.
        Returns the number of cleaned up sessions.
        """
        now = time.monotonic()
        cleaned = 0
        with self._lock:
            stale_keys = [
                k for k, v in self._sessions.items()
                if (now - v["last_accessed"]) > ttl_seconds
            ]
            for k in stale_keys:
                self._sessions[k]["tracker"].reset()
                del self._sessions[k]
                cleaned += 1
        return cleaned

    def active_session_count(self) -> int:
        """Returns the number of currently active tracking sessions."""
        with self._lock:
            return len(self._sessions)

# Global singleton instance of SessionTrackerManager
_session_manager = SessionTrackerManager()

def get_session_tracker(session_id: str, **kwargs) -> LightweightIoUTracker:
    """Convenience accessor for session tracker."""
    return _session_manager.get_tracker(session_id, **kwargs)

def reset_session_tracker(session_id: str):
    """Convenience function to reset and purge a session tracker."""
    _session_manager.reset_tracker(session_id)

def cleanup_stale_tracker_sessions(ttl_seconds: float = 300.0) -> int:
    """Convenience function to purge stale tracker sessions."""
    return _session_manager.cleanup_stale_sessions(ttl_seconds)
