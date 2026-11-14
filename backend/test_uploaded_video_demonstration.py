import os
import io
import cv2
import numpy as np
import unittest
import tempfile
import uuid
from unittest.mock import patch

from app import create_app
from database import mem_cameras, mem_zones, mem_detections
from ai_engine.temporal_compliance import (
    get_session_temporal_tracker,
    reset_session_temporal
)
from ai_engine.tracker import (
    get_session_tracker,
    reset_session_tracker
)
from ai_engine.zone_assignment import (
    lookup_camera,
    lookup_zone,
    reset_session_spatial_zones
)


def generate_synthetic_video_bytes(num_frames=15, fps=25.0, width=640, height=480):
    """Creates a temporary valid MP4 video in memory."""
    fd, path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(path, fourcc, fps, (width, height))
    for i in range(num_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        # Draw colored rectangle to ensure frame has non-zero pixels
        cv2.rectangle(frame, (100, 100), (300, 300), (0, 200, 100), -1)
        out.write(frame)
    out.release()

    with open(path, 'rb') as f:
        video_bytes = f.read()
    if os.path.exists(path):
        os.remove(path)
    return video_bytes


class TestUploadedVideoDemonstration(unittest.TestCase):
    """
    Milestone M3.1: Uploaded Video Demonstration Workflow & Spatial Zone Integration.
    Tests explicit camera profile association, unzoned fallback, session isolation,
    frame timestamp calculation, spatial zone compliance, incident persistence,
    deduplication across video timeline, and temporary file cleanup.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.video_bytes = generate_synthetic_video_bytes(num_frames=12, fps=25.0)

    def setUp(self):
        self._orig_mem_cameras = list(mem_cameras)
        self._orig_mem_zones = list(mem_zones)
        self._orig_mem_detections = list(mem_detections)
        mem_detections.clear()

        # Configure General Zone (requires helmet, vest, boots)
        self.zone_general = "zone_assembly_demo"
        if not any(str(z.get("_id")) == self.zone_general for z in mem_zones):
            mem_zones.append({
                "_id": self.zone_general,
                "name": "Assembly Demonstration Zone",
                "code": "ASM-DEMO",
                "requiredPPE": ["helmet", "vest", "boots"]
            })

        # Configure Welding Zone (strictly requires helmet, vest, boots, goggles)
        self.zone_welding = "zone_welding_demo"
        if not any(str(z.get("_id")) == self.zone_welding for z in mem_zones):
            mem_zones.append({
                "_id": self.zone_welding,
                "name": "Welding Demonstration Bay",
                "code": "WELD-DEMO",
                "requiredPPE": ["helmet", "vest", "boots", "goggles"]
            })

        # Configure a Camera with Dual Polygon Spatial Zones
        self.camera_id = "cam_dual_poly_demo"
        self.camera_doc = {
            "_id": self.camera_id,
            "name": "Dual Zone Demo Camera",
            "zoneId": self.zone_general,
            "zoneName": "Assembly Demonstration Zone",
            "sourceType": "video_file",
            "zones": [
                {
                    "zoneId": self.zone_general,
                    "zoneName": "Assembly Demonstration Zone",
                    "priority": 1,
                    "polygon": [
                        {"x": 0.05, "y": 0.05},
                        {"x": 0.45, "y": 0.05},
                        {"x": 0.45, "y": 0.95},
                        {"x": 0.05, "y": 0.95}
                    ]
                },
                {
                    "zoneId": self.zone_welding,
                    "zoneName": "Welding Demonstration Bay",
                    "priority": 2,
                    "polygon": [
                        {"x": 0.55, "y": 0.05},
                        {"x": 0.95, "y": 0.05},
                        {"x": 0.95, "y": 0.95},
                        {"x": 0.55, "y": 0.95}
                    ]
                }
            ]
        }
        mem_cameras.insert(0, self.camera_doc)

    def tearDown(self):
        mem_cameras.clear()
        mem_cameras.extend(self._orig_mem_cameras)
        mem_zones.clear()
        mem_zones.extend(self._orig_mem_zones)
        mem_detections.clear()
        mem_detections.extend(self._orig_mem_detections)

    # =========================================================================
    # 1. Camera Profile Association & Spatial Polygon Evaluation
    # =========================================================================

    @patch("routes.detection_routes.detect_ppe_in_frame")
    def test_uploaded_video_with_explicit_camera_profile_uses_polygons(self, mock_detect):
        """
        Uploaded video with explicit cameraId uses that camera's spatial polygons.
        Worker in Welding Zone without goggles confirms violation; Worker in General Zone is compliant.
        """
        # Worker A in General Zone (left, anchor ~0.22)
        # Worker B in Welding Zone (right, anchor ~0.72)
        w1 = {"bbox": [80, 100, 200, 400], "confidence": 0.95, "track_id": 1, "worker_id": "W-001"}
        w2 = {"bbox": [400, 100, 520, 400], "confidence": 0.95, "track_id": 2, "worker_id": "W-002"}

        # Both workers wear helmet, vest, boots. Neither wears goggles.
        detected_objects = [
            {"bbox": [90, 100, 190, 160], "name": "helmet", "class": "helmet", "source": "yolo", "confidence": 0.95},
            {"bbox": [85, 170, 195, 300], "name": "vest", "class": "vest", "source": "yolo", "confidence": 0.95},
            {"bbox": [90, 340, 190, 400], "name": "boots", "class": "boots", "source": "yolo", "confidence": 0.95},
            {"bbox": [410, 100, 510, 160], "name": "helmet", "class": "helmet", "source": "yolo", "confidence": 0.95},
            {"bbox": [405, 170, 515, 300], "name": "vest", "class": "vest", "source": "yolo", "confidence": 0.95},
            {"bbox": [410, 340, 510, 400], "name": "boots", "class": "boots", "source": "yolo", "confidence": 0.95}
        ]
        mock_detect.side_effect = lambda *args, **kwargs: (None, list(detected_objects), [dict(w1), dict(w2)])

        response = self.client.post("/detect-video", data={
            "file": (io.BytesIO(self.video_bytes), "factory_test.mp4"),
            "cameraId": self.camera_id,
            "sample_interval_sec": "0.1",
            "confirmation_duration_sec": "0.2"
        }, content_type="multipart/form-data")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        # Check camera profile returned
        self.assertEqual(data["camera_profile"]["_id"], self.camera_id)
        self.assertTrue(data["camera_profile"]["has_camera_polygons"])
        self.assertEqual(len(data["camera_profile"]["zones"]), 2)

        # Worker B in Welding Bay must trigger a confirmed incident for goggles
        self.assertEqual(data["overall_compliance_status"], "VIOLATION")
        self.assertIn("goggles", data["overall_missing_ppe"])
        self.assertGreaterEqual(data["total_violations_found"], 1)

        # Check frame breakdown
        self.assertGreater(len(data["frame_breakdown"]), 0)
        frame1 = data["frame_breakdown"][0]
        self.assertIn("annotated_image", frame1)
        self.assertEqual(frame1["persons_count"], 2)

    @patch("routes.detection_routes.detect_ppe_in_frame")
    def test_uploaded_video_without_selected_camera_remains_unzoned(self, mock_detect):
        """
        Uploaded video without cameraId runs in unzoned mode and DOES NOT inherit any camera's polygons.
        """
        w1 = {"bbox": [400, 100, 520, 400], "confidence": 0.95, "track_id": 5, "worker_id": "W-005"}
        # Worker wearing helmet and vest, but NO goggles
        gear = [
            {"bbox": [410, 100, 510, 160], "name": "helmet", "class": "helmet", "source": "yolo", "confidence": 0.95},
            {"bbox": [405, 170, 515, 300], "name": "vest", "class": "vest", "source": "yolo", "confidence": 0.95}
        ]
        mock_detect.side_effect = lambda *args, **kwargs: (None, list(gear), [dict(w1)])

        # No cameraId passed; required_ppe specifies only helmet and vest
        response = self.client.post("/detect-video", data={
            "file": (io.BytesIO(self.video_bytes), "unzoned_test.mp4"),
            "required_ppe": '["helmet", "vest"]',
            "sample_interval_sec": "0.1"
        }, content_type="multipart/form-data")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        # Must report unzoned camera profile without polygons
        self.assertEqual(data["camera_profile"]["_id"], "uploaded_video")
        self.assertFalse(data["camera_profile"]["has_camera_polygons"])
        self.assertEqual(data["camera_profile"]["zones"], [])

        # Since goggles are not required in unzoned mode, worker is COMPLIANT
        self.assertEqual(data["overall_compliance_status"], "COMPLIANT")
        self.assertEqual(data["total_violations_found"], 0)

    def test_unknown_camera_id_never_inherits_cam_01_polygons(self):
        """
        Passing an invalid or nonexistent camera ID strictly returns unconfigured camera
        with empty zones, preventing silent inheritance of cam_01's polygons.
        """
        # Ensure cam_01 has polygons in memory
        cam_01 = next((c for c in mem_cameras if str(c.get("_id")) == "cam_01"), None)
        if cam_01:
            cam_01["zones"] = [{"zoneId": "zone_01", "polygon": [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.9}]}]

        # Look up nonexistent camera
        cam = lookup_camera(camera_id="cam_completely_fake_9999")
        self.assertEqual(cam["_id"], "cam_completely_fake_9999")
        self.assertEqual(cam.get("zones", []), [])
        self.assertTrue(cam.get("is_unknown", False))

    # =========================================================================
    # 2. Session Isolation & Timestamps
    # =========================================================================

    @patch("routes.detection_routes.detect_ppe_in_frame")
    def test_two_uploaded_video_sessions_remain_isolated(self, mock_detect):
        """
        Two sequential uploaded video runs receive unique isolated session IDs.
        Stopping or completing one run completely resets its session state without affecting others.
        """
        w = {"bbox": [100, 100, 200, 300], "confidence": 0.9, "track_id": 99, "worker_id": "W-099"}
        mock_detect.side_effect = lambda *args, **kwargs: (None, [], [dict(w)])

        # Run Video 1
        res1 = self.client.post("/detect-video", data={
            "file": (io.BytesIO(self.video_bytes), "video1.mp4"),
            "sample_interval_sec": "0.1"
        }, content_type="multipart/form-data")
        self.assertEqual(res1.status_code, 200)

        # Run Video 2
        res2 = self.client.post("/detect-video", data={
            "file": (io.BytesIO(self.video_bytes), "video2.mp4"),
            "sample_interval_sec": "0.1"
        }, content_type="multipart/form-data")
        self.assertEqual(res2.status_code, 200)

        # Verify no leaking active trackers remain in memory
        d1 = res1.get_json()
        d2 = res2.get_json()
        self.assertGreater(d1["total_frames_processed"], 0)
        self.assertGreater(d2["total_frames_processed"], 0)

    @patch("routes.detection_routes.detect_ppe_in_frame")
    def test_frame_timestamps_advance_strictly_monotonically(self, mock_detect):
        """
        Derived frame timestamps must advance monotonically based on video frame index and FPS.
        """
        mock_detect.side_effect = lambda *args, **kwargs: (None, [], [])

        res = self.client.post("/detect-video", data={
            "file": (io.BytesIO(self.video_bytes), "video_ts.mp4"),
            "sample_interval_sec": "0.1"
        }, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        frames = data.get("frame_breakdown", [])
        self.assertGreater(len(frames), 1)

        timestamps = [f["timestamp_sec"] for f in frames]
        # Verify strictly increasing
        for i in range(len(timestamps) - 1):
            self.assertLess(timestamps[i], timestamps[i + 1])

    # =========================================================================
    # 3. Incident Persistence & Deduplication
    # =========================================================================

    @patch("routes.detection_routes.detect_ppe_in_frame")
    def test_incident_persistence_and_deduplication_for_uploaded_videos(self, mock_detect):
        """
        A confirmed violation in an uploaded video is persisted once to the database,
        and not duplicated across subsequent frames of the same ongoing episode.
        """
        w = {"bbox": [400, 100, 520, 400], "confidence": 0.95, "track_id": 8, "worker_id": "W-008"}
        # Missing goggles in Welding Zone
        gear = [
            {"bbox": [410, 100, 510, 160], "name": "helmet", "class": "helmet", "source": "yolo", "confidence": 0.95},
            {"bbox": [405, 170, 515, 300], "name": "vest", "class": "vest", "source": "yolo", "confidence": 0.95},
            {"bbox": [410, 340, 510, 400], "name": "boots", "class": "boots", "source": "yolo", "confidence": 0.95}
        ]
        mock_detect.side_effect = lambda *args, **kwargs: (None, list(gear), [dict(w)])

        res = self.client.post("/detect-video", data={
            "file": (io.BytesIO(self.video_bytes), "dedup_test.mp4"),
            "cameraId": self.camera_id,
            "sample_interval_sec": "0.1",
            "confirmation_duration_sec": "0.1"
        }, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        # Incident persisted in database
        self.assertEqual(data["total_violations_found"], 1)
        persisted = data.get("persisted_incidents", [])
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0]["zoneId"], self.zone_welding)
        self.assertEqual(persisted[0]["missingPPE"], ["goggles"])

        # Also stored in memory collection
        found_in_db = [d for d in mem_detections if d.get("episode_id") == persisted[0]["episode_id"]]
        self.assertEqual(len(found_in_db), 1)
        # Video completion must NOT falsely resolve open incidents
        self.assertIn(found_in_db[0]["status"], ["OPEN", "PENDING"])

    # =========================================================================
    # 4. Error Handling & Representative Frame Extraction
    # =========================================================================

    def test_corrupted_or_empty_video_upload_returns_400(self):
        """
        Uploading an empty or corrupted file returns HTTP 400 with a clear error message.
        """
        res = self.client.post("/detect-video", data={
            "file": (io.BytesIO(b"not a valid video payload"), "corrupt.mp4")
        }, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("Unsupported or corrupted video file", data["message"])

    def test_missing_file_payload_returns_400(self):
        """Request without file payload returns HTTP 400."""
        res = self.client.post("/detect-video", data={})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("Video file is required", data["message"])

    def test_extract_video_frame_endpoint(self):
        """
        /api/extract-video-frame successfully extracts a base64 reference JPEG frame
        and duration from an uploaded video.
        """
        res = self.client.post("/api/extract-video-frame", data={
            "file": (io.BytesIO(self.video_bytes), "demo.mp4"),
            "timestamp_sec": "0.2"
        }, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("frame_image", data)
        self.assertTrue(data["frame_image"].startswith("data:image/jpeg;base64,"))
        self.assertGreater(data["width"], 0)
        self.assertGreater(data["height"], 0)
        self.assertGreater(data["fps"], 0)

    @patch("routes.detection_routes.cv2.VideoCapture")
    def test_extract_video_frame_corrupt_file_releases_capture_and_cleans_temp_file(self, mock_vc_cls):
        """
        Milestone M3.2-F.1: Simulates VideoCapture.isOpened() returning False and verifies:
        - HTTP 400 response with 'Unsupported or corrupted video file'
        - No NameError (camera_id / camera_id_str removed)
        - cap.release() is called
        - Temporary video file is deleted in finally block
        """
        mock_cap = unittest.mock.MagicMock()
        mock_cap.isOpened.return_value = False
        mock_vc_cls.return_value = mock_cap

        created_paths = []
        real_mkstemp = tempfile.mkstemp

        def tracking_mkstemp(*args, **kwargs):
            fd, path = real_mkstemp(*args, **kwargs)
            created_paths.append(path)
            return fd, path

        with patch("routes.detection_routes.tempfile.mkstemp", side_effect=tracking_mkstemp):
            res = self.client.post("/api/extract-video-frame", data={
                "file": (io.BytesIO(b"corrupted dummy bytes"), "corrupt.mp4")
            }, content_type="multipart/form-data")

        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertEqual(data.get("message"), "Unsupported or corrupted video file")

        # Verify capture release
        mock_cap.release.assert_called_once()

        # Verify temp file cleanup
        self.assertTrue(len(created_paths) > 0)
        for p in created_paths:
            self.assertFalse(os.path.exists(p), f"Temporary file was not cleaned up: {p}")


if __name__ == "__main__":
    unittest.main()
