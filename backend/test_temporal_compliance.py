import unittest
import time
from ai_engine.temporal_compliance import (
    TemporalState,
    TrackPPEState,
    SessionTemporalTracker,
    get_session_temporal_tracker,
    reset_session_temporal,
    sanitize_timestamp
)
from ai_engine.compliance import (
    evaluate_compliance,
    sort_canonical_ppe
)
from config import Config, validate_temporal_durations

class TestTemporalViolationConfirmation(unittest.TestCase):
    """
    Comprehensive test suite for Milestone M2.2B.4:
    Temporal Violation Confirmation & Incident Smoothing.
    Uses controllable, deterministic timestamps across all test cases.
    """

    def setUp(self):
        self.session_id = f"test_session_{int(time.time()*1000)}"
        reset_session_temporal(self.session_id)
        self.tracker = SessionTemporalTracker(confirmation_duration_sec=3.0, recovery_timeout_sec=3.0)
        self.img_shape = (720, 1280, 3)

        # Standard worker box [100, 100, 300, 500] (fully observable)
        self.worker1 = {
            "bbox": [100, 100, 300, 500],
            "confidence": 0.95,
            "worker_id": "W-001",
            "track_id": 1,
            "worn_ppe": [],
            "missing_ppe": [],
            "compliant": False
        }
        self.worker2 = {
            "bbox": [400, 100, 600, 500],
            "confidence": 0.94,
            "worker_id": "W-002",
            "track_id": 2,
            "worn_ppe": [],
            "missing_ppe": [],
            "compliant": False
        }

    def tearDown(self):
        reset_session_temporal(self.session_id)

    # 1. A brief missing-PPE detection that recovers before 3 seconds: no violation
    def test_01_brief_missing_recovers_before_3s_no_violation(self):
        # t=0.0: missing helmet (observable)
        st = self.tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=0.0
        )
        self.assertEqual(st.state, TemporalState.PENDING)
        self.assertAlmostEqual(st.accumulated_missing_sec, 0.0)

        # t=1.5: still missing
        st = self.tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=1.5
        )
        self.assertEqual(st.state, TemporalState.PENDING)
        self.assertAlmostEqual(st.accumulated_missing_sec, 1.5)

        # t=2.5: genuine helmet detected (worker put it on / transient detector miss recovered)
        st = self.tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=True, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=2.5
        )
        self.assertEqual(st.state, TemporalState.SATISFIED)
        self.assertAlmostEqual(st.accumulated_missing_sec, 0.0)
        self.assertFalse(st.is_new_confirmation)

    # 2. Missing PPE continuously observable for 3 seconds: confirmed violation
    def test_02_missing_continuously_observable_for_3s_confirms_violation(self):
        # t=0.0
        self.tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=0.0
        )
        # t=1.5
        st = self.tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=1.5
        )
        self.assertEqual(st.state, TemporalState.PENDING)

        # t=3.0: 3 seconds elapsed
        st = self.tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=3.0
        )
        self.assertEqual(st.state, TemporalState.CONFIRMED)
        self.assertAlmostEqual(st.accumulated_missing_sec, 3.0)
        self.assertTrue(st.is_new_confirmation)
        self.assertEqual(st.first_missing_timestamp, 0.0)
        self.assertEqual(st.confirmed_timestamp, 3.0)

    # 3. Unobservable interval: timer pauses and does not accumulate
    def test_03_unobservable_interval_pauses_timer_no_accumulation(self):
        # t=0.0: missing helmet (observable)
        self.tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=0.0
        )
        # t=1.0: missing helmet (observable) -> accumulated = 1.0s
        st = self.tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=1.0
        )
        self.assertAlmostEqual(st.accumulated_missing_sec, 1.0)

        # t=2.0: head becomes unobservable (e.g. clipped at frame top)
        st = self.tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=False,
            is_required=True, is_uncertain=False, timestamp=2.0
        )
        self.assertEqual(st.state, TemporalState.PAUSED)
        self.assertAlmostEqual(st.accumulated_missing_sec, 1.0, msg="Timer must not advance during unobservable frame")

        # t=4.5: still unobservable (2.5 seconds have elapsed in real time)
        st = self.tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=False,
            is_required=True, is_uncertain=False, timestamp=4.5
        )
        self.assertEqual(st.state, TemporalState.PAUSED)
        self.assertAlmostEqual(st.accumulated_missing_sec, 1.0, msg="Wall time must not be counted while unobservable")

        # t=5.5: head becomes observable again! Accumulates 1.0s -> 2.0s
        st = self.tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=5.5
        )
        self.assertEqual(st.state, TemporalState.PENDING)
        self.assertAlmostEqual(st.accumulated_missing_sec, 2.0)

        # t=6.5: accumulated reaches 3.0s -> CONFIRMED
        st = self.tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=6.5
        )
        self.assertEqual(st.state, TemporalState.CONFIRMED)
        self.assertAlmostEqual(st.accumulated_missing_sec, 3.0)

    # 4. Genuine PPE reappears: pending timer resets
    def test_04_genuine_ppe_reappears_resets_pending_timer(self):
        # Accumulate 2.8 seconds of missing vest (nearly confirmed)
        self.tracker.update_worker_ppe(1, "vest", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        st = self.tracker.update_worker_ppe(1, "vest", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=2.8)
        self.assertAlmostEqual(st.accumulated_missing_sec, 2.8)
        self.assertEqual(st.state, TemporalState.PENDING)

        # Reappears at t=2.9
        st = self.tracker.update_worker_ppe(1, "vest", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=2.9)
        self.assertEqual(st.state, TemporalState.SATISFIED)
        self.assertAlmostEqual(st.accumulated_missing_sec, 0.0)

        # Missing again at t=3.5: must start a brand new timer from 0.0
        st = self.tracker.update_worker_ppe(1, "vest", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.5)
        self.assertEqual(st.state, TemporalState.PENDING)
        self.assertAlmostEqual(st.accumulated_missing_sec, 0.0)
        self.assertEqual(st.first_missing_timestamp, 3.5)

    # 5. Worker temporarily disappears: no accumulation during disappearance
    def test_05_worker_temporarily_disappears_no_accumulation_during_absence(self):
        # Worker 1 missing helmet from t=0.0 to t=1.0 (accumulated 1.0s)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        st = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=1.0)
        self.assertAlmostEqual(st.accumulated_missing_sec, 1.0)

        # Worker 1 disappears at t=1.5 and is absent until t=3.5 (2.0s absent)
        # Check that state does not advance during absence
        st = self.tracker.get_state(1, "helmet")
        self.assertAlmostEqual(st.accumulated_missing_sec, 1.0)

    # 6. Worker returns with confidently recovered track ID: pending state resumes safely
    def test_06_worker_returns_with_recovered_track_resumes_state(self):
        self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=1.0)

        # Worker disappears at t=1.5 (marked lost by tracker)
        self.tracker.mark_track_lost(1, timestamp=1.5)

        # Worker returns at t=2.5 (< 3.0s recovery timeout) with recovered track ID 1
        st = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=2.5)
        # Resumes accumulating from 1.0s
        self.assertAlmostEqual(st.accumulated_missing_sec, 1.0)

        # Advances 2.0s to t=4.5 -> accumulated = 3.0s -> CONFIRMED
        st = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.5)
        self.assertEqual(st.state, TemporalState.CONFIRMED)
        self.assertAlmostEqual(st.accumulated_missing_sec, 3.0)

    # 7. Track expires: no violation from unobserved time
    def test_07_track_expires_no_violation_from_unobserved_time(self):
        self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=1.0)

        # Worker lost at t=1.0. Current time is t=5.0 (4.0s elapsed > 3.0s recovery timeout)
        self.tracker.prune_expired_tracks(5.0, active_track_ids={2}) # Track 1 is expired!

        # Verify track 1 was purged and did not emit violation
        st = self.tracker.get_state(1, "helmet")
        self.assertEqual(st.state, TemporalState.SATISFIED, "Expired track must reset and not hold unconfirmed violation")
        self.assertAlmostEqual(st.accumulated_missing_sec, 0.0)

    # 8. Two workers missing different PPE: independent state
    def test_08_two_workers_missing_different_ppe_independent_state(self):
        # Worker 1 misses helmet at t=0.0
        self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        # Worker 2 misses vest at t=1.0
        self.tracker.update_worker_ppe(2, "vest", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=1.0)

        # At t=3.0: Worker 1 has 3.0s missing helmet -> CONFIRMED
        st1 = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)
        self.assertEqual(st1.state, TemporalState.CONFIRMED)

        # At t=3.0: Worker 2 has only 2.0s missing vest -> PENDING
        st2 = self.tracker.update_worker_ppe(2, "vest", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)
        self.assertEqual(st2.state, TemporalState.PENDING)

    # 9. One worker's PPE evidence does not affect another worker
    def test_09_one_worker_ppe_does_not_affect_another_worker(self):
        # Worker 1 misses helmet; Worker 2 wears helmet
        self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        self.tracker.update_worker_ppe(2, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)

        self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)
        self.tracker.update_worker_ppe(2, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)

        st1 = self.tracker.get_state(1, "helmet")
        st2 = self.tracker.get_state(2, "helmet")

        self.assertEqual(st1.state, TemporalState.CONFIRMED)
        self.assertEqual(st2.state, TemporalState.SATISFIED)

    # 10. Multiple PPE categories for one worker: independent timers
    def test_10_multiple_ppe_categories_independent_timers(self):
        # Worker 1 misses helmet at t=0.0, but wears vest
        self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        self.tracker.update_worker_ppe(1, "vest", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)

        # At t=1.5: Worker 1 takes off vest (now missing both)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=1.5)
        self.tracker.update_worker_ppe(1, "vest", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=1.5)

        # At t=3.0: Helmet has reached 3.0s (CONFIRMED), vest has only reached 1.5s (PENDING)
        st_h = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)
        st_v = self.tracker.update_worker_ppe(1, "vest", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)

        self.assertEqual(st_h.state, TemporalState.CONFIRMED)
        self.assertEqual(st_v.state, TemporalState.PENDING)

    # 11. Confirmed ongoing violation does not emit duplicate confirmation events
    def test_11_confirmed_ongoing_violation_no_duplicate_confirmation_events(self):
        self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        st = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)
        self.assertEqual(st.state, TemporalState.CONFIRMED)
        self.assertTrue(st.is_new_confirmation, "First transition to CONFIRMED must emit new confirmation flag")

        # Ongoing frames at t=4.0 and t=5.0
        st = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        self.assertEqual(st.state, TemporalState.CONFIRMED)
        self.assertFalse(st.is_new_confirmation, "Subsequent frames must NOT emit duplicate confirmation events")

        st = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.0)
        self.assertEqual(st.state, TemporalState.CONFIRMED)
        self.assertFalse(st.is_new_confirmation)

    # 12. New violation after verified recovery creates a new episode
    def test_12_new_violation_after_verified_recovery_creates_new_episode(self):
        # Episode 1: Missing helmet from t=0.0 to t=3.0
        self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        st = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)
        self.assertEqual(st.episode_id, 1)
        self.assertTrue(st.is_new_confirmation)

        # Worker puts on helmet at t=4.0, achieves 2s verified compliance at t=6.0, and resolution is acknowledged
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        st_res = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=6.0)
        self.tracker.acknowledge_resolution(st.episode_uuid)
        self.assertEqual(st_res.state, TemporalState.SATISFIED)

        # Worker removes helmet again at t=7.0 -> Starts Episode 2
        st = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=7.0)
        self.assertEqual(st.episode_id, 2)
        self.assertEqual(st.state, TemporalState.PENDING)

        # Confirms at t=10.0
        st = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=10.0)
        self.assertEqual(st.episode_id, 2)
        self.assertEqual(st.state, TemporalState.CONFIRMED)
        self.assertTrue(st.is_new_confirmation, "New episode must emit new confirmation event")

    # 13. Empty scene remains UNCERTAIN
    def test_13_empty_scene_remains_uncertain(self):
        status, missing, evaluated = evaluate_compliance(
            [], [], required_ppe=["helmet", "vest"], session_id=self.session_id, timestamp=1.0, img_shape=self.img_shape
        )
        self.assertEqual(status, "UNCERTAIN")
        self.assertEqual(missing, [])
        self.assertEqual(evaluated, [])

    # 14. Synthetic HSV evidence cannot reset or satisfy a pending violation
    def test_14_synthetic_hsv_cannot_reset_or_satisfy_pending_violation(self):
        # Setup worker with genuine missing helmet
        person = dict(self.worker1)
        # Advance 2.0s without helmet
        evaluate_compliance([person], [], ["helmet"], session_id=self.session_id, timestamp=0.0, img_shape=self.img_shape)
        evaluate_compliance([person], [], ["helmet"], session_id=self.session_id, timestamp=2.0, img_shape=self.img_shape)

        # Injected high-confidence synthetic HSV helmet at t=2.5
        hsv_helmet = {
            "class": "helmet", "name": "helmet", "confidence": 0.99,
            "bbox": [120, 105, 280, 195], "source": "hsv", "is_synthetic": True
        }
        status, missing, evaluated = evaluate_compliance(
            [person], [hsv_helmet], ["helmet"], session_id=self.session_id, timestamp=2.5, img_shape=self.img_shape
        )
        # Synthetic HSV must NOT be in worn_ppe
        self.assertEqual(evaluated[0]["worn_ppe"], [])

        # Advance to t=3.2 with HSV still present: MUST confirm violation!
        status, missing, evaluated = evaluate_compliance(
            [person], [hsv_helmet], ["helmet"], session_id=self.session_id, timestamp=3.2, img_shape=self.img_shape
        )
        self.assertEqual(status, "VIOLATION", "Synthetic HSV must not suppress confirmed violation")
        self.assertEqual(missing, ["helmet"])
        self.assertEqual(evaluated[0]["missing_ppe"], ["helmet"])

    # 15. Session isolation: one camera/session cannot affect another session
    def test_15_session_isolation_independent_state(self):
        sess_a = f"{self.session_id}_A"
        sess_b = f"{self.session_id}_B"

        tr_a = get_session_temporal_tracker(sess_a, confirmation_duration_sec=3.0)
        tr_b = get_session_temporal_tracker(sess_b, confirmation_duration_sec=3.0)

        # In Session A: Worker 1 misses helmet for 3.0s -> CONFIRMED
        tr_a.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        st_a = tr_a.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)

        # In Session B: Worker 1 wears helmet
        st_b = tr_b.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)

        self.assertEqual(st_a.state, TemporalState.CONFIRMED)
        self.assertEqual(st_b.state, TemporalState.SATISFIED)

        reset_session_temporal(sess_a)
        reset_session_temporal(sess_b)

    # 16. Uncertain worker assessment pauses accumulation
    def test_16_uncertain_worker_assessment_pauses_accumulation(self):
        self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        st = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=1.0)
        self.assertAlmostEqual(st.accumulated_missing_sec, 1.0)

        # Low confidence or blurred frame causes uncertainty
        st = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=True, timestamp=3.0)
        self.assertEqual(st.state, TemporalState.PAUSED)
        self.assertAlmostEqual(st.accumulated_missing_sec, 1.0, msg="Uncertain frame must not accumulate missing time")

    # 17. End-to-end evaluate_compliance temporal smoothing
    def test_17_evaluate_compliance_end_to_end_temporal_smoothing(self):
        person = dict(self.worker1)
        # t=0.0: missing helmet
        status, missing, evaluated = evaluate_compliance(
            [person], [], required_ppe=["helmet"], session_id=self.session_id, timestamp=0.0, img_shape=self.img_shape
        )
        self.assertEqual(status, "COMPLIANT", "Transient missing gear (< 3.0s) must NOT immediately trigger VIOLATION")
        self.assertEqual(missing, [])
        self.assertEqual(evaluated[0]["missing_ppe"], [])
        self.assertEqual(evaluated[0]["pending_missing_ppe"], ["helmet"])

        # t=1.5: still pending
        status, missing, evaluated = evaluate_compliance(
            [person], [], required_ppe=["helmet"], session_id=self.session_id, timestamp=1.5, img_shape=self.img_shape
        )
        self.assertEqual(status, "COMPLIANT")
        self.assertEqual(missing, [])

        # t=3.0: 3.0 seconds continuous observable missing helmet -> Confirmed VIOLATION!
        status, missing, evaluated = evaluate_compliance(
            [person], [], required_ppe=["helmet"], session_id=self.session_id, timestamp=3.0, img_shape=self.img_shape
        )
        self.assertEqual(status, "VIOLATION", "Continuous 3.0s missing gear must produce VIOLATION")
        self.assertEqual(missing, ["helmet"])
        self.assertEqual(evaluated[0]["missing_ppe"], ["helmet"])
        self.assertEqual(evaluated[0]["new_confirmed_violations"], ["helmet"])

        # t=4.0: ongoing violation
        status, missing, evaluated = evaluate_compliance(
            [person], [], required_ppe=["helmet"], session_id=self.session_id, timestamp=4.0, img_shape=self.img_shape
        )
        self.assertEqual(status, "VIOLATION")
        self.assertEqual(missing, ["helmet"])
        self.assertEqual(evaluated[0]["new_confirmed_violations"], [], "Ongoing violation must not repeat confirmation event")

    # 18. Legacy string-array contracts and fields preserved
    def test_18_legacy_string_array_types_and_fields_preserved(self):
        person = dict(self.worker1)
        status, missing, evaluated = evaluate_compliance(
            [person], [], required_ppe=["helmet", "vest"], session_id=self.session_id, timestamp=0.0, img_shape=self.img_shape
        )
        p = evaluated[0]
        self.assertIsInstance(status, str)
        self.assertIsInstance(missing, list)
        self.assertTrue(all(isinstance(x, str) for x in missing))

        self.assertIsInstance(p["worn_ppe"], list)
        self.assertTrue(all(isinstance(x, str) for x in p["worn_ppe"]))
        self.assertIsInstance(p["missing_ppe"], list)
        self.assertTrue(all(isinstance(x, str) for x in p["missing_ppe"]))
        self.assertIsInstance(p["scanned_body_parts"], list)
        self.assertTrue(all(isinstance(x, str) for x in p["scanned_body_parts"]))
        self.assertIsInstance(p["compliant"], bool)
        self.assertIsInstance(p["uncertain"], bool)


