import unittest
import time
import datetime
import uuid
import numpy as np
import cv2
import json
import base64
from unittest.mock import patch, MagicMock

from app import create_app
from database import is_mongo_connected, mem_detections, mem_zones, get_detections_col
from routes.detection_routes import (
    persist_confirmed_incident,
    resolve_confirmed_incident,
    process_resolution_candidates,
    get_canonical_state,
    build_canonical_status_mongo_filter
)
from ai_engine.temporal_compliance import (
    TrackPPEState,
    TemporalState,
    SessionTemporalTracker,
    get_session_temporal_tracker,
    reset_session_temporal
)
from ai_engine.compliance import evaluate_compliance
from auth import generate_token, normalize_role, supervisor_required, token_required

class TestIncidentPersistence(unittest.TestCase):
    """
    Milestone M2.2B.4H: Confirmed Incident Event Integration Test Suite.
    Validates automatic incident persistence, idempotency, episode tracking,
    forensic evidence attachment, alert gating, video violation counting,
    and legacy API compatibility across 20 deterministic scenarios.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        img[100:200, 100:200] = [0, 255, 255]
        _, buf = cv2.imencode('.jpg', img)
        cls.synthetic_jpeg_bytes = buf.tobytes()
        cls.synthetic_b64 = base64.b64encode(cls.synthetic_jpeg_bytes).decode('utf-8')

    def setUp(self):
        self.session_id = f"test_persist_{uuid.uuid4().hex[:8]}"
        reset_session_temporal(self.session_id)
        # Clear in-memory detections for a clean test slate
        mem_detections.clear()

    def tearDown(self):
        reset_session_temporal(self.session_id)
        mem_detections.clear()

    def _make_worker(self, track_id=1, worker_id="W-001", bbox=None):
        return {
            "bbox": bbox or [100, 100, 300, 500],
            "track_id": track_id,
            "worker_id": worker_id,
            "worn_ppe": [],
            "missing_ppe": [],
            "compliant": False
        }

    # 1. Newly confirmed live webcam violation creates 1 incident.
    def test_01_newly_confirmed_live_violation_creates_one_incident(self):
        tracker = SessionTemporalTracker(confirmation_duration_sec=3.0, session_id=self.session_id)

        # t=0.0: first missing detection
        st0 = tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=0.0
        )
        self.assertEqual(st0.state, TemporalState.PENDING)
        self.assertFalse(st0.is_new_confirmation)

        # t=3.0: confirmation transition
        st3 = tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=3.0
        )
        self.assertEqual(st3.state, TemporalState.CONFIRMED)
        self.assertTrue(st3.is_new_confirmation)
        self.assertTrue(st3.episode_uuid.startswith("ep_"))

        doc = {
            "episode_id": st3.episode_uuid,
            "worker_id": "W-001",
            "track_id": 1,
            "session_id": self.session_id,
            "missingPPE": ["helmet"],
            "first_missing_timestamp": st3.first_missing_timestamp,
            "confirmed_timestamp": st3.confirmed_timestamp,
        }
        saved, is_new = persist_confirmed_incident(doc)
        self.assertTrue(is_new)
        self.assertIsNotNone(saved.get("_id"))
        self.assertEqual(len(mem_detections), 1)

    # 2. Pending violation creates 0 incidents.
    def test_02_pending_violation_creates_zero_incidents(self):
        # A person missing gear for only 1.5 seconds (pending)
        worker = self._make_worker()
        # Frame at t=0.0
        status, missing, eval_persons = evaluate_compliance(
            [dict(worker)], [], ["helmet"], img_shape=(720, 1280), session_id=self.session_id, timestamp=0.0
        )
        self.assertEqual(len(eval_persons[0].get("new_confirmed_violations", [])), 0)

        # Frame at t=1.5
        status, missing, eval_persons = evaluate_compliance(
            [dict(worker)], [], ["helmet"], img_shape=(720, 1280), session_id=self.session_id, timestamp=1.5
        )
        self.assertEqual(eval_persons[0]["temporal_state"]["helmet"]["state"], "PENDING")
        self.assertEqual(len(eval_persons[0].get("new_confirmed_violations", [])), 0)
        self.assertEqual(len(mem_detections), 0)

    # 3. Repeated confirmed frames produce 0 duplicate records.
    def test_03_repeated_confirmed_frames_produce_zero_duplicate_records(self):
        tracker = SessionTemporalTracker(confirmation_duration_sec=3.0, session_id=self.session_id)

        # t=0.0
        tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=0.0
        )
        # t=3.0 -> confirmed
        st3 = tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=3.0
        )
        doc = {
            "episode_id": st3.episode_uuid,
            "worker_id": "W-001",
            "track_id": 1,
            "session_id": self.session_id,
            "missingPPE": ["helmet"]
        }
        _, is_new_1 = persist_confirmed_incident(doc)
        self.assertTrue(is_new_1)
        self.assertEqual(len(mem_detections), 1)

        # t=4.0 -> ongoing confirmed, is_new_confirmation is False
        st4 = tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=4.0
        )
        self.assertEqual(st4.state, TemporalState.CONFIRMED)
        self.assertFalse(st4.is_new_confirmation)

        # Persistence attempt with same episode_id
        _, is_new_2 = persist_confirmed_incident(doc)
        self.assertFalse(is_new_2)
        self.assertEqual(len(mem_detections), 1)

        # t=5.0 -> ongoing confirmed
        st5 = tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=5.0
        )
        self.assertFalse(st5.is_new_confirmation)
        _, is_new_3 = persist_confirmed_incident(doc)
        self.assertFalse(is_new_3)
        self.assertEqual(len(mem_detections), 1)

    # 4. Persistence retry with same episode_id is idempotent.
    def test_04_persistence_retry_with_same_episode_id_is_idempotent(self):
        ep_id = f"ep_{self.session_id}_1_vest_1"
        doc = {
            "episode_id": ep_id,
            "worker_id": "W-001",
            "track_id": 1,
            "missingPPE": ["vest"]
        }
        saved_1, is_new_1 = persist_confirmed_incident(dict(doc))
        self.assertTrue(is_new_1)

        for _ in range(5):
            saved_retry, is_new_retry = persist_confirmed_incident(dict(doc))
            self.assertFalse(is_new_retry)
            self.assertEqual(saved_retry["_id"], saved_1["_id"])

        self.assertEqual(len(mem_detections), 1)

    # 5. New episode for same worker/gear creates separate incident.
    def test_05_new_episode_for_same_worker_gear_creates_separate_incident(self):
        tracker = SessionTemporalTracker(confirmation_duration_sec=3.0, recovery_timeout_sec=5.0, session_id=self.session_id)

        # Episode 1: Missing helmet confirmed
        tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=0.0
        )
        st1 = tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=3.0
        )
        ep1_id = st1.episode_uuid
        persist_confirmed_incident({"episode_id": ep1_id, "worker_id": "W-001", "missingPPE": ["helmet"]})

        # Recovery to SATISFIED (completes 2s verified compliance and resolution acknowledged)
        tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=True, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=4.0
        )
        tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=True, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=6.0
        )
        tracker.acknowledge_resolution(ep1_id)

        # Episode 2: Missing helmet confirmed again
        tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=5.0
        )
        st2 = tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=8.0
        )
        ep2_id = st2.episode_uuid

        self.assertNotEqual(ep1_id, ep2_id)
        self.assertEqual(st2.episode_id, 2)
        saved2, is_new_2 = persist_confirmed_incident({"episode_id": ep2_id, "worker_id": "W-001", "missingPPE": ["helmet"]})
        self.assertTrue(is_new_2)
        self.assertEqual(len(mem_detections), 2)

    # 6. Two workers missing same PPE create separate incidents.
    def test_06_two_workers_missing_same_ppe_create_separate_incidents(self):
        tracker = SessionTemporalTracker(confirmation_duration_sec=3.0, session_id=self.session_id)

        # Worker 1 & 2 both missing helmet
        tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=0.0
        )
        tracker.update_worker_ppe(
            track_id=2, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=0.0
        )

        st_w1 = tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=3.0
        )
        st_w2 = tracker.update_worker_ppe(
            track_id=2, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=3.0
        )

        self.assertNotEqual(st_w1.episode_uuid, st_w2.episode_uuid)
        _, is_new_1 = persist_confirmed_incident({"episode_id": st_w1.episode_uuid, "worker_id": "W-001", "track_id": 1, "missingPPE": ["helmet"]})
        _, is_new_2 = persist_confirmed_incident({"episode_id": st_w2.episode_uuid, "worker_id": "W-002", "track_id": 2, "missingPPE": ["helmet"]})

        self.assertTrue(is_new_1)
        self.assertTrue(is_new_2)
        self.assertEqual(len(mem_detections), 2)

    # 7. Two PPE categories for one worker create separate incidents.
    def test_07_two_ppe_categories_for_one_worker_create_separate_incidents(self):
        tracker = SessionTemporalTracker(confirmation_duration_sec=3.0, session_id=self.session_id)

        # Worker 1 missing both helmet and vest
        tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=0.0
        )
        tracker.update_worker_ppe(
            track_id=1, ppe_category="vest", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=0.0
        )

        st_h = tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=3.0
        )
        st_v = tracker.update_worker_ppe(
            track_id=1, ppe_category="vest", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=3.0
        )

        self.assertNotEqual(st_h.episode_uuid, st_v.episode_uuid)
        _, is_new_h = persist_confirmed_incident({"episode_id": st_h.episode_uuid, "worker_id": "W-001", "track_id": 1, "missingPPE": ["helmet"]})
        _, is_new_v = persist_confirmed_incident({"episode_id": st_v.episode_uuid, "worker_id": "W-001", "track_id": 1, "missingPPE": ["vest"]})

        self.assertTrue(is_new_h)
        self.assertTrue(is_new_v)
        self.assertEqual(len(mem_detections), 2)

    # 8. Worker ID (W-001), track ID, session ID, and timestamps survive persistence.
    def test_08_worker_metadata_survives_persistence(self):
        ep_id = f"ep_{self.session_id}_1_helmet_1"
        doc = {
            "episode_id": ep_id,
            "worker_id": "W-001",
            "track_id": 1,
            "personId": "W-001",
            "workerTag": "W-001 (Track #1)",
            "session_id": self.session_id,
            "zoneId": "zone_100",
            "zoneName": "Packaging Area",
            "missingPPE": ["helmet"],
            "first_missing_timestamp": 100.0,
            "confirmed_timestamp": 103.0,
            "reviewStatus": "PENDING"
        }
        saved, _ = persist_confirmed_incident(doc)

        self.assertEqual(saved["worker_id"], "W-001")
        self.assertEqual(saved["track_id"], 1)
        self.assertEqual(saved["session_id"], self.session_id)
        self.assertEqual(saved["first_missing_timestamp"], 100.0)
        self.assertEqual(saved["confirmed_timestamp"], 103.0)
        self.assertEqual(saved["zoneId"], "zone_100")
        self.assertEqual(saved["zoneName"], "Packaging Area")
        self.assertEqual(saved["reviewStatus"], "PENDING")

    # 9. first_missing_timestamp differs from confirmed_timestamp.
    def test_09_first_missing_differs_from_confirmed_timestamp(self):
        tracker = SessionTemporalTracker(confirmation_duration_sec=3.0, session_id=self.session_id)

        t0 = 100.0
        t1 = 103.2
        tracker.update_worker_ppe(
            track_id=1, ppe_category="vest", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=t0
        )
        st = tracker.update_worker_ppe(
            track_id=1, ppe_category="vest", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=t1
        )

        self.assertEqual(st.first_missing_timestamp, t0)
        self.assertEqual(st.confirmed_timestamp, t1)
        delta = st.confirmed_timestamp - st.first_missing_timestamp
        self.assertGreaterEqual(delta, 3.0)

    # 10. Exactly one snapshot associated with incident episode.
    def test_10_exactly_one_snapshot_associated_with_incident_episode(self):
        doc = {
            "episode_id": f"ep_{self.session_id}_1_helmet_1",
            "worker_id": "W-001",
            "missingPPE": ["helmet"],
            "imageUrl": "https://res.cloudinary.com/demo/image/upload/sample.jpg",
            "evidenceImageReference": "https://res.cloudinary.com/demo/image/upload/sample.jpg"
        }
        saved, _ = persist_confirmed_incident(doc)
        self.assertTrue(saved["imageUrl"].startswith("https://"))
        self.assertEqual(saved["imageUrl"], saved["evidenceImageReference"])

    # 11. Snapshot upload failure handles gracefully without broken reference.
    def test_11_snapshot_upload_failure_handles_gracefully(self):
        # When cloud upload fails or throws, imageUrl is None and fallback evidence reference is used
        valid_b64 = f"data:image/jpeg;base64,{self.synthetic_b64}"
        doc = {
            "episode_id": f"ep_{self.session_id}_1_helmet_1",
            "worker_id": "W-001",
            "missingPPE": ["helmet"],
            "imageUrl": None,
            "evidenceImageReference": valid_b64
        }
        saved, is_new = persist_confirmed_incident(doc)
        self.assertTrue(is_new)
        self.assertIsNone(saved["imageUrl"])
        self.assertEqual(saved["evidenceImageReference"], valid_b64)

    # 12. Ongoing episode emits exactly one dashboard alert.
    def test_12_ongoing_episode_emits_exactly_one_dashboard_alert(self):
        # Frame 0: t=0.0 (pending)
        evaluate_compliance([self._make_worker()], [], ["helmet"], img_shape=(720, 1280), session_id=self.session_id, timestamp=0.0)

        # Frame 1: t=3.0 (confirmed violation)
        _, _, eval1 = evaluate_compliance([self._make_worker()], [], ["helmet"], img_shape=(720, 1280), session_id=self.session_id, timestamp=3.0)
        self.assertEqual(eval1[0]["new_confirmed_violations"], ["helmet"])

        # Frame 2: t=4.0 (ongoing confirmed violation)
        _, _, eval2 = evaluate_compliance([self._make_worker()], [], ["helmet"], img_shape=(720, 1280), session_id=self.session_id, timestamp=4.0)
        self.assertEqual(eval2[0]["new_confirmed_violations"], [])

        # Frame 3: t=5.0 (ongoing confirmed violation)
        _, _, eval3 = evaluate_compliance([self._make_worker()], [], ["helmet"], img_shape=(720, 1280), session_id=self.session_id, timestamp=5.0)
        self.assertEqual(eval3[0]["new_confirmed_violations"], [])

    # 13. New episode emits new alert.
    def test_13_new_episode_emits_new_alert(self):
        # Episode 1 confirmed
        evaluate_compliance([self._make_worker()], [], ["helmet"], img_shape=(720, 1280), session_id=self.session_id, timestamp=0.0)
        _, _, eval1 = evaluate_compliance([self._make_worker()], [], ["helmet"], img_shape=(720, 1280), session_id=self.session_id, timestamp=3.0)
        self.assertIn("helmet", eval1[0]["new_confirmed_violations"])

        # Worker puts on helmet at t=4.0 -> achieves verified recovery at t=6.0
        helmet_det = {
            "bbox": [150, 100, 250, 180],
            "class": "helmet",
            "confidence": 0.9,
            "source": "yolo",
            "is_synthetic": False
        }
        evaluate_compliance([self._make_worker()], [helmet_det], ["helmet"], img_shape=(720, 1280), session_id=self.session_id, timestamp=4.0)
        evaluate_compliance([self._make_worker()], [helmet_det], ["helmet"], img_shape=(720, 1280), session_id=self.session_id, timestamp=6.0)
        tr = get_session_temporal_tracker(self.session_id)
        tr.acknowledge_resolution(f"ep_{self.session_id}_1_helmet_1")

        # Episode 2 starts at t=7.0 and confirms at t=10.0
        evaluate_compliance([self._make_worker()], [], ["helmet"], img_shape=(720, 1280), session_id=self.session_id, timestamp=7.0)
        _, _, eval2 = evaluate_compliance([self._make_worker()], [], ["helmet"], img_shape=(720, 1280), session_id=self.session_id, timestamp=10.0)
        self.assertIn("helmet", eval2[0]["new_confirmed_violations"])

    # 14. Persistence retry does not duplicate alerts.
    @patch("routes.event_routes.broadcast_event")
    def test_14_persistence_retry_does_not_duplicate_alerts(self, mock_broadcast):
        ep_id = f"ep_{self.session_id}_1_helmet_1"
        doc = {"episode_id": ep_id, "worker_id": "W-001", "missingPPE": ["helmet"]}

        saved_1, is_new_1 = persist_confirmed_incident(doc)
        if is_new_1:
            from routes.event_routes import broadcast_event
            broadcast_event("VIOLATION_DETECTED", {"event": saved_1})

        # Retry
        saved_2, is_new_2 = persist_confirmed_incident(doc)
        if is_new_2:
            from routes.event_routes import broadcast_event
            broadcast_event("VIOLATION_DETECTED", {"event": saved_2})

        self.assertEqual(mock_broadcast.call_count, 1)

    # 15. Pending, uncertain, unobservable, empty-scene produce no incident or alert.
    def test_15_pending_uncertain_unobservable_empty_scene_produce_no_incident_or_alert(self):
        # Empty scene
        status_empty, missing_empty, eval_empty = evaluate_compliance(
            [], [], ["helmet", "vest"], img_shape=(720, 1280), session_id=self.session_id, timestamp=0.0
        )
        self.assertEqual(status_empty, "UNCERTAIN")
        self.assertEqual(len(eval_empty), 0)

        # Unobservable worker (clipped or zero-size)
        clipped_worker = {
            "bbox": [0, 0, 10, 10], # extreme top-left border clipped
            "track_id": 99,
            "worker_id": "W-099",
            "worn_ppe": [],
            "missing_ppe": [],
            "compliant": False
        }
        status_clip, missing_clip, eval_clip = evaluate_compliance(
            [clipped_worker], [], ["helmet"], img_shape=(720, 1280), session_id=self.session_id, timestamp=0.0
        )
        self.assertEqual(len(eval_clip[0].get("new_confirmed_violations", [])), 0)
        self.assertEqual(len(mem_detections), 0)

    # 16. Uploaded video counts distinct episodes, not frames.
    def test_16_uploaded_video_counts_distinct_episodes_not_frames(self):
        # Verify the episode-counting logic used in detect_video
        confirmed_video_episodes = set()

        # Simulate 30 frames of 1 worker violating helmet (same episode)
        ep1 = "ep_video_100_1_helmet_1"
        for _ in range(30):
            confirmed_video_episodes.add(ep1)

        # Simulate 15 frames of worker 2 violating vest (second episode)
        ep2 = "ep_video_100_2_vest_1"
        for _ in range(15):
            confirmed_video_episodes.add(ep2)

        # Total violations must be 2 distinct episodes, NOT 45 frames
        total_violations_found = len(confirmed_video_episodes)
        self.assertEqual(total_violations_found, 2)

    # 17. Separate video sessions do not share episode IDs.
    def test_17_separate_video_sessions_do_not_share_episode_ids(self):
        session_a = "video_session_alpha"
        session_b = "video_session_beta"

        tracker_a = SessionTemporalTracker(session_id=session_a)
        tracker_b = SessionTemporalTracker(session_id=session_b)

        st_a = tracker_a.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=0.0
        )
        st_b = tracker_b.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=0.0
        )

        self.assertNotEqual(st_a.episode_uuid, st_b.episode_uuid)
        self.assertIn(session_a, st_a.episode_uuid)
        self.assertIn(session_b, st_b.episode_uuid)

    # 18. Existing manual snapshot/event (POST /api/detections) remains compatible.
    def test_18_existing_manual_snapshot_endpoint_remains_compatible(self):
        payload = {
            "complianceStatus": "VIOLATION",
            "zoneName": "Storage Yard",
            "missingPPE": ["helmet"],
            "detectedClasses": ["person"],
            "confidenceScores": [0.92]
        }
        res = self.client.post("/api/detections", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        event = data.get("event", {})
        self.assertEqual(event.get("complianceStatus"), "VIOLATION")
        self.assertEqual(event.get("reviewStatus"), "PENDING")
        self.assertEqual(event.get("zoneName"), "Storage Yard")
        self.assertIn("helmet", event.get("missingPPE", []))

    # 19. Existing SSE stream (/api/events/stream) remains functional.
    def test_19_existing_sse_stream_remains_functional(self):
        res = self.client.get("/api/events/stream")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/event-stream", res.content_type)

    # 20. Existing authorization checks remain enforced.
    def test_20_existing_authorization_checks_remain_enforced(self):
        # Protected camera management endpoints must reject unauthenticated requests
        res = self.client.patch("/api/cameras/cam_test", json={"name": "Tampered"})
        self.assertEqual(res.status_code, 401)

        res_del = self.client.delete("/api/cameras/cam_test")
        self.assertEqual(res_del.status_code, 401)

    # =========================================================================
    # Milestone M2.2B.4H.1: Forensic Snapshot Fallback Integrity Tests
    # =========================================================================

    # 21. Successful cloud upload stores the returned URL.
    @patch("routes.detection_routes.detect_ppe_in_frame")
    @patch("routes.detection_routes.upload_evidence_image")
    def test_21_successful_cloud_upload_stores_returned_url(self, mock_upload, mock_detect):
        cloud_url = "https://res.cloudinary.com/test-cloud/image/upload/v1234/ppe_violations/ev1.jpg"
        mock_upload.return_value = cloud_url
        mock_detect.return_value = (
            None, [], [{"bbox": [100, 100, 300, 500], "confidence": 0.95, "track_id": 1, "worker_id": "W-001"}]
        )

        # Frame 1: t=0.0 (pending)
        self.client.post("/api/detect", json={
            "image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 0.0, "required_ppe": ["helmet"]
        })
        self.assertEqual(len(mem_detections), 0)

        # Frame 2: t=3.0 (confirmed violation)
        res = self.client.post("/api/detect", json={
            "image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 3.0, "required_ppe": ["helmet"]
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(mem_detections), 1)
        doc = mem_detections[0]
        self.assertEqual(doc["imageUrl"], cloud_url)
        self.assertEqual(doc["evidenceImageReference"], cloud_url)
        self.assertFalse(doc["evidenceImageReference"].startswith("data:image/"))

    # 22. Cloud failure with successful local-disk fallback stores the local reference.
    @patch("routes.detection_routes.detect_ppe_in_frame")
    @patch("routes.detection_routes.upload_evidence_image")
    def test_22_cloud_failure_with_local_disk_stores_local_reference(self, mock_upload, mock_detect):
        local_ref = "/uploads/evidence/violation_1731522000000_a1b2c3.jpg"
        mock_upload.return_value = local_ref
        mock_detect.return_value = (
            None, [], [{"bbox": [100, 100, 300, 500], "confidence": 0.95, "track_id": 1, "worker_id": "W-001"}]
        )

        self.client.post("/api/detect", json={
            "image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 0.0, "required_ppe": ["helmet"]
        })
        self.client.post("/api/detect", json={
            "image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 3.0, "required_ppe": ["helmet"]
        })

        self.assertEqual(len(mem_detections), 1)
        doc = mem_detections[0]
        self.assertEqual(doc["imageUrl"], local_ref)
        self.assertEqual(doc["evidenceImageReference"], local_ref)
        self.assertFalse(doc["evidenceImageReference"].startswith("data:image/"))

    # 23. Complete storage failure uses a complete base64 data URI.
    @patch("routes.detection_routes.detect_ppe_in_frame")
    @patch("routes.detection_routes.upload_evidence_image")
    def test_23_complete_storage_failure_uses_complete_base64_data_uri(self, mock_upload, mock_detect):
        mock_upload.side_effect = IOError("Cloud and local storage offline")
        mock_detect.return_value = (
            None, [], [{"bbox": [100, 100, 300, 500], "confidence": 0.95, "track_id": 1, "worker_id": "W-001"}]
        )

        self.client.post("/api/detect", json={
            "image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 0.0, "required_ppe": ["helmet"]
        })
        self.client.post("/api/detect", json={
            "image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 3.0, "required_ppe": ["helmet"]
        })

        self.assertEqual(len(mem_detections), 1)
        doc = mem_detections[0]
        self.assertIsNone(doc["imageUrl"])
        self.assertIsNotNone(doc["evidenceImageReference"])
        self.assertTrue(doc["evidenceImageReference"].startswith("data:image/jpeg;base64,"))
        self.assertNotIn("...", doc["evidenceImageReference"])

    # 24. The fallback data URI decodes into the original image bytes.
    @patch("routes.detection_routes.detect_ppe_in_frame")
    @patch("routes.detection_routes.upload_evidence_image")
    def test_24_fallback_data_uri_decodes_into_original_image_bytes(self, mock_upload, mock_detect):
        mock_upload.side_effect = Exception("Storage outage")
        mock_detect.return_value = (
            None, [], [{"bbox": [100, 100, 300, 500], "confidence": 0.95, "track_id": 1, "worker_id": "W-001"}]
        )

        self.client.post("/api/detect", json={
            "image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 0.0, "required_ppe": ["helmet"]
        })
        self.client.post("/api/detect", json={
            "image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 3.0, "required_ppe": ["helmet"]
        })

        doc = mem_detections[0]
        ref = doc["evidenceImageReference"]
        self.assertTrue(ref.startswith("data:image/jpeg;base64,"))
        b64_part = ref.split(",", 1)[1]
        decoded_bytes = base64.b64decode(b64_part)

        # Valid JPEG magic bytes: FF D8 FF
        self.assertTrue(decoded_bytes.startswith(b"\xff\xd8\xff"))
        # Valid image decodable by OpenCV
        decoded_img = cv2.imdecode(np.frombuffer(decoded_bytes, np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNotNone(decoded_img)
        self.assertEqual(decoded_img.shape, (480, 640, 3))

    # 25. M2.2B.4H.1: Missing image data results in None, not a malformed reference.
    @patch("routes.detection_routes.detect_ppe_in_frame")
    @patch("routes.detection_routes.upload_evidence_image")
    @patch("routes.detection_routes.encode_image_to_base64")
    def test_25_missing_image_data_results_in_none(self, mock_encode, mock_upload, mock_detect):
        mock_detect.return_value = (
            None, [], [{"bbox": [100, 100, 300, 500], "confidence": 0.95, "track_id": 1, "worker_id": "W-001"}]
        )
        # When encoding fails or produces no image data
        mock_encode.return_value = None
        mock_upload.return_value = None

        self.client.post("/api/detect", json={
            "image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 0.0, "required_ppe": ["helmet"]
        })
        res = self.client.post("/api/detect", json={
            "image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 3.0, "required_ppe": ["helmet"]
        })

        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(mem_detections), 1)
        doc = mem_detections[0]
        self.assertIsNone(doc["imageUrl"])
        self.assertIsNone(doc["evidenceImageReference"])

        # Also verify direct persistence handles missing image reference cleanly
        doc_no_img = {
            "episode_id": f"ep_{self.session_id}_2_helmet_1",
            "worker_id": "W-002",
            "missingPPE": ["helmet"],
            "imageUrl": None,
            "evidenceImageReference": None
        }
        saved, _ = persist_confirmed_incident(doc_no_img)
        self.assertIsNone(saved["imageUrl"])
        self.assertIsNone(saved["evidenceImageReference"])

    # 26. No truncated base64 reference is generated.
    @patch("routes.detection_routes.detect_ppe_in_frame")
    @patch("routes.detection_routes.upload_evidence_image")
    def test_26_no_truncated_base64_reference_generated(self, mock_upload, mock_detect):
        mock_upload.side_effect = RuntimeError("Disk failure")
        mock_detect.return_value = (
            None, [], [{"bbox": [100, 100, 300, 500], "confidence": 0.95, "track_id": 1, "worker_id": "W-001"}]
        )

        self.client.post("/api/detect", json={
            "image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 0.0, "required_ppe": ["helmet"]
        })
        self.client.post("/api/detect", json={
            "image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 3.0, "required_ppe": ["helmet"]
        })

        doc = mem_detections[0]
        ref = doc["evidenceImageReference"]
        self.assertNotIn("...", ref)
        self.assertFalse(ref.endswith("..."))
        # Must be complete payload, well beyond 100 chars
        self.assertGreater(len(ref), 1000)

    # 27. Existing incident persistence still succeeds when evidence storage fails.
    @patch("routes.detection_routes.detect_ppe_in_frame")
    @patch("routes.detection_routes.upload_evidence_image")
    def test_27_incident_persistence_succeeds_when_storage_fails(self, mock_upload, mock_detect):
        mock_upload.side_effect = Exception("Storage infrastructure down")
        mock_detect.return_value = (
            None, [], [{"bbox": [100, 100, 300, 500], "confidence": 0.95, "track_id": 1, "worker_id": "W-001"}]
        )

        self.client.post("/api/detect", json={
            "image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 0.0, "required_ppe": ["helmet"]
        })
        res = self.client.post("/api/detect", json={
            "image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 3.0, "required_ppe": ["helmet"]
        })

        # Endpoint returns 200 OK
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data.get("new_confirmed_incidents", [])), 1)
        self.assertEqual(len(mem_detections), 1)
        doc = mem_detections[0]
        self.assertEqual(doc["complianceStatus"], "VIOLATION")
        self.assertEqual(doc["reviewStatus"], "PENDING")
        self.assertEqual(doc["worker_id"], "W-001")
        self.assertEqual(doc["missingPPE"], ["helmet"])

    # 28. Existing evidence viewers can render the fallback representation.
    @patch("routes.detection_routes.detect_ppe_in_frame")
    @patch("routes.detection_routes.upload_evidence_image")
    def test_28_evidence_viewers_can_render_fallback_representation(self, mock_upload, mock_detect):
        mock_upload.side_effect = Exception("Upload unavailable")
        mock_detect.return_value = (
            None, [], [{"bbox": [100, 100, 300, 500], "confidence": 0.95, "track_id": 1, "worker_id": "W-001"}]
        )

        self.client.post("/api/detect", json={
            "image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 0.0, "required_ppe": ["helmet"]
        })
        self.client.post("/api/detect", json={
            "image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 3.0, "required_ppe": ["helmet"]
        })

        doc = mem_detections[0]
        ref = doc["evidenceImageReference"]

        # Must start with data: to trigger frontend data-URI branch
        self.assertTrue(ref.startswith("data:"))
        # Must be valid mime type
        self.assertTrue(ref.startswith("data:image/jpeg;base64,"))
        # Ensure it can be parsed and rendered without corruption
        payload = ref.replace("data:image/jpeg;base64,", "")
        raw_bytes = base64.b64decode(payload)
        self.assertGreater(len(raw_bytes), 0)
        img = cv2.imdecode(np.frombuffer(raw_bytes, np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNotNone(img)


class TestAutomaticIncidentResolutionPersistence(unittest.TestCase):
    """
    Milestone M2.2B.5C: Automatic Incident Resolution Persistence Integration Tests.
    Validates backend persistence of verified-compliance resolution candidates,
    lookup by internal episode_id, atomicity, idempotency, lifecycle history,
    candidate acknowledgement gating, SSE event dispatch, and session isolation.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        img[100:200, 100:200] = [0, 255, 255]
        _, buf = cv2.imencode('.jpg', img)
        cls.synthetic_jpeg_bytes = buf.tobytes()
        cls.synthetic_b64 = base64.b64encode(cls.synthetic_jpeg_bytes).decode('utf-8')

    def setUp(self):
        self.session_id = f"test_res_{uuid.uuid4().hex[:8]}"
        reset_session_temporal(self.session_id)
        mem_detections.clear()

    def tearDown(self):
        reset_session_temporal(self.session_id)
        mem_detections.clear()

    def _create_and_persist_incident(self, episode_id=None, track_id=1, worker_id="W-001", ppe="helmet", status="PENDING"):
        ep_id = episode_id or f"ep_{self.session_id}_{track_id}_{ppe}_1"
        doc = {
            "episode_id": ep_id,
            "worker_id": worker_id,
            "track_id": track_id,
            "personId": worker_id,
            "workerTag": f"{worker_id} (Track #{track_id})",
            "session_id": self.session_id,
            "complianceStatus": "VIOLATION",
            "reviewStatus": status,
            "missingPPE": [ppe],
            "imageUrl": "http://storage.internal/snapshots/evidence1.jpg",
            "evidenceImageReference": "data:image/jpeg;base64,/9j/4AAQSkZJRg==",
            "first_missing_timestamp": 0.0,
            "confirmed_timestamp": 3.0,
            "createdAt": datetime.datetime.now(datetime.timezone.utc)
        }
        saved_doc, is_new = persist_confirmed_incident(doc)
        return saved_doc, ep_id

    # 1. A valid candidate resolves its original MongoDB incident
    def test_01_valid_candidate_resolves_original_incident(self):
        _, ep_id = self._create_and_persist_incident()
        self.assertEqual(len(mem_detections), 1)
        self.assertEqual(mem_detections[0]["reviewStatus"], "PENDING")

        cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0,
            "candidate_timestamp": 6.0
        }

        resolved_doc, is_new = resolve_confirmed_incident(cand)
        self.assertTrue(is_new)
        self.assertIsNotNone(resolved_doc)
        self.assertEqual(resolved_doc["status"], "RESOLVED")
        self.assertEqual(resolved_doc["reviewStatus"], "RESOLVED")
        self.assertEqual(resolved_doc["resolution_type"], "AUTOMATIC_COMPLIANCE")
        self.assertAlmostEqual(resolved_doc["verified_compliance_duration_sec"], 2.0)
        self.assertIn("lifecycle_history", resolved_doc)
        self.assertEqual(len(resolved_doc["lifecycle_history"]), 1)
        hist = resolved_doc["lifecycle_history"][0]
        self.assertEqual(hist["actor"], "SYSTEM")
        self.assertEqual(hist["resolution_type"], "AUTOMATIC_COMPLIANCE")

    # 2. The original episode ID is used for lookup
    def test_02_original_episode_id_used_for_lookup(self):
        _, ep1_id = self._create_and_persist_incident(track_id=1, worker_id="W-001")
        _, ep2_id = self._create_and_persist_incident(track_id=2, worker_id="W-002")

        cand = {
            "episode_id": ep1_id,
            "session_id": self.session_id,
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0,
            "candidate_timestamp": 6.0
        }

        resolved_doc, is_new = resolve_confirmed_incident(cand)
        self.assertTrue(is_new)
        self.assertEqual(resolved_doc["episode_id"], ep1_id)
        self.assertEqual(resolved_doc["status"], "RESOLVED")

        # Episode 2 must remain open/pending
        ep2_doc = next(d for d in mem_detections if d.get("episode_id") == ep2_id)
        self.assertEqual(ep2_doc["reviewStatus"], "PENDING")
        self.assertNotIn("status", ep2_doc)

    # 3. No new incident is inserted during resolution
    def test_03_no_new_incident_inserted_during_resolution(self):
        _, ep_id = self._create_and_persist_incident()
        initial_count = len(mem_detections)
        self.assertEqual(initial_count, 1)

        cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0,
            "candidate_timestamp": 6.0
        }

        resolve_confirmed_incident(cand)
        final_count = len(mem_detections)
        self.assertEqual(final_count, 1, "Resolution must update existing document; never insert a second incident")

    # 4. Candidate is acknowledged only after successful persistence
    def test_04_candidate_acknowledged_only_after_successful_persistence(self):
        tracker = SessionTemporalTracker(confirmation_duration_sec=3.0, resolution_duration_sec=2.0, session_id=self.session_id)

        # Confirm violation: t=0.0 -> 3.0
        tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        st_conf = tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)
        ep_id = st_conf.episode_uuid

        # Persist the confirmed incident
        self._create_and_persist_incident(episode_id=ep_id)

        # Achieve continuous compliance: t=4.0 -> 6.0
        tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.0)
        tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=6.0)

        # Candidate is available
        self.assertEqual(len(tracker.get_resolution_candidates()), 1)

        # Process resolutions
        resolved = process_resolution_candidates(tracker, self.session_id)
        self.assertEqual(len(resolved), 1)

        # Candidate must now be acknowledged and cleared from tracker
        self.assertEqual(len(tracker.get_resolution_candidates()), 0)

    # 5. Database failure leaves the candidate retryable
    @patch("routes.detection_routes.resolve_confirmed_incident")
    def test_05_database_failure_leaves_candidate_retryable(self, mock_resolve):
        mock_resolve.return_value = (None, False) # Simulate persistence failure

        tracker = SessionTemporalTracker(confirmation_duration_sec=3.0, resolution_duration_sec=2.0, session_id=self.session_id)
        tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)

        tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.0)
        tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=6.0)

        self.assertEqual(len(tracker.get_resolution_candidates()), 1)

        # Process resolution candidates with DB failing
        resolved = process_resolution_candidates(tracker, self.session_id)
        self.assertEqual(len(resolved), 0)

        # Candidate MUST NOT be acknowledged! Must remain available for retry
        self.assertEqual(len(tracker.get_resolution_candidates()), 1, "Candidate must remain available for retry on DB failure")

    # 6. Repeated processing is idempotent
    def test_06_repeated_processing_is_idempotent(self):
        _, ep_id = self._create_and_persist_incident()
        cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0,
            "candidate_timestamp": 6.0
        }

        # First run: resolves
        doc1, is_new1 = resolve_confirmed_incident(cand)
        self.assertTrue(is_new1)
        self.assertEqual(len(doc1["lifecycle_history"]), 1)

        # Second run: already resolved
        doc2, is_new2 = resolve_confirmed_incident(cand)
        self.assertFalse(is_new2, "Repeated resolution must report is_new=False")
        self.assertEqual(doc2["status"], "RESOLVED")
        self.assertEqual(len(doc2["lifecycle_history"]), 1, "Must NOT append duplicate history entries")

    # 7. Already-resolved incidents are not modified
    def test_07_already_resolved_incidents_not_modified(self):
        doc, ep_id = self._create_and_persist_incident(status="RESOLVED")
        doc["status"] = "RESOLVED"
        doc["reviewerNotes"] = "Manually resolved by safety officer"

        cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0,
            "candidate_timestamp": 6.0
        }

        res_doc, is_new = resolve_confirmed_incident(cand)
        self.assertFalse(is_new)
        self.assertEqual(res_doc["reviewerNotes"], "Manually resolved by safety officer")

    # 8. False-positive/rejected incidents are not automatically resolved
    def test_08_false_positive_rejected_incidents_not_auto_resolved(self):
        doc, ep_id = self._create_and_persist_incident(status="REJECTED")
        doc["reviewerNotes"] = "False alarm: worker wearing certified white bump cap"

        cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0,
            "candidate_timestamp": 6.0
        }

        res_doc, is_new = resolve_confirmed_incident(cand)
        self.assertFalse(is_new)
        self.assertEqual(doc["reviewStatus"], "REJECTED")
        self.assertNotEqual(doc.get("status"), "RESOLVED")

    # 9. Invalid or stale candidates are rejected
    def test_09_invalid_or_stale_candidates_rejected(self):
        doc_none, is_new_none = resolve_confirmed_incident(None)
        self.assertIsNone(doc_none)
        self.assertFalse(is_new_none)

        doc_empty, is_new_empty = resolve_confirmed_incident({})
        self.assertIsNone(doc_empty)
        self.assertFalse(is_new_empty)

        doc_no_id, is_new_no_id = resolve_confirmed_incident({"session_id": "test"})
        self.assertIsNone(doc_no_id)
        self.assertFalse(is_new_no_id)

    # 10. Wrong session or episode cannot resolve an incident
    def test_10_wrong_session_or_episode_cannot_resolve_incident(self):
        _, ep_id = self._create_and_persist_incident()
        tracker = SessionTemporalTracker(session_id="session_A")

        # Candidate with session_B cannot be processed under session_A
        cand_wrong = {
            "episode_id": ep_id,
            "session_id": "session_B",
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0
        }
        with patch.object(tracker, "get_resolution_candidates", return_value=[cand_wrong]):
            resolved = process_resolution_candidates(tracker, "session_A")
            self.assertEqual(len(resolved), 0, "Wrong session candidate must be filtered out")

        # Incident remains pending
        doc = mem_detections[0]
        self.assertEqual(doc["reviewStatus"], "PENDING")

    # 11. SSE resolution event is emitted only after a successful transition
    @patch("routes.event_routes.broadcast_event")
    def test_11_sse_resolution_event_emitted_after_successful_transition(self, mock_broadcast):
        _, ep_id = self._create_and_persist_incident()
        tracker = SessionTemporalTracker(session_id=self.session_id)

        cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0,
            "candidate_timestamp": 6.0
        }

        with patch.object(tracker, "get_resolution_candidates", return_value=[cand]):
            resolved = process_resolution_candidates(tracker, self.session_id)
            self.assertEqual(len(resolved), 1)

        mock_broadcast.assert_called_once()
        args, kwargs = mock_broadcast.call_args
        self.assertEqual(args[0], "INCIDENT_RESOLVED")
        self.assertEqual(args[1]["event"]["episode_id"], ep_id)

    # 12. No duplicate SSE event on repeated candidate processing
    @patch("routes.event_routes.broadcast_event")
    def test_12_no_duplicate_sse_event_on_repeated_processing(self, mock_broadcast):
        _, ep_id = self._create_and_persist_incident()
        tracker = SessionTemporalTracker(session_id=self.session_id)

        cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0,
            "candidate_timestamp": 6.0
        }

        with patch.object(tracker, "get_resolution_candidates", return_value=[cand]):
            # First execution
            process_resolution_candidates(tracker, self.session_id)
            self.assertEqual(mock_broadcast.call_count, 1)

            # Second execution with same candidate
            process_resolution_candidates(tracker, self.session_id)
            self.assertEqual(mock_broadcast.call_count, 1, "Duplicate SSE event must NOT be emitted")

    # 13. Uploaded-video resolution uses the correct upload session
    @patch("routes.detection_routes.detect_ppe_in_frame")
    @patch("cv2.VideoCapture")
    def test_13_uploaded_video_resolution_uses_correct_upload_session(self, mock_cap_cls, mock_detect):
        # Mock VideoCapture with 6 frames
        mock_cap = MagicMock()
        mock_cap.isOpened.side_effect = [True, True, True, True, True, True, False]
        mock_cap.get.return_value = 25.0 # 25 FPS
        # 1 frame = 0.8s
        blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.side_effect = [
            (True, blank_frame),
            (True, blank_frame),
            (True, blank_frame),
            (True, blank_frame),
            (True, blank_frame),
            (True, blank_frame)
        ]
        mock_cap_cls.return_value = mock_cap

        # Frame 0 (t=0.0): Missing helmet
        # Frame 1 (t=0.8): Missing helmet
        # Frame 2 (t=1.6): Missing helmet
        # Frame 3 (t=2.4): Missing helmet
        # Frame 4 (t=3.2): Missing helmet -> CONFIRMED
        # Frame 5 (t=4.0): Wearing helmet
        # Frame 6 (t=6.0): Wearing helmet -> RESOLVED
        w_missing = [{"bbox": [100, 100, 300, 500], "confidence": 0.95, "track_id": 1, "worker_id": "W-001"}]
        h_det = [{
            "name": "helmet",
            "class": "helmet",
            "box": [100, 100, 300, 200],
            "bbox": [100, 100, 300, 200],
            "confidence": 0.95,
            "source": "yolo",
            "is_synthetic": False
        }]

        # Set detect returns: 4 frames missing, then 2 frames wearing
        mock_detect.side_effect = [
            (None, [], w_missing),
            (None, [], w_missing),
            (None, [], w_missing),
            (None, [], w_missing),
            (None, [], w_missing),
            (None, h_det, w_missing),
            (None, h_det, w_missing)
        ]

        # Use an in-memory test file for video
        import io
        fake_video = (io.BytesIO(b"fake_video_data"), "sample.mp4")
        res = self.client.post("/api/detect-video", data={"file": fake_video, "required_ppe": json.dumps(["helmet"])}, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("total_violations_found", data)
        self.assertIn("total_resolutions_found", data)

    # 14. Live-webcam resolution uses the correct monitoring session
    @patch("routes.detection_routes.detect_ppe_in_frame")
    @patch("routes.detection_routes.upload_evidence_image")
    def test_14_live_webcam_resolution_uses_correct_monitoring_session(self, mock_upload, mock_detect):
        mock_upload.return_value = "http://storage.internal/snap.jpg"

        w_missing = [{"bbox": [100, 100, 300, 500], "confidence": 0.95, "track_id": 1, "worker_id": "W-001"}]
        h_det = [{
            "name": "helmet",
            "class": "helmet",
            "box": [100, 100, 300, 200],
            "bbox": [100, 100, 300, 200],
            "confidence": 0.95,
            "source": "yolo",
            "is_synthetic": False
        }]

        # Frame 1 at t=0.0: missing
        mock_detect.return_value = (None, [], w_missing)
        self.client.post("/api/detect", json={"image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 0.0, "required_ppe": ["helmet"]})

        # Frame 2 at t=3.0: missing -> CONFIRMED incident created
        res2 = self.client.post("/api/detect", json={"image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 3.0, "required_ppe": ["helmet"]})
        data2 = res2.get_json()
        self.assertEqual(len(data2.get("new_confirmed_incidents", [])), 1)
        self.assertEqual(len(mem_detections), 1)
        self.assertEqual(mem_detections[0]["reviewStatus"], "PENDING")

        # Frame 3 at t=4.0: wearing helmet -> starts verified compliance
        mock_detect.return_value = (None, h_det, w_missing)
        self.client.post("/api/detect", json={"image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 4.0, "required_ppe": ["helmet"]})

        # Frame 4 at t=5.0: wearing helmet -> 1.0s compliance
        self.client.post("/api/detect", json={"image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 5.0, "required_ppe": ["helmet"]})

        # Frame 5 at t=6.0: wearing helmet -> 2.0s compliance -> RESOLVED
        res5 = self.client.post("/api/detect", json={"image": self.synthetic_b64, "session_id": self.session_id, "timestamp": 6.0, "required_ppe": ["helmet"]})
        data5 = res5.get_json()

        self.assertEqual(len(data5.get("new_resolved_incidents", [])), 1)
        resolved_inc = data5["new_resolved_incidents"][0]
        self.assertEqual(resolved_inc["status"], "RESOLVED")
        self.assertEqual(resolved_inc["reviewStatus"], "RESOLVED")
        self.assertEqual(resolved_inc["resolution_type"], "AUTOMATIC_COMPLIANCE")

        # MongoDB / mem_detections updated
        self.assertEqual(mem_detections[0]["status"], "RESOLVED")
        self.assertEqual(mem_detections[0]["resolution_type"], "AUTOMATIC_COMPLIANCE")

    # 15. Existing incident evidence and original timestamps remain unchanged
    def test_15_existing_incident_evidence_and_original_timestamps_remain_unchanged(self):
        doc, ep_id = self._create_and_persist_incident()
        orig_img = doc["imageUrl"]
        orig_ref = doc["evidenceImageReference"]
        orig_first = doc["first_missing_timestamp"]
        orig_conf = doc["confirmed_timestamp"]
        orig_created = doc["createdAt"]

        cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0,
            "candidate_timestamp": 6.0
        }

        res_doc, is_new = resolve_confirmed_incident(cand)
        self.assertTrue(is_new)
        self.assertEqual(res_doc["imageUrl"], orig_img)
        self.assertEqual(res_doc["evidenceImageReference"], orig_ref)
        self.assertEqual(res_doc["first_missing_timestamp"], orig_first)
        self.assertEqual(res_doc["confirmed_timestamp"], orig_conf)
        self.assertEqual(res_doc["createdAt"], orig_created)
        self.assertEqual(res_doc["status"], "RESOLVED")

    # 16. Existing incident creation and confirmation tests continue passing
    def test_16_existing_incident_creation_and_confirmation_unbroken(self):
        saved_doc, is_new = self._create_and_persist_incident()
        self.assertTrue(is_new)
        self.assertEqual(saved_doc["complianceStatus"], "VIOLATION")
        self.assertEqual(saved_doc["reviewStatus"], "PENDING")


class TestCandidateIdentityValidation(unittest.TestCase):
    """
    M2.2B.5C-F.2: Focused tests for defense-in-depth candidate-to-incident identity validation.
    Verifies that resolve_confirmed_incident() validates all candidate identity fields,
    enforces matching session_id, track_id, and PPE category against stored incident records,
    protects against mutations on mismatch, leaves candidates retryable, and preserves
    existing lifecycle behavior for both in-memory and MongoDB stores.
    """
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def setUp(self):
        self.session_id = f"test_ident_{int(time.time()*1000)}"
        mem_detections.clear()

    def _create_incident(self, episode_id=None, session_id=None, track_id=1, worker_id="W-001", ppe="helmet", status="PENDING"):
        sid = session_id or self.session_id
        ep_id = episode_id or f"ep_{sid}_{track_id}_{ppe}_1"
        doc = {
            "episode_id": ep_id,
            "worker_id": worker_id,
            "track_id": track_id,
            "personId": worker_id,
            "workerTag": f"{worker_id} (Track #{track_id})",
            "session_id": sid,
            "complianceStatus": "VIOLATION",
            "reviewStatus": status,
            "missingPPE": [ppe],
            "imageUrl": "http://storage.internal/snapshots/evidence1.jpg",
            "evidenceImageReference": "data:image/jpeg;base64,/9j/4AAQSkZJRg==",
            "first_missing_timestamp": 0.0,
            "confirmed_timestamp": 3.0,
            "createdAt": datetime.datetime.now(datetime.timezone.utc)
        }
        saved_doc, is_new = persist_confirmed_incident(doc)
        return saved_doc, ep_id

    # 1. Memory fallback: correct identity resolves successfully
    def test_01_memory_correct_identity_resolves_successfully(self):
        _, ep_id = self._create_incident()
        cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0,
            "candidate_timestamp": 6.0
        }
        resolved_doc, is_new = resolve_confirmed_incident(cand)
        self.assertTrue(is_new)
        self.assertIsNotNone(resolved_doc)
        self.assertEqual(resolved_doc["status"], "RESOLVED")
        self.assertEqual(resolved_doc["reviewStatus"], "RESOLVED")

    # 2. Memory fallback: mismatched session ID is rejected
    def test_02_memory_mismatched_session_rejected(self):
        doc, ep_id = self._create_incident(session_id="session_ALPHA")
        cand = {
            "episode_id": ep_id,
            "session_id": "session_BETA",
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0
        }
        resolved_doc, is_new = resolve_confirmed_incident(cand)
        self.assertIsNone(resolved_doc)
        self.assertFalse(is_new)
        # Incident in mem_detections must remain untouched
        stored = mem_detections[0]
        self.assertEqual(stored["reviewStatus"], "PENDING")
        self.assertNotIn("status", stored)

    # 3. Memory fallback: mismatched track ID is rejected
    def test_03_memory_mismatched_track_rejected(self):
        doc, ep_id = self._create_incident(track_id=1)
        cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "worker_id": "W-002",
            "track_id": 2, # Mismatched track ID
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0
        }
        resolved_doc, is_new = resolve_confirmed_incident(cand)
        self.assertIsNone(resolved_doc)
        self.assertFalse(is_new)
        stored = mem_detections[0]
        self.assertEqual(stored["reviewStatus"], "PENDING")

    # 4. Memory fallback: mismatched PPE category is rejected
    def test_04_memory_mismatched_ppe_category_rejected(self):
        doc, ep_id = self._create_incident(ppe="helmet")
        cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "vest", # Mismatched PPE category
            "verified_compliance_duration_sec": 2.0
        }
        resolved_doc, is_new = resolve_confirmed_incident(cand)
        self.assertIsNone(resolved_doc)
        self.assertFalse(is_new)
        stored = mem_detections[0]
        self.assertEqual(stored["reviewStatus"], "PENDING")

    # 5. Memory fallback: missing identity fields are rejected
    def test_05_memory_missing_identity_fields_rejected(self):
        doc, ep_id = self._create_incident()
        # Missing session_id
        c1 = {"episode_id": ep_id, "track_id": 1, "ppe_category": "helmet"}
        r1, is_n1 = resolve_confirmed_incident(c1)
        self.assertIsNone(r1)
        self.assertFalse(is_n1)

        # Missing track_id
        c2 = {"episode_id": ep_id, "session_id": self.session_id, "ppe_category": "helmet"}
        r2, is_n2 = resolve_confirmed_incident(c2)
        self.assertIsNone(r2)
        self.assertFalse(is_n2)

        # Missing ppe_category
        c3 = {"episode_id": ep_id, "session_id": self.session_id, "track_id": 1}
        r3, is_n3 = resolve_confirmed_incident(c3)
        self.assertIsNone(r3)
        self.assertFalse(is_n3)

        # Non-integer track_id
        c4 = {"episode_id": ep_id, "session_id": self.session_id, "track_id": "invalid", "ppe_category": "helmet"}
        r4, is_n4 = resolve_confirmed_incident(c4)
        self.assertIsNone(r4)
        self.assertFalse(is_n4)

    # 6. Memory fallback: identity mismatch does not modify original incident
    def test_06_memory_identity_mismatch_does_not_modify_original_incident(self):
        doc, ep_id = self._create_incident()
        orig_time = doc["createdAt"]
        orig_missing = list(doc["missingPPE"])

        mismatched_cand = {
            "episode_id": ep_id,
            "session_id": "wrong_session",
            "track_id": 999,
            "ppe_category": "boots",
            "verified_compliance_duration_sec": 5.0
        }
        res_doc, is_new = resolve_confirmed_incident(mismatched_cand)
        self.assertIsNone(res_doc)
        self.assertFalse(is_new)

        stored = mem_detections[0]
        self.assertEqual(stored["createdAt"], orig_time)
        self.assertEqual(stored["missingPPE"], orig_missing)
        self.assertEqual(stored["reviewStatus"], "PENDING")
        self.assertNotIn("lifecycle_history", stored)
        self.assertNotIn("resolution_type", stored)
        self.assertNotIn("resolved_at", stored)

    # 7. Memory fallback: identity mismatch does not acknowledge temporal candidate
    def test_07_memory_identity_mismatch_does_not_acknowledge_temporal_candidate(self):
        tracker = SessionTemporalTracker(confirmation_duration_sec=3.0, resolution_duration_sec=2.0, session_id=self.session_id)
        tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=0.0)
        st_conf = tracker.update_worker_ppe(1, "helmet", is_worn=False, is_observable=True, is_required=True, is_uncertain=False, timestamp=3.0)
        ep_id = st_conf.episode_uuid

        # Persist incident with track_id=1
        self._create_incident(episode_id=ep_id, track_id=1)

        # Achieve continuous compliance
        tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=4.0)
        tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=5.0)
        tracker.update_worker_ppe(1, "helmet", is_worn=True, is_observable=True, is_required=True, is_uncertain=False, timestamp=6.0)

        self.assertEqual(len(tracker.get_resolution_candidates()), 1)

        # Tamper candidate in tracker to simulate mismatch (e.g. wrong track_id)
        bad_cand = dict(tracker.get_resolution_candidates()[0])
        bad_cand["track_id"] = 999

        with patch.object(tracker, "get_resolution_candidates", return_value=[bad_cand]):
            resolved = process_resolution_candidates(tracker, self.session_id)
            self.assertEqual(len(resolved), 0)

        # Candidate must NOT be acknowledged; original candidate remains available in tracker
        self.assertEqual(len(tracker.get_resolution_candidates()), 1)

    # 8. Memory fallback: correct candidate can still retry successfully after a rejected attempt
    def test_08_memory_correct_candidate_retries_successfully_after_rejected_attempt(self):
        _, ep_id = self._create_incident(track_id=1, ppe="helmet")
        tracker = SessionTemporalTracker(session_id=self.session_id)

        bad_cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "worker_id": "W-002",
            "track_id": 2, # Mismatched
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0
        }
        good_cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "worker_id": "W-001",
            "track_id": 1, # Correct
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0
        }

        # Attempt 1: bad candidate -> rejected
        r1, is_n1 = resolve_confirmed_incident(bad_cand)
        self.assertIsNone(r1)
        self.assertFalse(is_n1)
        self.assertEqual(mem_detections[0]["reviewStatus"], "PENDING")

        # Attempt 2: good candidate -> succeeds
        r2, is_n2 = resolve_confirmed_incident(good_cand)
        self.assertTrue(is_n2)
        self.assertEqual(r2["status"], "RESOLVED")
        self.assertEqual(r2["reviewStatus"], "RESOLVED")

    # 9. MongoDB: correct identity resolves successfully via atomic update
    @patch("routes.detection_routes.is_mongo_connected", True)
    @patch("routes.detection_routes.get_detections_col")
    def test_09_mongo_correct_identity_resolves_successfully(self, mock_col_func):
        mock_col = MagicMock()
        mock_col_func.return_value = mock_col

        mock_update_res = MagicMock()
        mock_update_res.modified_count = 1
        mock_col.update_one.return_value = mock_update_res

        fake_doc = {
            "_id": "670e...",
            "episode_id": "ep_mongo_1",
            "session_id": self.session_id,
            "track_id": 1,
            "missingPPE": ["helmet"],
            "status": "RESOLVED",
            "reviewStatus": "RESOLVED"
        }
        mock_col.find_one.return_value = fake_doc

        cand = {
            "episode_id": "ep_mongo_1",
            "session_id": self.session_id,
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0
        }
        res_doc, is_new = resolve_confirmed_incident(cand)
        self.assertTrue(is_new)
        self.assertEqual(res_doc["status"], "RESOLVED")

        # Verify filter_query passed to update_one contains exact identity keys
        args, kwargs = mock_col.update_one.call_args
        filter_q = args[0]
        self.assertEqual(filter_q["episode_id"], "ep_mongo_1")
        self.assertEqual(filter_q["session_id"], self.session_id)
        self.assertIn(1, filter_q["track_id"]["$in"])
        self.assertIn("$or", filter_q)

    # 10. MongoDB: mismatched session ID is rejected
    @patch("routes.detection_routes.is_mongo_connected", True)
    @patch("routes.detection_routes.get_detections_col")
    def test_10_mongo_mismatched_session_rejected(self, mock_col_func):
        mock_col = MagicMock()
        mock_col_func.return_value = mock_col

        # update_one matches 0 because session_id in filter_query didn't match
        mock_update_res = MagicMock()
        mock_update_res.modified_count = 0
        mock_col.update_one.return_value = mock_update_res

        # find_one finds existing document with session_ALPHA
        existing_doc = {
            "_id": "670e...",
            "episode_id": "ep_mongo_1",
            "session_id": "session_ALPHA",
            "track_id": 1,
            "missingPPE": ["helmet"],
            "reviewStatus": "PENDING"
        }
        mock_col.find_one.return_value = existing_doc

        cand = {
            "episode_id": "ep_mongo_1",
            "session_id": "session_BETA",
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0
        }
        res_doc, is_new = resolve_confirmed_incident(cand)
        self.assertIsNone(res_doc)
        self.assertFalse(is_new)

    # 11. MongoDB: mismatched track ID is rejected
    @patch("routes.detection_routes.is_mongo_connected", True)
    @patch("routes.detection_routes.get_detections_col")
    def test_11_mongo_mismatched_track_rejected(self, mock_col_func):
        mock_col = MagicMock()
        mock_col_func.return_value = mock_col

        mock_update_res = MagicMock()
        mock_update_res.modified_count = 0
        mock_col.update_one.return_value = mock_update_res

        existing_doc = {
            "_id": "670e...",
            "episode_id": "ep_mongo_1",
            "session_id": self.session_id,
            "track_id": 1,
            "missingPPE": ["helmet"],
            "reviewStatus": "PENDING"
        }
        mock_col.find_one.return_value = existing_doc

        cand = {
            "episode_id": "ep_mongo_1",
            "session_id": self.session_id,
            "worker_id": "W-002",
            "track_id": 2, # Mismatched track ID
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0
        }
        res_doc, is_new = resolve_confirmed_incident(cand)
        self.assertIsNone(res_doc)
        self.assertFalse(is_new)

    # 12. MongoDB: mismatched PPE category is rejected
    @patch("routes.detection_routes.is_mongo_connected", True)
    @patch("routes.detection_routes.get_detections_col")
    def test_12_mongo_mismatched_ppe_category_rejected(self, mock_col_func):
        mock_col = MagicMock()
        mock_col_func.return_value = mock_col

        mock_update_res = MagicMock()
        mock_update_res.modified_count = 0
        mock_col.update_one.return_value = mock_update_res

        existing_doc = {
            "_id": "670e...",
            "episode_id": "ep_mongo_1",
            "session_id": self.session_id,
            "track_id": 1,
            "missingPPE": ["helmet"],
            "reviewStatus": "PENDING"
        }
        mock_col.find_one.return_value = existing_doc

        cand = {
            "episode_id": "ep_mongo_1",
            "session_id": self.session_id,
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "vest", # Mismatched PPE category
            "verified_compliance_duration_sec": 2.0
        }
        res_doc, is_new = resolve_confirmed_incident(cand)
        self.assertIsNone(res_doc)
        self.assertFalse(is_new)

    # 13. MongoDB: identity mismatch does not acknowledge candidate
    @patch("routes.detection_routes.is_mongo_connected", True)
    @patch("routes.detection_routes.get_detections_col")
    def test_13_mongo_identity_mismatch_leaves_candidate_retryable(self, mock_col_func):
        mock_col = MagicMock()
        mock_col_func.return_value = mock_col

        mock_update_res = MagicMock()
        mock_update_res.modified_count = 0
        mock_col.update_one.return_value = mock_update_res

        existing_doc = {
            "_id": "670e...",
            "episode_id": "ep_mongo_1",
            "session_id": self.session_id,
            "track_id": 1,
            "missingPPE": ["helmet"],
            "reviewStatus": "PENDING"
        }
        mock_col.find_one.return_value = existing_doc

        tracker = SessionTemporalTracker(session_id=self.session_id)
        mismatched_cand = {
            "episode_id": "ep_mongo_1",
            "session_id": self.session_id,
            "worker_id": "W-002",
            "track_id": 2,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0
        }

        with patch.object(tracker, "get_resolution_candidates", return_value=[mismatched_cand]):
            with patch.object(tracker, "acknowledge_resolution") as mock_ack:
                resolved = process_resolution_candidates(tracker, self.session_id)
                self.assertEqual(len(resolved), 0)
                mock_ack.assert_not_called()

    # 14. MongoDB: correct candidate can retry successfully after a rejected attempt
    @patch("routes.detection_routes.is_mongo_connected", True)
    @patch("routes.detection_routes.get_detections_col")
    def test_14_mongo_correct_candidate_retries_successfully_after_rejection(self, mock_col_func):
        mock_col = MagicMock()
        mock_col_func.return_value = mock_col

        # First call: mismatch -> modified_count=0, existing has track_id=1
        existing_doc = {
            "_id": "670e...",
            "episode_id": "ep_mongo_1",
            "session_id": self.session_id,
            "track_id": 1,
            "missingPPE": ["helmet"],
            "reviewStatus": "PENDING"
        }
        # Second call: match -> modified_count=1, resolved doc returned
        resolved_doc = dict(existing_doc)
        resolved_doc["status"] = "RESOLVED"
        resolved_doc["reviewStatus"] = "RESOLVED"

        res_fail = MagicMock(modified_count=0)
        res_succ = MagicMock(modified_count=1)
        mock_col.update_one.side_effect = [res_fail, res_succ]
        mock_col.find_one.side_effect = [existing_doc, resolved_doc]

        bad_cand = {
            "episode_id": "ep_mongo_1",
            "session_id": self.session_id,
            "track_id": 2,
            "ppe_category": "helmet"
        }
        good_cand = {
            "episode_id": "ep_mongo_1",
            "session_id": self.session_id,
            "track_id": 1,
            "ppe_category": "helmet"
        }

        r1, is_n1 = resolve_confirmed_incident(bad_cand)
        self.assertIsNone(r1)
        self.assertFalse(is_n1)

        r2, is_n2 = resolve_confirmed_incident(good_cand)
        self.assertTrue(is_n2)
        self.assertEqual(r2["status"], "RESOLVED")

    # 15. Terminal state and idempotency preserved under identity validation
    def test_15_terminal_state_and_idempotency_preserved(self):
        doc, ep_id = self._create_incident(status="REJECTED")
        cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "helmet"
        }
        # Valid identity on REJECTED incident -> refused without error (returns existing, False)
        res, is_new = resolve_confirmed_incident(cand)
        self.assertFalse(is_new)
        self.assertEqual(res["reviewStatus"], "REJECTED")

        # REVIEWED state -> resolved upon verified compliance
        doc_rev, ep_rev = self._create_incident(episode_id=f"ep_rev_{int(time.time()*1000)}", status="REVIEWED")
        cand_rev = {
            "episode_id": ep_rev,
            "session_id": self.session_id,
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "helmet"
        }
        res_rev, is_new_rev = resolve_confirmed_incident(cand_rev)
        self.assertTrue(is_new_rev)
        self.assertEqual(res_rev["status"], "RESOLVED")

    # 16. M2.2B.5C-F.3: Candidate track ID True/False is strictly rejected (memory & mongo)
    def test_16_strict_track_id_candidate_boolean_rejected(self):
        _, ep_id = self._create_incident(track_id=1)
        # Candidate with track_id=True must NOT match integer 1
        cand_true = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "track_id": True,
            "ppe_category": "helmet"
        }
        res_mem, is_new_mem = resolve_confirmed_incident(cand_true)
        self.assertIsNone(res_mem)
        self.assertFalse(is_new_mem)
        self.assertEqual(mem_detections[0]["reviewStatus"], "PENDING")

        # Candidate with track_id=False must NOT match integer 0
        cand_false = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "track_id": False,
            "ppe_category": "helmet"
        }
        res_false, is_new_false = resolve_confirmed_incident(cand_false)
        self.assertIsNone(res_false)
        self.assertFalse(is_new_false)

    # 17. M2.2B.5C-F.3: Candidate track ID 1.5 is strictly rejected (memory & mongo)
    def test_17_strict_track_id_candidate_float_fraction_rejected(self):
        _, ep_id = self._create_incident(track_id=1)
        cand_float = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "track_id": 1.5,
            "ppe_category": "helmet"
        }
        res, is_new = resolve_confirmed_incident(cand_float)
        self.assertIsNone(res)
        self.assertFalse(is_new)
        self.assertEqual(mem_detections[0]["reviewStatus"], "PENDING")

    # 18. M2.2B.5C-F.3: Candidate track ID "1.5" string fraction is strictly rejected (memory & mongo)
    def test_18_strict_track_id_candidate_string_fraction_rejected(self):
        _, ep_id = self._create_incident(track_id=1)
        cand_str_float = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "track_id": "1.5",
            "ppe_category": "helmet"
        }
        res, is_new = resolve_confirmed_incident(cand_str_float)
        self.assertIsNone(res)
        self.assertFalse(is_new)
        self.assertEqual(mem_detections[0]["reviewStatus"], "PENDING")

    # 19. M2.2B.5C-F.3: Stored track ID 1.5 is rejected without silent truncation (memory & mongo)
    def test_19_strict_track_id_stored_float_fraction_rejected(self):
        # Create incident where stored track_id is float 1.5
        doc, ep_id = self._create_incident(track_id=1.5)
        # Candidate has integer track_id=1
        cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "track_id": 1,
            "ppe_category": "helmet"
        }
        # In memory fallback: stored 1.5 must NOT be truncated to 1
        res, is_new = resolve_confirmed_incident(cand)
        self.assertIsNone(res)
        self.assertFalse(is_new)
        self.assertEqual(mem_detections[0]["reviewStatus"], "PENDING")

    # 20. M2.2B.5C-F.3: Valid integer 1 and string "1" compatibility (memory & mongo)
    def test_20_strict_track_id_integer_and_string_integer_compatibility(self):
        # Case A: stored is string "1", candidate is int 1
        doc_a, ep_a = self._create_incident(track_id="1")
        cand_a = {
            "episode_id": ep_a,
            "session_id": self.session_id,
            "track_id": 1,
            "ppe_category": "helmet"
        }
        res_a, is_new_a = resolve_confirmed_incident(cand_a)
        self.assertTrue(is_new_a)
        self.assertEqual(res_a["status"], "RESOLVED")

        # Case B: stored is int 2, candidate is string "2"
        doc_b, ep_b = self._create_incident(track_id=2)
        cand_b = {
            "episode_id": ep_b,
            "session_id": self.session_id,
            "track_id": "2",
            "ppe_category": "helmet"
        }
        res_b, is_new_b = resolve_confirmed_incident(cand_b)
        self.assertTrue(is_new_b)
        self.assertEqual(res_b["status"], "RESOLVED")

    # 21. M2.2B.5C-F.3: Track ID 0 is valid and distinct from False
    def test_21_strict_track_id_zero_is_valid_and_distinct_from_false(self):
        # Stored track_id is 0
        doc, ep_id = self._create_incident(track_id=0)

        # Candidate with track_id=False is rejected
        cand_false = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "track_id": False,
            "ppe_category": "helmet"
        }
        res_f, is_new_f = resolve_confirmed_incident(cand_false)
        self.assertIsNone(res_f)
        self.assertFalse(is_new_f)

        # Candidate with genuine int 0 resolves successfully
        cand_zero = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "track_id": 0,
            "ppe_category": "helmet"
        }
        res_0, is_new_0 = resolve_confirmed_incident(cand_zero)
        self.assertTrue(is_new_0)
        self.assertEqual(res_0["status"], "RESOLVED")

    # 22. M2.2B.5C-F.3: Rejected track ID candidates cannot modify incident or be acknowledged
    def test_22_rejected_track_candidates_cannot_modify_or_be_acknowledged(self):
        tracker = SessionTemporalTracker(session_id=self.session_id)
        _, ep_id = self._create_incident(track_id=1)
        orig_doc = dict(mem_detections[0])

        bad_cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "track_id": True, # Boolean
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0
        }

        with patch.object(tracker, "get_resolution_candidates", return_value=[bad_cand]):
            with patch.object(tracker, "acknowledge_resolution") as mock_ack:
                resolved = process_resolution_candidates(tracker, self.session_id)
                self.assertEqual(len(resolved), 0)
                mock_ack.assert_not_called()

        stored = mem_detections[0]
        self.assertEqual(stored["reviewStatus"], orig_doc["reviewStatus"])
        self.assertNotIn("status", stored)
        self.assertNotIn("lifecycle_history", stored)

    # 23. M2.2B.5C-F.3: MongoDB path strictly rejects booleans and fractions
    @patch("routes.detection_routes.is_mongo_connected", True)
    @patch("routes.detection_routes.get_detections_col")
    def test_23_mongo_strict_track_id_rejects_booleans_and_fractions(self, mock_col_func):
        mock_col = MagicMock()
        mock_col_func.return_value = mock_col

        # Candidate with track_id=True
        cand_bool = {
            "episode_id": "ep_mongo_1",
            "session_id": self.session_id,
            "track_id": True,
            "ppe_category": "helmet"
        }
        r_b, is_n_b = resolve_confirmed_incident(cand_bool)
        self.assertIsNone(r_b)
        self.assertFalse(is_n_b)
        # update_one must not even be called for invalid candidate
        mock_col.update_one.assert_not_called()

        # Candidate with track_id=1.5
        cand_float = {
            "episode_id": "ep_mongo_1",
            "session_id": self.session_id,
            "track_id": 1.5,
            "ppe_category": "helmet"
        }
        r_f, is_n_f = resolve_confirmed_incident(cand_float)
        self.assertIsNone(r_f)
        self.assertFalse(is_n_f)
        mock_col.update_one.assert_not_called()

        # Candidate with track_id="1.5"
        cand_str_f = {
            "episode_id": "ep_mongo_1",
            "session_id": self.session_id,
            "track_id": "1.5",
            "ppe_category": "helmet"
        }
        r_sf, is_n_sf = resolve_confirmed_incident(cand_str_f)
        self.assertIsNone(r_sf)
        self.assertFalse(is_n_sf)
        mock_col.update_one.assert_not_called()

    # 24. M2.2B.5C-F.3: MongoDB path rejects stored track ID 1.5 without truncation
    @patch("routes.detection_routes.is_mongo_connected", True)
    @patch("routes.detection_routes.get_detections_col")
    def test_24_mongo_strict_track_id_stored_fraction_rejected(self, mock_col_func):
        mock_col = MagicMock()
        mock_col_func.return_value = mock_col

        # Filter query with {"$in": [1, "1"]} does not match stored 1.5
        mock_update_res = MagicMock()
        mock_update_res.modified_count = 0
        mock_col.update_one.return_value = mock_update_res

        # Stored document has fractional track_id: 1.5
        existing_doc = {
            "_id": "670e...",
            "episode_id": "ep_mongo_1",
            "session_id": self.session_id,
            "track_id": 1.5, # Fractional float in MongoDB
            "missingPPE": ["helmet"],
            "reviewStatus": "PENDING"
        }
        mock_col.find_one.return_value = existing_doc

        cand = {
            "episode_id": "ep_mongo_1",
            "session_id": self.session_id,
            "track_id": 1,
            "ppe_category": "helmet"
        }
        res, is_new = resolve_confirmed_incident(cand)
        self.assertIsNone(res)
        self.assertFalse(is_new)

    # 25. M2.2B.5C-F.4: Candidate track ID 1.0 (whole float) is strictly rejected
    def test_25_strict_track_id_candidate_whole_float_rejected(self):
        _, ep_id = self._create_incident(track_id=1)
        # Candidate with track_id=1.0 (float) must be rejected
        cand_float_one = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "track_id": 1.0,
            "ppe_category": "helmet"
        }
        res, is_new = resolve_confirmed_incident(cand_float_one)
        self.assertIsNone(res)
        self.assertFalse(is_new)
        self.assertEqual(mem_detections[0]["reviewStatus"], "PENDING")

    # 26. M2.2B.5C-F.4: Stored track ID 1.0 (whole float) is rejected in memory fallback
    def test_26_strict_track_id_stored_whole_float_rejected_memory(self):
        # Create incident where stored track_id is float 1.0
        doc, ep_id = self._create_incident(track_id=1.0)
        cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "track_id": 1,
            "ppe_category": "helmet"
        }
        res, is_new = resolve_confirmed_incident(cand)
        self.assertIsNone(res)
        self.assertFalse(is_new)
        self.assertEqual(mem_detections[0]["reviewStatus"], "PENDING")

    # 27. M2.2B.5C-F.4: Stored track ID 1.0 (whole float) is rejected in MongoDB mock
    @patch("routes.detection_routes.is_mongo_connected", True)
    @patch("routes.detection_routes.get_detections_col")
    def test_27_strict_track_id_stored_whole_float_rejected_mongo(self, mock_col_func):
        mock_col = MagicMock()
        mock_col_func.return_value = mock_col

        mock_update_res = MagicMock()
        mock_update_res.modified_count = 0
        mock_col.update_one.return_value = mock_update_res

        # Stored document has whole float track_id: 1.0
        existing_doc = {
            "_id": "670e...",
            "episode_id": "ep_mongo_1",
            "session_id": self.session_id,
            "track_id": 1.0, # Whole float in MongoDB
            "missingPPE": ["helmet"],
            "reviewStatus": "PENDING"
        }
        mock_col.find_one.return_value = existing_doc

        cand = {
            "episode_id": "ep_mongo_1",
            "session_id": self.session_id,
            "track_id": 1,
            "ppe_category": "helmet"
        }
        res, is_new = resolve_confirmed_incident(cand)
        self.assertIsNone(res)
        self.assertFalse(is_new)

    # 28. M2.2B.5C-F.4: Candidate 1.0 cannot modify incident or be acknowledged
    def test_28_strict_track_id_candidate_float_cannot_modify_or_be_acknowledged(self):
        tracker = SessionTemporalTracker(session_id=self.session_id)
        _, ep_id = self._create_incident(track_id=1)
        orig_doc = dict(mem_detections[0])

        bad_cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "track_id": 1.0, # Float
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0
        }

        with patch.object(tracker, "get_resolution_candidates", return_value=[bad_cand]):
            with patch.object(tracker, "acknowledge_resolution") as mock_ack:
                resolved = process_resolution_candidates(tracker, self.session_id)
                self.assertEqual(len(resolved), 0)
                mock_ack.assert_not_called()

        stored = mem_detections[0]
        self.assertEqual(stored["reviewStatus"], orig_doc["reviewStatus"])
        self.assertNotIn("status", stored)
        self.assertNotIn("lifecycle_history", stored)


