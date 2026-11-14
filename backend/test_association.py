import unittest
import numpy as np
from ai_engine.compliance import (
    compute_box_intersection_ratio,
    compute_person_anatomical_regions,
    normalize_ppe_class,
    sort_canonical_ppe,
    max_weight_bipartite_matching,
    associate_ppe_with_persons,
    evaluate_compliance,
    CANONICAL_PPE_REGION_MAP,
    CANONICAL_PPE_ORDER
)
from config import Config

class TestPPEAssociationEngine(unittest.TestCase):

    def setUp(self):
        # Baseline worker at (100, 100, 200, 400), pw=100, ph=300
        # Head: (100, 100, 200, 175)
        # Face: (120, 130, 180, 190)
        # Torso: (100, 175, 200, 310)
        # Feet: (100, 325, 200, 400)
        self.worker1 = {
            "bbox": [100, 100, 200, 400],
            "confidence": 0.92,
            "worker_id": "W-001",
            "track_id": 1
        }
        self.worker2 = {
            "bbox": [300, 100, 400, 400],
            "confidence": 0.90,
            "worker_id": "W-002",
            "track_id": 2
        }

    # 1. One worker and one correctly positioned helmet
    def test_01_single_worker_correct_helmet(self):
        persons = [dict(self.worker1)]
        detections = [{
            "class": "helmet",
            "name": "helmet",
            "confidence": 0.89,
            "bbox": [110, 105, 190, 165], # 100% inside head region
            "source": "yolo",
            "is_synthetic": False
        }]
        res = associate_ppe_with_persons(persons, detections)
        self.assertEqual(res[0]["worn_ppe"], ["helmet"])
        self.assertEqual(len(res[0]["ppe_associations"]), 1)
        assoc = res[0]["ppe_associations"][0]
        self.assertEqual(assoc["ppe_class"], "helmet")
        self.assertEqual(assoc["matched_region"], "head")
        self.assertTrue(assoc["is_valid_wear"])
        self.assertEqual(assoc["assigned_worker_id"], "W-001")
        self.assertGreater(assoc["association_score"], 0.80)

    # 2. One worker and a helmet positioned at the feet
    def test_02_helmet_at_feet_rejected(self):
        persons = [dict(self.worker1)]
        detections = [{
            "class": "helmet",
            "name": "helmet",
            "confidence": 0.85,
            "bbox": [110, 330, 190, 395], # Located at feet, not head!
            "source": "yolo",
            "is_synthetic": False
        }]
        res = associate_ppe_with_persons(persons, detections)
        self.assertEqual(res[0]["worn_ppe"], [])
        self.assertEqual(len(res[0]["ppe_associations"]), 0)

    # 3. One worker and boots positioned at the head
    def test_03_boots_at_head_rejected(self):
        persons = [dict(self.worker1)]
        detections = [{
            "class": "boots",
            "name": "boots",
            "confidence": 0.88,
            "bbox": [110, 105, 190, 165], # Located at head, not feet!
            "source": "yolo",
            "is_synthetic": False
        }]
        res = associate_ppe_with_persons(persons, detections)
        self.assertEqual(res[0]["worn_ppe"], [])
        self.assertEqual(len(res[0]["ppe_associations"]), 0)

    # 4. Two separated workers with separate helmets
    def test_04_two_separated_workers_two_helmets(self):
        persons = [dict(self.worker1), dict(self.worker2)]
        detections = [
            {
                "class": "helmet",
                "name": "helmet",
                "confidence": 0.91,
                "bbox": [110, 105, 190, 165],
                "source": "yolo",
                "is_synthetic": False
            },
            {
                "class": "helmet",
                "name": "helmet",
                "confidence": 0.87,
                "bbox": [310, 105, 390, 165],
                "source": "yolo",
                "is_synthetic": False
            }
        ]
        res = associate_ppe_with_persons(persons, detections)
        self.assertEqual(res[0]["worn_ppe"], ["helmet"])
        self.assertEqual(res[1]["worn_ppe"], ["helmet"])
        self.assertEqual(res[0]["ppe_associations"][0]["assigned_worker_id"], "W-001")
        self.assertEqual(res[1]["ppe_associations"][0]["assigned_worker_id"], "W-002")

    # 5. Two overlapping workers with one helmet (Exclusivity)
    def test_05_two_overlapping_workers_one_helmet_exclusive(self):
        w1 = {"bbox": [100, 100, 200, 400], "worker_id": "W-001"}
        w2 = {"bbox": [150, 100, 250, 400], "worker_id": "W-002"}
        # Helmet centered over W1's head: (105, 105, 175, 165)
        # In W1 head: [100, 100, 200, 175] -> 100% inside
        # In W2 head: [150, 100, 250, 175] -> overlap is only [150..175], ratio ~25/70 = 0.35, below dominant score
        detections = [{
            "class": "helmet",
            "name": "helmet",
            "confidence": 0.90,
            "bbox": [105, 105, 165, 165],
            "source": "yolo",
            "is_synthetic": False
        }]
        res = associate_ppe_with_persons([w1, w2], detections)
        # Exactly one worker gets the helmet!
        worn_count = sum(1 for p in res if "helmet" in p["worn_ppe"])
        self.assertEqual(worn_count, 1)
        self.assertIn("helmet", res[0]["worn_ppe"])
        self.assertNotIn("helmet", res[1]["worn_ppe"])

    # 6. Two overlapping workers with two helmets
    def test_06_two_overlapping_workers_two_helmets(self):
        w1 = {"bbox": [100, 100, 200, 400], "worker_id": "W-001"}
        w2 = {"bbox": [160, 100, 260, 400], "worker_id": "W-002"}
        h1 = {
            "class": "helmet", "name": "helmet", "confidence": 0.92,
            "bbox": [110, 105, 150, 160], "source": "yolo", "is_synthetic": False
        }
        h2 = {
            "class": "helmet", "name": "helmet", "confidence": 0.88,
            "bbox": [190, 105, 230, 160], "source": "yolo", "is_synthetic": False
        }
        res = associate_ppe_with_persons([w1, w2], [h1, h2])
        self.assertEqual(res[0]["worn_ppe"], ["helmet"])
        self.assertEqual(res[1]["worn_ppe"], ["helmet"])
        self.assertEqual(res[0]["ppe_associations"][0]["assigned_worker_id"], "W-001")
        self.assertEqual(res[1]["ppe_associations"][0]["assigned_worker_id"], "W-002")

    # 7. One detection with two competing workers (Decisive winner with both above min_score)
    def test_07_competing_workers_decisive_winner(self):
        # W1 head: [100, 100, 200, 175] (pw=100)
        # W2 head: [140, 100, 240, 175] (pw=100)
        # Helmet at [110, 105, 170, 165]: pw=60.
        # W1 overlap: [110..170] = 60/60 = 1.00 (>= 0.35)
        # W2 overlap: [140..170] = 30/60 = 0.50 (>= 0.35)
        # Delta: 1.00 - 0.50 = 0.50 >= ambiguity_margin (0.08)
        w1 = {"bbox": [100, 100, 200, 400], "worker_id": "W-001"}
        w2 = {"bbox": [140, 100, 240, 400], "worker_id": "W-002"}
        det = {
            "class": "helmet", "name": "helmet", "confidence": 0.95,
            "bbox": [110, 105, 170, 165], "source": "yolo", "is_synthetic": False
        }
        res = associate_ppe_with_persons([w1, w2], [det])
        self.assertEqual(res[0]["worn_ppe"], ["helmet"])
        self.assertEqual(res[1]["worn_ppe"], [])

    # 8. Ambiguous matching rejection
    def test_08_ambiguous_matching_rejection(self):
        # Two workers side by side overlapping:
        # W1: [100, 100, 200, 400], head=[100, 100, 200, 175]
        # W2: [120, 100, 220, 400], head=[120, 100, 220, 175]
        # Helmet centered exactly on the boundary: [140, 105, 180, 165], width=40.
        # Both W1 and W2 head completely contain this 40px box! Score on W1 = 1.0, Score on W2 = 1.0.
        # Diff = |1.0 - 1.0| = 0.0 < ambiguity_margin (0.08).
        w1 = {"bbox": [100, 100, 200, 400], "worker_id": "W-001"}
        w2 = {"bbox": [120, 100, 220, 400], "worker_id": "W-002"}
        det = {
            "class": "helmet", "name": "helmet", "confidence": 0.90,
            "bbox": [140, 105, 180, 165], "source": "yolo", "is_synthetic": False
        }
        res = associate_ppe_with_persons([w1, w2], [det])
        # Ambiguous association MUST be rejected: neither worker claims it with certainty!
        self.assertEqual(res[0]["worn_ppe"], [])
        self.assertEqual(res[1]["worn_ppe"], [])

    # 9. Greedy counterexample solved by global assignment
    def test_09_greedy_counterexample_solved_by_global(self):
        # Matrix:
        #        D0    D1
        #   W0  0.80  0.65
        #   W1  0.65  0.10
        # Min threshold = 0.35
        S = [[0.80, 0.65], [0.65, 0.10]]
        # 1. Verify greedy behavior
        # Greedy sorts candidates: (0,0)=0.80, (0,1)=0.65, (1,0)=0.65, (1,1)=0.10
        # Picks (0,0)=0.80 -> W0 and D0 matched.
        # Next candidate with available (W, D) is (1,1)=0.10 -> rejected (< 0.35).
        # Greedy matched count = 1, sum = 0.80.
        greedy_matches = [(0, 0)]

        # 2. Verify global Hungarian behavior
        global_matches = max_weight_bipartite_matching(S)
        # Optimal matching: (1, 0) and (0, 1) -> sum = 0.65 + 0.65 = 1.30
        self.assertEqual(len(global_matches), 2)
        match_dict = dict(global_matches)
        self.assertEqual(match_dict[1], 0) # W1 -> D0
        self.assertEqual(match_dict[0], 1) # W0 -> D1
        total_weight = S[0][match_dict[0]] + S[1][match_dict[1]]
        self.assertAlmostEqual(total_weight, 1.30, places=2)
        self.assertGreater(total_weight, 0.80)

        # 3. Verify complete associate_ppe_with_persons pipeline on geometric counterexample
        # W0 head: [100, 100, 200, 200]
        # W1 head: [155, 100, 255, 200]
        # H0: [120, 110, 220, 160] (overlap W0: 80%, overlap W1: 65%)
        # H1: [65, 110, 165, 160]  (overlap W0: 65%, overlap W1: 10% < 0.35)
        w0 = {"bbox": [100, 100, 200, 500], "worker_id": "W-001"}
        w1 = {"bbox": [155, 100, 255, 500], "worker_id": "W-002"}
        h0 = {"class": "helmet", "name": "helmet", "confidence": 0.90, "bbox": [120, 110, 220, 160], "source": "yolo", "is_synthetic": False}
        h1 = {"class": "helmet", "name": "helmet", "confidence": 0.90, "bbox": [65, 110, 165, 160], "source": "yolo", "is_synthetic": False}

        pipe_res = associate_ppe_with_persons([w0, w1], [h0, h1])
        # Both workers receive their exclusive helmet!
        self.assertEqual(pipe_res[0]["worn_ppe"], ["helmet"])
        self.assertEqual(pipe_res[1]["worn_ppe"], ["helmet"])
        self.assertEqual(len(pipe_res[0]["ppe_associations"]), 1)
        self.assertEqual(len(pipe_res[1]["ppe_associations"]), 1)

    # 10. Multiple PPE classes assigned independently
    def test_10_multiple_ppe_classes_independent_assignment(self):
        persons = [dict(self.worker1)]
        detections = [
            {
                "class": "helmet", "name": "helmet", "confidence": 0.91,
                "bbox": [110, 105, 190, 165], "source": "yolo", "is_synthetic": False
            },
            {
                "class": "vest", "name": "vest", "confidence": 0.88,
                "bbox": [105, 185, 195, 305], "source": "yolo", "is_synthetic": False
            }
        ]
        res = associate_ppe_with_persons(persons, detections)
        self.assertEqual(res[0]["worn_ppe"], ["helmet", "vest"])
        self.assertEqual(len(res[0]["ppe_associations"]), 2)
        classes = [a["ppe_class"] for a in res[0]["ppe_associations"]]
        self.assertIn("helmet", classes)
        self.assertIn("vest", classes)

    # 11. Invalid and zero-area bounding boxes
    def test_11_invalid_and_zero_area_boxes(self):
        # Box with zero width/height
        zero_box = [100, 100, 100, 100]
        regions_zero = compute_person_anatomical_regions(zero_box)
        self.assertEqual(regions_zero, {})

        # Inverted box
        inv_box = [200, 200, 100, 100]
        regions_inv = compute_person_anatomical_regions(inv_box)
        self.assertEqual(regions_inv, {})

        # None / empty box
        self.assertEqual(compute_person_anatomical_regions(None), {})
        self.assertEqual(compute_person_anatomical_regions([]), {})

    # 12. Coordinate clipping at image boundaries
    def test_12_coordinate_clipping_at_image_boundaries(self):
        # Person box starting with negative coords and extending past image dims
        person_box = [-20, -10, 150, 500]
        img_shape = (480, 640)
        regions = compute_person_anatomical_regions(person_box, img_shape=img_shape)
        for r_name, r_box in regions.items():
            self.assertGreaterEqual(r_box[0], 0, f"{r_name} x1 negative")
            self.assertGreaterEqual(r_box[1], 0, f"{r_name} y1 negative")
            self.assertLessEqual(r_box[2], 640, f"{r_name} x2 exceeds width")
            self.assertLessEqual(r_box[3], 480, f"{r_name} y2 exceeds height")

    # 13. Genuine YOLO versus synthetic HSV provenance
    def test_13_genuine_yolo_vs_synthetic_hsv_provenance(self):
        persons = [dict(self.worker1)]
        detections = [
            {
                "class": "helmet", "name": "helmet", "confidence": 0.90,
                "bbox": [110, 105, 190, 165], "source": "yolo", "is_synthetic": False
            },
            {
                "class": "vest", "name": "vest", "confidence": 0.85,
                "bbox": [105, 185, 195, 305], "source": "hsv", "is_synthetic": True
            }
        ]
        res = associate_ppe_with_persons(persons, detections)
        # Genuine YOLO helmet is added to worn_ppe
        self.assertIn("helmet", res[0]["worn_ppe"])
        # Synthetic HSV vest is NOT added to worn_ppe in this milestone
        self.assertNotIn("vest", res[0]["worn_ppe"])

        # Evidence records both with clear provenance
        self.assertEqual(len(res[0]["ppe_associations"]), 2)
        h_assoc = next(a for a in res[0]["ppe_associations"] if a["ppe_class"] == "helmet")
        v_assoc = next(a for a in res[0]["ppe_associations"] if a["ppe_class"] == "vest")

        self.assertEqual(h_assoc["detection_source"], "yolo")
        self.assertFalse(h_assoc["is_synthetic"])
        self.assertTrue(h_assoc["is_valid_wear"])

        self.assertEqual(v_assoc["detection_source"], "hsv")
        self.assertTrue(v_assoc["is_synthetic"])
        self.assertFalse(v_assoc["is_valid_wear"])

    # 14. Legacy worn_ppe and missing_ppe types remain lists of strings
    def test_14_legacy_types_remain_list_of_strings(self):
        persons = [dict(self.worker1)]
        detections = [{
            "class": "helmet", "name": "helmet", "confidence": 0.90,
            "bbox": [110, 105, 190, 165], "source": "yolo", "is_synthetic": False
        }]
        status, missing, evaluated = evaluate_compliance(persons, detections, required_ppe=["helmet", "vest"])
        p = evaluated[0]

        # Check types
        self.assertIsInstance(p["worn_ppe"], list)
        self.assertTrue(all(isinstance(x, str) for x in p["worn_ppe"]))

        self.assertIsInstance(p["missing_ppe"], list)
        self.assertTrue(all(isinstance(x, str) for x in p["missing_ppe"]))

        self.assertIsInstance(p["scanned_body_parts"], list)
        self.assertTrue(all(isinstance(x, str) for x in p["scanned_body_parts"]))

        self.assertIsInstance(p["compliant"], bool)
        self.assertIsInstance(p["uncertain"], bool)

        # Check deterministic sorting
        self.assertEqual(p["worn_ppe"], ["helmet"])
        self.assertEqual(p["missing_ppe"], ["vest"])

    # 15. Structured evidence contains all required fields
    def test_15_structured_evidence_fields(self):
        persons = [dict(self.worker1)]
        detections = [{
            "class": "helmet", "name": "helmet", "confidence": 0.88,
            "bbox": [110, 105, 190, 165], "source": "yolo", "is_synthetic": False
        }]
        res = associate_ppe_with_persons(persons, detections)
        assoc = res[0]["ppe_associations"][0]

        required_keys = [
            "ppe_class", "name", "confidence", "bbox",
            "detection_source", "is_synthetic", "assigned_worker_id",
            "matched_region", "region_bbox", "association_score", "is_valid_wear"
        ]
        for key in required_keys:
            self.assertIn(key, assoc, f"Missing required evidence key: {key}")

        self.assertIsInstance(assoc["ppe_class"], str)
        self.assertIsInstance(assoc["confidence"], float)
        self.assertIsInstance(assoc["bbox"], list)
        self.assertIsInstance(assoc["detection_source"], str)
        self.assertIsInstance(assoc["is_synthetic"], bool)
        self.assertIsInstance(assoc["is_valid_wear"], bool)

    # 16. Existing tracker tests remain unaffected (Smoke check)
    def test_16_tracker_integration_smoke(self):
        from ai_engine.tracker import LightweightIoUTracker
        tracker = LightweightIoUTracker()
        det = [{"bbox": [100, 100, 200, 300], "confidence": 0.9}]
        res = tracker.update(det, timestamp=1.0)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["worker_id"], "W-001")

    # 17. Symmetric matching ambiguity rejection
    def test_17_symmetric_matching_ambiguity_rejection(self):
        # Two workers with completely identical head positions and two identical helmet detections
        # Score matrix: [[0.90, 0.90], [0.90, 0.90]]
        # Multiple equally good global assignments exist; ambiguity evaluation must reject both
        w1 = {"bbox": [100, 100, 200, 400], "worker_id": "W-001"}
        w2 = {"bbox": [100, 100, 200, 400], "worker_id": "W-002"}
        h1 = {"class": "helmet", "name": "helmet", "confidence": 0.90, "bbox": [110, 105, 190, 165], "source": "yolo", "is_synthetic": False}
        h2 = {"class": "helmet", "name": "helmet", "confidence": 0.90, "bbox": [110, 105, 190, 165], "source": "yolo", "is_synthetic": False}
        res = associate_ppe_with_persons([w1, w2], [h1, h2])
        # Both rejected due to delta = 0.0 < 0.08
        self.assertEqual(res[0]["worn_ppe"], [])
        self.assertEqual(res[1]["worn_ppe"], [])

    # 18. Forbidden edge alternative evaluation
    def test_18_forbidden_edge_alternative_evaluation(self):
        # One detection with two workers: W1 score=1.00, W2 score=0.95
        # Total_0 = 1.00. Alternative when (W1, D) forbidden: W2 gets D with 0.95.
        # Delta = 1.00 - 0.95 = 0.05 < 0.08 -> ambiguous!
        w1 = {"bbox": [100, 100, 200, 400], "worker_id": "W-001"}
        w2 = {"bbox": [105, 100, 205, 400], "worker_id": "W-002"}
        det = {"class": "helmet", "name": "helmet", "confidence": 0.90, "bbox": [110, 105, 190, 165], "source": "yolo", "is_synthetic": False}
        res = associate_ppe_with_persons([w1, w2], [det])
        self.assertEqual(res[0]["worn_ppe"], [])
        self.assertEqual(res[1]["worn_ppe"], [])

    # 19. Unmatched entities handling
    def test_19_unmatched_entities_handling(self):
        # 3 workers, 1 helmet: 1 matched, 2 remain unmatched without false evidence
        w1 = {"bbox": [100, 100, 200, 400], "worker_id": "W-001"}
        w2 = {"bbox": [300, 100, 400, 400], "worker_id": "W-002"}
        w3 = {"bbox": [500, 100, 600, 400], "worker_id": "W-003"}
        h1 = {"class": "helmet", "name": "helmet", "confidence": 0.92, "bbox": [110, 105, 190, 165], "source": "yolo", "is_synthetic": False}
        res = associate_ppe_with_persons([w1, w2, w3], [h1])
        self.assertEqual(res[0]["worn_ppe"], ["helmet"])
        self.assertEqual(res[1]["worn_ppe"], [])
        self.assertEqual(res[2]["worn_ppe"], [])
        self.assertEqual(len(res[0]["ppe_associations"]), 1)
        self.assertEqual(len(res[1]["ppe_associations"]), 0)
        self.assertEqual(len(res[2]["ppe_associations"]), 0)

    # 20. Four-class independent assignment and canonical sorting
    def test_20_four_class_independent_assignment(self):
        w = {"bbox": [100, 100, 200, 500], "worker_id": "W-001"}
        # Head: [100, 100, 200, 200]
        # Face: [120, 140, 180, 220]
        # Torso: [100, 200, 200, 380]
        # Feet: [100, 400, 200, 500]
        h = {"class": "helmet", "name": "helmet", "confidence": 0.9, "bbox": [110, 105, 190, 180], "source": "yolo", "is_synthetic": False}
        g = {"class": "goggles", "name": "goggles", "confidence": 0.85, "bbox": [130, 150, 170, 190], "source": "yolo", "is_synthetic": False}
        v = {"class": "vest", "name": "vest", "confidence": 0.92, "bbox": [105, 220, 195, 360], "source": "yolo", "is_synthetic": False}
        b = {"class": "boots", "name": "boots", "confidence": 0.88, "bbox": [110, 420, 190, 490], "source": "yolo", "is_synthetic": False}
        res = associate_ppe_with_persons([w], [b, v, g, h]) # passed in reverse order
        # Must be canonically sorted: helmet, vest, goggles, boots
        self.assertEqual(res[0]["worn_ppe"], ["helmet", "vest", "goggles", "boots"])
        self.assertEqual(len(res[0]["ppe_associations"]), 4)


if __name__ == "__main__":
    unittest.main()