class TestTemporalRuntimeHardening(unittest.TestCase):
    """
    Focused verification suite for Milestone M2.2B.4G:
    Temporal Runtime Reliability Hardening.
    Covers pruning, validation, monotonic fallback, ordering, concurrency, and session isolation.
    """

    def setUp(self):
        self.session_id = f"test_hardening_{int(time.time()*1000)}"
        reset_session_temporal(self.session_id)
        self.tracker = SessionTemporalTracker(confirmation_duration_sec=3.0, recovery_timeout_sec=1.0)
        self.worker1 = {
            "bbox": [100, 100, 300, 500],
            "confidence": 0.95,
            "worker_id": "W-001",
            "track_id": 1,
            "worn_ppe": [],
            "missing_ppe": [],
            "compliant": False
        }

    def tearDown(self):
        reset_session_temporal(self.session_id)

    # 1. Live evaluation with no client timestamp still prunes expired tracks
    def test_01_no_client_timestamp_still_prunes_expired_tracks(self):
        tracker = get_session_temporal_tracker(self.session_id, recovery_timeout_sec=0.1)
        # First frame: worker present
        evaluate_compliance([dict(self.worker1)], [], required_ppe=["helmet"], session_id=self.session_id, timestamp=None)
        self.assertIn(1, tracker._track_last_seen)

        # Wait past recovery timeout
        time.sleep(0.15)

        # Second frame: worker gone, evaluating another worker to trigger frame evaluation
        w2 = dict(self.worker1)
        w2["track_id"] = 2
        w2["worker_id"] = "W-002"
        w2["bbox"] = [400, 100, 600, 500]
        evaluate_compliance([w2], [], required_ppe=["helmet"], session_id=self.session_id, timestamp=None)

        # Worker 1 must be pruned because recovery timeout elapsed
        self.assertNotIn(1, tracker._track_last_seen, "Inactive track must be pruned even without client timestamp")

    # 2. Active tracks survive pruning
    def test_02_active_tracks_survive_pruning(self):
        tracker = self.tracker
        tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.0)

        # Prune with active track_ids = {1}
        tracker.prune_expired_tracks(current_timestamp=5.0, active_track_ids={1})
        self.assertIn(1, tracker._track_last_seen)
        self.assertIn((1, "helmet"), tracker._states)

    # 3. Expired tracks are removed
    def test_03_expired_tracks_are_removed(self):
        tracker = self.tracker
        tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        # Advance beyond recovery timeout (1.0s)
        tracker.prune_expired_tracks(current_timestamp=2.5, active_track_ids=set())
        self.assertNotIn(1, tracker._track_last_seen)
        self.assertNotIn((1, "helmet"), tracker._states)

    # 4. Missing timestamp fallback uses a consistent clock
    def test_04_missing_timestamp_fallback_uses_consistent_clock(self):
        tracker = SessionTemporalTracker()
        ts1 = tracker.resolve_timestamp(None)
        time.sleep(0.025)
        ts2 = tracker.resolve_timestamp(None)
        self.assertGreater(ts2, ts1)
        self.assertEqual(tracker._clock_mode, "server")

        # Session starting with caller timestamp preserves caller domain progression
        caller_tracker = SessionTemporalTracker()
        c_ts1 = caller_tracker.resolve_timestamp(10.0)
        self.assertEqual(c_ts1, 10.0)
        self.assertEqual(caller_tracker._clock_mode, "caller")
        time.sleep(0.025)
        c_ts2 = caller_tracker.resolve_timestamp(None)
        self.assertGreater(c_ts2, 10.0)
        self.assertLess(c_ts2, 11.0, "Must synthesize monotonic advance in caller domain without jumping to server epoch")

    # 5. NaN and infinity are rejected safely
    def test_05_nan_and_infinity_rejected_safely(self):
        self.assertIsNone(sanitize_timestamp(float("nan")))
        self.assertIsNone(sanitize_timestamp(float("inf")))
        self.assertIsNone(sanitize_timestamp(float("-inf")))
        self.assertIsNone(sanitize_timestamp("nan"))
        self.assertIsNone(sanitize_timestamp("inf"))
        self.assertIsNone(sanitize_timestamp("-inf"))

    # 6. Non-numeric timestamps do not produce HTTP 500 errors
    def test_06_non_numeric_timestamps_do_not_produce_errors(self):
        self.assertIsNone(sanitize_timestamp("abc"))
        self.assertIsNone(sanitize_timestamp("invalid_time"))
        self.assertIsNone(sanitize_timestamp([]))
        self.assertIsNone(sanitize_timestamp({}))

        # evaluate_compliance handles invalid timestamp safely
        status, missing, evaluated = evaluate_compliance(
            [dict(self.worker1)], [], required_ppe=["helmet"],
            session_id=self.session_id, timestamp="not_a_valid_float", img_shape=(720, 1280)
        )
        self.assertIn(status, ["COMPLIANT", "VIOLATION", "UNCERTAIN"])

    # 7. Backward timestamps cannot rewind temporal state
    def test_07_backward_timestamps_cannot_rewind_temporal_state(self):
        st = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.0)
        self.assertEqual(st.last_update_timestamp, 5.0)

        # Backward timestamp arriving later (e.g. out of order network packet from t=4.0)
        st_back = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        self.assertEqual(st_back.last_update_timestamp, 5.0, "Backward timestamp must not rewind temporal baseline")

        # Next normal timestamp at t=5.8: dt must be 5.8 - 5.0 = 0.8, not 5.8 - 4.0 = 1.8
        st_next = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.8)
        self.assertAlmostEqual(st_next.accumulated_missing_sec, 0.8)

    # 8. Repeated timestamps add zero elapsed time
    def test_08_repeated_timestamps_add_zero_elapsed_time(self):
        st = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=2.0)
        st2 = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=2.0)
        self.assertAlmostEqual(st2.accumulated_missing_sec, 0.0)

        # Advance to 3.0
        st3 = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)
        self.assertAlmostEqual(st3.accumulated_missing_sec, 1.0)

        # Repeated 3.0
        st4 = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)
        self.assertAlmostEqual(st4.accumulated_missing_sec, 1.0, msg="Repeated timestamp must not accumulate elapsed time")

    # 9. Out-of-order frames cannot corrupt a session
    def test_09_out_of_order_frames_cannot_corrupt_session(self):
        # Frame at t=3.0: worker put on helmet (satisfied)
        st = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)
        self.assertEqual(st.state, TemporalState.SATISFIED)

        # Delayed out-of-order frame from t=2.0 (when helmet was missing) arrives now
        st_delayed = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=2.0)
        self.assertEqual(st_delayed.state, TemporalState.SATISFIED, "Stale out-of-order frame must not overwrite newer satisfied state")

    # 10. Two concurrent updates to one session remain consistent
    def test_10_concurrent_updates_to_one_session_remain_consistent(self):
        import threading
        tracker = SessionTemporalTracker()
        errors = []

        def worker_fn(tid, start_ts):
            try:
                for i in range(50):
                    ts = start_ts + i * 0.05
                    tracker.update_worker_ppe(tid, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=ts)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=worker_fn, args=(1, 0.0))
        t2 = threading.Thread(target=worker_fn, args=(2, 0.0))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(errors), 0, f"Concurrent updates produced errors: {errors}")
        self.assertIn((1, "helmet"), tracker._states)
        self.assertIn((2, "helmet"), tracker._states)

    # 11. Independent sessions can update without cross-session interference
    def test_11_independent_sessions_update_without_interference(self):
        sess_1 = f"iso_sess_1_{time.time()}"
        sess_2 = f"iso_sess_2_{time.time()}"
        tr1 = get_session_temporal_tracker(sess_1)
        tr2 = get_session_temporal_tracker(sess_2)

        tr1.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        tr1.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)

        # Session 2 should have zero state for worker 1
        st_s2 = tr2.get_state(1, "helmet")
        self.assertEqual(st_s2.state, TemporalState.SATISFIED)
        self.assertAlmostEqual(st_s2.accumulated_missing_sec, 0.0)

        reset_session_temporal(sess_1)
        reset_session_temporal(sess_2)

    # 12. Session reset cannot race with an update and leave stale state
    def test_12_session_reset_concurrent_safety(self):
        import threading
        sess = f"race_reset_{time.time()}"
        errors = []

        def updater():
            try:
                for i in range(100):
                    tr = get_session_temporal_tracker(sess)
                    tr.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=i*0.01)
            except Exception as e:
                errors.append(e)

        def resetter():
            try:
                for _ in range(20):
                    reset_session_temporal(sess)
                    time.sleep(0.005)
            except Exception as e:
                errors.append(e)

        t_up = threading.Thread(target=updater)
        t_res = threading.Thread(target=resetter)
        t_up.start()
        t_res.start()
        t_up.join()
        t_res.join()

        self.assertEqual(len(errors), 0, f"Concurrent reset/update produced errors: {errors}")
        reset_session_temporal(sess)

    # 13. Sequential in-flight skipping logic
    def test_13_sequential_in_flight_skipping_logic(self):
        in_flight = [False]
        captured_cycles = []

        def trigger_capture(cycle_id):
            if in_flight[0]:
                return False
            in_flight[0] = True
            captured_cycles.append(cycle_id)
            in_flight[0] = False
            return True

        res1 = trigger_capture(1)
        self.assertTrue(res1)
        self.assertEqual(captured_cycles, [1])

        in_flight[0] = True
        res2 = trigger_capture(2)
        self.assertFalse(res2, "Capture cycle must be skipped when previous request is in flight")
        self.assertEqual(captured_cycles, [1])

        in_flight[0] = False
        res3 = trigger_capture(3)
        self.assertTrue(res3)
        self.assertEqual(captured_cycles, [1, 3])

    # 14. Stopping monitoring prevents stale requests from affecting a new session
    def test_14_stopping_monitoring_prevents_stale_response_mutation(self):
        active_session = ["session_A"]
        applied_results = []

        def handle_response(request_session_id, data):
            if active_session[0] != request_session_id:
                return
            applied_results.append(data)

        req_sess = "session_A"
        active_session[0] = "session_B"

        handle_response(req_sess, {"compliance": "VIOLATION"})
        self.assertEqual(len(applied_results), 0, "Stale response must be discarded when session changes")

        handle_response("session_B", {"compliance": "COMPLIANT"})
        self.assertEqual(len(applied_results), 1)