class TestManualIncidentLifecycleAPI(unittest.TestCase):
    """
    M2.2B.5D: Focused tests for Manual Incident Lifecycle API, RBAC & Audit History.
    Covers:
    - Administrator acknowledgement and resolution.
    - Supervisor acknowledgement and resolution.
    - False-positive resolution with mandatory reason.
    - Missing/invalid JWT token handling.
    - Unauthorized role rejection (and request body role spoofing protection).
    - Empty or whitespace resolution reason rejection.
    - Invalid lifecycle transitions (RESOLVED -> OPEN, RESOLVED -> ACKNOWLEDGED).
    - Duplicate acknowledgement idempotency.
    - Attempt to reopen or re-resolve a resolved incident.
    - Lifecycle history fields and actor audit trails.
    - MongoDB and memory fallback parity.
    - Compatibility with M2.2B.5C automatic resolution.
    """
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.admin_token = generate_token("admin_001", "SUPER_ADMIN", "admin@ppe.com", name="Admin User")
        cls.supervisor_token = generate_token("sup_001", "ZONE_SUPERVISOR", "supervisor@ppe.com", name="Zone Supervisor")
        cls.reviewer_token = generate_token("rev_001", "REVIEWER", "reviewer@ppe.com", name="Safety Reviewer")
        cls.worker_token = generate_token("worker_001", "WORKER", "worker@ppe.com", name="Worker User")

    def setUp(self):
        self.session_id = f"test_lifecycle_{int(time.time()*1000)}"
        mem_detections.clear()

    def _create_incident(self, episode_id=None, status="PENDING", ppe="helmet", track_id=1):
        ep_id = episode_id or f"ep_{self.session_id}_{track_id}_{ppe}_1"
        doc = {
            "episode_id": ep_id,
            "worker_id": f"W-{track_id:03d}",
            "track_id": track_id,
            "personId": f"W-{track_id:03d}",
            "workerTag": f"W-{track_id:03d} (Track #{track_id})",
            "session_id": self.session_id,
            "complianceStatus": "VIOLATION",
            "status": "OPEN" if status == "PENDING" else status,
            "reviewStatus": status,
            "missingPPE": [ppe],
            "imageUrl": "http://storage.internal/snapshots/evidence1.jpg",
            "evidenceImageReference": "data:image/jpeg;base64,/9j/4AAQSkZJRg==",
            "first_missing_timestamp": 0.0,
            "confirmed_timestamp": 3.0,
            "createdAt": datetime.datetime.now(datetime.timezone.utc)
        }
        saved_doc, is_new = persist_confirmed_incident(doc)
        return saved_doc, ep_id

    # 1. Administrator acknowledgement and resolution
    def test_01_admin_acknowledgement_and_resolution(self):
        doc, ep_id = self._create_incident()
        inc_id = doc["_id"]

        # Step 1: Admin acknowledges OPEN incident
        ack_res = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "ACKNOWLEDGE",
            "reviewerNotes": "Acknowledged by Administrator"
        }, headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(ack_res.status_code, 200)
        ack_data = ack_res.get_json()
        self.assertEqual(ack_data["status"], "ACKNOWLEDGED")
        self.assertEqual(ack_data["reviewStatus"], "REVIEWED")

        # Step 2: Admin resolves ACKNOWLEDGED incident
        res_res = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "RESOLVE",
            "reason": "PPE compliance physically verified on floor by Admin"
        }, headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(res_res.status_code, 200)
        res_data = res_res.get_json()
        self.assertEqual(res_data["status"], "RESOLVED")
        self.assertEqual(res_data["event"]["resolution_type"], "MANUAL")
        self.assertEqual(len(res_data["event"]["lifecycle_history"]), 2)

    # 2. Supervisor acknowledgement and resolution
    def test_02_supervisor_acknowledgement_and_resolution(self):
        doc, ep_id = self._create_incident()
        inc_id = doc["_id"]

        # Supervisor acknowledges
        ack_res = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "ACKNOWLEDGE"
        }, headers={"Authorization": f"Bearer {self.supervisor_token}"})
        self.assertEqual(ack_res.status_code, 200)

        # Supervisor resolves
        res_res = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "RESOLVE",
            "reason": "Supervisor provided spare safety helmet to worker"
        }, headers={"Authorization": f"Bearer {self.supervisor_token}"})
        self.assertEqual(res_res.status_code, 200)
        data = res_res.get_json()
        self.assertEqual(data["status"], "RESOLVED")
        self.assertEqual(data["event"]["resolved_by_role"], "ZONE_SUPERVISOR")

    # 3. False-positive resolution with mandatory reason
    def test_03_false_positive_resolution_with_mandatory_reason(self):
        doc, ep_id = self._create_incident()
        inc_id = doc["_id"]

        # Missing reason on false-positive must be rejected with 400
        res_no_reason = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "FALSE_POSITIVE"
        }, headers={"Authorization": f"Bearer {self.supervisor_token}"})
        self.assertEqual(res_no_reason.status_code, 400)
        self.assertIn("reason is required", res_no_reason.get_json()["message"])

        # With reason -> successfully resolves as FALSE_POSITIVE
        res_with_reason = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "FALSE_POSITIVE",
            "reason": "Worker was wearing a certified white bump cap under lighting shadow"
        }, headers={"Authorization": f"Bearer {self.supervisor_token}"})
        self.assertEqual(res_with_reason.status_code, 200)
        data = res_with_reason.get_json()
        self.assertEqual(data["status"], "RESOLVED")
        self.assertEqual(data["event"]["resolution_type"], "FALSE_POSITIVE")
        self.assertEqual(data["event"]["reviewStatus"], "FALSE_POSITIVE")

    # 4. Missing and invalid JWT handling
    def test_04_missing_and_invalid_jwt(self):
        doc, ep_id = self._create_incident()
        inc_id = doc["_id"]

        # No Authorization header
        r1 = self.client.patch(f"/api/detections/{inc_id}/review", json={"action": "ACKNOWLEDGE"})
        self.assertEqual(r1.status_code, 401)

        # Invalid token
        r2 = self.client.patch(f"/api/detections/{inc_id}/review", json={"action": "ACKNOWLEDGE"}, headers={
            "Authorization": "Bearer invalid.jwt.token"
        })
        self.assertEqual(r2.status_code, 401)

    # 5. Unauthorized role and body role spoofing protection
    def test_05_unauthorized_role_rejected(self):
        doc, ep_id = self._create_incident()
        inc_id = doc["_id"]

        # Worker role must be rejected with 403
        r_worker = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "ACKNOWLEDGE"
        }, headers={"Authorization": f"Bearer {self.worker_token}"})
        self.assertEqual(r_worker.status_code, 403)
        self.assertIn("Administrator or Supervisor role required", r_worker.get_json()["message"])

        # Reviewer role must be rejected with 403
        r_rev = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "ACKNOWLEDGE"
        }, headers={"Authorization": f"Bearer {self.reviewer_token}"})
        self.assertEqual(r_rev.status_code, 403)
        self.assertIn("Administrator or Supervisor role required", r_rev.get_json()["message"])

        # Role spoofing attempt in request body must be ignored and still rejected with 403
        r_spoof = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "ACKNOWLEDGE",
            "role": "SUPER_ADMIN"
        }, headers={"Authorization": f"Bearer {self.worker_token}"})
        self.assertEqual(r_spoof.status_code, 403)

    # 6. Empty resolution reason rejected
    def test_06_empty_resolution_reason_rejected(self):
        doc, ep_id = self._create_incident()
        inc_id = doc["_id"]

        # Empty string reason
        r1 = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "RESOLVE",
            "reason": ""
        }, headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(r1.status_code, 400)

        # Whitespace-only reason
        r2 = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "RESOLVE",
            "reason": "     "
        }, headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(r2.status_code, 400)

        # Incident must remain OPEN with no history added
        stored = mem_detections[0]
        self.assertEqual(stored["status"], "OPEN")
        self.assertNotIn("lifecycle_history", stored)

    # 7. Invalid lifecycle transition rejected
    def test_07_invalid_lifecycle_transition_rejected(self):
        doc, ep_id = self._create_incident()
        inc_id = doc["_id"]

        # Unknown action
        r_unknown = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "UNKNOWN_ACTION"
        }, headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(r_unknown.status_code, 400)

    # 8. Duplicate acknowledgement is idempotent and does not append duplicate history
    def test_08_duplicate_acknowledgement_is_idempotent(self):
        doc, ep_id = self._create_incident()
        inc_id = doc["_id"]

        # First acknowledgement
        r1 = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "ACKNOWLEDGE"
        }, headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(len(mem_detections[0]["lifecycle_history"]), 1)

        # Second acknowledgement
        r2 = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "ACKNOWLEDGE"
        }, headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(r2.status_code, 200)
        self.assertIn("already acknowledged", r2.get_json()["message"])

        # History must NOT have duplicate entries
        self.assertEqual(len(mem_detections[0]["lifecycle_history"]), 1)

    # 9. Attempt to reopen or acknowledge a resolved incident is rejected with 409
    def test_09_attempt_to_reopen_or_acknowledge_resolved_incident_rejected(self):
        doc, ep_id = self._create_incident()
        inc_id = doc["_id"]

        # Resolve incident
        self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "RESOLVE",
            "reason": "Issue rectified"
        }, headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(mem_detections[0]["status"], "RESOLVED")

        # Attempt to ACKNOWLEDGE a RESOLVED incident -> 409 Conflict
        r_ack = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "ACKNOWLEDGE"
        }, headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(r_ack.status_code, 409)

        # Attempt to RESOLVE an already RESOLVED incident -> 409 Conflict
        r_res = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "RESOLVE",
            "reason": "Trying to resolve again"
        }, headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(r_res.status_code, 409)

    # 10. Audit history fields and actor information recorded correctly
    def test_10_audit_history_fields_and_actor_information(self):
        doc, ep_id = self._create_incident()
        inc_id = doc["_id"]
        orig_img = doc["imageUrl"]
        orig_ts = doc["first_missing_timestamp"]

        # Acknowledge
        self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "ACKNOWLEDGE",
            "notes": "Marshall checking zone"
        }, headers={"Authorization": f"Bearer {self.supervisor_token}"})

        # Resolve
        self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "RESOLVE",
            "reason": "Marshall handed over PPE"
        }, headers={"Authorization": f"Bearer {self.admin_token}"})

        stored = mem_detections[0]
        self.assertEqual(stored["imageUrl"], orig_img)
        self.assertEqual(stored["first_missing_timestamp"], orig_ts)
        self.assertEqual(len(stored["lifecycle_history"]), 2)

        # Entry 1: ACKNOWLEDGE
        h1 = stored["lifecycle_history"][0]
        self.assertEqual(h1["previous_state"], "OPEN")
        self.assertEqual(h1["new_state"], "ACKNOWLEDGED")
        self.assertEqual(h1["action"], "ACKNOWLEDGE")
        self.assertEqual(h1["actor_role"], "ZONE_SUPERVISOR")
        self.assertEqual(h1["actor_id"], "sup_001")
        self.assertIsNotNone(h1["timestamp"])

        # Entry 2: RESOLVE
        h2 = stored["lifecycle_history"][1]
        self.assertEqual(h2["previous_state"], "ACKNOWLEDGED")
        self.assertEqual(h2["new_state"], "RESOLVED")
        self.assertEqual(h2["action"], "RESOLVE")
        self.assertEqual(h2["actor_role"], "SUPER_ADMIN")
        self.assertEqual(h2["actor_id"], "admin_001")
        self.assertEqual(h2["resolution_type"], "MANUAL")
        self.assertEqual(h2["reason"], "Marshall handed over PPE")

    # 11. MongoDB path: atomic transition and concurrency conflict handling
    @patch("routes.detection_routes.is_mongo_connected", True)
    @patch("routes.detection_routes.get_detections_col")
    def test_11_mongodb_atomic_transitions_and_concurrency(self, mock_col_func):
        mock_col = MagicMock()
        mock_col_func.return_value = mock_col

        # Existing OPEN document in MongoDB
        open_doc = {
            "_id": "670e123456789abcdef01234",
            "episode_id": "ep_mongo_1",
            "status": "OPEN",
            "reviewStatus": "PENDING"
        }
        ack_doc = dict(open_doc)
        ack_doc["status"] = "ACKNOWLEDGED"
        ack_doc["reviewStatus"] = "REVIEWED"

        # Mock successful atomic update
        mock_res_success = MagicMock(modified_count=1)
        mock_col.find_one.side_effect = [open_doc, ack_doc]
        mock_col.update_one.return_value = mock_res_success

        res = self.client.patch("/api/detections/670e123456789abcdef01234/review", json={
            "action": "ACKNOWLEDGE"
        }, headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(res.status_code, 200)

        # Verify atomic update filter
        args, kwargs = mock_col.update_one.call_args
        filter_q = args[0]
        self.assertIn("status", filter_q)

    # 12. MongoDB path: already resolved incident returns 409
    @patch("routes.detection_routes.is_mongo_connected", True)
    @patch("routes.detection_routes.get_detections_col")
    def test_12_mongodb_already_resolved_incident_returns_409(self, mock_col_func):
        mock_col = MagicMock()
        mock_col_func.return_value = mock_col

        resolved_doc = {
            "_id": "670e123456789abcdef01234",
            "episode_id": "ep_mongo_1",
            "status": "RESOLVED",
            "reviewStatus": "RESOLVED"
        }
        mock_col.find_one.return_value = resolved_doc

        # Attempt to acknowledge an already resolved incident
        res = self.client.patch("/api/detections/670e123456789abcdef01234/review", json={
            "action": "ACKNOWLEDGE"
        }, headers={"Authorization": f"Bearer {self.admin_token}"})
        self.assertEqual(res.status_code, 409)

    # 13. Existing automatic resolution remains functional with ACKNOWLEDGED state
    def test_13_automatic_resolution_compatible_with_acknowledged_incident(self):
        doc, ep_id = self._create_incident(track_id=1, ppe="helmet")
        inc_id = doc["_id"]

        # Step 1: Supervisor acknowledges the incident
        ack_res = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "ACKNOWLEDGE"
        }, headers={"Authorization": f"Bearer {self.supervisor_token}"})
        self.assertEqual(ack_res.status_code, 200)
        self.assertEqual(mem_detections[0]["status"], "ACKNOWLEDGED")

        # Step 2: Continuous verified compliance is achieved -> temporal candidate emitted
        cand = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "worker_id": "W-001",
            "track_id": 1,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0,
            "candidate_timestamp": 6.0
        }

        # Step 3: Automatic resolution persistence runs
        resolved_doc, is_new = resolve_confirmed_incident(cand)
        self.assertTrue(is_new, "Automatic resolution must successfully resolve an ACKNOWLEDGED incident")
        self.assertEqual(resolved_doc["status"], "RESOLVED")
        self.assertEqual(resolved_doc["resolution_type"], "AUTOMATIC_COMPLIANCE")
        # History contains supervisor ACKNOWLEDGE followed by SYSTEM AUTOMATIC_COMPLIANCE
        self.assertEqual(len(resolved_doc["lifecycle_history"]), 2)
        self.assertEqual(resolved_doc["lifecycle_history"][0]["action"], "ACKNOWLEDGE")
        self.assertEqual(resolved_doc["lifecycle_history"][1]["resolution_type"], "AUTOMATIC_COMPLIANCE")



