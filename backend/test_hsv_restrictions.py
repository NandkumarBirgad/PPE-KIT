import unittest
from ai_engine.compliance import (
    associate_ppe_with_persons,
    evaluate_compliance,
    detect_scanned_body_parts,
    compute_person_anatomical_regions,
    sort_canonical_ppe
)
from config import Config

class TestHSVRestrictionsAndComplianceSafety(unittest.TestCase):
    """
    Focused unit tests for Milestone M2.2B.3:
    HSV Heuristic Restrictions and Compliance Safety.
    Verifies that synthetic HSV evidence cannot independently establish compliance,
    cannot populate worn_ppe, cannot suppress missing PPE, and cannot interfere with
    genuine YOLO detections.
    """

    def setUp(self):
        # Standard fully visible worker at (100, 100, 300, 500), H=400, W=200
        # Head: [100, 100, 300, 200]
        # Torso: [100, 200, 300, 380]
        # Feet: [100, 400, 300, 500]
        self.worker1 = {
            "bbox": [100, 100, 300, 500],
            "confidence": 0.95,
            "worker_id": "W-001",
            "worn_ppe": [],
            "missing_ppe": [],
            "compliant": False
        }
        self.img_shape = (720, 1280, 3)

    # 1. A synthetic HSV helmet cannot populate worn_ppe
    def test_01_synthetic_hsv_helmet_cannot_populate_worn_ppe(self):
        person = dict(self.worker1)
        hsv_helmet = {
            "class": "helmet",
            "name": "helmet",
            "confidence": 0.88,
            "bbox": [120, 105, 280, 195],
            "source": "hsv",
            "is_synthetic": True
        }
        res = associate_ppe_with_persons([person], [hsv_helmet], img_shape=self.img_shape)
        self.assertEqual(res[0]["worn_ppe"], [], "Synthetic HSV helmet must NOT populate worn_ppe")
        self.assertEqual(len(res[0]["ppe_associations"]), 1)
        assoc = res[0]["ppe_associations"][0]
        self.assertFalse(assoc["is_valid_wear"])
        self.assertTrue(assoc["is_synthetic"])
        self.assertEqual(assoc["detection_source"], "hsv")

    # 2. A synthetic HSV vest cannot populate worn_ppe
    def test_02_synthetic_hsv_vest_cannot_populate_worn_ppe(self):
        person = dict(self.worker1)
        hsv_vest = {
            "class": "vest",
            "name": "vest",
            "confidence": 0.90,
            "bbox": [110, 210, 290, 370],
            "source": "hsv",
            "is_synthetic": True
        }
        res = associate_ppe_with_persons([person], [hsv_vest], img_shape=self.img_shape)
        self.assertEqual(res[0]["worn_ppe"], [], "Synthetic HSV vest must NOT populate worn_ppe")
        self.assertEqual(len(res[0]["ppe_associations"]), 1)
        assoc = res[0]["ppe_associations"][0]
        self.assertFalse(assoc["is_valid_wear"])
        self.assertTrue(assoc["is_synthetic"])
        self.assertEqual(assoc["detection_source"], "hsv")

    # 3. HSV evidence cannot suppress a missing-helmet result
    def test_03_hsv_evidence_cannot_suppress_missing_helmet(self):
        person = dict(self.worker1)
        hsv_helmet = {
            "class": "helmet",
            "name": "helmet",
            "confidence": 0.85,
            "bbox": [120, 105, 280, 195],
            "source": "hsv",
            "is_synthetic": True
        }
        status, missing, evaluated = evaluate_compliance(
            [person], [hsv_helmet], required_ppe=["helmet"], img_shape=self.img_shape
        )
        self.assertEqual(status, "VIOLATION")
        self.assertIn("helmet", missing, "Missing helmet must NOT be suppressed by HSV")
        self.assertFalse(evaluated[0]["compliant"])
        self.assertIn("helmet", evaluated[0]["missing_ppe"])

    # 4. HSV evidence cannot suppress a missing-vest result
    def test_04_hsv_evidence_cannot_suppress_missing_vest(self):
        person = dict(self.worker1)
        hsv_vest = {
            "class": "vest",
            "name": "vest",
            "confidence": 0.92,
            "bbox": [110, 210, 290, 370],
            "source": "hsv",
            "is_synthetic": True
        }
        status, missing, evaluated = evaluate_compliance(
            [person], [hsv_vest], required_ppe=["vest"], img_shape=self.img_shape
        )
        self.assertEqual(status, "VIOLATION")
        self.assertIn("vest", missing, "Missing vest must NOT be suppressed by HSV")
        self.assertFalse(evaluated[0]["compliant"])
        self.assertIn("vest", evaluated[0]["missing_ppe"])

    # 5. High HSV confidence does not make synthetic evidence authoritative
    def test_05_high_hsv_confidence_does_not_make_synthetic_authoritative(self):
        person = dict(self.worker1)
        ultra_conf_hsv = [
            {
                "class": "helmet", "name": "helmet", "confidence": 0.9999,
                "bbox": [120, 105, 280, 195], "source": "hsv", "is_synthetic": True
            },
            {
                "class": "vest", "name": "vest", "confidence": 1.0000,
                "bbox": [110, 210, 290, 370], "source": "hsv", "is_synthetic": True
            }
        ]
        status, missing, evaluated = evaluate_compliance(
            [person], ultra_conf_hsv, required_ppe=["helmet", "vest"], img_shape=self.img_shape
        )
        self.assertEqual(status, "VIOLATION")
        self.assertEqual(evaluated[0]["worn_ppe"], [])
        self.assertEqual(evaluated[0]["missing_ppe"], ["helmet", "vest"])
        self.assertFalse(evaluated[0]["compliant"])

    # 6. Genuine YOLO helmet evidence can still satisfy the helmet requirement
    def test_06_genuine_yolo_helmet_satisfies_requirement(self):
        person = dict(self.worker1)
        yolo_helmet = {
            "class": "helmet",
            "name": "helmet",
            "confidence": 0.88,
            "bbox": [120, 105, 280, 195],
            "source": "yolo",
            "is_synthetic": False
        }
        status, missing, evaluated = evaluate_compliance(
            [person], [yolo_helmet], required_ppe=["helmet"], img_shape=self.img_shape
        )
        self.assertEqual(status, "COMPLIANT")
        self.assertEqual(missing, [])
        self.assertTrue(evaluated[0]["compliant"])
        self.assertEqual(evaluated[0]["worn_ppe"], ["helmet"])
        self.assertEqual(evaluated[0]["missing_ppe"], [])

    # 7. Genuine YOLO vest evidence can still satisfy the vest requirement
    def test_07_genuine_yolo_vest_satisfies_requirement(self):
        person = dict(self.worker1)
        yolo_vest = {
            "class": "vest",
            "name": "vest",
            "confidence": 0.91,
            "bbox": [110, 210, 290, 370],
            "source": "yolo",
            "is_synthetic": False
        }
        status, missing, evaluated = evaluate_compliance(
            [person], [yolo_vest], required_ppe=["vest"], img_shape=self.img_shape
        )
        self.assertEqual(status, "COMPLIANT")
        self.assertEqual(missing, [])
        self.assertTrue(evaluated[0]["compliant"])
        self.assertEqual(evaluated[0]["worn_ppe"], ["vest"])
        self.assertEqual(evaluated[0]["missing_ppe"], [])

    # 8. A synthetic HSV detection cannot establish compliance for two overlapping workers
    def test_08_synthetic_hsv_cannot_establish_compliance_for_two_overlapping_workers(self):
        w1 = {"bbox": [100, 100, 250, 500], "confidence": 0.92, "worker_id": "W-001"}
        w2 = {"bbox": [140, 100, 290, 500], "confidence": 0.91, "worker_id": "W-002"}
        # A single synthetic HSV helmet overlapping both workers' heads
        single_hsv_helmet = {
            "class": "helmet", "name": "helmet", "confidence": 0.86,
            "bbox": [130, 105, 260, 190], "source": "hsv", "is_synthetic": True
        }
        status, missing, evaluated = evaluate_compliance(
            [w1, w2], [single_hsv_helmet], required_ppe=["helmet"], img_shape=self.img_shape
        )
        self.assertEqual(status, "VIOLATION")
        self.assertIn("helmet", missing)
        self.assertFalse(evaluated[0]["compliant"])
        self.assertFalse(evaluated[1]["compliant"])
        self.assertEqual(evaluated[0]["worn_ppe"], [])
        self.assertEqual(evaluated[1]["worn_ppe"], [])

    # 9. YOLO and HSV provenance remains distinguishable through the pipeline
    def test_09_yolo_and_hsv_provenance_distinguishable(self):
        person = dict(self.worker1)
        mixed_dets = [
            {
                "class": "helmet", "name": "helmet", "confidence": 0.93,
                "bbox": [120, 105, 280, 195], "source": "yolo", "is_synthetic": False
            },
            {
                "class": "vest", "name": "vest", "confidence": 0.82,
                "bbox": [110, 210, 290, 370], "source": "hsv", "is_synthetic": True
            }
        ]
        res = associate_ppe_with_persons([person], mixed_dets, img_shape=self.img_shape)
        assocs = res[0]["ppe_associations"]
        self.assertEqual(len(assocs), 2)

        h_ev = next(a for a in assocs if a["ppe_class"] == "helmet")
        v_ev = next(a for a in assocs if a["ppe_class"] == "vest")

        self.assertEqual(h_ev["detection_source"], "yolo")
        self.assertFalse(h_ev["is_synthetic"])
        self.assertTrue(h_ev["is_valid_wear"])

        self.assertEqual(v_ev["detection_source"], "hsv")
        self.assertTrue(v_ev["is_synthetic"])
        self.assertFalse(v_ev["is_valid_wear"])

    # 10. Existing body-region visibility behavior remains unchanged
    def test_10_body_region_visibility_remains_unchanged(self):
        # Worker with head clipped at top boundary (py1 = -15)
        clipped_worker_box = [100, -15, 250, 450]
        # Injected high-confidence HSV helmet right at the head location
        injected_hsv_helmet = {
            "class": "helmet", "name": "helmet", "confidence": 0.99,
            "bbox": [110, -10, 240, 80], "source": "hsv", "is_synthetic": True
        }
        scan = detect_scanned_body_parts(clipped_worker_box, img_shape=self.img_shape)
        # Head must remain unobservable regardless of any HSV detections
        self.assertFalse(scan["head"])
        self.assertNotIn("head", scan["scanned_regions"])
        self.assertEqual(scan["visibility_details"]["head"]["status"], "unobservable")

    # 11. Existing exclusive PPE association and ambiguity rejection remain unchanged
    def test_11_exclusive_association_and_ambiguity_rejection_unchanged(self):
        w0 = {"bbox": [100, 100, 200, 500], "worker_id": "W-001"}
        w1 = {"bbox": [155, 100, 255, 500], "worker_id": "W-002"}
        h0 = {"class": "helmet", "name": "helmet", "confidence": 0.90, "bbox": [120, 110, 220, 160], "source": "yolo", "is_synthetic": False}
        h1 = {"class": "helmet", "name": "helmet", "confidence": 0.90, "bbox": [65, 110, 165, 160], "source": "yolo", "is_synthetic": False}

        pipe_res = associate_ppe_with_persons([w0, w1], [h0, h1], img_shape=self.img_shape)
        self.assertEqual(pipe_res[0]["worn_ppe"], ["helmet"])
        self.assertEqual(pipe_res[1]["worn_ppe"], ["helmet"])
        self.assertEqual(len(pipe_res[0]["ppe_associations"]), 1)
        self.assertEqual(len(pipe_res[1]["ppe_associations"]), 1)

    # 12. Legacy API response fields and types remain compatible
    def test_12_legacy_api_response_fields_and_types_compatible(self):
        person = dict(self.worker1)
        dets = [
            {"class": "helmet", "name": "helmet", "confidence": 0.90, "bbox": [120, 105, 280, 195], "source": "yolo", "is_synthetic": False},
            {"class": "vest", "name": "vest", "confidence": 0.85, "bbox": [110, 210, 290, 370], "source": "hsv", "is_synthetic": True}
        ]
        status, missing, evaluated = evaluate_compliance(
            [person], dets, required_ppe=["helmet", "vest"], img_shape=self.img_shape
        )
        self.assertIsInstance(status, str)
        self.assertIsInstance(missing, list)
        self.assertTrue(all(isinstance(x, str) for x in missing))
        self.assertIsInstance(evaluated, list)

        p = evaluated[0]
        self.assertIsInstance(p["worn_ppe"], list)
        self.assertTrue(all(isinstance(x, str) for x in p["worn_ppe"]))
        self.assertIsInstance(p["missing_ppe"], list)
        self.assertTrue(all(isinstance(x, str) for x in p["missing_ppe"]))
        self.assertIsInstance(p["scanned_body_parts"], list)
        self.assertTrue(all(isinstance(x, str) for x in p["scanned_body_parts"]))
        self.assertIsInstance(p["compliant"], bool)
        self.assertIsInstance(p["uncertain"], bool)

    # 13. End-to-end compliance test mixing genuine YOLO and synthetic HSV detections
    def test_13_end_to_end_compliance_mixed_yolo_and_hsv(self):
        # Two workers:
        # Worker 1: Genuine Helmet + Synthetic Vest -> Missing Vest -> VIOLATION
        # Worker 2: Genuine Helmet + Genuine Vest -> Fully Compliant -> COMPLIANT
        w1 = {"bbox": [100, 100, 300, 500], "confidence": 0.94, "worker_id": "W-001"}
        w2 = {"bbox": [400, 100, 600, 500], "confidence": 0.96, "worker_id": "W-002"}

        detections = [
            # W1: Genuine YOLO Helmet
            {"class": "helmet", "name": "helmet", "confidence": 0.91, "bbox": [120, 105, 280, 195], "source": "yolo", "is_synthetic": False},
            # W1: Synthetic HSV Vest (invalid wear)
            {"class": "vest", "name": "vest", "confidence": 0.85, "bbox": [110, 210, 290, 370], "source": "hsv", "is_synthetic": True},
            # W2: Genuine YOLO Helmet
            {"class": "helmet", "name": "helmet", "confidence": 0.90, "bbox": [420, 105, 580, 195], "source": "yolo", "is_synthetic": False},
            # W2: Genuine YOLO Vest
            {"class": "vest", "name": "vest", "confidence": 0.93, "bbox": [410, 210, 590, 370], "source": "yolo", "is_synthetic": False}
        ]

        status, missing, evaluated = evaluate_compliance(
            [w1, w2], detections, required_ppe=["helmet", "vest"], img_shape=self.img_shape
        )
        self.assertEqual(status, "VIOLATION", "Overall status must be VIOLATION because W1 is missing vest")
        self.assertEqual(missing, ["vest"])

        p1 = next(p for p in evaluated if p["worker_id"] == "W-001")
        p2 = next(p for p in evaluated if p["worker_id"] == "W-002")

        self.assertFalse(p1["compliant"])
        self.assertEqual(p1["worn_ppe"], ["helmet"])
        self.assertEqual(p1["missing_ppe"], ["vest"])

        self.assertTrue(p2["compliant"])
        self.assertEqual(p2["worn_ppe"], ["helmet", "vest"])
        self.assertEqual(p2["missing_ppe"], [])

    # 14. Empty scene with no detections returns UNCERTAIN
    def test_14_empty_scene_no_detections_returns_uncertain(self):
        status, missing, evaluated = evaluate_compliance(
            [], [], required_ppe=["helmet", "vest"], img_shape=self.img_shape
        )
        self.assertEqual(status, "UNCERTAIN")
        self.assertEqual(missing, [])
        self.assertEqual(evaluated, [])

    # 15. Empty scene with synthetic HSV helmet/vest returns UNCERTAIN
    def test_15_empty_scene_with_hsv_detections_returns_uncertain(self):
        synthetic_scene_dets = [
            {"class": "helmet", "name": "helmet", "confidence": 0.95, "bbox": [100, 100, 200, 200], "source": "hsv", "is_synthetic": True},
            {"class": "vest", "name": "vest", "confidence": 0.95, "bbox": [100, 200, 200, 400], "source": "hsv", "is_synthetic": True}
        ]
        status, missing, evaluated = evaluate_compliance(
            [], synthetic_scene_dets, required_ppe=["helmet", "vest"], img_shape=self.img_shape
        )
        self.assertEqual(status, "UNCERTAIN", "Empty scene with HSV detections must return UNCERTAIN")
        self.assertEqual(missing, [])
        self.assertEqual(evaluated, [])

    # 16. Empty scene with genuine YOLO helmet/vest returns UNCERTAIN
    def test_16_empty_scene_with_genuine_yolo_detections_returns_uncertain(self):
        genuine_loose_dets = [
            {"class": "helmet", "name": "helmet", "confidence": 0.92, "bbox": [100, 100, 200, 200], "source": "yolo", "is_synthetic": False},
            {"class": "vest", "name": "vest", "confidence": 0.89, "bbox": [100, 200, 200, 400], "source": "yolo", "is_synthetic": False}
        ]
        status, missing, evaluated = evaluate_compliance(
            [], genuine_loose_dets, required_ppe=["helmet", "vest"], img_shape=self.img_shape
        )
        self.assertEqual(status, "UNCERTAIN", "Empty scene with loose YOLO gear must return UNCERTAIN, not COMPLIANT")
        self.assertEqual(missing, [])
        self.assertEqual(evaluated, [])

    # 17. Empty scene with mixed YOLO and HSV detections returns UNCERTAIN
    def test_17_empty_scene_with_mixed_detections_returns_uncertain(self):
        mixed_loose_dets = [
            {"class": "helmet", "name": "helmet", "confidence": 0.92, "bbox": [100, 100, 200, 200], "source": "yolo", "is_synthetic": False},
            {"class": "vest", "name": "vest", "confidence": 0.85, "bbox": [100, 200, 200, 400], "source": "hsv", "is_synthetic": True}
        ]
        status, missing, evaluated = evaluate_compliance(
            [], mixed_loose_dets, required_ppe=["helmet", "vest"], img_shape=self.img_shape
        )
        self.assertEqual(status, "UNCERTAIN", "Empty scene with mixed loose gear must return UNCERTAIN")
        self.assertEqual(missing, [])
        self.assertEqual(evaluated, [])

    # 18. All empty-scene cases return empty missing-PPE and evaluated-person lists
    def test_18_all_empty_scene_cases_return_empty_lists(self):
        cases = [
            [],
            [{"class": "helmet", "name": "helmet", "confidence": 0.9, "bbox": [10, 10, 50, 50], "source": "yolo", "is_synthetic": False}],
            [{"class": "vest", "name": "vest", "confidence": 0.9, "bbox": [10, 10, 50, 50], "source": "hsv", "is_synthetic": True}],
            [{"class": "boots", "name": "boots", "confidence": 0.8, "bbox": [10, 10, 50, 50], "source": "yolo", "is_synthetic": False}]
        ]
        for dets in cases:
            status, missing, evaluated = evaluate_compliance(
                [], dets, required_ppe=["helmet", "vest", "boots"], img_shape=self.img_shape
            )
            self.assertEqual(status, "UNCERTAIN")
            self.assertIsInstance(missing, list)
            self.assertEqual(missing, [])
            self.assertIsInstance(evaluated, list)
            self.assertEqual(evaluated, [])

    # 19. A worker with observable body regions and genuinely missing PPE receives VIOLATION
    def test_19_worker_with_observable_regions_and_missing_ppe_receives_violation(self):
        person = dict(self.worker1) # observable head and torso
        status, missing, evaluated = evaluate_compliance(
            [person], [], required_ppe=["helmet", "vest"], img_shape=self.img_shape
        )
        self.assertEqual(status, "VIOLATION")
        self.assertEqual(missing, ["helmet", "vest"])
        self.assertEqual(len(evaluated), 1)
        self.assertFalse(evaluated[0]["compliant"])
        self.assertEqual(evaluated[0]["missing_ppe"], ["helmet", "vest"])

    # 20. A worker with correctly associated genuine YOLO PPE receives COMPLIANT
    def test_20_worker_with_genuine_yolo_ppe_receives_compliant(self):
        person = dict(self.worker1)
        genuine_dets = [
            {"class": "helmet", "name": "helmet", "confidence": 0.91, "bbox": [120, 105, 280, 195], "source": "yolo", "is_synthetic": False},
            {"class": "vest", "name": "vest", "confidence": 0.93, "bbox": [110, 210, 290, 370], "source": "yolo", "is_synthetic": False}
        ]
        status, missing, evaluated = evaluate_compliance(
            [person], genuine_dets, required_ppe=["helmet", "vest"], img_shape=self.img_shape
        )
        self.assertEqual(status, "COMPLIANT")
        self.assertEqual(missing, [])
        self.assertEqual(len(evaluated), 1)
        self.assertTrue(evaluated[0]["compliant"])
        self.assertEqual(evaluated[0]["worn_ppe"], ["helmet", "vest"])
        self.assertEqual(evaluated[0]["missing_ppe"], [])

    # 21. HSV detection cannot interfere with or steal matching from genuine YOLO detection
    def test_21_hsv_does_not_interfere_with_genuine_yolo_matching(self):
        # Worker has both a genuine YOLO helmet and a synthetic HSV helmet
        person = dict(self.worker1)
        dets = [
            # Genuine YOLO helmet with containment = 0.82
            {"class": "helmet", "name": "helmet", "confidence": 0.88, "bbox": [130, 110, 270, 190], "source": "yolo", "is_synthetic": False},
            # Synthetic HSV helmet synthesized exactly over head (containment = 0.98)
            {"class": "helmet", "name": "helmet", "confidence": 0.96, "bbox": [105, 102, 295, 198], "source": "hsv", "is_synthetic": True}
        ]
        res = associate_ppe_with_persons([person], dets, img_shape=self.img_shape)
        # Worker MUST receive the genuine helmet in worn_ppe!
        self.assertEqual(res[0]["worn_ppe"], ["helmet"], "Genuine YOLO helmet must be assigned to worn_ppe")
        valid_assocs = [a for a in res[0]["ppe_associations"] if a["is_valid_wear"]]
        self.assertEqual(len(valid_assocs), 1)
        self.assertEqual(valid_assocs[0]["detection_source"], "yolo")
        self.assertFalse(valid_assocs[0]["is_synthetic"])

if __name__ == "__main__":
    unittest.main()
