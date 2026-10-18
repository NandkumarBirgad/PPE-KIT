import unittest
import json
import numpy as np
import cv2
import base64
from app import create_app

class BackendFlaskTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def test_01_health_check(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertTrue(data["ai_engine"]["loaded"])

    def test_02_auth_login_admin(self):
        res = self.client.post("/api/auth/login", json={
            "email": "admin@ppe.com",
            "password": "Admin@123"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("token", data)
        self.assertIn(data["user"]["role"].upper(), ["ADMIN", "SUPER_ADMIN"])
        BackendFlaskTestCase.admin_token = data["token"]

    def test_03_auth_me(self):
        res = self.client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {self.admin_token}"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["user"]["email"], "admin@ppe.com")

    def test_04_zones_list(self):
        res = self.client.get("/api/zones")
        self.assertEqual(res.status_code, 200)
        zones = res.get_json()
        self.assertIsInstance(zones, list)
        self.assertGreater(len(zones), 0)

    def test_05_dashboard_summary(self):
        res = self.client.get("/api/dashboard/summary")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("totalEvents", data)
        self.assertIn("complianceRate", data)

    def test_06_ai_detection_inference(self):
        # Create a synthetic 480x640 test image
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        # Draw a synthetic worker: blue torso, yellow helmet
        cv2.rectangle(img, (200, 150), (440, 450), (180, 50, 20), -1) # torso
        cv2.circle(img, (320, 120), 40, (0, 220, 240), -1) # yellow helmet
        _, buffer = cv2.imencode('.jpg', img)
        b64_str = "data:image/jpeg;base64," + base64.b64encode(buffer).decode('utf-8')

        res = self.client.post("/api/detect", json={
            "image": b64_str,
            "required_ppe": ["helmet", "vest"],
            "zone_name": "Test Factory Floor"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("compliance_status", data)
        self.assertIn("annotated_image", data)
        self.assertIn("latency_ms", data)

    def test_07_create_and_get_detection_event(self):
        create_res = self.client.post("/api/detections", json={
            "zoneName": "Test Factory Floor",
            "sourceType": "image",
            "complianceStatus": "VIOLATION",
            "missingPPE": ["vest"],
            "personCount": 1
        })
        self.assertEqual(create_res.status_code, 201)

        list_res = self.client.get("/api/detections")
        self.assertEqual(list_res.status_code, 200)
        data = list_res.get_json()
        self.assertGreaterEqual(data["totalCount"], 1)

    def test_08_reports_and_csv_export(self):
        rep_res = self.client.get("/api/reports/summary")
        self.assertEqual(rep_res.status_code, 200)

        csv_res = self.client.get("/api/reports/export")
        self.assertEqual(csv_res.status_code, 200)
        self.assertEqual(csv_res.mimetype, "text/csv")
        self.assertIn(b"Incident ID,Timestamp,Zone", csv_res.data)

if __name__ == "__main__":
    unittest.main()