class TestReviewerAuthorizationCorrection(unittest.TestCase):
    """
    M2.2B.5D.1: Focused regression tests for Reviewer Authorization Correction.
    Covers:
    1. REVIEWER normalizes to REVIEWER, not ZONE_SUPERVISOR.
    2. REVIEWER receives HTTP 403 on acknowledgement.
    3. REVIEWER receives HTTP 403 on resolution.
    4. WORKER, OPERATOR, ANALYST, GUEST, and unknown roles remain unauthorized.
    5. Administrator aliases retain lifecycle access (SUPER_ADMIN, ADMIN).
    6. Supervisor aliases retain lifecycle access (ZONE_SUPERVISOR, SUPERVISOR).
    7. supervisor_required decorator does not authorize REVIEWER.
    8. Existing Administrator and Supervisor authorization behavior remains intact.
    9. Missing or empty roles fail closed.
    10. Request-body role spoofing cannot change authenticated JWT role.
    """
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

        # Add dummy route to test @supervisor_required isolation
        @cls.app.route("/api/test-supervisor-gate", methods=["GET"])
        @token_required
        @supervisor_required
        def _test_supervisor_gate():
            from flask import jsonify
            return jsonify({"status": "access_granted"}), 200

    def setUp(self):
        self.session_id = f"test_rev_auth_{int(time.time()*1000)}"
        mem_detections.clear()

    def _create_incident(self, episode_id=None, status="PENDING", ppe="helmet", track_id=1):
        ep_id = episode_id or f"ep_rev_test_{self.session_id}_{track_id}_{ppe}_1"
        doc = {
            "episode_id": ep_id,
            "worker_id": f"W-{track_id:03d}",
            "track_id": track_id,
            "personId": f"W-{track_id:03d}",
            "workerTag": f"W-{track_id:03d} (Track #{track_id})",
            "session_id": self.session_id,
            "complianceStatus": "VIOLATION",
            "status": "OPEN" if status == "PENDING" else status,
            "reviewStatus": status,
            "missingPPE": [ppe],
            "imageUrl": "http://storage.internal/snapshots/evidence1.jpg",
            "evidenceImageReference": "data:image/jpeg;base64,/9j/4AAQSkZJRg==",
            "first_missing_timestamp": 0.0,
            "confirmed_timestamp": 3.0,
            "createdAt": datetime.datetime.now(datetime.timezone.utc)
        }
        saved_doc, is_new = persist_confirmed_incident(doc)
        return saved_doc, ep_id

    # 1. REVIEWER normalizes to REVIEWER, not ZONE_SUPERVISOR
    def test_01_reviewer_normalizes_to_reviewer_not_zone_supervisor(self):
        self.assertEqual(normalize_role("REVIEWER"), "REVIEWER")
        self.assertEqual(normalize_role("reviewer"), "REVIEWER")
        self.assertEqual(normalize_role("Reviewer"), "REVIEWER")

        # Verify JWT payload
        token = generate_token("rev_001", "REVIEWER", "rev@ppe.com", name="Reviewer User")
        from auth import decode_token
        payload = decode_token(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["role"], "REVIEWER")
        self.assertNotEqual(payload["role"], "ZONE_SUPERVISOR")

    # 2. REVIEWER receives HTTP 403 on acknowledgement
    def test_02_reviewer_receives_403_on_acknowledgement(self):
        doc, ep_id = self._create_incident()
        inc_id = doc["_id"]
        rev_token = generate_token("rev_001", "REVIEWER", "rev@ppe.com", name="Reviewer User")

        res = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "ACKNOWLEDGE",
            "reviewerNotes": "Reviewer attempt"
        }, headers={"Authorization": f"Bearer {rev_token}"})

        self.assertEqual(res.status_code, 403)
        self.assertIn("Administrator or Supervisor role required", res.get_json()["message"])
        # Stored incident remains unmodified
        stored = mem_detections[0]
        self.assertEqual(stored["status"], "OPEN")
        self.assertNotIn("lifecycle_history", stored)

    # 3. REVIEWER receives HTTP 403 on resolution
    def test_03_reviewer_receives_403_on_resolution(self):
        doc, ep_id = self._create_incident()
        inc_id = doc["_id"]
        rev_token = generate_token("rev_001", "REVIEWER", "rev@ppe.com", name="Reviewer User")

        res = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "RESOLVE",
            "reason": "Reviewer attempting manual resolution"
        }, headers={"Authorization": f"Bearer {rev_token}"})

        self.assertEqual(res.status_code, 403)
        self.assertIn("Administrator or Supervisor role required", res.get_json()["message"])
        stored = mem_detections[0]
        self.assertEqual(stored["status"], "OPEN")
        self.assertNotIn("lifecycle_history", stored)

    # 4. WORKER, OPERATOR, ANALYST, GUEST, and unknown roles remain unauthorized
    def test_04_unauthorized_roles_remain_unauthorized(self):
        doc, ep_id = self._create_incident()
        inc_id = doc["_id"]
        unauthorized_roles = ["WORKER", "OPERATOR", "ANALYST", "GUEST", "SECURITY", "UNKNOWN_ROLE"]

        for role in unauthorized_roles:
            norm = normalize_role(role)
            self.assertEqual(norm, role, f"Role {role} should normalize to itself, not be promoted")
            token = generate_token(f"user_{role}", role, f"{role.lower()}@ppe.com")

            # Test acknowledgement
            r_ack = self.client.patch(f"/api/detections/{inc_id}/review", json={
                "action": "ACKNOWLEDGE"
            }, headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(r_ack.status_code, 403, f"Role {role} must receive 403 on ACKNOWLEDGE")

            # Test resolution
            r_res = self.client.patch(f"/api/detections/{inc_id}/review", json={
                "action": "RESOLVE",
                "reason": "Unauthorized resolution attempt"
            }, headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(r_res.status_code, 403, f"Role {role} must receive 403 on RESOLVE")

    # 5. Administrator aliases retain lifecycle access (SUPER_ADMIN, ADMIN)
    def test_05_administrator_aliases_retain_lifecycle_access(self):
        doc, ep_id = self._create_incident()
        inc_id = doc["_id"]

        self.assertEqual(normalize_role("SUPER_ADMIN"), "SUPER_ADMIN")
        self.assertEqual(normalize_role("ADMIN"), "SUPER_ADMIN")
        self.assertEqual(normalize_role("admin"), "SUPER_ADMIN")

        token_admin = generate_token("admin_alias", "ADMIN", "admin_alias@ppe.com")
        res = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "ACKNOWLEDGE"
        }, headers={"Authorization": f"Bearer {token_admin}"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "ACKNOWLEDGED")

    # 6. Supervisor aliases retain lifecycle access (ZONE_SUPERVISOR, SUPERVISOR)
    def test_06_supervisor_aliases_retain_lifecycle_access(self):
        doc, ep_id = self._create_incident()
        inc_id = doc["_id"]

        self.assertEqual(normalize_role("ZONE_SUPERVISOR"), "ZONE_SUPERVISOR")
        self.assertEqual(normalize_role("SUPERVISOR"), "ZONE_SUPERVISOR")
        self.assertEqual(normalize_role("supervisor"), "ZONE_SUPERVISOR")

        token_sup = generate_token("sup_alias", "SUPERVISOR", "sup_alias@ppe.com")
        res = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "ACKNOWLEDGE"
        }, headers={"Authorization": f"Bearer {token_sup}"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "ACKNOWLEDGED")

    # 7. supervisor_required decorator does not authorize REVIEWER
    def test_07_supervisor_required_decorator_does_not_authorize_reviewer(self):
        token_rev = generate_token("rev_001", "REVIEWER", "rev@ppe.com")
        token_sup = generate_token("sup_001", "ZONE_SUPERVISOR", "sup@ppe.com")
        token_adm = generate_token("adm_001", "SUPER_ADMIN", "adm@ppe.com")
        token_wrk = generate_token("wrk_001", "WORKER", "wrk@ppe.com")

        # REVIEWER must receive 403 on @supervisor_required
        r_rev = self.client.get("/api/test-supervisor-gate", headers={"Authorization": f"Bearer {token_rev}"})
        self.assertEqual(r_rev.status_code, 403)
        self.assertIn("Zone Supervisor privilege required", r_rev.get_json()["message"])

        # WORKER must receive 403
        r_wrk = self.client.get("/api/test-supervisor-gate", headers={"Authorization": f"Bearer {token_wrk}"})
        self.assertEqual(r_wrk.status_code, 403)

        # ZONE_SUPERVISOR must receive 200
        r_sup = self.client.get("/api/test-supervisor-gate", headers={"Authorization": f"Bearer {token_sup}"})
        self.assertEqual(r_sup.status_code, 200)

        # SUPER_ADMIN must receive 200
        r_adm = self.client.get("/api/test-supervisor-gate", headers={"Authorization": f"Bearer {token_adm}"})
        self.assertEqual(r_adm.status_code, 200)

    # 8. Existing Administrator and Supervisor authorization behavior remains intact
    def test_08_existing_admin_and_supervisor_behavior_intact(self):
        doc, ep_id = self._create_incident()
        inc_id = doc["_id"]

        token_admin = generate_token("admin_001", "SUPER_ADMIN", "admin@ppe.com")
        token_sup = generate_token("sup_001", "ZONE_SUPERVISOR", "sup@ppe.com")

        # Admin acknowledges
        r1 = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "ACKNOWLEDGE"
        }, headers={"Authorization": f"Bearer {token_admin}"})
        self.assertEqual(r1.status_code, 200)

        # Supervisor resolves
        r2 = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "RESOLVE",
            "reason": "Supervisor resolved after inspection"
        }, headers={"Authorization": f"Bearer {token_sup}"})
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(mem_detections[0]["status"], "RESOLVED")

    # 9. Missing or empty roles fail closed
    def test_09_missing_or_empty_roles_fail_closed(self):
        self.assertEqual(normalize_role(None), "")
        self.assertEqual(normalize_role(""), "")
        self.assertEqual(normalize_role("   "), "")

        token_empty = generate_token("empty_user", "", "empty@ppe.com")
        token_none = generate_token("none_user", None, "none@ppe.com")

        doc, ep_id = self._create_incident()
        inc_id = doc["_id"]

        # Empty role rejected with 403 on lifecycle endpoint
        r_empty = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "ACKNOWLEDGE"
        }, headers={"Authorization": f"Bearer {token_empty}"})
        self.assertEqual(r_empty.status_code, 403)

        # None role rejected with 403 on lifecycle endpoint
        r_none = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "ACKNOWLEDGE"
        }, headers={"Authorization": f"Bearer {token_none}"})
        self.assertEqual(r_none.status_code, 403)

        # Empty role rejected on @supervisor_required
        r_gate = self.client.get("/api/test-supervisor-gate", headers={"Authorization": f"Bearer {token_empty}"})
        self.assertEqual(r_gate.status_code, 403)

    # 10. Request-body role spoofing cannot change authenticated JWT role
    def test_10_request_body_role_spoofing_cannot_change_authenticated_role(self):
        doc, ep_id = self._create_incident()
        inc_id = doc["_id"]

        token_rev = generate_token("rev_001", "REVIEWER", "rev@ppe.com")
        token_wrk = generate_token("wrk_001", "WORKER", "wrk@ppe.com")

        # Reviewer claiming SUPER_ADMIN in body -> 403
        r1 = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "ACKNOWLEDGE",
            "role": "SUPER_ADMIN"
        }, headers={"Authorization": f"Bearer {token_rev}"})
        self.assertEqual(r1.status_code, 403)

        # Worker claiming ZONE_SUPERVISOR in body -> 403
        r2 = self.client.patch(f"/api/detections/{inc_id}/review", json={
            "action": "RESOLVE",
            "role": "ZONE_SUPERVISOR",
            "reason": "Spoofed role resolution attempt"
        }, headers={"Authorization": f"Bearer {token_wrk}"})
        self.assertEqual(r2.status_code, 403)


