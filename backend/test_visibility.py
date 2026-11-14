import unittest
from ai_engine.compliance import (
    detect_scanned_body_parts,
    evaluate_compliance,
    associate_ppe_with_persons
)
from ai_engine.tracker import LightweightIoUTracker
from config import Config

class TestIndependentBodyRegionVisibility(unittest.TestCase):

    def setUp(self):
        self.img_shape = (480, 640) # h=480, w=640

    # 1. Fully visible person
    def test_01_fully_visible_person(self):
        # Cleanly in frame: pw=100, ph=370, aspect=3.7, py1=50, py2=420
        box = [100, 50, 200, 420]
        res = detect_scanned_body_parts(box, img_shape=self.img_shape)
        self.assertTrue(res["head"])
        self.assertTrue(res["face"])
        self.assertTrue(res["torso"])
        self.assertTrue(res["feet"])
        self.assertIn("head", res["scanned_regions"])
        self.assertIn("face", res["scanned_regions"])
        self.assertIn("torso", res["scanned_regions"])
        self.assertIn("feet", res["scanned_regions"])
        self.assertEqual(res["visibility_details"]["head"]["status"], "observable")
        self.assertEqual(res["visibility_details"]["feet"]["status"], "observable")

    # 2. Head clipped at upper image boundary
    def test_02_head_clipped_at_upper_image_boundary(self):
        # py1 < 0: Head extends above camera boundary
        box = [100, -15, 200, 350]
        res = detect_scanned_body_parts(box, img_shape=self.img_shape)
        self.assertFalse(res["head"])
        self.assertNotIn("head", res["scanned_regions"])
        self.assertEqual(res["visibility_details"]["head"]["status"], "unobservable")
        self.assertEqual(res["visibility_details"]["head"]["reason"], "head_cut_off_at_top_boundary")

    # 3. Head partially clipped (touching top edge)
    def test_03_head_partially_clipped(self):
        # 0 <= py1 <= 10: Head touches top border
        box = [100, 5, 200, 370]
        res = detect_scanned_body_parts(box, img_shape=self.img_shape)
        self.assertFalse(res["head"])
        self.assertNotIn("head", res["scanned_regions"])
        self.assertEqual(res["visibility_details"]["head"]["status"], "partially_observable")
        self.assertEqual(res["visibility_details"]["head"]["reason"], "head_touches_top_edge")

    # 4. Face region unavailable despite visible head
    def test_04_face_unavailable_despite_visible_head(self):
        # Head cleanly in frame (py1=50), but low person height (ph=65 < 80 min_face_h)
        box = [100, 50, 140, 115]
        res = detect_scanned_body_parts(box, img_shape=self.img_shape)
        self.assertTrue(res["head"])
        self.assertFalse(res["face"])
        self.assertIn("head", res["scanned_regions"])
        self.assertNotIn("face", res["scanned_regions"])
        self.assertEqual(res["visibility_details"]["face"]["status"], "uncertain")
        self.assertEqual(res["visibility_details"]["face"]["reason"], "insufficient_face_resolution")

    # 5. Torso clipped at image boundary
    def test_05_torso_clipped_at_image_boundary(self):
        # Person starting above frame such that torso is partially clipped at top:
        # py1 = -80, py2 = 200 -> ph = 280
        # torso_y1 = -80 + 0.25*280 = -10 < 0 (top of torso is clipped)
        # torso_y2 = -80 + 0.70*280 = 116 > 0 (bottom of torso is in frame)
        box = [100, -80, 200, 200]
        res = detect_scanned_body_parts(box, img_shape=self.img_shape)
        self.assertFalse(res["torso"])
        self.assertNotIn("torso", res["scanned_regions"])
        self.assertEqual(res["visibility_details"]["torso"]["status"], "partially_observable")
        self.assertEqual(res["visibility_details"]["torso"]["reason"], "torso_clipped_at_top")

    # 6. Feet clipped at lower boundary
    def test_06_feet_clipped_at_lower_boundary(self):
        # py2 = 475 >= 480 - 25 (margin_bottom)
        box = [100, 50, 200, 475]
        res = detect_scanned_body_parts(box, img_shape=self.img_shape)
        self.assertFalse(res["feet"])
        self.assertNotIn("feet", res["scanned_regions"])
        self.assertEqual(res["visibility_details"]["feet"]["status"], "unobservable")
        self.assertEqual(res["visibility_details"]["feet"]["reason"], "feet_cut_off_at_bottom_boundary")

    # 7. Person partially outside left boundary
    def test_07_person_partially_outside_left_boundary(self):
        # px1 = -20 <= 0 (clipped on left)
        box = [-20, 50, 80, 400]
        res = detect_scanned_body_parts(box, img_shape=self.img_shape)
        self.assertFalse(res["head"])
        self.assertFalse(res["torso"])
        self.assertFalse(res["feet"])
        self.assertEqual(res["visibility_details"]["head"]["status"], "partially_observable")
        self.assertEqual(res["visibility_details"]["torso"]["status"], "partially_observable")

    # 8. Person partially outside right boundary
    def test_08_person_partially_outside_right_boundary(self):
        # px2 = 650 >= 640 (clipped on right)
        box = [580, 50, 650, 400]
        res = detect_scanned_body_parts(box, img_shape=self.img_shape)
        self.assertFalse(res["head"])
        self.assertFalse(res["torso"])
        self.assertFalse(res["feet"])
        self.assertEqual(res["visibility_details"]["head"]["status"], "partially_observable")

    # 9. Helmet detection present while head is clipped
    def test_09_helmet_present_while_head_clipped(self):
        # Head is clipped at top (py1 = 0 <= margin_top 10)
        person = {"bbox": [100, 0, 200, 350], "worker_id": "W-001"}
        helmet = {"class": "helmet", "name": "helmet", "confidence": 0.95, "bbox": [110, 0, 190, 50], "source": "yolo", "is_synthetic": False}

        # Visibility assessment must be independent: head must NOT become observable
        status, missing, evaluated = evaluate_compliance([person], [helmet], required_ppe=["helmet", "vest"], img_shape=self.img_shape)
        p = evaluated[0]
        self.assertNotIn("head", p["scanned_body_parts"])
        self.assertEqual(p["body_region_visibility"]["head"]["status"], "partially_observable")
        # Helmet is ignored because head was not scanned
        self.assertIn("helmet", p["ignored_unscanned_ppe"])

    # 10. Helmet detection absent while head is observable
    def test_10_helmet_absent_while_head_observable(self):
        # Fully observable head, zero helmet detections
        person = {"bbox": [100, 50, 200, 420], "worker_id": "W-001"}
        status, missing, evaluated = evaluate_compliance([person], [], required_ppe=["helmet", "vest"], img_shape=self.img_shape)
        p = evaluated[0]
        self.assertIn("head", p["scanned_body_parts"])
        self.assertIn("helmet", p["missing_ppe"])
        self.assertEqual(status, "VIOLATION")

    # 11. Boots detection present while feet are unobservable
    def test_11_boots_present_while_feet_unobservable(self):
        # py2 = 478 (feet cut off by frame bottom)
        person = {"bbox": [100, 50, 200, 478], "worker_id": "W-001"}
        boots = {"class": "boots", "name": "boots", "confidence": 0.90, "bbox": [110, 430, 190, 475], "source": "yolo", "is_synthetic": False}

        # Boots detection MUST NOT make feet observable!
        status, missing, evaluated = evaluate_compliance([person], [boots], required_ppe=["helmet", "vest", "boots"], img_shape=self.img_shape)
        p = evaluated[0]
        self.assertNotIn("feet", p["scanned_body_parts"])
        self.assertEqual(p["body_region_visibility"]["feet"]["status"], "unobservable")
        self.assertIn("boots", p["ignored_unscanned_ppe"])

    # 12. No PPE detections must not change visibility results
    def test_12_no_ppe_detections_invariant(self):
        box = [100, 50, 200, 420]
        res_no_ppe = detect_scanned_body_parts(box, img_shape=self.img_shape, worn_ppe=[])
        res_with_ppe = detect_scanned_body_parts(box, img_shape=self.img_shape, worn_ppe=["helmet", "vest", "boots"])
        self.assertEqual(res_no_ppe["scanned_regions"], res_with_ppe["scanned_regions"])
        self.assertEqual(res_no_ppe["visibility_details"], res_with_ppe["visibility_details"])

    # 13. Visibility results remain consistent when PPE detections change
    def test_13_visibility_consistent_across_ppe_changes(self):
        box = [100, 50, 200, 475] # feet clipped
        res1 = detect_scanned_body_parts(box, img_shape=self.img_shape, worn_ppe=["boots"])
        res2 = detect_scanned_body_parts(box, img_shape=self.img_shape, worn_ppe=[])
        res3 = detect_scanned_body_parts(box, img_shape=self.img_shape, worn_ppe=["helmet"])
        self.assertEqual(res1["scanned_regions"], res2["scanned_regions"])
        self.assertEqual(res2["scanned_regions"], res3["scanned_regions"])
        self.assertFalse(res1["feet"])
        self.assertFalse(res2["feet"])
        self.assertFalse(res3["feet"])

    # 14. Welding-zone goggles requirement with unobservable face
    def test_14_welding_zone_goggles_unobservable_face(self):
        # Person with visible head and torso, but low height (ph=65 < 80) -> face is uncertain
        person = {"bbox": [100, 50, 140, 115], "worker_id": "W-001"}
        helmet = {"class": "helmet", "name": "helmet", "confidence": 0.90, "bbox": [105, 52, 135, 68], "source": "yolo", "is_synthetic": False}
        vest = {"class": "vest", "name": "vest", "confidence": 0.90, "bbox": [105, 70, 135, 95], "source": "yolo", "is_synthetic": False}

        # Welding zone requires helmet, vest, and goggles
        status, missing, evaluated = evaluate_compliance([person], [helmet, vest], required_ppe=["helmet", "vest", "goggles"], img_shape=self.img_shape)
        p = evaluated[0]
        # Goggles must be placed in ignored_unscanned_ppe, NOT in missing_ppe
        self.assertIn("goggles", p["ignored_unscanned_ppe"])
        self.assertNotIn("goggles", p["missing_ppe"])
        self.assertEqual(p["missing_ppe"], [])
        self.assertEqual(status, "COMPLIANT")

    # 15. General-zone policy does not require goggles
    def test_15_general_zone_policy_no_goggles(self):
        # General floor requires helmet and vest
        person = {"bbox": [100, 50, 140, 115], "worker_id": "W-001"}
        helmet = {"class": "helmet", "name": "helmet", "confidence": 0.90, "bbox": [105, 52, 135, 68], "source": "yolo", "is_synthetic": False}
        vest = {"class": "vest", "name": "vest", "confidence": 0.90, "bbox": [105, 70, 135, 95], "source": "yolo", "is_synthetic": False}

        status, missing, evaluated = evaluate_compliance([person], [helmet, vest], required_ppe=["helmet", "vest"], img_shape=self.img_shape)
        p = evaluated[0]
        self.assertEqual(p["missing_ppe"], [])
        self.assertEqual(status, "COMPLIANT")

    # 16. Legacy scanned_body_parts remains list of strings
    def test_16_legacy_scanned_body_parts_type(self):
        person = {"bbox": [100, 50, 200, 420], "worker_id": "W-001"}
        status, missing, evaluated = evaluate_compliance([person], [], required_ppe=["helmet", "vest"], img_shape=self.img_shape)
        p = evaluated[0]
        self.assertIsInstance(p["scanned_body_parts"], list)
        self.assertTrue(all(isinstance(x, str) for x in p["scanned_body_parts"]))
        self.assertIsInstance(p["body_region_visibility"], dict)

    # 17. Existing association and tracker tests unaffected
    def test_17_association_tracker_unaffected(self):
        tracker = LightweightIoUTracker()
        det = [{"bbox": [100, 100, 200, 300], "confidence": 0.9}]
        res = tracker.update(det, timestamp=1.0)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["worker_id"], "W-001")

if __name__ == "__main__":
    unittest.main()
