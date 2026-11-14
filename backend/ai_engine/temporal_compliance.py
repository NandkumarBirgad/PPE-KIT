"""
Temporal Violation Confirmation & Incident Smoothing Module
===========================================================
Maintains per-worker, per-PPE temporal compliance state machine across video frames.
Prevents transient detector flickers from generating false violations, while ensuring
sustained observable missing-PPE conditions are confirmed and logged safely.

Design Principles:
- Keyed by (session_id, worker_track_id, ppe_category).
- Configurable confirmation threshold (default: 3.0 seconds).
- Strict observable accumulation: time accumulates ONLY when worker is tracked,
  target region is observable, gear is required, and genuine PPE is absent.
- Pause on unobservable / uncertain: zero accumulation during occlusions or low confidence.
- Instant reset on genuine wear: wearing verified YOLO gear immediately clears pending state.
- Duplicate event suppression: confirmed state emits new confirmation event once per episode.
- Expiration safety: lost tracks expire after recovery timeout without creating false violations.
- Safe timestamp handling: rejects NaN, inf, and backward timestamps without rewinding state.
- Per-session thread safety: re-entrant synchronization per session without global bottlenecking.
"""

import math
import time
import threading
from typing import Any, Dict, List, Optional, Set, Tuple
from config import Config, validate_temporal_durations

def sanitize_timestamp(val: Any) -> Optional[float]:
    """
    Safely parses and validates a timestamp.
    Returns float seconds if valid, finite, and non-negative.
    Returns None if missing, non-numeric, NaN, infinite, or negative.
    Never raises ValueError or TypeError.
    """
    if val is None:
        return None
    try:
        ts = float(val)
        if math.isnan(ts) or math.isinf(ts) or ts < 0.0:
            return None
        return ts
    except (ValueError, TypeError):
        return None

class TemporalState:
    SATISFIED = "SATISFIED"
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    PAUSED = "PAUSED"