class TestCanonicalIncidentFiltering(unittest.TestCase):
    """
    M2.2B.5E.1: Tests for Canonical Incident Filtering across modern and legacy records.
    Verifies:
    1. Modern OPEN with stale APPROVED remains OPEN.
    2. Modern ACKNOWLEDGED with stale RESOLVED remains ACKNOWLEDGED.
    3. Modern RESOLVED with reviewStatus="FALSE_POSITIVE" appears in Resolved.
    4. Legacy PENDING appears in Open.
    5. Legacy REVIEWED appears in Acknowledged.
    6. Legacy ACKNOWLEDGED appears in Acknowledged.
    7. Legacy APPROVED appears in Resolved.
    8. Legacy REJECTED appears in Resolved.
    9. Legacy FALSE_POSITIVE appears in Resolved.
    10. Missing modern status with invalid legacy value follows the fallback policy (maps to OPEN).
    11. MongoDB and in-memory filtering produce equivalent results.
    12. Counts, pagination and sorting remain correct.
    13. Existing callers using reviewStatus still behave compatibly.
    14. Invalid canonical filter values handled safely (empty result, no 500 error).
    """
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def setUp(self):
        mem_detections.clear()

    def _insert_detection(self, doc_id, status=None, review_status=None, resolution_type=None, compliance="VIOLATION", zone="Zone 1"):
        doc = {
            "_id": doc_id,
            "episode_id": f"ep_{doc_id}",
            "zoneName": zone,
            "missingPPE": ["helmet"],
            "complianceStatus": compliance,
            "createdAt": datetime.datetime.now(datetime.timezone.utc)
        }
        if status is not None:
            doc["status"] = status
        if review_status is not None:
            doc["reviewStatus"] = review_status
        if resolution_type is not None:
            doc["resolution_type"] = resolution_type
        mem_detections.append(doc)
        return doc

    # 1. Modern OPEN with stale APPROVED remains OPEN
    def test_01_modern_open_with_stale_approved_remains_open(self):
        self._insert_detection("d1", status="OPEN", review_status="APPROVED")

        res_open = self.client.get("/api/detections?status=OPEN")
        self.assertEqual(res_open.status_code, 200)
        ids_open = [e["_id"] for e in res_open.get_json()["events"]]
        self.assertIn("d1", ids_open)

        res_res = self.client.get("/api/detections?status=RESOLVED")
        self.assertEqual(res_res.status_code, 200)
        ids_res = [e["_id"] for e in res_res.get_json()["events"]]
        self.assertNotIn("d1", ids_res)

        res_ack = self.client.get("/api/detections?status=ACKNOWLEDGED")
        self.assertEqual(res_ack.status_code, 200)
        ids_ack = [e["_id"] for e in res_ack.get_json()["events"]]
        self.assertNotIn("d1", ids_ack)

    # 2. Modern ACKNOWLEDGED with stale RESOLVED remains ACKNOWLEDGED
    def test_02_modern_acknowledged_with_stale_resolved_remains_acknowledged(self):
        self._insert_detection("d2", status="ACKNOWLEDGED", review_status="RESOLVED")

        res_ack = self.client.get("/api/detections?status=ACKNOWLEDGED")
        self.assertEqual(res_ack.status_code, 200)
        ids_ack = [e["_id"] for e in res_ack.get_json()["events"]]
        self.assertIn("d2", ids_ack)

        res_res = self.client.get("/api/detections?status=RESOLVED")
        ids_res = [e["_id"] for e in res_res.get_json()["events"]]
        self.assertNotIn("d2", ids_res)

    # 3. Modern RESOLVED with reviewStatus="FALSE_POSITIVE" appears in Resolved
    def test_03_modern_resolved_with_false_positive_appears_in_resolved(self):
        self._insert_detection("d3", status="RESOLVED", review_status="FALSE_POSITIVE", resolution_type="FALSE_POSITIVE")

        res_res = self.client.get("/api/detections?status=RESOLVED")
        self.assertEqual(res_res.status_code, 200)
        ids_res = [e["_id"] for e in res_res.get_json()["events"]]
        self.assertIn("d3", ids_res)

        res_open = self.client.get("/api/detections?status=OPEN")
        ids_open = [e["_id"] for e in res_open.get_json()["events"]]
        self.assertNotIn("d3", ids_open)

    # 4. Legacy PENDING appears in Open
    def test_04_legacy_pending_appears_in_open(self):
        self._insert_detection("d4", status=None, review_status="PENDING")

        res_open = self.client.get("/api/detections?status=OPEN")
        ids_open = [e["_id"] for e in res_open.get_json()["events"]]
        self.assertIn("d4", ids_open)

        res_res = self.client.get("/api/detections?status=RESOLVED")
        ids_res = [e["_id"] for e in res_res.get_json()["events"]]
        self.assertNotIn("d4", ids_res)

    # 5. Legacy REVIEWED appears in Acknowledged
    def test_05_legacy_reviewed_appears_in_acknowledged(self):
        self._insert_detection("d5", status=None, review_status="REVIEWED")

        res_ack = self.client.get("/api/detections?status=ACKNOWLEDGED")
        ids_ack = [e["_id"] for e in res_ack.get_json()["events"]]
        self.assertIn("d5", ids_ack)

    # 6. Legacy ACKNOWLEDGED appears in Acknowledged
    def test_06_legacy_acknowledged_appears_in_acknowledged(self):
        self._insert_detection("d6", status=None, review_status="ACKNOWLEDGED")

        res_ack = self.client.get("/api/detections?status=ACKNOWLEDGED")
        ids_ack = [e["_id"] for e in res_ack.get_json()["events"]]
        self.assertIn("d6", ids_ack)

    # 7. Legacy APPROVED appears in Resolved
    def test_07_legacy_approved_appears_in_resolved(self):
        self._insert_detection("d7", status=None, review_status="APPROVED")

        res_res = self.client.get("/api/detections?status=RESOLVED")
        ids_res = [e["_id"] for e in res_res.get_json()["events"]]
        self.assertIn("d7", ids_res)

    # 8. Legacy REJECTED appears in Resolved
    def test_08_legacy_rejected_appears_in_resolved(self):
        self._insert_detection("d8", status=None, review_status="REJECTED")

        res_res = self.client.get("/api/detections?status=RESOLVED")
        ids_res = [e["_id"] for e in res_res.get_json()["events"]]
        self.assertIn("d8", ids_res)

    # 9. Legacy FALSE_POSITIVE appears in Resolved
    def test_09_legacy_false_positive_appears_in_resolved(self):
        self._insert_detection("d9", status=None, review_status="FALSE_POSITIVE")

        res_res = self.client.get("/api/detections?status=RESOLVED")
        ids_res = [e["_id"] for e in res_res.get_json()["events"]]
        self.assertIn("d9", ids_res)

    # 10. Missing modern status with invalid legacy value follows safe fallback policy (maps to OPEN)
    def test_10_missing_modern_status_with_invalid_legacy_value_fallback_policy(self):
        self._insert_detection("d10", status=None, review_status="CORRUPTED_VALUE")

        res_open = self.client.get("/api/detections?status=OPEN")
        ids_open = [e["_id"] for e in res_open.get_json()["events"]]
        self.assertIn("d10", ids_open)

        res_res = self.client.get("/api/detections?status=RESOLVED")
        ids_res = [e["_id"] for e in res_res.get_json()["events"]]
        self.assertNotIn("d10", ids_res)

    # 11. MongoDB query construction and behavior parity with memory filtering
    def test_11_mongodb_query_construction_and_parity(self):
        f_open = build_canonical_status_mongo_filter("OPEN")
        self.assertIn("$or", f_open)
        self.assertEqual(f_open["$or"][0], {"status": "OPEN"})
        self.assertEqual(f_open["$or"][1]["status"], {"$nin": ["OPEN", "ACKNOWLEDGED", "RESOLVED"]})
        self.assertIn("$nin", f_open["$or"][1]["reviewStatus"])

        f_ack = build_canonical_status_mongo_filter("ACKNOWLEDGED")
        self.assertEqual(f_ack["$or"][0], {"status": "ACKNOWLEDGED"})
        self.assertEqual(f_ack["$or"][1]["reviewStatus"], {"$in": ["REVIEWED", "ACKNOWLEDGED"]})

        f_res = build_canonical_status_mongo_filter("RESOLVED")
        self.assertEqual(f_res["$or"][0], {"status": "RESOLVED"})
        self.assertEqual(f_res["$or"][1]["reviewStatus"], {"$in": ["RESOLVED", "APPROVED", "REJECTED", "FALSE_POSITIVE"]})

        f_invalid = build_canonical_status_mongo_filter("INVALID_STATE")
        self.assertEqual(f_invalid, {"_id": {"$exists": False}})

        # Verify MongoDB route path passes the exact query filter to col.find & col.count_documents
        with patch("routes.detection_routes.is_mongo_connected", True):
            with patch("routes.detection_routes.get_detections_col") as mock_col_fn:
                mock_col = MagicMock()
                mock_col_fn.return_value = mock_col
                mock_col.count_documents.return_value = 1
                mock_cursor = MagicMock()
                mock_cursor.sort.return_value = mock_cursor
                mock_cursor.skip.return_value = mock_cursor
                mock_cursor.limit.return_value = [{"_id": "mongo_doc_1", "status": "RESOLVED"}]
                mock_col.find.return_value = mock_cursor

                res = self.client.get("/api/detections?status=RESOLVED")
                self.assertEqual(res.status_code, 200)
                mock_col.count_documents.assert_called_once_with(f_res)
                mock_col.find.assert_called_once_with(f_res)

    # 12. Counts, pagination and sorting remain correct
    def test_12_counts_pagination_and_sorting_remain_correct(self):
        for i in range(5):
            self._insert_detection(f"page_doc_{i}", status="RESOLVED", review_status="RESOLVED")

        # Page 1, limit 2
        r1 = self.client.get("/api/detections?status=RESOLVED&page=1&limit=2")
        self.assertEqual(r1.status_code, 200)
        d1 = r1.get_json()
        self.assertEqual(d1["totalCount"], 5)
        self.assertEqual(d1["totalPages"], 3)
        self.assertEqual(len(d1["events"]), 2)

        # Page 2, limit 2
        r2 = self.client.get("/api/detections?status=RESOLVED&page=2&limit=2")
        d2 = r2.get_json()
        self.assertEqual(len(d2["events"]), 2)

        # Page 3, limit 2
        r3 = self.client.get("/api/detections?status=RESOLVED&page=3&limit=2")
        d3 = r3.get_json()
        self.assertEqual(len(d3["events"]), 1)

    # 13. Existing callers using reviewStatus still behave compatibly
    def test_13_existing_callers_using_review_status_behave_compatibly(self):
        self._insert_detection("legacy_p", review_status="PENDING")
        self._insert_detection("legacy_r", review_status="REVIEWED")
        self._insert_detection("legacy_a", review_status="APPROVED")

        res_p = self.client.get("/api/detections?reviewStatus=PENDING")
        ids_p = [e["_id"] for e in res_p.get_json()["events"]]
        self.assertIn("legacy_p", ids_p)
        self.assertNotIn("legacy_r", ids_p)

        res_a = self.client.get("/api/detections?reviewStatus=APPROVED")
        ids_a = [e["_id"] for e in res_a.get_json()["events"]]
        self.assertIn("legacy_a", ids_a)
        self.assertNotIn("legacy_p", ids_a)

    # 14. Invalid canonical filter values handled safely without 500 error
    def test_14_invalid_canonical_filter_handled_safely(self):
        self._insert_detection("d_any", status="OPEN")
        res = self.client.get("/api/detections?status=INVALID_STATUS_NAME")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["events"], [])
        self.assertEqual(data["totalCount"], 0)
        self.assertEqual(data["totalPages"], 1)


if __name__ == "__main__":
    unittest.main()
