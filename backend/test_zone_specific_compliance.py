import base64
import copy
import unittest
from unittest.mock import patch
import numpy as np
import cv2
import uuid
import datetime

from app import create_app
from database import mem_detections, mem_cameras, mem_zones, is_mongo_connected
from ai_engine.temporal_compliance import (
    TrackPPEState,
    TemporalState,
    SessionTemporalTracker,
    get_session_temporal_tracker,
    reset_session_temporal
)
from ai_engine.compliance import evaluate_compliance, normalize_ppe_class
from ai_engine.zone_assignment import (
    assign_persons_spatial_zones,
    get_authoritative_zone_ppe,
    lookup_camera,
    lookup_zone,
    reset_session_spatial_zones
)
from routes.detection_routes import resolve_confirmed_incident

class TestZoneSpecificComplianceIntegration(unittest.TestCase):
    """
    Milestone M2.2B.7D: Zone-Specific PPE Policy & Pipeline Integration Tests.
    Verifies multi-worker independent zone evaluation, authoritative zone policy retrieval,
    unassigned / uncertain boundary safety, temporal compliance zone isolation,
    and zone-matched auto-resolution safety.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

        # Generate synthetic 640x480 test image
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        img[100:200, 100:200] = [0, 255, 255]
        _, buf = cv2.imencode('.jpg', img)
        cls.synthetic_jpeg_bytes = buf.tobytes()
        cls.synthetic_b64 = base64.b64encode(cls.synthetic_jpeg_bytes).decode('utf-8')

    def setUp(self):
        self.session_id = f"test_zone_int_{uuid.uuid4().hex[:8]}"
        reset_session_temporal(self.session_id)
        reset_session_spatial_zones(self.session_id)

        self._orig_mem_cameras = list(mem_cameras)
        self._orig_mem_zones = list(mem_zones)
        self._orig_mem_detections = list(mem_detections)
        mem_detections.clear()

        # Ensure canonical General Zone (no goggles) and Welding Zone (requires goggles) exist
        self.zone_general_id = "zone_01"
        self.zone_welding_id = "zone_welding"

        # General Zone: helmet, vest, boots (NO goggles required)
        if not any(str(z.get("_id")) == self.zone_general_id for z in mem_zones):
            mem_zones.append({
                "_id": self.zone_general_id,
                "name": "Heavy Assembly Bay 01",
                "code": "BAY-01",
                "requiredPPE": ["helmet", "vest", "boots"]
            })
        else:
            z = next(z for z in mem_zones if str(z.get("_id")) == self.zone_general_id)
            z["requiredPPE"] = ["helmet", "vest", "boots"]

        # Welding Zone: helmet, vest, boots, goggles (goggles strictly required)
        if not any(str(z.get("_id")) == self.zone_welding_id for z in mem_zones):
            mem_zones.append({
                "_id": self.zone_welding_id,
                "name": "Welding & Cutting Bay",
                "code": "WELD-04",
                "requiredPPE": ["helmet", "vest", "boots", "goggles"]
            })
        else:
            z = next(z for z in mem_zones if str(z.get("_id")) == self.zone_welding_id)
            z["requiredPPE"] = ["helmet", "vest", "boots", "goggles"]

        # Camera with dual polygon configuration:
        # Left polygon: General Zone (x in [0.05, 0.45], y in [0.05, 0.95])
        # Right polygon: Welding Zone (x in [0.55, 0.95], y in [0.05, 0.95])
        self.camera_id = "cam_dual_zone_test"
        self.camera_doc = {
            "_id": self.camera_id,
            "name": "Dual Zone Test Camera",
            "zoneId": self.zone_general_id,
            "zoneName": "Heavy Assembly Bay 01",
            "sourceType": "webcam",
            "zones": [
                {
                    "zoneId": self.zone_general_id,
                    "zoneName": "Heavy Assembly Bay 01",
                    "polygon": [
                        {"x": 0.05, "y": 0.05},
                        {"x": 0.45, "y": 0.05},
                        {"x": 0.45, "y": 0.95},
                        {"x": 0.05, "y": 0.95}
                    ],
                    "priority": 1
                },
                {
                    "zoneId": self.zone_welding_id,
                    "zoneName": "Welding & Cutting Bay",
                    "polygon": [
                        {"x": 0.55, "y": 0.05},
                        {"x": 0.95, "y": 0.05},
                        {"x": 0.95, "y": 0.95},
                        {"x": 0.55, "y": 0.95}
                    ],
                    "priority": 2
                }
            ]
        }
        mem_cameras.insert(0, self.camera_doc)

    def tearDown(self):
        reset_session_temporal(self.session_id)
        reset_session_spatial_zones(self.session_id)
        mem_cameras.clear()
        mem_cameras.extend(self._orig_mem_cameras)
        mem_zones.clear()
        mem_zones.extend(self._orig_mem_zones)
        mem_detections.clear()
        mem_detections.extend(self._orig_mem_detections)

    # =========================================================================
    # 1. Authoritative Zone Policy Retrieval Tests
    # =========================================================================

    def test_authoritative_zone_ppe_normalizes_aliases(self):
        """Aliases like 'safety_shoe' and 'hard hat' must normalize to canonical 4."""
        test_zid = "zone_alias_test"
        mem_zones.append({
            "_id": test_zid,
            "name": "Alias Zone",
            "requiredPPE": ["Hard Hat", "reflective vest", "safety_shoe", "safety glasses", "unsupported_item"]
        })
        policy = get_authoritative_zone_ppe(test_zid)
        self.assertIsNotNone(policy)
        self.assertEqual(policy, ["helmet", "vest", "goggles", "boots"])

    def test_authoritative_zone_ppe_general_zone_does_not_require_goggles(self):
        """General factory floor policy must require helmet, vest, boots and NOT goggles."""
        policy = get_authoritative_zone_ppe(self.zone_general_id)
        self.assertEqual(policy, ["helmet", "vest", "boots"])
        self.assertNotIn("goggles", policy)

    def test_authoritative_zone_ppe_welding_zone_requires_goggles(self):
        """Welding zone policy must require helmet, vest, boots, and goggles."""
        policy = get_authoritative_zone_ppe(self.zone_welding_id)
        self.assertEqual(policy, ["helmet", "vest", "goggles", "boots"])
        self.assertIn("goggles", policy)

    def test_authoritative_zone_ppe_missing_or_invalid_returns_none(self):
        """Non-existent zone or invalid policy (non-list) returns None (triggers UNCERTAIN)."""
        self.assertIsNone(get_authoritative_zone_ppe("non_existent_zone_999"))
        self.assertIsNone(get_authoritative_zone_ppe(None))

        bad_zid = "zone_bad_policy"
        mem_zones.append({"_id": bad_zid, "name": "Bad Zone", "requiredPPE": "not_a_list"})
        self.assertIsNone(get_authoritative_zone_ppe(bad_zid))

    # =========================================================================
    # 2. Multi-Worker Independent Policy Evaluation in Same Frame
    # =========================================================================

    def test_multi_worker_independent_zone_evaluation(self):
        """
        Worker A in General Zone without goggles is COMPLIANT (goggles not required).
        Worker B in Welding Zone without goggles is VIOLATION (goggles required).
        Evaluated in the exact same camera frame!
        """
        # Frame: 640x480
        # Worker A: bbox [80, 100, 200, 400] -> anchor_x = 140/640 = 0.21875, anchor_y = 100+0.95*300 = 385/480 = 0.802 -> General Zone
        # Worker B: bbox [400, 100, 520, 400] -> anchor_x = 460/640 = 0.71875, anchor_y = 385/480 = 0.802 -> Welding Zone
        workers = [
            {"bbox": [80, 100, 200, 400], "confidence": 0.95, "track_id": 1, "worker_id": "W-001"},
            {"bbox": [400, 100, 520, 400], "confidence": 0.95, "track_id": 2, "worker_id": "W-002"}
        ]

        # Both workers are wearing helmet, vest, boots (neither is wearing goggles)
        detected_objects = [
            # Worker A gear
            {"bbox": [90, 100, 190, 160], "name": "helmet", "class": "helmet", "source": "yolo", "is_synthetic": False, "confidence": 0.95},
            {"bbox": [85, 170, 195, 300], "name": "vest", "class": "vest", "source": "yolo", "is_synthetic": False, "confidence": 0.95},
            {"bbox": [90, 340, 190, 400], "name": "boots", "class": "boots", "source": "yolo", "is_synthetic": False, "confidence": 0.95},
            # Worker B gear
            {"bbox": [410, 100, 510, 160], "name": "helmet", "class": "helmet", "source": "yolo", "is_synthetic": False, "confidence": 0.95},
            {"bbox": [405, 170, 515, 300], "name": "vest", "class": "vest", "source": "yolo", "is_synthetic": False, "confidence": 0.95},
            {"bbox": [410, 340, 510, 400], "name": "boots", "class": "boots", "source": "yolo", "is_synthetic": False, "confidence": 0.95}
        ]

        # Step 1: Assign spatial zones (using session_id=None for direct single-frame evaluation)
        assigned = assign_persons_spatial_zones(
            workers, self.camera_doc, img_shape=(480, 640), session_id=None, timestamp=0.0
        )
        self.assertEqual(assigned[0]["zone_id"], self.zone_general_id)
        self.assertEqual(assigned[0]["zone_assignment_status"], "ASSIGNED")
        self.assertEqual(assigned[1]["zone_id"], self.zone_welding_id)
        self.assertEqual(assigned[1]["zone_assignment_status"], "ASSIGNED")

        # Step 2: Apply authoritative policies per worker
        for p in assigned:
            p["required_ppe"] = get_authoritative_zone_ppe(p["zone_id"])

        self.assertEqual(assigned[0]["required_ppe"], ["helmet", "vest", "boots"])
        self.assertEqual(assigned[1]["required_ppe"], ["helmet", "vest", "goggles", "boots"])

        # Step 3: Evaluate compliance
        tracker = get_session_temporal_tracker(self.session_id)
        status, missing, eval_persons = evaluate_compliance(
            assigned, detected_objects, required_ppe=["helmet", "vest"], img_shape=(480, 640),
            session_id=self.session_id, timestamp=0.0, temporal_tracker=tracker
        )

        # Worker A must be COMPLIANT (not penalized for missing goggles!)
        self.assertTrue(eval_persons[0]["compliant"])
        self.assertEqual(eval_persons[0]["missing_ppe"], [])
        self.assertEqual(eval_persons[0]["pending_missing_ppe"], [])

        # Worker B must be PENDING/VIOLATION for goggles (goggles required in Welding Zone)
        self.assertIn("goggles", eval_persons[1]["pending_missing_ppe"])
        self.assertNotIn("helmet", eval_persons[1]["pending_missing_ppe"])
        self.assertNotIn("vest", eval_persons[1]["pending_missing_ppe"])
        self.assertNotIn("boots", eval_persons[1]["pending_missing_ppe"])

    # =========================================================================
    # 3. Unassigned & Uncertain Zone Worker Safety Tests
    # =========================================================================

    def test_unassigned_worker_generates_zero_violations(self):
        """Worker in neutral aisle (between zones) generates NO violations even if gear is missing."""
        # Worker in center aisle: x in [0.46, 0.54] (between General Zone and Welding Zone)
        worker = [{"bbox": [300, 100, 340, 400], "confidence": 0.95, "track_id": 10, "worker_id": "W-010"}]
        # No gear detected
        detected_objects = []

        assigned = assign_persons_spatial_zones(
            worker, self.camera_doc, img_shape=(480, 640), session_id=self.session_id, timestamp=0.0
        )
        self.assertEqual(assigned[0]["zone_assignment_status"], "UNASSIGNED")
        self.assertIsNone(assigned[0]["zone_id"])

        tracker = get_session_temporal_tracker(self.session_id)
        status, missing, eval_persons = evaluate_compliance(
            assigned, detected_objects, required_ppe=["helmet", "vest"], img_shape=(480, 640),
            session_id=self.session_id, timestamp=0.0, temporal_tracker=tracker
        )

        # Unassigned worker in neutral area must generate zero violations!
        # According to M2.2B.7D-F: unassigned workers are represented as UNCERTAIN (not COMPLIANT),
        # with uncertain_reason="NO_MONITORED_ZONE" and zero violation accumulation.
        self.assertFalse(eval_persons[0]["compliant"])
        self.assertTrue(eval_persons[0]["uncertain"])
        self.assertEqual(eval_persons[0].get("uncertain_reason"), "NO_MONITORED_ZONE")
        self.assertEqual(eval_persons[0]["missing_ppe"], [])
        self.assertEqual(eval_persons[0]["pending_missing_ppe"], [])
        self.assertEqual(eval_persons[0]["new_confirmed_violations"], [])
        self.assertEqual(status, "UNCERTAIN")

    def test_uncertain_zone_worker_generates_no_violations(self):
        """Worker anchor on polygon boundary produces UNCERTAIN status and NO violations."""
        # Worker whose anchor lands exactly on boundary of General Zone: x = 0.05
        # Frame width 640 -> anchor_x = 32 -> x1=20, x2=44 -> anchor = 32 -> 32/640 = 0.05
        worker = [{"bbox": [20, 100, 44, 400], "confidence": 0.95, "track_id": 11, "worker_id": "W-011"}]
        detected_objects = []

        assigned = assign_persons_spatial_zones(
            worker, self.camera_doc, img_shape=(480, 640), session_id=self.session_id, timestamp=0.0
        )
        self.assertEqual(assigned[0]["zone_assignment_status"], "UNCERTAIN")

        tracker = get_session_temporal_tracker(self.session_id)
        status, missing, eval_persons = evaluate_compliance(
            assigned, detected_objects, required_ppe=["helmet", "vest"], img_shape=(480, 640),
            session_id=self.session_id, timestamp=0.0, temporal_tracker=tracker
        )

        # Uncertain zone anchor must not trigger a violation!
        self.assertFalse(eval_persons[0]["compliant"])
        self.assertTrue(eval_persons[0]["uncertain"])
        self.assertEqual(eval_persons[0]["missing_ppe"], [])
        self.assertEqual(eval_persons[0]["pending_missing_ppe"], [])
        self.assertEqual(status, "UNCERTAIN")

    def test_invalid_zone_policy_produces_uncertain_compliance(self):
        """Camera zone pointing to non-existent zone produces UNCERTAIN compliance."""
        bad_cam = {
            "_id": "cam_bad_policy",
            "name": "Bad Zone Cam",
            "zones": [
                {
                    "zoneId": "zone_missing_from_db_999",
                    "polygon": [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1}, {"x": 0.9, "y": 0.9}, {"x": 0.1, "y": 0.9}],
                    "priority": 1
                }
            ]
        }
        worker = [{"bbox": [200, 100, 400, 400], "confidence": 0.95, "track_id": 12, "worker_id": "W-012"}]
        assigned = assign_persons_spatial_zones(
            worker, bad_cam, img_shape=(480, 640), session_id=None, timestamp=0.0
        )
        self.assertEqual(assigned[0]["zone_assignment_status"], "ASSIGNED")
        self.assertEqual(assigned[0]["zone_id"], "zone_missing_from_db_999")

        # Authoritative lookup returns None -> invalid policy
        policy = get_authoritative_zone_ppe(assigned[0]["zone_id"])
        self.assertIsNone(policy)
        assigned[0]["zone_policy_valid"] = False
        assigned[0]["uncertain"] = True

        status, missing, eval_persons = evaluate_compliance(
            assigned, [], required_ppe=["helmet", "vest"], img_shape=(480, 640),
            session_id=self.session_id, timestamp=0.0
        )
        self.assertEqual(status, "UNCERTAIN")
        self.assertTrue(eval_persons[0]["uncertain"])
        self.assertEqual(eval_persons[0]["missing_ppe"], [])

    # =========================================================================
    # 4. Temporal Compliance State Isolation & Zone Transitions
    # =========================================================================

    def test_zone_transition_halts_pending_violation_without_transferring_time(self):
        """
        Worker in Zone A accumulates 1.5s missing helmet.
        Worker transitions to Zone B (where helmet is also required).
        In Zone B, accumulated missing time starts from 0.0s (no time transferred).
        Zone A pending state is paused.
        """
        tracker = get_session_temporal_tracker(self.session_id, confirmation_duration_sec=3.0)

        # Observation 1 in Zone A at t=0.0: missing helmet
        st_za_0 = tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=0.0, zone_id=self.zone_general_id
        )
        self.assertEqual(st_za_0.state, TemporalState.PENDING)

        # Observation 2 in Zone A at t=1.5: 1.5s accumulated missing
        st_za_15 = tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=1.5, zone_id=self.zone_general_id
        )
        self.assertEqual(st_za_15.state, TemporalState.PENDING)
        self.assertAlmostEqual(st_za_15.accumulated_missing_sec, 1.5, places=2)

        # Worker transitions to Zone B at t=2.0
        st_zb_20 = tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=2.0, zone_id=self.zone_welding_id
        )
        # Zone B state is fresh: starts at 0.0s!
        self.assertEqual(st_zb_20.state, TemporalState.PENDING)
        self.assertAlmostEqual(st_zb_20.accumulated_missing_sec, 0.0, places=2)
        self.assertEqual(st_zb_20.zone_id, self.zone_welding_id)

        # Zone A state was paused upon zone transition
        st_za = tracker.get_state(1, "helmet", zone_id=self.zone_general_id)
        self.assertEqual(st_za.state, TemporalState.PAUSED)
        self.assertAlmostEqual(st_za.accumulated_missing_sec, 1.5, places=2)

    def test_confirmed_incident_remains_open_when_worker_exits_zone(self):
        """
        Worker confirmed violation in Zone A at t=3.0.
        Worker exits to neutral aisle (UNASSIGNED) at t=4.0.
        Zone A confirmed violation remains CONFIRMED (open).
        """
        tracker = get_session_temporal_tracker(self.session_id, confirmation_duration_sec=3.0)

        # Confirmation in Zone A at t=3.0
        tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=0.0, zone_id=self.zone_general_id
        )
        st_conf = tracker.update_worker_ppe(
            track_id=1, ppe_category="helmet", is_worn=False, is_observable=True,
            is_required=True, is_uncertain=False, timestamp=3.0, zone_id=self.zone_general_id
        )
        self.assertEqual(st_conf.state, TemporalState.CONFIRMED)
        orig_ep = st_conf.episode_uuid
        self.assertIn(self.zone_general_id, orig_ep)

        # Worker moves to neutral aisle (unassigned): pause_track_pending called
        tracker.pause_track_pending(track_id=1, timestamp=4.0)

        # Zone A state must remain CONFIRMED!
        st_za = tracker.get_state(1, "helmet", zone_id=self.zone_general_id)
        self.assertEqual(st_za.state, TemporalState.CONFIRMED)
        self.assertEqual(st_za.active_confirmed_episode_uuid, orig_ep)

    # =========================================================================
    # 5. Auto-Resolution Requires Matching Zone ID (Rejects Cross-Zone Resolution)
    # =========================================================================

    def test_auto_resolution_rejected_when_candidate_zone_does_not_match_incident_zone(self):
        """
        Incident opened in Zone A (zoneId = 'zone_01').
        Worker verified compliant in Zone B (zoneId = 'zone_welding').
        Auto-resolution must be REJECTED due to zone mismatch!
        Incident in Zone A remains OPEN.
        """
        incident_ep = f"ep_{self.session_id}_1_{self.zone_general_id}_helmet_1"
        stored_incident = {
            "episode_id": incident_ep,
            "session_id": self.session_id,
            "track_id": 1,
            "worker_id": "W-001",
            "zoneId": self.zone_general_id,
            "zoneName": "Heavy Assembly Bay 01",
            "missingPPE": ["helmet"],
            "status": "OPEN",
            "reviewStatus": "PENDING",
            "createdAt": datetime.datetime.now(datetime.timezone.utc)
        }
        mem_detections.append(stored_incident)

        # Candidate generated from Zone B (Welding Bay)
        cross_zone_candidate = {
            "episode_id": incident_ep,
            "session_id": self.session_id,
            "track_id": 1,
            "worker_id": "W-001",
            "zone_id": self.zone_welding_id,  # Different zone!
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.5,
            "candidate_timestamp": 5.0,
            "resolution_event_id": f"res_{incident_ep}"
        }

        resolved_doc, is_new = resolve_confirmed_incident(cross_zone_candidate)
        # Resolution must be rejected!
        self.assertIsNone(resolved_doc)
        self.assertFalse(is_new)

        # Incident in Zone A must remain OPEN / PENDING!
        self.assertEqual(stored_incident["status"], "OPEN")
        self.assertEqual(stored_incident["reviewStatus"], "PENDING")

    def test_auto_resolution_succeeds_when_zone_matches(self):
        """
        Incident opened in Zone A (zoneId = 'zone_01').
        Worker verified compliant in Zone A (zoneId = 'zone_01').
        Auto-resolution SUCCEEDS and marks incident RESOLVED.
        """
        incident_ep = f"ep_{self.session_id}_1_{self.zone_general_id}_helmet_1"
        stored_incident = {
            "episode_id": incident_ep,
            "session_id": self.session_id,
            "track_id": 1,
            "worker_id": "W-001",
            "zoneId": self.zone_general_id,
            "zoneName": "Heavy Assembly Bay 01",
            "missingPPE": ["helmet"],
            "status": "OPEN",
            "reviewStatus": "PENDING",
            "createdAt": datetime.datetime.now(datetime.timezone.utc)
        }
        mem_detections.append(stored_incident)

        matching_candidate = {
            "episode_id": incident_ep,
            "session_id": self.session_id,
            "track_id": 1,
            "worker_id": "W-001",
            "zone_id": self.zone_general_id,  # Matching zone!
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.5,
            "candidate_timestamp": 5.0,
            "resolution_event_id": f"res_{incident_ep}"
        }

        resolved_doc, is_new = resolve_confirmed_incident(matching_candidate)
        self.assertIsNotNone(resolved_doc)
        self.assertTrue(is_new)
        self.assertEqual(resolved_doc["status"], "RESOLVED")
        self.assertEqual(resolved_doc["reviewStatus"], "RESOLVED")
        self.assertEqual(resolved_doc["resolution_type"], "AUTOMATIC_COMPLIANCE")

    # =========================================================================
    # 6. End-to-End Pipeline Integration via /api/detect HTTP Endpoint
    # =========================================================================

    @patch("routes.detection_routes.detect_ppe_in_frame")
    @patch("routes.detection_routes.upload_evidence_image")
    def test_api_detect_dual_zone_frame_e2e(self, mock_upload, mock_detect):
        """
        Tests end-to-end HTTP pipeline /api/detect with dual-zone camera.
        Worker A in General Zone (wearing helmet, vest, boots, NO goggles): COMPLIANT.
        Worker B in Welding Zone (wearing helmet, vest, boots, NO goggles): VIOLATION for goggles.
        """
        mock_upload.return_value = "https://res.cloudinary.com/test/ev1.jpg"

        # Worker 1: anchor inside General Zone polygon (left)
        # Worker 2: anchor inside Welding Zone polygon (right)
        w1 = {"bbox": [80, 100, 200, 400], "confidence": 0.95, "track_id": 1, "worker_id": "W-001"}
        w2 = {"bbox": [400, 100, 520, 400], "confidence": 0.95, "track_id": 2, "worker_id": "W-002"}

        # Both workers wear helmet, vest, boots. Neither wears goggles.
        detected_objects = [
            {"bbox": [90, 100, 190, 160], "name": "helmet", "class": "helmet", "source": "yolo", "is_synthetic": False, "confidence": 0.95},
            {"bbox": [85, 170, 195, 300], "name": "vest", "class": "vest", "source": "yolo", "is_synthetic": False, "confidence": 0.95},
            {"bbox": [90, 340, 190, 400], "name": "boots", "class": "boots", "source": "yolo", "is_synthetic": False, "confidence": 0.95},
            {"bbox": [410, 100, 510, 160], "name": "helmet", "class": "helmet", "source": "yolo", "is_synthetic": False, "confidence": 0.95},
            {"bbox": [405, 170, 515, 300], "name": "vest", "class": "vest", "source": "yolo", "is_synthetic": False, "confidence": 0.95},
            {"bbox": [410, 340, 510, 400], "name": "boots", "class": "boots", "source": "yolo", "is_synthetic": False, "confidence": 0.95}
        ]
        mock_detect.side_effect = lambda *args, **kwargs: (None, copy.deepcopy(detected_objects), copy.deepcopy([w1, w2]))

        # Frames 1-3: Establish debounced spatial zone assignments (3 observations required)
        for t in [0.0, 0.5, 1.0]:
            r = self.client.post("/api/detect", json={
                "image": self.synthetic_b64,
                "session_id": self.session_id,
                "camera_id": self.camera_id,
                "timestamp": t
            })
            self.assertEqual(r.status_code, 200)

        # Frame 4 at t=2.5: 1.5s missing in confirmed Welding Zone
        r4 = self.client.post("/api/detect", json={
            "image": self.synthetic_b64,
            "session_id": self.session_id,
            "camera_id": self.camera_id,
            "timestamp": 2.5
        })
        self.assertEqual(r4.status_code, 200)

        # Frame 5 at t=4.0: 3.0s missing in confirmed Welding Zone -> CONFIRMED incident created!
        res_conf = self.client.post("/api/detect", json={
            "image": self.synthetic_b64,
            "session_id": self.session_id,
            "camera_id": self.camera_id,
            "timestamp": 4.0
        })
        self.assertEqual(res_conf.status_code, 200)
        data3 = res_conf.get_json()

        # Frame overall status is VIOLATION due to Worker B
        self.assertEqual(data3["compliance_status"], "VIOLATION")
        self.assertEqual(data3["missing_ppe"], ["goggles"])

        # Inspect individual evaluated persons
        p_list = data3["persons"]
        self.assertEqual(len(p_list), 2)

        p_worker_a = next(p for p in p_list if p.get("track_id") == 1)
        p_worker_b = next(p for p in p_list if p.get("track_id") == 2)

        # Worker A in General Zone must be COMPLIANT!
        self.assertEqual(p_worker_a["zone_id"], self.zone_general_id)
        self.assertTrue(p_worker_a["compliant"])
        self.assertEqual(p_worker_a["missing_ppe"], [])

        # Worker B in Welding Zone must be in VIOLATION for goggles!
        self.assertEqual(p_worker_b["zone_id"], self.zone_welding_id)
        self.assertFalse(p_worker_b["compliant"])
        self.assertEqual(p_worker_b["missing_ppe"], ["goggles"])

        # Newly confirmed incident must belong to Worker B and Welding Zone!
        new_incidents = data3.get("new_confirmed_incidents", [])
        self.assertEqual(len(new_incidents), 1)
        inc = new_incidents[0]
        self.assertEqual(inc["track_id"], 2)
        self.assertEqual(inc["zoneId"], self.zone_welding_id)
        self.assertEqual(inc["missingPPE"], ["goggles"])
        self.assertEqual(inc["cameraId"], self.camera_id)

    # =========================================================================
    # 7. Milestone M2.2B.7D-F Safety Verification Tests
    # =========================================================================

    def test_unassigned_worker_does_not_accumulate_temporal_violation_or_resolution(self):
        """
        Unassigned worker tracked across multiple frames over 5 seconds without PPE
        must never accumulate missing time, never transition to CONFIRMED, and remain UNCERTAIN.
        """
        worker = [{"bbox": [310, 100, 330, 400], "confidence": 0.95, "track_id": 20, "worker_id": "W-020"}]
        tracker = get_session_temporal_tracker(self.session_id)

        # Feed 10 consecutive frames over 5.0 seconds
        for frame_idx in range(10):
            ts = frame_idx * 0.5
            assigned = assign_persons_spatial_zones(
                worker, self.camera_doc, img_shape=(480, 640), session_id=self.session_id, timestamp=ts
            )
            self.assertEqual(assigned[0]["zone_assignment_status"], "UNASSIGNED")

            status, missing, eval_persons = evaluate_compliance(
                assigned, [], required_ppe=["helmet", "vest"], img_shape=(480, 640),
                session_id=self.session_id, timestamp=ts, temporal_tracker=tracker
            )

            self.assertFalse(eval_persons[0]["compliant"])
            self.assertTrue(eval_persons[0]["uncertain"])
            self.assertEqual(eval_persons[0].get("uncertain_reason"), "NO_MONITORED_ZONE")
            self.assertEqual(eval_persons[0]["missing_ppe"], [])
            self.assertEqual(eval_persons[0]["pending_missing_ppe"], [])
            self.assertEqual(eval_persons[0]["new_confirmed_violations"], [])
            self.assertEqual(status, "UNCERTAIN")

        # Zero resolution candidates should exist
        self.assertEqual(tracker.get_resolution_candidates(), [])

    def test_lookup_camera_missing_camera_id_does_not_inherit_cam_01_polygons(self):
        """
        When camera_id is missing/None, lookup_camera() must return default camera
        with empty zones (zones: []) and MUST NOT silently inherit cam_01's polygons.
        """
        # Ensure cam_01 in mem_cameras has configured polygons
        cam_01 = next((c for c in mem_cameras if str(c.get("_id")) == "cam_01"), None)
        if cam_01:
            cam_01["zones"] = [
                {
                    "zoneId": "zone_01",
                    "polygon": [{"x": 0.1, "y": 0.1}, {"x": 0.4, "y": 0.1}, {"x": 0.4, "y": 0.9}, {"x": 0.1, "y": 0.9}],
                    "priority": 1
                }
            ]

        # Call with missing camera_id and missing zone_id
        cam = lookup_camera(camera_id=None, zone_id=None)
        self.assertIsNotNone(cam)
        self.assertEqual(cam.get("zones", []), [])

    def test_lookup_camera_unknown_camera_id_does_not_inherit_cam_01_polygons(self):
        """
        When camera_id is unknown/invalid, lookup_camera() must return an unconfigured camera
        with zones: [] and MUST NOT silently select cam_01 and inherit its polygons.
        """
        cam_01 = next((c for c in mem_cameras if str(c.get("_id")) == "cam_01"), None)
        if cam_01:
            cam_01["zones"] = [
                {
                    "zoneId": "zone_01",
                    "polygon": [{"x": 0.1, "y": 0.1}, {"x": 0.4, "y": 0.1}, {"x": 0.4, "y": 0.9}, {"x": 0.1, "y": 0.9}],
                    "priority": 1
                }
            ]

        cam = lookup_camera(camera_id="cam_ghost_nonexistent_999", zone_id=None)
        self.assertIsNotNone(cam)
        self.assertEqual(cam.get("_id"), "cam_ghost_nonexistent_999")
        self.assertEqual(cam.get("zones", []), [])
        self.assertTrue(cam.get("is_unknown", False))

    def test_lookup_camera_uploaded_video_returns_unzoned_configuration(self):
        """
        Uploaded video sessions must use the intended camera configuration without polygons.
        """
        cam = lookup_camera(camera_id="uploaded_video", zone_id=None)
        self.assertIsNotNone(cam)
        self.assertEqual(cam.get("_id"), "uploaded_video")
        self.assertEqual(cam.get("sourceType"), "video_file")
        self.assertEqual(cam.get("zones", []), [])

    def test_cross_zone_auto_resolution_prevented_with_stored_zone_incident(self):
        """
        A candidate's zone_id must strictly match the stored incident's zoneId.
        Evidence from Zone B or unzoned candidate cannot resolve a Zone A incident.
        """
        ep_id = f"ep_{self.session_id}_30_{self.zone_general_id}_helmet_1"
        incident = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "track_id": 30,
            "zoneId": self.zone_general_id,
            "zoneName": "Heavy Assembly Bay 01",
            "missingPPE": ["helmet"],
            "status": "OPEN",
            "reviewStatus": "PENDING"
        }
        mem_detections.append(incident)

        # Candidate from different zone (Welding Zone)
        cand_wrong_zone = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "track_id": 30,
            "zone_id": self.zone_welding_id,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0
        }
        doc, res = resolve_confirmed_incident(cand_wrong_zone)
        self.assertIsNone(doc)
        self.assertFalse(res)
        self.assertEqual(incident["status"], "OPEN")

        # Candidate with missing/None zone
        cand_none_zone = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "track_id": 30,
            "zone_id": None,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0
        }
        doc2, res2 = resolve_confirmed_incident(cand_none_zone)
        self.assertIsNone(doc2)
        self.assertFalse(res2)
        self.assertEqual(incident["status"], "OPEN")

        # Candidate with matching zone (General Zone)
        cand_matching_zone = {
            "episode_id": ep_id,
            "session_id": self.session_id,
            "track_id": 30,
            "zone_id": self.zone_general_id,
            "ppe_category": "helmet",
            "verified_compliance_duration_sec": 2.0
        }
        doc3, res3 = resolve_confirmed_incident(cand_matching_zone)
        self.assertIsNotNone(doc3)
        self.assertTrue(res3)
        self.assertEqual(doc3["status"], "RESOLVED")
        self.assertEqual(doc3["resolution_type"], "AUTOMATIC_COMPLIANCE")


if __name__ == "__main__":
    unittest.main()