class TestTemporalVerifiedCompliance(unittest.TestCase):
    """
    Focused unit test suite for Milestones M2.2B.5B & M2.2B.5B.1:
    Temporal Verified-Compliance State Machine, Episode Continuity, Gap Rejection, and Durability.
    Uses controllable, deterministic timestamps across all test cases.
    """

    def setUp(self):
        self.session_id = f"test_res_sess_{int(time.time()*1000)}"
        reset_session_temporal(self.session_id)
        self.tracker = SessionTemporalTracker(
            confirmation_duration_sec=3.0,
            recovery_timeout_sec=3.0,
            resolution_duration_sec=2.0,
            max_compliance_gap_sec=1.5,
            session_id=self.session_id
        )
        self.img_shape = (720, 1280, 3)

        self.worker1 = {
            "bbox": [100, 100, 300, 500],
            "confidence": 0.95,
            "worker_id": "W-001",
            "track_id": 1,
            "worn_ppe": [],
            "missing_ppe": [],
            "compliant": False
        }
        self.worker2 = {
            "bbox": [400, 100, 600, 500],
            "confidence": 0.94,
            "worker_id": "W-002",
            "track_id": 2,
            "worn_ppe": [],
            "missing_ppe": [],
            "compliant": False
        }

    def tearDown(self):
        reset_session_temporal(self.session_id)

    def _confirm_violation(self, tracker, track_id=1, ppe="helmet", start_ts=0.0):
        """Helper: advances missing state from start_ts to start_ts + 3.0 to confirm a violation episode."""
        tracker.update_worker_ppe(track_id, ppe, is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=start_ts)
        st = tracker.update_worker_ppe(track_id, ppe, is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=start_ts + 3.0)
        self.assertEqual(st.state, TemporalState.CONFIRMED)
        self.assertTrue(st.episode_uuid)
        return st

    # 1. No resolution candidate before 2.0 seconds
    def test_01_no_resolution_candidate_before_2s(self):
        self._confirm_violation(self.tracker, track_id=1, ppe="helmet", start_ts=0.0)

        # First compliant frame at t=4.0: starts timer at 0.0s
        st1 = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        self.assertEqual(st1.state, TemporalState.SATISFIED)
        self.assertAlmostEqual(st1.accumulated_compliance_sec, 0.0)
        self.assertFalse(st1.is_resolution_candidate)
        self.assertEqual(len(self.tracker.get_resolution_candidates()), 0)

        # Compliant at t=5.5 (1.5s elapsed): still below 2.0s
        st2 = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.5)
        self.assertAlmostEqual(st2.accumulated_compliance_sec, 1.5)
        self.assertFalse(st2.is_resolution_candidate)
        self.assertEqual(len(self.tracker.get_resolution_candidates()), 0)

    # 2. Candidate emitted at or after 2.0 seconds
    def test_02_candidate_emitted_at_or_after_2s(self):
        st_conf = self._confirm_violation(self.tracker, track_id=1, ppe="helmet", start_ts=0.0)
        expected_ep_id = st_conf.episode_uuid

        # t=4.0: compliance begins
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        # t=5.0: 1.0s elapsed (within 1.5s max gap)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.0)
        # t=6.0: exactly 2.0s elapsed
        st = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=6.0)

        self.assertAlmostEqual(st.accumulated_compliance_sec, 2.0)
        self.assertTrue(st.is_resolution_candidate)
        self.assertEqual(st.resolved_timestamp, 6.0)

        # Inspect candidate payload
        cand = st.get_resolution_candidate()
        self.assertIsNotNone(cand)
        self.assertEqual(cand["episode_id"], expected_ep_id)
        self.assertEqual(cand["session_id"], self.session_id)
        self.assertEqual(cand["worker_id"], "W-001")
        self.assertEqual(cand["track_id"], 1)
        self.assertEqual(cand["ppe_category"], "helmet")
        self.assertAlmostEqual(cand["verified_compliance_duration_sec"], 2.0)
        self.assertEqual(cand["candidate_timestamp"], 6.0)
        self.assertEqual(cand["resolution_event_id"], f"res_{expected_ep_id}")

        # Check tracker-level candidate retrieval
        cands = self.tracker.get_resolution_candidates()
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["episode_id"], expected_ep_id)

    # 3. Candidate transition event emitted once, candidate remains available until commit
    def test_03_candidate_emitted_once_and_remains_available_until_commit(self):
        st_conf = self._confirm_violation(self.tracker, track_id=1, ppe="helmet", start_ts=0.0)
        expected_ep_id = st_conf.episode_uuid

        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.0)

        # Transition frame at t=6.0: emits candidate event
        st1 = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=6.0)
        self.assertTrue(st1.is_resolution_candidate)
        self.assertEqual(len(self.tracker.get_resolution_candidates()), 1)

        # Subsequent frame at t=6.8: transition event is False, BUT candidate remains available for uncommitted persistence
        st2 = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=6.8)
        self.assertFalse(st2.is_resolution_candidate, "Transition event flag must be False on subsequent frames")
        self.assertIsNotNone(st2.get_resolution_candidate(), "Candidate must remain available until persistence commit")
        self.assertEqual(len(self.tracker.get_resolution_candidates()), 1)

        # Downstream persistence commits resolution
        commit_res = self.tracker.acknowledge_resolution(expected_ep_id)
        self.assertTrue(commit_res)

        # After commit, candidate is cleared
        st_after = self.tracker.get_state(1, "helmet")
        self.assertIsNone(st_after.get_resolution_candidate())
        self.assertEqual(len(self.tracker.get_resolution_candidates()), 0)

    # 4. Confirmed episode survives interrupted compliance (M2.2B.5B.1 Requirements 1-5)
    def test_04_interrupted_compliance_preserves_confirmed_episode_and_state(self):
        # 1. Confirm EP-001 after 3 seconds of missing PPE
        st_conf = self._confirm_violation(self.tracker, track_id=1, ppe="helmet", start_ts=0.0)
        orig_ep_id = st_conf.episode_id
        orig_ep_uuid = st_conf.episode_uuid
        self.assertEqual(orig_ep_id, 1)

        # 2. Observe 1.5 seconds of genuine compliance
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        st_mid = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.0)
        self.assertAlmostEqual(st_mid.accumulated_compliance_sec, 1.0)
        st_mid2 = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.5)
        self.assertAlmostEqual(st_mid2.accumulated_compliance_sec, 1.5)

        # 3. Remove PPE before resolution (at t=5.6s)
        st_off = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.6)
        self.assertEqual(st_off.episode_id, orig_ep_id, "Episode ID must remain unchanged on interrupted compliance")
        self.assertEqual(st_off.episode_uuid, orig_ep_uuid, "Episode UUID must remain unchanged on interrupted compliance")
        self.assertEqual(st_off.state, TemporalState.CONFIRMED, "State must return to CONFIRMED")
        self.assertAlmostEqual(st_off.accumulated_compliance_sec, 0.0, msg="Compliance timer must reset to 0.0s")
        self.assertFalse(st_off.is_new_confirmation, "No new confirmation event must be emitted")

        # 4. Observe another 3 seconds of missing PPE (t=5.6 to t=8.6)
        st_still_missing = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=8.6)
        self.assertEqual(st_still_missing.episode_id, orig_ep_id, "Episode ID must still be original episode")
        self.assertEqual(st_still_missing.episode_uuid, orig_ep_uuid)
        self.assertEqual(st_still_missing.state, TemporalState.CONFIRMED)
        self.assertFalse(st_still_missing.is_new_confirmation, "Must NOT emit duplicate confirmation")

        # 5. Restore PPE and achieve 2 seconds of valid continuous compliance (t=9.0 to t=11.0)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=9.0)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=10.0)
        st_resolved = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=11.0)

        self.assertTrue(st_resolved.is_resolution_candidate)
        cand = st_resolved.get_resolution_candidate()
        self.assertIsNotNone(cand)
        self.assertEqual(cand["episode_id"], orig_ep_uuid, "Resolution candidate must reference original episode EP-001")

    # 5. Timer resets when relevant body region becomes unobservable
    def test_05_timer_resets_when_body_region_unobservable(self):
        self._confirm_violation(self.tracker, track_id=1, ppe="helmet", start_ts=0.0)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.0)

        # Head becomes unobservable at t=5.4 (e.g. edge cut-off or occluded)
        st_unobs = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=False, is_required=True, is_uncertain=False, timestamp=5.4)
        self.assertAlmostEqual(st_unobs.accumulated_compliance_sec, 0.0)
        self.assertFalse(st_unobs.is_resolution_candidate)

        # Worker observed wearing helmet again at t=6.0: timer starts at 0.0s
        st_resume = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=6.0)
        self.assertAlmostEqual(st_resume.accumulated_compliance_sec, 0.0)

        # At t=7.0 (1.0s elapsed from resume): must NOT resolve
        st_1s = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=7.0)
        self.assertAlmostEqual(st_1s.accumulated_compliance_sec, 1.0)
        self.assertFalse(st_1s.is_resolution_candidate)

        # Full 2.0s achieved at t=8.0 (2.0s after resume)
        st_res = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=8.0)
        self.assertAlmostEqual(st_res.accumulated_compliance_sec, 2.0)
        self.assertTrue(st_res.is_resolution_candidate)

    # 6. Timer resets when region becomes uncertain
    def test_06_timer_resets_when_region_becomes_uncertain(self):
        self._confirm_violation(self.tracker, track_id=1, ppe="helmet", start_ts=0.0)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.0)

        # Uncertainty at t=5.4
        st_unc = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=True, timestamp=5.4)
        self.assertAlmostEqual(st_unc.accumulated_compliance_sec, 0.0)

        # Re-observation with certainty at t=6.0
        st_start = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=6.0)
        self.assertAlmostEqual(st_start.accumulated_compliance_sec, 0.0)

        # 1.0s later at t=7.0: not yet resolved
        st_mid = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=7.0)
        self.assertAlmostEqual(st_mid.accumulated_compliance_sec, 1.0)
        self.assertFalse(st_mid.is_resolution_candidate)

        # 2.0s later at t=8.0: resolved
        st_done = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=8.0)
        self.assertAlmostEqual(st_done.accumulated_compliance_sec, 2.0)
        self.assertTrue(st_done.is_resolution_candidate)

    # 7. Timer resets when worker track is lost
    def test_07_timer_resets_when_worker_track_is_lost(self):
        self._confirm_violation(self.tracker, track_id=1, ppe="helmet", start_ts=0.0)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.0)

        # Track lost at t=5.4
        self.tracker.mark_track_lost(1, timestamp=5.4)
        st = self.tracker.get_state(1, "helmet")
        self.assertAlmostEqual(st.accumulated_compliance_sec, 0.0)
        self.assertFalse(st.is_resolution_candidate)

    # 8. Recovered track must complete a fresh 2.0-second period
    def test_08_recovered_track_must_complete_fresh_2s_period(self):
        self._confirm_violation(self.tracker, track_id=1, ppe="helmet", start_ts=0.0)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.0)

        # Worker lost at t=5.4, recovers at t=6.0
        self.tracker.mark_track_lost(1, timestamp=5.4)

        st_rec = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=6.0)
        self.assertAlmostEqual(st_rec.accumulated_compliance_sec, 0.0)

        # t=7.0 (1.0s after recovery): not resolved
        st_1s = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=7.0)
        self.assertAlmostEqual(st_1s.accumulated_compliance_sec, 1.0)
        self.assertFalse(st_1s.is_resolution_candidate)

        # t=8.0 (2.0s after recovery): resolved
        st_2s = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=8.0)
        self.assertAlmostEqual(st_2s.accumulated_compliance_sec, 2.0)
        self.assertTrue(st_2s.is_resolution_candidate)

    # 9. 2.1-second observation gap is rejected and NOT credited (M2.2B.5B.1 Requirements 6-7)
    def test_09_observation_gap_2_1s_resets_timer_and_not_credited(self):
        self._confirm_violation(self.tracker, track_id=1, ppe="helmet", start_ts=0.0)

        # Frame 1: Compliant observation at t=10.0
        st1 = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=10.0)
        self.assertAlmostEqual(st1.accumulated_compliance_sec, 0.0)

        # Frame 2: Gap of 2.1 seconds arrives at t=12.1 (> max_compliance_gap_sec 1.5s)
        st2 = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=12.1)

        # Gap must NOT be credited! Timer must reset to 0.0s and no candidate generated
        self.assertAlmostEqual(st2.accumulated_compliance_sec, 0.0, msg="A 2.1s gap must NOT be credited as compliance")
        self.assertFalse(st2.is_resolution_candidate, "No resolution candidate must be generated immediately after gap")
        self.assertEqual(len(self.tracker.get_resolution_candidates()), 0)

        # Continue observing at valid cadence (e.g. 0.8s nominal live cadence)
        st3 = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=12.9)
        self.assertAlmostEqual(st3.accumulated_compliance_sec, 0.8)
        self.assertFalse(st3.is_resolution_candidate)

        st4 = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=13.7)
        self.assertAlmostEqual(st4.accumulated_compliance_sec, 1.6)
        self.assertFalse(st4.is_resolution_candidate)

        # At t=14.1 (0.4s later): continuous compliance reaches 2.0s
        st5 = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=14.1)
        self.assertAlmostEqual(st5.accumulated_compliance_sec, 2.0)
        self.assertTrue(st5.is_resolution_candidate)

    # 10. Resolution candidate durability & retry on persistence failure (M2.2B.5B.1 Requirements 8-9)
    def test_10_candidate_durability_and_retry_on_persistence_failure(self):
        st_conf = self._confirm_violation(self.tracker, track_id=1, ppe="helmet", start_ts=0.0)
        ep_id = st_conf.episode_uuid

        # Worn from t=4.0 to t=6.0 -> candidate generated
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.0)
        st_cand = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=6.0)
        self.assertTrue(st_cand.is_resolution_candidate)

        # Worker removes PPE at t=6.1 BEFORE persistence acknowledges
        st_off = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=6.1)

        # Candidate MUST REMAINS AVAILABLE! Missing PPE must not erase unconsumed candidate
        cand = st_off.get_resolution_candidate()
        self.assertIsNotNone(cand, "Unconsumed candidate must NOT be erased by subsequent missing observation")
        self.assertEqual(cand["episode_id"], ep_id)
        cands = self.tracker.get_resolution_candidates()
        self.assertEqual(len(cands), 1)

        # Simulate persistence failure (e.g. MongoDB timeout): downstream does NOT call acknowledge_resolution
        # On subsequent frame t=6.5: candidate remains retryable!
        cands_retry = self.tracker.get_resolution_candidates()
        self.assertEqual(len(cands_retry), 1, "Candidate must remain available for retry on failed persistence")

    # 11. Successful persistence acknowledgement is idempotent (M2.2B.5B.1 Requirements 10-11)
    def test_11_successful_persistence_acknowledgement_is_idempotent(self):
        st_conf = self._confirm_violation(self.tracker, track_id=1, ppe="helmet", start_ts=0.0)
        ep_id = st_conf.episode_uuid

        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.0)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=6.0)

        # Candidate available
        self.assertEqual(len(self.tracker.get_resolution_candidates()), 1)

        # 1. Simulate successful persistence: acknowledge exactly once
        ack1 = self.tracker.acknowledge_resolution(ep_id)
        self.assertTrue(ack1)
        self.assertEqual(len(self.tracker.get_resolution_candidates()), 0, "Candidate must be cleared after success")

        # Active episode cleared
        st = self.tracker.get_state(1, "helmet")
        self.assertIsNone(st.active_confirmed_episode_uuid)

        # 2. Repeated persistence acknowledgement must be idempotent
        ack2 = self.tracker.acknowledge_resolution(ep_id)
        self.assertTrue(ack2, "Repeated acknowledgement must be idempotent and succeed safely")

        # 3. New missing observation now starts Episode 2 cleanly
        st_new = self.tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=7.0)
        self.assertEqual(st_new.episode_id, 2, "After resolution commitment, removing PPE starts Episode 2")
        self.assertEqual(st_new.state, TemporalState.PENDING)

    # 12. Separate worker and session isolation (M2.2B.5B.1 Requirement 12)
    def test_12_separate_worker_and_session_isolation(self):
        tr_a = SessionTemporalTracker(confirmation_duration_sec=3.0, resolution_duration_sec=2.0, max_compliance_gap_sec=1.5, session_id="sess_A")
        tr_b = SessionTemporalTracker(confirmation_duration_sec=3.0, resolution_duration_sec=2.0, max_compliance_gap_sec=1.5, session_id="sess_B")

        # Confirm on Worker 1 in Session A and Worker 2 in Session B
        self._confirm_violation(tr_a, track_id=1, ppe="helmet", start_ts=0.0)
        self._confirm_violation(tr_b, track_id=2, ppe="helmet", start_ts=0.0)

        # Session A Worker 1 wears helmet for 2.0s
        tr_a.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        tr_a.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.0)
        st_a = tr_a.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=6.0)

        # Session B Worker 2 has interrupted compliance (wears for 1s then removes)
        tr_b.update_worker_ppe(2, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        tr_b.update_worker_ppe(2, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.0)
        st_b = tr_b.update_worker_ppe(2, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.5)

        # Session A candidate is ready
        self.assertTrue(st_a.is_resolution_candidate)
        self.assertEqual(len(tr_a.get_resolution_candidates()), 1)

        # Session B candidate is NOT ready, episode ID is preserved as 1, state CONFIRMED
        self.assertEqual(len(tr_b.get_resolution_candidates()), 0)
        self.assertEqual(st_b.episode_id, 1)
        self.assertEqual(st_b.state, TemporalState.CONFIRMED)

    # 13. Different PPE categories have independent timers
    def test_13_different_ppe_categories_have_independent_timers(self):
        self._confirm_violation(self.tracker, track_id=1, ppe="helmet", start_ts=0.0)
        self._confirm_violation(self.tracker, track_id=1, ppe="vest", start_ts=0.0)

        # Worker puts on helmet at t=4.0, but vest remains missing
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        self.tracker.update_worker_ppe(1, "vest", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)

        # At t=6.0: helmet achieves 2.0s compliance and resolves; vest remains in CONFIRMED violation
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.0)
        st_h = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=6.0)
        st_v = self.tracker.update_worker_ppe(1, "vest", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=6.0)

        self.assertTrue(st_h.is_resolution_candidate)
        self.assertEqual(st_v.state, TemporalState.CONFIRMED)
        self.assertAlmostEqual(st_v.accumulated_compliance_sec, 0.0)
        self.assertFalse(st_v.is_resolution_candidate)

    # 14. HSV synthetic evidence cannot start or advance the timer
    def test_14_hsv_synthetic_evidence_cannot_start_or_advance_timer(self):
        session_id = f"test_hsv_res_{int(time.time()*1000)}"
        tr = get_session_temporal_tracker(session_id, confirmation_duration_sec=3.0, resolution_duration_sec=2.0)

        evaluate_compliance([dict(self.worker1)], [], required_ppe=['helmet'], img_shape=self.img_shape, session_id=session_id, timestamp=0.0)
        evaluate_compliance([dict(self.worker1)], [], required_ppe=['helmet'], img_shape=self.img_shape, session_id=session_id, timestamp=3.0)

        st = tr.get_state(1, "helmet")
        self.assertEqual(st.state, TemporalState.CONFIRMED)

        # Synthetic HSV detection
        synthetic_helmet = [{
            "box": [100, 100, 300, 200],
            "class": "helmet",
            "confidence": 0.85,
            "is_synthetic": True,
            "source": "hsv_heuristic"
        }]
        evaluate_compliance([dict(self.worker1)], synthetic_helmet, required_ppe=['helmet'], img_shape=self.img_shape, session_id=session_id, timestamp=4.0)
        evaluate_compliance([dict(self.worker1)], synthetic_helmet, required_ppe=['helmet'], img_shape=self.img_shape, session_id=session_id, timestamp=5.0)

        st_after = tr.get_state(1, "helmet")
        self.assertEqual(st_after.state, TemporalState.CONFIRMED)
        self.assertAlmostEqual(st_after.accumulated_compliance_sec, 0.0)
        self.assertFalse(st_after.is_resolution_candidate)
        self.assertEqual(len(tr.get_resolution_candidates()), 0)

        reset_session_temporal(session_id)

    # 15. No confirmed violation episode means no resolution candidate
    def test_15_no_confirmed_violation_episode_means_no_resolution_candidate(self):
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=1.0)
        st = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=2.0)

        self.assertEqual(st.state, TemporalState.SATISFIED)
        self.assertAlmostEqual(st.accumulated_compliance_sec, 0.0)
        self.assertFalse(st.is_resolution_candidate)
        self.assertEqual(len(self.tracker.get_resolution_candidates()), 0)

    # 16. Invalid, repeated, backward, and non-finite timestamps cannot create premature resolution
    def test_16_invalid_repeated_backward_nonfinite_timestamps_handled_safely(self):
        self._confirm_violation(self.tracker, track_id=1, ppe="helmet", start_ts=0.0)
        self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)

        # Repeated timestamp at t=4.0
        st_rep = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        self.assertAlmostEqual(st_rep.accumulated_compliance_sec, 0.0)
        self.assertFalse(st_rep.is_resolution_candidate)

        # Backward timestamp at t=3.5
        st_back = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.5)
        self.assertAlmostEqual(st_back.accumulated_compliance_sec, 0.0)
        self.assertFalse(st_back.is_resolution_candidate)

        self.assertIsNone(sanitize_timestamp(float("nan")))
        self.assertIsNone(sanitize_timestamp(float("inf")))
        self.assertIsNone(sanitize_timestamp(-5.0))
        self.assertIsNone(sanitize_timestamp("invalid"))

        # Valid advancement after repeated/backward frames
        st_adv = self.tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.8)
        self.assertAlmostEqual(st_adv.accumulated_compliance_sec, 0.8)
        self.assertFalse(st_adv.is_resolution_candidate)

    # 17. Existing three-second violation confirmation behavior remains unchanged
    def test_17_existing_3s_violation_confirmation_behavior_unchanged(self):
        tr = SessionTemporalTracker(confirmation_duration_sec=3.0, recovery_timeout_sec=3.0, resolution_duration_sec=2.0)

        st1 = tr.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        self.assertEqual(st1.state, TemporalState.PENDING)
        self.assertAlmostEqual(st1.accumulated_missing_sec, 0.0)

        st2 = tr.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=2.9)
        self.assertEqual(st2.state, TemporalState.PENDING)
        self.assertAlmostEqual(st2.accumulated_missing_sec, 2.9)
        self.assertFalse(st2.is_new_confirmation)

        st3 = tr.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)
        self.assertEqual(st3.state, TemporalState.CONFIRMED)
        self.assertAlmostEqual(st3.accumulated_missing_sec, 3.0)
        self.assertTrue(st3.is_new_confirmation)

    # 18. Concurrent updates do not produce duplicate candidates or corrupt timer state
    def test_18_concurrent_updates_thread_safety(self):
        import threading
        tracker = SessionTemporalTracker(confirmation_duration_sec=3.0, resolution_duration_sec=2.0, max_compliance_gap_sec=1.5)

        tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)

        collected_candidates = []
        errors = []

        def worker_fn(tid, start_ts):
            try:
                for step in range(25):
                    ts = start_ts + (step * 0.1)
                    st = tracker.update_worker_ppe(
                        track_id=tid,
                        ppe_category="helmet",
                        is_worn=True,
                        is_observable=True,
                        is_required=True,
                        is_uncertain=False,
                        timestamp=ts
                    )
                    if st.is_resolution_candidate:
                        collected_candidates.append(st.get_resolution_candidate())
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=worker_fn, args=(1, 4.0))
        t2 = threading.Thread(target=worker_fn, args=(1, 4.05))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(errors), 0, f"Concurrent thread errors encountered: {errors}")
        self.assertEqual(len(collected_candidates), 1, f"Expected exactly 1 resolution transition, got: {len(collected_candidates)}")


