import unittest
import time
from ai_engine.compliance import (
    evaluate_compliance,
    detect_scanned_body_parts,
    reset_session_temporal
)
from ai_engine.temporal_compliance import TemporalState, get_session_temporal_tracker
from config import Config

class TestM27ComplianceFalsePositiveProtection(unittest.TestCase):
    """
    Milestone M2.7 — Final Compliance False-Positive Protection Test Suite.
    Verifies that physically occluded or unobservable body parts never cause
    false PPE violations, while genuine missing-PPE violations confirm normally.
    """

    def setUp(self):
        self.session_id = f"test_m27_{int(time.time() * 1000)}"
        reset_session_temporal(self.session_id)
        self.img_shape = (720, 1280, 3)

    def tearDown(self):
        reset_session_temporal(self.session_id)

    # 1. Feet hidden behind an object do not produce a boots violation
    def test_01_feet_hidden_behind_object_does_not_produce_boots_violation(self):
        # Worker standing behind a workbench or timber: feet occluded
        person = {
            "bbox": [100, 100, 300, 500],
            "confidence": 0.95,
            "worker_id": "W-001",
            "track_id": 1,
            "worn_ppe": ["helmet", "vest"],
            "feet_occluded": True
        }
        # Required PPE: helmet, vest, boots
        # Run across multiple frames beyond the 3.0-second confirmation threshold
        for ts in [0.0, 1.0, 2.0, 3.2, 5.0]:
            status, missing, evaluated = evaluate_compliance(
                [person], [], required_ppe=["helmet", "vest", "boots"],
                session_id=self.session_id, timestamp=ts, img_shape=self.img_shape
            )
            p = evaluated[0]
            # Boots must NOT be in missing_ppe or cause a violation
            self.assertNotIn("boots", p["missing_ppe"])
            self.assertNotIn("boots", missing)
            self.assertIn("boots", p["ignored_unscanned_ppe"])
            self.assertNotEqual(status, "VIOLATION", f"Occluded feet must NOT trigger VIOLATION at t={ts}")
            # Worker is UNCERTAIN because boots compliance cannot be established
            self.assertTrue(p["uncertain"])
            self.assertFalse(p["compliant"])
            self.assertEqual(status, "UNCERTAIN")

    # 1b. Feet hidden via half-body framing (aspect ratio < 1.85) do not produce boots violation
    def test_01b_half_body_framing_does_not_produce_boots_violation(self):
        # Waist-up worker detection behind table: width=200, height=300 -> aspect ratio=1.5
        person = {
            "bbox": [200, 150, 400, 450],
            "confidence": 0.95,
            "worker_id": "W-002",
            "track_id": 2,
            "worn_ppe": ["helmet", "vest"]
        }
        status, missing, evaluated = evaluate_compliance(
            [person], [], required_ppe=["helmet", "vest", "boots"],
            session_id=self.session_id, timestamp=0.0, img_shape=self.img_shape
        )
        p = evaluated[0]
        self.assertNotIn("feet", p["scanned_body_parts"])
        self.assertIn("boots", p["ignored_unscanned_ppe"])

        # Advance to t=4.0s (past 3s threshold)
        status, missing, evaluated = evaluate_compliance(
            [person], [], required_ppe=["helmet", "vest", "boots"],
            session_id=self.session_id, timestamp=4.0, img_shape=self.img_shape
        )
        self.assertNotIn("boots", evaluated[0]["missing_ppe"])
        self.assertNotEqual(status, "VIOLATION")

    # 2. Visible feet without detected boots can still produce a confirmed violation after 3 seconds
    def test_02_visible_feet_without_boots_confirms_violation_after_3_seconds(self):
        person = {
            "bbox": [100, 100, 300, 500],
            "confidence": 0.95,
            "worker_id": "W-003",
            "track_id": 3,
            "worn_ppe": ["helmet", "vest"]
        }
        # t=0.0: Initial detection, pending confirmation
        status, missing, evaluated = evaluate_compliance(
            [person], [], required_ppe=["helmet", "vest", "boots"],
            session_id=self.session_id, timestamp=0.0, img_shape=self.img_shape
        )
        self.assertIn("feet", evaluated[0]["scanned_body_parts"])
        self.assertEqual(evaluated[0]["missing_ppe"], [])
        self.assertIn("boots", evaluated[0]["pending_missing_ppe"])

        # t=1.5: Still within 3-second grace window -> no confirmed violation
        status, missing, evaluated = evaluate_compliance(
            [person], [], required_ppe=["helmet", "vest", "boots"],
            session_id=self.session_id, timestamp=1.5, img_shape=self.img_shape
        )
        self.assertEqual(evaluated[0]["missing_ppe"], [])
        self.assertIn("boots", evaluated[0]["pending_missing_ppe"])

        # t=3.2: Exceeded 3.0 seconds continuous observable missing boots -> Confirmed VIOLATION!
        status, missing, evaluated = evaluate_compliance(
            [person], [], required_ppe=["helmet", "vest", "boots"],
            session_id=self.session_id, timestamp=3.2, img_shape=self.img_shape
        )
        self.assertEqual(status, "VIOLATION")
        self.assertIn("boots", evaluated[0]["missing_ppe"])
        self.assertIn("boots", missing)
        self.assertIn("boots", evaluated[0]["new_confirmed_violations"])

    # 3. Torso occlusion does not produce a false vest violation
    def test_03_torso_occlusion_does_not_produce_false_vest_violation(self):
        # Worker carrying heavy lumber planks across chest: torso occluded
        person = {
            "bbox": [100, 100, 300, 500],
            "confidence": 0.95,
            "worker_id": "W-004",
            "track_id": 4,
            "worn_ppe": ["helmet"],
            "torso_occluded": True
        }
        # Run across multiple frames up to 6.0 seconds
        for ts in [0.0, 1.5, 3.2, 6.0]:
            status, missing, evaluated = evaluate_compliance(
                [person], [], required_ppe=["helmet", "vest"],
                session_id=self.session_id, timestamp=ts, img_shape=self.img_shape
            )
            p = evaluated[0]
            self.assertNotIn("torso", p["scanned_body_parts"])
            self.assertIn("vest", p["ignored_unscanned_ppe"])
            self.assertNotIn("vest", p["missing_ppe"])
            self.assertNotEqual(status, "VIOLATION", f"Occluded torso must NOT trigger VIOLATION at t={ts}")
            self.assertTrue(p["uncertain"])
            self.assertEqual(p["uncertain_reason"], "UNOBSERVABLE_TORSO")

    # 4. Clearly visible torso without detected vest can still produce a confirmed violation
    def test_04_clearly_visible_torso_without_vest_confirms_violation(self):
        person = {
            "bbox": [100, 100, 300, 500],
            "confidence": 0.95,
            "worker_id": "W-005",
            "track_id": 5,
            "worn_ppe": ["helmet"]
        }
        # t=0.0: pending
        status, missing, evaluated = evaluate_compliance(
            [person], [], required_ppe=["helmet", "vest"],
            session_id=self.session_id, timestamp=0.0, img_shape=self.img_shape
        )
        self.assertIn("torso", evaluated[0]["scanned_body_parts"])
        self.assertEqual(evaluated[0]["missing_ppe"], [])
        self.assertIn("vest", evaluated[0]["pending_missing_ppe"])

        # t=3.0: 3.0s elapsed -> confirmed violation!
        status, missing, evaluated = evaluate_compliance(
            [person], [], required_ppe=["helmet", "vest"],
            session_id=self.session_id, timestamp=3.0, img_shape=self.img_shape
        )
        self.assertEqual(status, "VIOLATION")
        self.assertIn("vest", evaluated[0]["missing_ppe"])
        self.assertIn("vest", missing)

    # 5. Unobservable head does not produce a helmet violation
    def test_05_unobservable_head_does_not_produce_helmet_violation(self):
        # Worker with head clipped at top frame boundary (py1 = -20)
        person = {
            "bbox": [100, -20, 300, 450],
            "confidence": 0.95,
            "worker_id": "W-006",
            "track_id": 6,
            "worn_ppe": ["vest"]
        }
        for ts in [0.0, 1.5, 3.5]:
            status, missing, evaluated = evaluate_compliance(
                [person], [], required_ppe=["helmet", "vest"],
                session_id=self.session_id, timestamp=ts, img_shape=self.img_shape
            )
            p = evaluated[0]
            self.assertNotIn("head", p["scanned_body_parts"])
            self.assertIn("helmet", p["ignored_unscanned_ppe"])
            self.assertNotIn("helmet", p["missing_ppe"])
            self.assertNotEqual(status, "VIOLATION")
            self.assertTrue(p["uncertain"])
            self.assertEqual(p["uncertain_reason"], "UNOBSERVABLE_HEAD")

    # 6. Existing genuine violations still confirm and are preserved across occlusion
    def test_06_existing_confirmed_violations_preserved_across_temporary_occlusion(self):
        person = {
            "bbox": [100, 100, 300, 500],
            "confidence": 0.95,
            "worker_id": "W-007",
            "track_id": 7,
            "worn_ppe": []
        }
        # Confirm helmet and vest violation over 3.0s
        evaluate_compliance([person], [], ["helmet", "vest"], session_id=self.session_id, timestamp=0.0, img_shape=self.img_shape)
        status, missing, evaluated = evaluate_compliance([person], [], ["helmet", "vest"], session_id=self.session_id, timestamp=3.0, img_shape=self.img_shape)
        self.assertEqual(status, "VIOLATION")
        self.assertEqual(set(missing), {"helmet", "vest"})

        # Worker now carries timber temporarily occluding torso at t=4.0s
        person_occluded = dict(person)
        person_occluded["torso_occluded"] = True
        status, missing, evaluated = evaluate_compliance([person_occluded], [], ["helmet", "vest"], session_id=self.session_id, timestamp=4.0, img_shape=self.img_shape)
        # Rule: Existing confirmed violations are not automatically erased by temporary occlusion!
        self.assertEqual(status, "VIOLATION")
        self.assertIn("vest", evaluated[0]["missing_ppe"])
        self.assertIn("helmet", evaluated[0]["missing_ppe"])

    # 7. Webcam endpoint / detect flow consistency
    def test_07_webcam_and_video_pipeline_consistency(self):
        # Verify that static single-frame evaluation without a session tracker behaves consistently
        person_observable = {
            "bbox": [100, 100, 300, 500],
            "confidence": 0.95,
            "worker_id": "W-008",
            "worn_ppe": ["helmet", "vest"]
        }
        status, missing, evaluated = evaluate_compliance(
            [person_observable], [], required_ppe=["helmet", "vest"], img_shape=self.img_shape
        )
        self.assertEqual(status, "COMPLIANT")
        self.assertEqual(missing, [])

        # Occluded feet in single-frame inspection does NOT produce boots violation
        person_occluded_feet = dict(person_observable)
        person_occluded_feet["feet_occluded"] = True
        status, missing, evaluated = evaluate_compliance(
            [person_occluded_feet], [], required_ppe=["helmet", "vest", "boots"], img_shape=self.img_shape
        )
        self.assertNotIn("boots", evaluated[0]["missing_ppe"])
        self.assertNotEqual(status, "VIOLATION")

if __name__ == "__main__":
    unittest.main()