class TrackPPEState:
    """
    Maintains temporal state for a single (track_id, ppe_category, zone_id).
    Supports dual accumulators:
    1. Missing-PPE violation confirmation (accumulates towards CONFIRMED status)
    2. Verified-compliance resolution (accumulates continuously towards RESOLVED candidate)
    """
    def __init__(self, track_id: int, ppe_category: str, session_id: str = "default_session", zone_id: Optional[str] = None):
        self.track_id = int(track_id)
        self.ppe_category = str(ppe_category).lower()
        self.session_id = str(session_id or "default_session").strip()
        self.zone_id = str(zone_id).strip() if zone_id else None
        self.state = TemporalState.SATISFIED
        self.accumulated_missing_sec = 0.0
        self.first_missing_timestamp = None
        self.confirmed_timestamp = None
        self.last_update_timestamp = None
        self.last_observed_timestamp = None
        self.episode_id = 0
        self.episode_uuid = ""
        self.confirmation_event_emitted = False
        self.is_new_confirmation = False
        self.is_lost = False

        # Verified Compliance Attributes (M2.2B.5B / M2.2B.5B.1)
        self.active_confirmed_episode_uuid: Optional[str] = None
        self.active_confirmed_episode_id: int = 0
        self.accumulated_compliance_sec = 0.0
        self.first_compliance_timestamp: Optional[float] = None
        self.last_compliance_timestamp: Optional[float] = None
        self.resolved_timestamp: Optional[float] = None
        self.resolution_event_emitted = False
        self.is_resolution_candidate = False
        self.resolution_candidate: Optional[dict] = None

    def reset_compliance_timer(self):
        """
        Immediately resets the continuous verified compliance timer to zero.
        Used on interruptions (unobservable, uncertain, track lost, or PPE removed).
        Does not pause or preserve elapsed compliance duration.
        Preserves uncommitted resolution candidates if already achieved.
        """
        self.accumulated_compliance_sec = 0.0
        self.first_compliance_timestamp = None
        self.last_compliance_timestamp = None
        self.is_resolution_candidate = False

    def commit_resolution(self, episode_id: Optional[str] = None) -> bool:
        """
        Idempotently commits / acknowledges that a resolution candidate has been successfully
        persisted by downstream systems. Clears the active confirmed episode and candidate.
        """
        if episode_id is not None:
            current_ep = self.active_confirmed_episode_uuid or (
                self.resolution_candidate.get("episode_id") if self.resolution_candidate else None
            )
            if current_ep is not None and current_ep != episode_id:
                return False

        self.resolution_candidate = None
        self.active_confirmed_episode_uuid = None
        self.active_confirmed_episode_id = 0
        self.resolution_event_emitted = False
        self.resolved_timestamp = None
        self.accumulated_missing_sec = 0.0
        self.first_missing_timestamp = None
        self.confirmed_timestamp = None
        self.is_resolution_candidate = False
        self.state = TemporalState.SATISFIED
        return True

    def reset_to_satisfied(self, timestamp: float):
        """Worker is wearing genuine gear: reset pending timers and clear confirmation."""
        ts = float(timestamp)
        if self.last_update_timestamp is not None and ts < self.last_update_timestamp:
            return
        self.state = TemporalState.SATISFIED
        self.accumulated_missing_sec = 0.0
        self.first_missing_timestamp = None
        self.confirmed_timestamp = None
        self.confirmation_event_emitted = False
        self.is_new_confirmation = False
        self.is_lost = False
        self.reset_compliance_timer()
        self.commit_resolution()
        self.last_update_timestamp = ts
        self.last_observed_timestamp = ts

    def pause(self, timestamp: float, mark_lost: bool = False):
        """Worker/region is unobservable, uncertain, or lost: pause missing timer and reset compliance timer."""
        ts = float(timestamp)
        if self.last_update_timestamp is not None and ts < self.last_update_timestamp:
            return
        if self.state != TemporalState.CONFIRMED:
            self.state = TemporalState.PAUSED
        if mark_lost:
            self.is_lost = True
        self.is_new_confirmation = False
        # Interruption immediately resets continuous compliance timer (Rule 2)
        self.reset_compliance_timer()
        self.last_update_timestamp = ts

    def accumulate_compliance(self, timestamp: float, resolution_threshold: float, max_gap_sec: float = 1.5):
        """
        Worker is wearing genuine YOLO gear with observable region:
        Accumulate elapsed verified compliance time towards resolution candidate threshold.
        Applies only if a confirmed violation episode already exists for this track and PPE.
        Enforces max_gap_sec to prevent unobserved intervals from counting as compliance.
        """
        ts = float(timestamp)

        # 1. Guard against backward timestamps
        if self.last_update_timestamp is not None and ts < self.last_update_timestamp:
            return

        # 2. Worker is wearing gear, so instantaneous missing PPE state is satisfied
        self.state = TemporalState.SATISFIED
        self.is_lost = False

        # 3. Must have an active confirmed violation episode to accumulate compliance towards resolution
        if self.active_confirmed_episode_uuid is None:
            self.accumulated_missing_sec = 0.0
            self.first_missing_timestamp = None
            self.confirmed_timestamp = None
            self.confirmation_event_emitted = False
            self.is_new_confirmation = False
            self.reset_compliance_timer()
            self.last_update_timestamp = ts
            self.last_observed_timestamp = ts
            return

        # 4. First verified-compliance frame starts timer at 0.0
        if self.first_compliance_timestamp is None:
            self.first_compliance_timestamp = ts
            self.accumulated_compliance_sec = 0.0
            self.last_compliance_timestamp = ts
            self.is_resolution_candidate = False
        else:
            # Check inter-observation gap: reject excessive gap that breaks continuity
            dt = max(0.0, ts - float(self.last_compliance_timestamp))
            if dt > max_gap_sec:
                # Interruption: unobserved gap exceeds allowable frame cadence.
                # Reset continuous compliance to 0.0s and restart from current observation.
                self.accumulated_compliance_sec = 0.0
                self.first_compliance_timestamp = ts
                self.last_compliance_timestamp = ts
                self.is_resolution_candidate = False
            else:
                self.accumulated_compliance_sec += dt
                self.last_compliance_timestamp = ts

                if self.accumulated_compliance_sec >= resolution_threshold:
                    if not self.resolution_event_emitted:
                        self.is_resolution_candidate = True
                        self.resolution_event_emitted = True
                        self.resolved_timestamp = ts
                        ep_id = self.active_confirmed_episode_uuid or self.episode_uuid
                        self.resolution_candidate = {
                            "episode_id": ep_id,
                            "session_id": self.session_id,
                            "worker_id": f"W-{self.track_id:03d}",
                            "track_id": self.track_id,
                            "zone_id": self.zone_id,
                            "ppe_category": self.ppe_category,
                            "verified_compliance_duration_sec": round(self.accumulated_compliance_sec, 3),
                            "candidate_timestamp": self.resolved_timestamp or ts,
                            "resolution_event_id": f"res_{ep_id}"
                        }
                    else:
                        self.is_resolution_candidate = False
                else:
                    self.is_resolution_candidate = False

        self.last_update_timestamp = ts
        self.last_observed_timestamp = ts

    def accumulate_missing(self, timestamp: float, duration_threshold: float):
        """Observable missing gear: accumulate elapsed time towards confirmation threshold."""
        ts = float(timestamp)

        # 1. Guard against backward timestamps: never rewind baseline or accumulate time
        if self.last_update_timestamp is not None and ts < self.last_update_timestamp:
            return

        # Missing gear immediately resets compliance timer
        self.reset_compliance_timer()

        # 2. Check if an unresolved confirmed episode already exists!
        if self.active_confirmed_episode_uuid is not None:
            # The violation was ALREADY confirmed!
            # The interrupted compliance failed to resolve it.
            # Preserve original episode identity, episode_id, and active_confirmed_episode_uuid!
            self.state = TemporalState.CONFIRMED
            self.is_new_confirmation = False
            self.confirmation_event_emitted = True
            self.episode_uuid = self.active_confirmed_episode_uuid
            self.episode_id = self.active_confirmed_episode_id
            self.is_lost = False
            self.last_update_timestamp = ts
            self.last_observed_timestamp = ts
            return

        # 3. No unresolved confirmed episode: normal missing accumulation / new episode
        dt = 0.0
        if (
            self.state in (TemporalState.PENDING, TemporalState.CONFIRMED, TemporalState.PAUSED)
            and not self.is_lost
            and self.last_update_timestamp is not None
        ):
            dt = max(0.0, ts - float(self.last_update_timestamp))

        # Reset lost flag upon observation
        self.is_lost = False

        if self.first_missing_timestamp is None:
            self.first_missing_timestamp = ts
            self.episode_id += 1
            if self.zone_id:
                self.episode_uuid = f"ep_{self.session_id}_{self.track_id}_{self.zone_id}_{self.ppe_category}_{self.episode_id}"
            else:
                self.episode_uuid = f"ep_{self.session_id}_{self.track_id}_{self.ppe_category}_{self.episode_id}"
            self.confirmation_event_emitted = False
            self.is_new_confirmation = False
            self.confirmed_timestamp = None
            self.active_confirmed_episode_uuid = None
            self.active_confirmed_episode_id = 0
            self.resolution_event_emitted = False
            self.resolved_timestamp = None
            self.resolution_candidate = None

        self.accumulated_missing_sec += dt
        self.last_update_timestamp = ts
        self.last_observed_timestamp = ts

        if self.accumulated_missing_sec >= duration_threshold:
            self.state = TemporalState.CONFIRMED
            if self.confirmed_timestamp is None:
                self.confirmed_timestamp = ts
            self.active_confirmed_episode_uuid = self.episode_uuid
            self.active_confirmed_episode_id = self.episode_id
            if not self.confirmation_event_emitted:
                self.is_new_confirmation = True
                self.confirmation_event_emitted = True
            else:
                self.is_new_confirmation = False
        else:
            self.state = TemporalState.PENDING
            self.is_new_confirmation = False

    def get_resolution_candidate(self) -> Optional[dict]:
        """
        Returns resolution candidate dictionary if this state has a pending or transition candidate.
        Returns None otherwise.
        """
        if self.resolution_candidate is not None:
            return dict(self.resolution_candidate)
        return None

    def to_dict(self) -> dict:
        fallback_ep = (
            f"ep_{self.session_id}_{self.track_id}_{self.zone_id}_{self.ppe_category}_{max(1, self.episode_id)}"
            if self.zone_id
            else f"ep_{self.session_id}_{self.track_id}_{self.ppe_category}_{max(1, self.episode_id)}"
        )
        ep_id = self.active_confirmed_episode_uuid or self.episode_uuid or fallback_ep
        return {
            "track_id": self.track_id,
            "ppe_category": self.ppe_category,
            "session_id": self.session_id,
            "zone_id": self.zone_id,
            "state": self.state,
            "accumulated_missing_sec": round(self.accumulated_missing_sec, 3),
            "first_missing_timestamp": self.first_missing_timestamp,
            "confirmed_timestamp": self.confirmed_timestamp,
            "is_new_confirmation": self.is_new_confirmation,
            "episode_id": ep_id,
            "episode_number": self.episode_id,
            "accumulated_compliance_sec": round(self.accumulated_compliance_sec, 3),
            "is_resolution_candidate": self.is_resolution_candidate,
            "has_resolution_candidate": self.resolution_candidate is not None,
            "resolved_timestamp": self.resolved_timestamp
        }