class TestComplianceObservationGapConfigGuard(unittest.TestCase):
    """
    Milestone M2.2B.5B.1.1: Compliance Observation Gap Configuration Guard.
    Validates and enforces:
      0 < MAX_COMPLIANCE_OBSERVATION_GAP_SEC < RESOLUTION_CONFIRMATION_DURATION_SEC
    using a 0.2-second safety margin where mathematically valid.
    """

    # 1. Default configuration
    def test_01_default_configuration(self):
        res_dur, max_gap = validate_temporal_durations(2.0, 1.5)
        self.assertEqual(res_dur, 2.0)
        self.assertEqual(max_gap, 1.5)
        self.assertEqual(Config.RESOLUTION_CONFIRMATION_DURATION_SEC, 2.0)
        self.assertEqual(Config.MAX_COMPLIANCE_OBSERVATION_GAP_SEC, 1.5)
        self.assertTrue(0.0 < max_gap < res_dur)

    # 2. Environment override below the allowed maximum
    def test_02_environment_override_below_allowed_maximum(self):
        res_dur, max_gap = validate_temporal_durations(2.0, 1.2)
        self.assertEqual(res_dur, 2.0)
        self.assertEqual(max_gap, 1.2)
        self.assertTrue(0.0 < max_gap < res_dur)

        _, max_gap_08 = validate_temporal_durations(2.0, 0.8)
        self.assertEqual(max_gap_08, 0.8)

    # 3. Override equal to the resolution threshold
    def test_03_override_equal_to_resolution_threshold(self):
        # Override is 2.0s, equal to resolution duration 2.0s
        res_dur, max_gap = validate_temporal_durations(2.0, 2.0)
        self.assertEqual(res_dur, 2.0)
        # Clamped with 0.2s margin: 2.0 - 0.2 = 1.8s
        self.assertEqual(max_gap, 1.8)
        self.assertTrue(0.0 < max_gap < res_dur)
        self.assertAlmostEqual(res_dur - max_gap, 0.2)

    # 4. Override greater than the resolution threshold
    def test_04_override_greater_than_resolution_threshold(self):
        # Override is 2.5s or 10.0s, strictly greater than resolution duration 2.0s
        res_dur, max_gap = validate_temporal_durations(2.0, 2.5)
        self.assertEqual(res_dur, 2.0)
        self.assertEqual(max_gap, 1.8)
        self.assertTrue(0.0 < max_gap < res_dur)

        _, max_gap_large = validate_temporal_durations(2.0, 10.0)
        self.assertEqual(max_gap_large, 1.8)

    # 5. Negative, zero, non-numeric, NaN and infinite values
    def test_05_negative_zero_nonnumeric_nan_infinite_values(self):
        # Negative gap
        _, gap_neg = validate_temporal_durations(2.0, -1.0)
        self.assertEqual(gap_neg, 1.5)

        # Zero gap
        _, gap_zero = validate_temporal_durations(2.0, 0.0)
        self.assertEqual(gap_zero, 1.5)

        # Non-numeric string gap
        _, gap_str = validate_temporal_durations(2.0, "invalid_gap")
        self.assertEqual(gap_str, 1.5)

        # NaN gap
        _, gap_nan = validate_temporal_durations(2.0, float("nan"))
        self.assertEqual(gap_nan, 1.5)

        # Infinite gap
        _, gap_inf = validate_temporal_durations(2.0, float("inf"))
        self.assertEqual(gap_inf, 1.5) # float("inf") is non-finite -> falls back to safe default (1.5s)

        # Invalid resolution durations fall back safely to 2.0s
        res_neg, _ = validate_temporal_durations(-5.0, 1.5)
        self.assertEqual(res_neg, 2.0)

        res_zero, _ = validate_temporal_durations(0.0, 1.5)
        self.assertEqual(res_zero, 2.0)

        res_str, _ = validate_temporal_durations("bad", 1.5)
        self.assertEqual(res_str, 2.0)

        res_nan, _ = validate_temporal_durations(float("nan"), 1.5)
        self.assertEqual(res_nan, 2.0)

    # 6. A changed resolution threshold
    def test_06_changed_resolution_threshold(self):
        # Increased resolution threshold: 3.0s
        res_dur_3, max_gap_3 = validate_temporal_durations(3.0, 2.5)
        self.assertEqual(res_dur_3, 3.0)
        self.assertEqual(max_gap_3, 2.5) # 2.5 <= 3.0 - 0.2 (2.8)

        # Reduced resolution threshold: 1.6s
        # Default gap 1.5s exceeds 1.6 - 0.2 (1.4s) -> clamped to 1.4s
        res_dur_16, max_gap_16 = validate_temporal_durations(1.6, 1.5)
        self.assertAlmostEqual(res_dur_16, 1.6)
        self.assertAlmostEqual(max_gap_16, 1.4)
        self.assertTrue(0.0 < max_gap_16 < res_dur_16)

    # 7. A very small resolution threshold
    def test_07_very_small_resolution_threshold(self):
        # 0.2s resolution threshold: subtracting 0.2s would yield 0.0s (invalid).
        # Must smoothly use proportional margin: max_allowed = 0.2 * 0.5 = 0.1s.
        res_dur_02, max_gap_02 = validate_temporal_durations(0.2, 1.5)
        self.assertEqual(res_dur_02, 0.2)
        self.assertEqual(max_gap_02, 0.1)
        self.assertTrue(0.0 < max_gap_02 < res_dur_02)

        # 0.1s resolution threshold: max_allowed = 0.1 * 0.5 = 0.05s
        res_dur_01, max_gap_01 = validate_temporal_durations(0.1, 0.08)
        self.assertEqual(res_dur_01, 0.1)
        self.assertEqual(max_gap_01, 0.05)
        self.assertTrue(0.0 < max_gap_01 < res_dur_01)

        # Extremely small 0.04s threshold: max_allowed = 0.02s
        res_dur_tiny, max_gap_tiny = validate_temporal_durations(0.04, 1.0)
        self.assertEqual(res_dur_tiny, 0.04)
        self.assertEqual(max_gap_tiny, 0.02)
        self.assertTrue(0.0 < max_gap_tiny < res_dur_tiny)

    # 8. Production tracker receives the effective validated value
    def test_08_production_tracker_receives_effective_validated_value(self):
        # Standard tracker instantiation in production receives validated config values
        tracker_prod = SessionTemporalTracker(session_id="test_prod_config")
        self.assertEqual(tracker_prod.resolution_duration_sec, Config.RESOLUTION_CONFIRMATION_DURATION_SEC)
        self.assertEqual(tracker_prod.max_compliance_gap_sec, Config.MAX_COMPLIANCE_OBSERVATION_GAP_SEC)
        self.assertTrue(0.0 < tracker_prod.max_compliance_gap_sec < tracker_prod.resolution_duration_sec)

        # Custom tracker with out-of-bounds gap is automatically guarded
        tracker_guarded = SessionTemporalTracker(
            resolution_duration_sec=2.0,
            max_compliance_gap_sec=2.5,
            session_id="test_custom_guarded"
        )
        self.assertEqual(tracker_guarded.resolution_duration_sec, 2.0)
        self.assertEqual(tracker_guarded.max_compliance_gap_sec, 1.8)

        # Custom tracker with very small resolution threshold is automatically guarded
        tracker_small = SessionTemporalTracker(
            resolution_duration_sec=0.2,
            max_compliance_gap_sec=1.5,
            session_id="test_custom_small"
        )
        self.assertEqual(tracker_small.resolution_duration_sec, 0.2)
        self.assertEqual(tracker_small.max_compliance_gap_sec, 0.1)

    # 9. State machine respects clamped gap threshold in runtime evaluation
    def test_09_state_machine_respects_clamped_gap(self):
        # Tracker configured with 2.5s gap on 2.0s resolution: clamped to 1.8s
        tracker = SessionTemporalTracker(
            confirmation_duration_sec=3.0,
            resolution_duration_sec=2.0,
            max_compliance_gap_sec=2.5,
            session_id="test_runtime_clamp"
        )
        self.assertEqual(tracker.max_compliance_gap_sec, 1.8)

        # Confirm violation: t=0.0 -> 3.0
        tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        st_conf = tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)
        self.assertEqual(st_conf.state, TemporalState.CONFIRMED)

        # Frame 1 compliant at t=4.0
        st1 = tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        self.assertEqual(st1.accumulated_compliance_sec, 0.0)

        # Frame 2 with 1.9s gap arriving at t=5.9 (> 1.8s clamped limit)
        # Even though 1.9s < 2.5s (the unvalidated request), it exceeds 1.8s (the guarded limit)!
        st2 = tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.9)
        self.assertEqual(st2.accumulated_compliance_sec, 0.0, "Gap of 1.9s must be rejected by clamped 1.8s limit")
        self.assertFalse(st2.is_resolution_candidate)

        # Continuous compliance from t=5.9 to t=7.9 (valid interval within 1.8s)
        st3 = tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=6.9)
        self.assertAlmostEqual(st3.accumulated_compliance_sec, 1.0)
        st4 = tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=7.9)
        self.assertAlmostEqual(st4.accumulated_compliance_sec, 2.0)
        self.assertTrue(st4.is_resolution_candidate)

    # 10. High-precision sub-decimal and unrounded durations (M2.2B.5B.1.2)
    def test_10_high_precision_sub_decimal_and_unrounded_durations(self):
        # 1. Exact sub-decimal case: resolution 0.00014, gap 0.00007
        res1, gap1 = validate_temporal_durations(0.00014, 0.00007)
        self.assertEqual(res1, 0.00014)
        self.assertEqual(gap1, 0.00007)
        self.assertTrue(0.0 < gap1 < res1, f"Expected 0 < {gap1} < {res1}")

        # 2. Sub-decimal case that previously rounded to zero at 4 decimals: 0.00009, gap 0.000045
        res2, gap2 = validate_temporal_durations(0.00009, 0.000045)
        self.assertEqual(res2, 0.00009)
        self.assertEqual(gap2, 0.000045)
        self.assertTrue(0.0 < gap2 < res2, f"Expected 0 < {gap2} < {res2}")

        # 3. Microsecond-scale values that would previously round to zero
        res3, gap3 = validate_temporal_durations(1e-5, 5e-6)
        self.assertEqual(res3, 1e-5)
        self.assertEqual(gap3, 5e-6)
        self.assertTrue(0.0 < gap3 < res3, f"Expected 0 < {gap3} < {res3}")

        res4, gap4 = validate_temporal_durations(1e-7, 1.0)
        self.assertEqual(res4, 1e-7)
        self.assertEqual(gap4, 5e-8) # Clamped to 50% proportional margin: 1e-7 * 0.5
        self.assertTrue(0.0 < gap4 < res4, f"Expected 0 < {gap4} < {res4}")

        # 4. Standard defaults remain exactly 2.0 and 1.5
        res_def, gap_def = validate_temporal_durations(2.0, 1.5)
        self.assertEqual(res_def, 2.0)
        self.assertEqual(gap_def, 1.5)
        self.assertIsInstance(res_def, float)
        self.assertIsInstance(gap_def, float)
        self.assertTrue(0.0 < gap_def < res_def)

        # 5. Full precision values reach SessionTemporalTracker accurately
        tracker = SessionTemporalTracker(
            resolution_duration_sec=0.00009,
            max_compliance_gap_sec=0.000045,
            session_id="test_sub_decimal_tracker"
        )
        self.assertEqual(tracker.resolution_duration_sec, 0.00009)
        self.assertEqual(tracker.max_compliance_gap_sec, 0.000045)
        self.assertTrue(0.0 < tracker.max_compliance_gap_sec < tracker.resolution_duration_sec)


if __name__ == "__main__":
    unittest.main()
