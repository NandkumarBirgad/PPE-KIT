import unittest
import json
import time
import datetime
from unittest.mock import patch

from app import create_app
from database import (
    mem_cameras,
    mem_zones,
    mem_detections,
    mem_settings,
    DEFAULT_SYSTEM_SETTINGS,
    get_system_settings,
    update_system_settings
)
from auth import generate_token
from ai_engine.camera_health import (
    evaluate_camera_health,
    record_camera_frame_success,
    record_camera_frame_failure,
    record_camera_video_completed,
    HEALTH_STATUS_ONLINE,
    HEALTH_STATUS_WARNING,
    HEALTH_STATUS_OFFLINE,
    HEALTH_STATUS_DEGRADED,
    HEALTH_STATUS_COMPLETED
)

class TestConfigurationAndCameraHealth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

        # Auth tokens
        cls.admin_token = generate_token("usr_admin_test", "SUPER_ADMIN", "admin@ppe.com")
        cls.supervisor_token = generate_token("usr_sup_test", "ZONE_SUPERVISOR", "supervisor@ppe.com")
        cls.admin_headers = {"Authorization": f"Bearer {cls.admin_token}"}
        cls.supervisor_headers = {"Authorization": f"Bearer {cls.supervisor_token}"}

    def setUp(self):
        self._orig_mem_cameras = [dict(c) for c in mem_cameras]
        self._orig_mem_zones = [dict(z) for z in mem_zones]
        self._orig_mem_detections = [dict(d) for d in mem_detections]
        self._orig_mem_settings = dict(mem_settings)

    def tearDown(self):
        mem_cameras.clear()
        mem_cameras.extend(self._orig_mem_cameras)
        mem_zones.clear()
        mem_zones.extend(self._orig_mem_zones)
        mem_detections.clear()
        mem_detections.extend(self._orig_mem_detections)
        mem_settings.clear()
        mem_settings.update(self._orig_mem_settings)

    # -------------------------------------------------------------
    # 1. Configuration Tests
    # -------------------------------------------------------------

    def test_1_default_settings_when_none_exist(self):
        """1. Default settings returned when no saved configuration exists."""
        mem_settings.clear()
        res = self.client.get("/api/settings", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["_id"], "global_settings")
        self.assertEqual(data["confidence_threshold"], 0.35)
        self.assertEqual(data["violation_confirmation_duration_sec"], 3.0)
        self.assertEqual(data["incident_auto_resolution_duration_sec"], 2.0)
        self.assertEqual(data["default_required_ppe"], ["helmet", "vest", "boots"])

    def test_m3_2f_factory_defaults_alignment(self):
        """M3.2-F: Factory defaults include helmet, vest, boots and exactly 2.0s auto-resolution."""
        settings = get_system_settings()
        self.assertEqual(settings["default_required_ppe"], ["helmet", "vest", "boots"])
        self.assertEqual(settings["incident_auto_resolution_duration_sec"], 2.0)

    def test_m3_2f_welding_zone_policy_still_requires_goggles(self):
        """M3.2-F: Explicitly configured zone policies (Welding Zone) remain unchanged and require goggles."""
        welding_zone = next((z for z in mem_zones if z["_id"] == "zone_welding"), None)
        self.assertIsNotNone(welding_zone)
        self.assertIn("goggles", welding_zone["requiredPPE"])
        self.assertEqual(welding_zone["requiredPPE"], ["helmet", "vest", "boots", "goggles"])

    def test_m3_2f_existing_saved_configurations_preserved(self):
        """M3.2-F: Existing persisted configurations are not overwritten by application defaults."""
        mem_settings.clear()
        mem_settings.update({
            "_id": "global_settings",
            "factory_name": "Custom User Plant",
            "confidence_threshold": 0.62,
            "default_required_ppe": ["helmet", "gloves"]
        })
        loaded = get_system_settings()
        self.assertEqual(loaded["factory_name"], "Custom User Plant")
        self.assertEqual(loaded["confidence_threshold"], 0.62)
        self.assertEqual(loaded["default_required_ppe"], ["helmet", "gloves"])
        # Absent field falls back to default
        self.assertEqual(loaded["incident_auto_resolution_duration_sec"], 2.0)

    @patch("routes.detection_routes.detect_ppe_in_frame")
    def test_m3_2f_unzoned_monitoring_applies_all_three_required_ppe(self, mock_detect):
        """M3.2-F: Unzoned uploaded-video monitoring applies factory default policy (helmet, vest, boots)."""
        import io
        import cv2
        import numpy as np
        import tempfile
        import os

        # Synthetic 5-frame video
        temp_fd, temp_path = tempfile.mkstemp(suffix=".mp4")
        os.close(temp_fd)
        writer = cv2.VideoWriter(temp_path, cv2.VideoWriter_fourcc(*'mp4v'), 10.0, (640, 480))
        for _ in range(5):
            writer.write(np.zeros((480, 640, 3), dtype=np.uint8))
        writer.release()
        with open(temp_path, "rb") as f:
            vbytes = f.read()
        os.remove(temp_path)

        # Worker wears helmet & vest, but is MISSING boots
        w1 = {"bbox": [100, 100, 250, 400], "confidence": 0.95, "track_id": 10, "worker_id": "W-010"}
        detected_gear = [
            {"name": "helmet", "class": "helmet", "confidence": 0.95, "source": "yolo", "is_synthetic": False, "bbox": [110, 100, 240, 160]},
            {"name": "vest", "class": "vest", "confidence": 0.95, "source": "yolo", "is_synthetic": False, "bbox": [110, 170, 240, 300]}
        ]
        mock_detect.side_effect = lambda *args, **kwargs: (None, list(detected_gear), [dict(w1)])

        # Ensure system settings default is active
        mem_settings.clear()

        # Omit required_ppe so unzoned video inherits factory default policy
        res = self.client.post("/api/detect-video", data={
            "file": (io.BytesIO(vbytes), "test_unzoned.mp4"),
            "sample_interval_sec": "0.1",
            "confirmation_duration_sec": "0.1"
        }, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        # Overall missing PPE must flag boots!
        self.assertIn("boots", data["overall_missing_ppe"])

    def test_2_save_and_reload_configuration(self):
        """2. Administrator can update settings and reload authoritative configuration."""
        payload = {
            "factory_name": "Precision Heavy Engineering Ltd",
            "default_required_ppe": ["helmet", "vest", "boots", "goggles"],
            "confidence_threshold": 0.45,
            "violation_confirmation_duration_sec": 4.5,
            "incident_auto_resolution_duration_sec": 2.5,
            "video_sampling_interval_ms": 1200,
            "alert_cooldown_sec": 10,
            "floor_buzzer_enabled": False,
            "sound_enabled": True
        }
        res_put = self.client.put("/api/settings", json=payload, headers=self.admin_headers)
        self.assertEqual(res_put.status_code, 200)
        put_data = res_put.get_json()["settings"]
        self.assertEqual(put_data["factory_name"], "Precision Heavy Engineering Ltd")
        self.assertEqual(put_data["confidence_threshold"], 0.45)
        self.assertEqual(put_data["violation_confirmation_duration_sec"], 4.5)
        self.assertEqual(put_data["floor_buzzer_enabled"], False)

        # Reload via GET
        res_get = self.client.get("/api/settings", headers=self.supervisor_headers)
        self.assertEqual(res_get.status_code, 200)
        get_data = res_get.get_json()
        self.assertEqual(get_data["factory_name"], "Precision Heavy Engineering Ltd")
        self.assertEqual(get_data["confidence_threshold"], 0.45)
        self.assertEqual(get_data["default_required_ppe"], ["helmet", "vest", "boots", "goggles"])

    def test_3_persistence_across_reinitialization(self):
        """3. Persisted settings survive cache clear / re-fetching via get_system_settings."""
        update_system_settings({
            "confidence_threshold": 0.55,
            "camera_warning_timeout_sec": 6.0,
            "camera_offline_timeout_sec": 18.0
        })
        # Simulate retrieval
        reloaded = get_system_settings()
        self.assertEqual(reloaded["confidence_threshold"], 0.55)
        self.assertEqual(reloaded["camera_warning_timeout_sec"], 6.0)
        self.assertEqual(reloaded["camera_offline_timeout_sec"], 18.0)

    def test_4_invalid_configuration_values_rejected(self):
        """4. Rejects numeric out-of-range, malformed, or unaccepted PPE categories."""
        # Confidence out of bounds
        r1 = self.client.put("/api/settings", json={"confidence_threshold": 1.5}, headers=self.admin_headers)
        self.assertEqual(r1.status_code, 400)
        self.assertIn("confidence_threshold", r1.get_json()["message"])

        # Invalid PPE category
        r2 = self.client.put("/api/settings", json={"default_required_ppe": ["helmet", "laser_gun"]}, headers=self.admin_headers)
        self.assertEqual(r2.status_code, 400)
        self.assertIn("unsupported", r2.get_json()["message"].lower())

        # Offline timeout <= warning timeout
        r3 = self.client.put("/api/settings", json={
            "camera_warning_timeout_sec": 10.0,
            "camera_offline_timeout_sec": 8.0
        }, headers=self.admin_headers)
        self.assertEqual(r3.status_code, 400)
        self.assertIn("strictly greater", r3.get_json()["message"])

    def test_5_unauthorized_supervisor_modification_rejected(self):
        """5. Supervisor can view settings but cannot update them (403 Forbidden)."""
        # GET should succeed
        r_get = self.client.get("/api/settings", headers=self.supervisor_headers)
        self.assertEqual(r_get.status_code, 200)

        # PUT should be rejected with 403
        r_put = self.client.put("/api/settings", json={"confidence_threshold": 0.5}, headers=self.supervisor_headers)
        self.assertEqual(r_put.status_code, 403)

    def test_6_zone_specific_policies_remain_independent(self):
        """6. Factory default PPE changes do not overwrite existing zone-specific policies."""
        zone_id = "zone_chem_test"
        mem_zones.append({
            "_id": zone_id,
            "name": "Chemical Spray Bay",
            "code": "CHEM-99",
            "requiredPPE": ["mask", "goggles", "gloves"]
        })

        # Update factory-wide default PPE
        self.client.put("/api/settings", json={"default_required_ppe": ["helmet", "vest"]}, headers=self.admin_headers)

        # Verify zone policy remains untouched
        target_zone = next(z for z in mem_zones if z["_id"] == zone_id)
        self.assertEqual(target_zone["requiredPPE"], ["mask", "goggles", "gloves"])

    def test_7_existing_incident_history_intact_after_policy_change(self):
        """7. Existing incident history remains unchanged after system settings updates."""
        initial_incident_count = len(mem_detections)
        test_incident = {
            "_id": "det_test_hist_01",
            "episode_id": "ep_hist_01",
            "complianceStatus": "VIOLATION",
            "missingPPE": ["helmet"],
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
        }
        mem_detections.append(test_incident)

        # Update settings
        res = self.client.put("/api/settings", json={"confidence_threshold": 0.50}, headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)

        # Verify historical incident is fully preserved
        found = next((d for d in mem_detections if d.get("_id") == "det_test_hist_01"), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["missingPPE"], ["helmet"])

    # -------------------------------------------------------------
    # 2. Camera Health Tests
    # -------------------------------------------------------------

    def test_8_camera_normal_frame_reception_online(self):
        """8. Valid frame reception records timestamp and marks camera ONLINE."""
        cam_id = "cam_test_01"
        mem_cameras.append({
            "_id": cam_id,
            "name": "Assembly Cam #1",
            "status": "OFFLINE"
        })

        now = 1000.0
        updated = record_camera_frame_success(cam_id, timestamp=now)
        self.assertEqual(updated["status"], HEALTH_STATUS_ONLINE)
        self.assertEqual(updated["last_frame_time"], now)
        self.assertEqual(updated["consecutive_failures"], 0)

        # Evaluate health at now + 2s (within 5s warning window)
        evaluated = evaluate_camera_health(updated, current_time=now + 2.0)
        self.assertEqual(evaluated["status"], HEALTH_STATUS_ONLINE)

    def test_9_camera_warning_after_5_seconds(self):
        """9. Transitions to WARNING after 5 seconds without frames."""
        cam_id = "cam_test_warn"
        now = 1000.0
        cam_doc = {
            "_id": cam_id,
            "name": "Assembly Cam #2",
            "status": HEALTH_STATUS_ONLINE,
            "last_frame_time": now
        }
        mem_cameras.append(cam_doc)

        # At t = 1005.5s (5.5s elapsed, threshold: 5.0s)
        evaluated = evaluate_camera_health(cam_doc, current_time=now + 5.5)
        self.assertEqual(evaluated["status"], HEALTH_STATUS_WARNING)
        self.assertIn("warning threshold", evaluated["status_reason"])

    def test_10_camera_offline_after_15_seconds(self):
        """10. Transitions to OFFLINE after 15 seconds without frames."""
        cam_id = "cam_test_off"
        now = 1000.0
        cam_doc = {
            "_id": cam_id,
            "name": "Assembly Cam #3",
            "status": HEALTH_STATUS_ONLINE,
            "last_frame_time": now
        }
        mem_cameras.append(cam_doc)

        # At t = 1016.0s (16.0s elapsed, threshold: 15.0s)
        evaluated = evaluate_camera_health(cam_doc, current_time=now + 16.0)
        self.assertEqual(evaluated["status"], HEALTH_STATUS_OFFLINE)
        self.assertIn("offline threshold", evaluated["status_reason"])

    def test_11_camera_degraded_on_repeated_failures(self):
        """11. Transitions to DEGRADED after repeated processing failures."""
        cam_id = "cam_test_fail"
        cam_doc = {
            "_id": cam_id,
            "name": "Assembly Cam #4",
            "status": HEALTH_STATUS_ONLINE,
            "consecutive_failures": 0
        }
        mem_cameras.append(cam_doc)

        # 3 consecutive failures
        record_camera_frame_failure(cam_id, "Corrupt JPEG header", timestamp=100.0)
        record_camera_frame_failure(cam_id, "Corrupt JPEG header", timestamp=101.0)
        res3 = record_camera_frame_failure(cam_id, "Corrupt JPEG header", timestamp=102.0)

        self.assertEqual(res3["status"], HEALTH_STATUS_DEGRADED)
        self.assertEqual(res3["consecutive_failures"], 3)
        self.assertIn("Degraded", res3["status_reason"])

    def test_12_camera_recovery_after_valid_frames(self):
        """12. Camera in DEGRADED/OFFLINE recovers to ONLINE when valid frames resume."""
        cam_id = "cam_test_recov"
        cam_doc = {
            "_id": cam_id,
            "name": "Assembly Cam #5",
            "status": HEALTH_STATUS_DEGRADED,
            "consecutive_failures": 5,
            "error_details": "RTSP socket disconnected"
        }
        mem_cameras.append(cam_doc)

        # Valid frame received
        recovered = record_camera_frame_success(cam_id, timestamp=500.0)
        self.assertEqual(recovered["status"], HEALTH_STATUS_ONLINE)
        self.assertEqual(recovered["consecutive_failures"], 0)
        self.assertIsNone(recovered["error_details"])
        self.assertIn("normally", recovered["status_reason"])

    def test_13_uploaded_video_completion(self):
        """13. Uploaded video completion transitions camera to COMPLETED, not OFFLINE."""
        cam_id = "cam_test_vid_done"
        cam_doc = {
            "_id": cam_id,
            "name": "Video Cam Profile",
            "status": HEALTH_STATUS_ONLINE,
            "last_frame_time": 200.0
        }
        mem_cameras.append(cam_doc)

        completed = record_camera_video_completed(cam_id, "Uploaded video inspection completed normally", timestamp=205.0)
        self.assertEqual(completed["status"], HEALTH_STATUS_COMPLETED)

        # Evaluating health even after 100 seconds keeps COMPLETED status
        evaluated = evaluate_camera_health(completed, current_time=400.0)
        self.assertEqual(evaluated["status"], HEALTH_STATUS_COMPLETED)

    def test_14_camera_failures_never_generate_ppe_incidents(self):
        """14. Camera frame failures reject request without generating PPE incidents."""
        initial_incident_count = len(mem_detections)
        cam_id = "cam_fail_safety"
        mem_cameras.append({"_id": cam_id, "name": "Failing Camera", "status": HEALTH_STATUS_ONLINE})

        # Send invalid image payload to /api/detect
        r = self.client.post("/api/detect", json={
            "camera_id": cam_id,
            "image": "not_a_valid_base64_string"
        })
        self.assertEqual(r.status_code, 400)

        # Verify no incident was created in mem_detections
        self.assertEqual(len(mem_detections), initial_incident_count)

if __name__ == "__main__":
    unittest.main()