class SessionTemporalTracker:
    """
    Session-scoped temporal compliance manager.
    Tracks state per (track_id, ppe_category).
    Thread-safe per session via internal re-entrant lock.
    """
    def __init__(
        self,
        confirmation_duration_sec: float = None,
        recovery_timeout_sec: float = None,
        resolution_duration_sec: float = None,
        max_compliance_gap_sec: float = None,
        session_id: str = None
    ):
        self.session_id = str(session_id or "default_session").strip()
        self.confirmation_duration_sec = (
            float(confirmation_duration_sec) if confirmation_duration_sec is not None
            else getattr(Config, "VIOLATION_CONFIRMATION_DURATION_SEC", 3.0)
        )
        self.recovery_timeout_sec = (
            float(recovery_timeout_sec) if recovery_timeout_sec is not None
            else getattr(Config, "TRACKER_RECOVERY_TIMEOUT_SEC", 3.0)
        )
        res_dur = resolution_duration_sec if resolution_duration_sec is not None else getattr(Config, "RESOLUTION_CONFIRMATION_DURATION_SEC", 2.0)
        max_gap = max_compliance_gap_sec if max_compliance_gap_sec is not None else getattr(Config, "MAX_COMPLIANCE_OBSERVATION_GAP_SEC", 1.5)
        self.resolution_duration_sec, self.max_compliance_gap_sec = validate_temporal_durations(res_dur, max_gap)

        self._states: Dict[Tuple[int, str], TrackPPEState] = {}
        self._track_last_seen: Dict[int, float] = {}
        self._lock = threading.RLock()

        # Clock domain management: ensures consistent clock domain throughout a session
        self._clock_mode: Optional[str] = None # 'caller' or 'server'
        self._clock_base_mono: Optional[float] = None
        self._clock_base_caller: Optional[float] = None
        self._last_resolved_ts: Optional[float] = None

    def resolve_timestamp(self, caller_ts: Optional[float]) -> float:
        """
        Resolves a consistent timestamp for the session.
        Guarantees that a single session never mixes discordant browser and server clocks.
        """
        with self._lock:
            now_mono = time.monotonic()
            if caller_ts is not None:
                # Caller provided a validated timestamp
                if self._clock_mode is None:
                    self._clock_mode = "caller"
                    self._clock_base_mono = now_mono
                    self._clock_base_caller = caller_ts
                ts = caller_ts
            else:
                # Missing caller timestamp: fallback to monotonic progression
                if self._clock_mode == "caller" and self._clock_base_caller is not None:
                    # Session established in caller domain: advance relative to established baseline
                    elapsed = now_mono - self._clock_base_mono
                    ts = self._clock_base_caller + elapsed
                else:
                    self._clock_mode = "server"
                    if self._clock_base_mono is None:
                        self._clock_base_mono = now_mono
                    ts = now_mono

            self._last_resolved_ts = ts
            return ts

    def reset(self):
        with self._lock:
            self._states.clear()
            self._track_last_seen.clear()
            self._clock_mode = None
            self._clock_base_mono = None
            self._clock_base_caller = None
            self._last_resolved_ts = None

    def get_state(self, track_id: int, ppe_category: str, zone_id: Optional[str] = None) -> TrackPPEState:
        with self._lock:
            tid = int(track_id)
            cat = str(ppe_category).lower()
            zid = str(zone_id).strip() if zone_id else None
            key = (tid, cat, zid) if zid else (tid, cat)
            if key not in self._states:
                self._states[key] = TrackPPEState(tid, cat, session_id=self.session_id, zone_id=zid)
            return self._states[key]

    def pause_track_pending(self, track_id: int, timestamp: float = None):
        """
        Pauses pending missing timers for all states belonging to track_id,
        without marking the track lost and without clearing confirmed incidents.
        Used when a worker is unassigned, uncertain, or in an unmonitored transition.
        """
        with self._lock:
            tid = int(track_id)
            ts = float(timestamp if timestamp is not None else self.resolve_timestamp(None))
            for k, state in self._states.items():
                if k[0] == tid:
                    if state.state == TemporalState.PENDING:
                        state.pause(ts)
                    elif state.state == TemporalState.CONFIRMED:
                        state.reset_compliance_timer()

    def mark_track_lost(self, track_id: int, timestamp: float = None):
        """Marks track as temporarily lost / unassessed, pausing pending timers."""
        with self._lock:
            ts = float(timestamp if timestamp is not None else self.resolve_timestamp(None))
            tid = int(track_id)
            for k, state in self._states.items():
                if k[0] == tid:
                    state.pause(ts, mark_lost=True)

    def mark_frame_tracks(self, active_track_ids: Set[int], timestamp: float = None):
        """
        Marks any known track not seen in the current frame as lost/paused,
        ensuring unobserved intervals do not accumulate missing time.
        """
        with self._lock:
            ts = float(timestamp if timestamp is not None else self.resolve_timestamp(None))
            for tid in list(self._track_last_seen.keys()):
                if tid not in active_track_ids:
                    self.mark_track_lost(tid, ts)

    def update_worker_ppe(
        self,
        track_id: int,
        ppe_category: str,
        is_worn: bool,
        is_observable: bool,
        is_required: bool,
        is_uncertain: bool,
        timestamp: float,
        zone_id: Optional[str] = None
    ) -> TrackPPEState:
        """
        Updates temporal state machine for a specific (track_id, ppe_category, zone_id).
        Enforces zone transition isolation:
        - When a worker moves to a new zone, pending states in previous zones are paused/halted.
        - Previous zone missing duration is NOT transferred to the new zone.
        - Confirmed incidents in previous zones remain open/confirmed.
        """
        with self._lock:
            tid = int(track_id)
            cat = str(ppe_category).lower()
            zid = str(zone_id).strip() if zone_id else None
            state = self.get_state(tid, cat, zone_id=zid)
            ts = float(timestamp)

            # Guard against out-of-order updates
            if state.last_update_timestamp is not None and ts < state.last_update_timestamp:
                return state

            self._track_last_seen[tid] = ts

            # Zone transition isolation:
            # If this worker has states in other zones, pause pending timers in those zones
            # and reset their compliance accumulator so compliance in this zone cannot resolve them.
            if zid is not None:
                for k, other_state in list(self._states.items()):
                    k_tid = k[0]
                    k_zid = k[2] if len(k) >= 3 else None
                    if k_tid == tid and k_zid != zid:
                        if other_state.state == TemporalState.PENDING:
                            other_state.pause(ts)
                        elif other_state.state == TemporalState.CONFIRMED:
                            other_state.reset_compliance_timer()

            # 1. Genuine gear is worn: evaluate verified compliance
            if is_worn:
                state.accumulate_compliance(ts, self.resolution_duration_sec, self.max_compliance_gap_sec)
                return state

            # 2. Not required by policy: do not accumulate missing, reset compliance
            if not is_required:
                state.pause(ts)
                return state

            # 3. Unobservable body region or uncertain assessment: pause missing, reset compliance
            if (not is_observable) or is_uncertain:
                state.pause(ts)
                return state

            # 4. Observable, required, and missing: accumulate observable missing duration
            state.accumulate_missing(ts, self.confirmation_duration_sec)
            return state

    def commit_resolution(
        self,
        track_id: int,
        ppe_category: str,
        episode_id: Optional[str] = None,
        zone_id: Optional[str] = None
    ) -> bool:
        """
        Commits resolution for a specific (track_id, ppe_category, zone_id).
        """
        with self._lock:
            tid = int(track_id)
            cat = str(ppe_category).lower()
            zid = str(zone_id).strip() if zone_id else None
            key = (tid, cat, zid) if zid else (tid, cat)
            if key in self._states:
                return self._states[key].commit_resolution(episode_id)
            # Fallback search matching track and category
            for k, state in self._states.items():
                if k[0] == tid and k[1] == cat:
                    if episode_id is None or state.active_confirmed_episode_uuid == episode_id or state.episode_uuid == episode_id:
                        return state.commit_resolution(episode_id)
            return True

    def acknowledge_resolution(self, episode_id: str) -> bool:
        """
        Finds any state tracking episode_id across the session and commits it idempotently.
        """
        with self._lock:
            for state in self._states.values():
                ep = state.active_confirmed_episode_uuid or (
                    state.resolution_candidate.get("episode_id") if state.resolution_candidate else None
                ) or state.episode_uuid
                if ep == episode_id:
                    state.commit_resolution(episode_id)
            return True

    def get_resolution_candidates(self) -> List[dict]:
        """
        Collects all active resolution candidates across all tracked workers and PPE categories
        for the current evaluation frame.
        """
        with self._lock:
            candidates = []
            for state in self._states.values():
                cand = state.get_resolution_candidate()
                if cand is not None:
                    candidates.append(cand)
            return candidates

    def prune_expired_tracks(self, current_timestamp: float, active_track_ids: Optional[Set[int]] = None):
        """
        Prunes track states for workers that have been lost longer than recovery_timeout_sec.
        Ensures no violation can ever be emitted from unobserved time.
        """
        with self._lock:
            ts = float(current_timestamp)
            expired_track_ids = set()

            for tid, last_seen in list(self._track_last_seen.items()):
                if active_track_ids is not None and tid in active_track_ids:
                    continue
                if (ts - last_seen) > self.recovery_timeout_sec:
                    expired_track_ids.add(tid)

            if expired_track_ids:
                for tid in expired_track_ids:
                    self._track_last_seen.pop(tid, None)
                    keys_to_remove = [k for k in self._states if k[0] == tid]
                    for k in keys_to_remove:
                        self._states.pop(k, None)


class TemporalComplianceRegistry:
    """
    Thread-safe registry of session temporal trackers.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: Dict[str, Dict] = {}

    def get_tracker(
        self,
        session_id: str,
        confirmation_duration_sec: float = None,
        recovery_timeout_sec: float = None,
        resolution_duration_sec: float = None,
        max_compliance_gap_sec: float = None
    ) -> SessionTemporalTracker:
        key = str(session_id or "default_session").strip()
        now = time.monotonic()
        with self._lock:
            if key not in self._sessions:
                self._sessions[key] = {
                    "tracker": SessionTemporalTracker(
                        confirmation_duration_sec=confirmation_duration_sec,
                        recovery_timeout_sec=recovery_timeout_sec,
                        resolution_duration_sec=resolution_duration_sec,
                        max_compliance_gap_sec=max_compliance_gap_sec,
                        session_id=key
                    ),
                    "last_accessed": now
                }
            else:
                self._sessions[key]["last_accessed"] = now
            return self._sessions[key]["tracker"]

    def reset_tracker(self, session_id: str):
        key = str(session_id or "default_session").strip()
        session_entry = None
        with self._lock:
            if key in self._sessions:
                session_entry = self._sessions.pop(key, None)
        if session_entry:
            session_entry["tracker"].reset()

    def cleanup_stale_sessions(self, ttl_seconds: float = 300.0) -> int:
        now = time.monotonic()
        stale_entries = []
        with self._lock:
            stale_keys = [
                k for k, v in self._sessions.items()
                if (now - v["last_accessed"]) > ttl_seconds
            ]
            for k in stale_keys:
                entry = self._sessions.pop(k, None)
                if entry:
                    stale_entries.append(entry)
        for entry in stale_entries:
            entry["tracker"].reset()
        return len(stale_entries)

_temporal_registry = TemporalComplianceRegistry()

def get_session_temporal_tracker(session_id: str, **kwargs) -> SessionTemporalTracker:
    return _temporal_registry.get_tracker(session_id, **kwargs)

def reset_session_temporal(session_id: str):
    _temporal_registry.reset_tracker(session_id)
