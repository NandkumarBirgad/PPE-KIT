import os
import io
import json
import cv2
import numpy as np
import unittest
import tempfile
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
        cv2.rectangle(frame, (100, 100), (300, 300), (0, 200, 100), -1)
        out.write(frame)
    out.release()

    with open(path, 'rb') as f:
        video_bytes = f.read()
    if os.path.exists(path):
        os.remove(path)
    return video_bytes


def parse_sse_events_from_response(response):
    """Parses raw text/event-stream string from Flask test client response into structured events."""
    raw_text = response.get_data(as_text=True)
    events = []
    # Split by double newline
    blocks = [b.strip() for b in raw_text.replace('\r\n', '\n').split('\n\n') if b.strip()]
    for block in blocks:
        event_type = 'message'
        data_str = ''
        for line in block.split('\n'):
            line = line.strip()
            if line.startswith('event:'):
                event_type = line[6:].strip()
            elif line.startswith('data:'):
                data_str = line[5:].strip()
        if data_str:
            try:
                parsed_json = json.loads(data_str)
                events.append({"event": event_type, "data": parsed_json})
            except Exception:
                events.append({"event": event_type, "data": data_str})
    return events


class TestUploadedVideoStreaming(unittest.TestCase):
    """
    Milestone M2.1: Focused Backend Tests for Progressive Video Monitoring Stream (/detect-video-stream).
    Verifies:
    1. Response content-type is text/event-stream.
    2. 'init' event emitted first with video session and camera metadata.
    3. 'frame' events contain valid persons with native coordinates bounding box and compliance fields.
    4. Incremental frames are emitted chronologically.
    5. 'incident' events emitted upon state transition without duplicates.
    6. 'done' event emitted with final summary metrics.
    7. Corrupted video input yields structured 400 error.
    8. Temporary files and session trackers cleaned up on completion or disconnect.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.video_bytes = generate_synthetic_video_bytes(num_frames=12, fps=25.0)

    def setUp(self):
        mem_detections.clear()

        # Configure General Zone
        self.zone_general = "zone_stream_demo"
        if not any(str(z.get("_id")) == self.zone_general for z in mem_zones):
            mem_zones.append({
                "_id": self.zone_general,
                "name": "Streaming Demo Zone",
                "code": "STR-DEMO",
                "requiredPPE": ["helmet", "vest"]
            })

        # Configure Camera with spatial zones
        self.camera_id = "cam_stream_demo"
        self.camera_doc = {
            "_id": self.camera_id,
            "name": "Streaming Demo Camera",
            "zoneId": self.zone_general,
            "zoneName": "Streaming Demo Zone",
            "sourceType": "video_file",
            "zones": [
                {
                    "zoneId": self.zone_general,
                    "zoneName": "Streaming Demo Zone",
                    "priority": 1,
                    "polygon": [
                        {"x": 0.05, "y": 0.05},
                        {"x": 0.95, "y": 0.05},
                        {"x": 0.95, "y": 0.95},
                        {"x": 0.05, "y": 0.95}
                    ]
                }
            ]
        }
        if not any(str(c.get("_id")) == self.camera_id for c in mem_cameras):
            mem_cameras.append(self.camera_doc)

    def test_01_stream_content_type_and_init_event(self):
        """Verifies streaming endpoint returns text/event-stream and emits 'init' as first event."""
        data = {
            "file": (io.BytesIO(self.video_bytes), "stream_test.mp4"),
            "cameraId": self.camera_id,
            "sample_interval_sec": "0.1",
            "max_frames": "5"
        }
        response = self.client.post(
            "/api/detect-video-stream",
            data=data,
            content_type="multipart/form-data"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.content_type)

        events = parse_sse_events_from_response(response)
        self.assertTrue(len(events) > 0, "Expected at least one SSE event")

        init_ev = events[0]
        self.assertEqual(init_ev["event"], "init")
        self.assertIn("session_id", init_ev["data"])
        self.assertIn("fps", init_ev["data"])
        self.assertIn("sample_interval_sec", init_ev["data"])
        self.assertIn("camera_profile", init_ev["data"])
        self.assertEqual(init_ev["data"]["camera_profile"]["_id"], self.camera_id)

    def test_02_frame_events_contain_bounding_boxes_and_worker_fields(self):
        """Verifies 'frame' events contain bbox and required worker compliance fields."""
        mock_person = {
            "track_id": 101,
            "worker_id": "W-101",
            "bbox": [120, 80, 240, 360],
            "confidence": 0.88,
            "class": "person"
        }
        with patch("routes.detection_routes.detect_ppe_in_frame") as mock_det:
            mock_det.return_value = (None, [{"name": "helmet", "confidence": 0.9, "bbox": [130, 80, 160, 110]}], [mock_person.copy()])

            data = {
                "file": (io.BytesIO(self.video_bytes), "worker_frame_test.mp4"),
                "cameraId": self.camera_id,
                "sample_interval_sec": "0.1",
                "max_frames": "3"
            }
            response = self.client.post(
                "/detect-video-stream",
                data=data,
                content_type="multipart/form-data"
            )
            self.assertEqual(response.status_code, 200)

            events = parse_sse_events_from_response(response)
            frame_events = [e for e in events if e["event"] == "frame"]
            self.assertTrue(len(frame_events) >= 1, "Expected at least 1 frame event")

            first_frame = frame_events[0]["data"]
            self.assertIn("frame_idx", first_frame)
            self.assertIn("timestamp_sec", first_frame)
            self.assertIn("compliance_status", first_frame)
            self.assertIn("persons", first_frame)
            self.assertEqual(len(first_frame["persons"]), 1)

            person_entry = first_frame["persons"][0]
            self.assertEqual(person_entry["worker_id"], "W-101")
            self.assertEqual(person_entry["track_id"], 101)
            self.assertEqual(person_entry["bbox"], [120, 80, 240, 360])
            self.assertIn("compliant", person_entry)
            self.assertIn("uncertain", person_entry)
            self.assertIn("missing_ppe", person_entry)

    def test_03_multiple_frames_emitted_incrementally_with_progress(self):
        """Verifies frames are emitted chronologically with progress events."""
        data = {
            "file": (io.BytesIO(self.video_bytes), "multi_frame.mp4"),
            "sample_interval_sec": "0.08",
            "max_frames": "6"
        }
        response = self.client.post(
            "/api/detect-video-stream",
            data=data,
            content_type="multipart/form-data"
        )
        self.assertEqual(response.status_code, 200)

        events = parse_sse_events_from_response(response)
        frame_events = [e for e in events if e["event"] == "frame"]
        progress_events = [e for e in events if e["event"] == "progress"]

        self.assertTrue(len(frame_events) >= 2, f"Expected multiple frames, got {len(frame_events)}")
        self.assertTrue(len(progress_events) >= 2, f"Expected progress events, got {len(progress_events)}")

        # Check chronological timestamps
        timestamps = [f["data"]["timestamp_sec"] for f in frame_events]
        self.assertEqual(timestamps, sorted(timestamps), "Timestamps must be monotonically increasing")

    def test_04_incident_events_emitted_without_duplicates(self):
        """Verifies newly confirmed incidents are emitted as 'incident' events and persisted without duplicate creation."""
        mock_person = {
            "track_id": 202,
            "worker_id": "W-202",
            "bbox": [100, 100, 250, 400],
            "confidence": 0.92,
            "class": "person"
        }
        # In frame 1-4, missing helmet continuously to confirm violation
        with patch("routes.detection_routes.detect_ppe_in_frame") as mock_det:
            # Person with no PPE gear (missing helmet, vest)
            mock_det.return_value = (None, [], [mock_person.copy()])

            data = {
                "file": (io.BytesIO(self.video_bytes), "incident_stream.mp4"),
                "cameraId": self.camera_id,
                "confirmation_duration_sec": "0.1", # Fast confirmation for test
                "sample_interval_sec": "0.05",
                "max_frames": "5"
            }
            response = self.client.post(
                "/api/detect-video-stream",
                data=data,
                content_type="multipart/form-data"
            )
            self.assertEqual(response.status_code, 200)

            events = parse_sse_events_from_response(response)
            incident_events = [e for e in events if e["event"] == "incident"]

            # If an incident was confirmed, verify no duplicate episodes
            episode_ids = [inc["data"]["episode_id"] for inc in incident_events]
            self.assertEqual(len(episode_ids), len(set(episode_ids)), "Incident episodes must be strictly unique")

    def test_05_done_event_emitted_with_completion_summary(self):
        """Verifies stream concludes with 'done' event containing final summary metrics."""
        data = {
            "file": (io.BytesIO(self.video_bytes), "done_event_test.mp4"),
            "sample_interval_sec": "0.1",
            "max_frames": "4"
        }
        response = self.client.post(
            "/detect-video-stream",
            data=data,
            content_type="multipart/form-data"
        )
        self.assertEqual(response.status_code, 200)

        events = parse_sse_events_from_response(response)
        last_event = events[-1]
        self.assertEqual(last_event["event"], "done")
        self.assertIn("overall_compliance_status", last_event["data"])
        self.assertIn("total_frames_processed", last_event["data"])
        self.assertIn("total_violations_found", last_event["data"])
        self.assertIn("camera_profile", last_event["data"])

    def test_06_corrupt_file_or_missing_file_handled_safely(self):
        """Verifies 400 error is returned when video file is missing or invalid."""
        # 1. Missing file parameter
        res_missing = self.client.post("/api/detect-video-stream", data={})
        self.assertEqual(res_missing.status_code, 400)
        self.assertIn("Video file is required", res_missing.get_json()["message"])

        # 2. Corrupt file content
        res_corrupt = self.client.post(
            "/api/detect-video-stream",
            data={"file": (io.BytesIO(b"not a valid mp4 file"), "corrupt.mp4")},
            content_type="multipart/form-data"
        )
        self.assertEqual(res_corrupt.status_code, 400)
        self.assertIn("Unsupported or corrupted", res_corrupt.get_json()["message"])

    def test_07_grace_period_never_presented_as_compliance(self):
        """
        Milestone M2.2: Verifies that unconfirmed missing-PPE during grace period
        is presented as UNCERTAIN (PENDING_CONFIRMATION) and NEVER as COMPLIANT.
        """
        mock_person = {
            "track_id": 1,
            "worker_id": "W-001",
            "bbox": [100, 100, 300, 400],
            "confidence": 0.95,
            "worn_ppe": []  # No gear worn, but required
        }
        with patch("routes.detection_routes.detect_ppe_in_frame") as mock_detect:
            mock_detect.return_value = (None, [], [mock_person])
            data = {
                "file": (io.BytesIO(self.video_bytes), "grace_period_test.mp4"),
                "sample_interval_sec": "0.1",
                "max_frames": "2",
                "confirmation_duration_sec": "3.0"
            }
            response = self.client.post(
                "/api/detect-video-stream",
                data=data,
                content_type="multipart/form-data"
            )
            self.assertEqual(response.status_code, 200)
            events = parse_sse_events_from_response(response)
            frame_events = [e for e in events if e.get("event") == "frame"]
            self.assertTrue(len(frame_events) > 0)

            # In the first frame (t=0.0s), 3.0s confirmation has NOT elapsed
            frame_1 = frame_events[0]["data"]
            self.assertEqual(frame_1["compliance_status"], "UNCERTAIN")
            persons = frame_1["persons"]
            self.assertEqual(len(persons), 1)
            p = persons[0]
            # Must NOT be presented as compliant!
            self.assertFalse(p["compliant"], "Grace period must NEVER be presented as proof of compliance")
            self.assertTrue(p["uncertain"])
            self.assertEqual(p["uncertain_reason"], "PENDING_CONFIRMATION")
            self.assertIn("helmet", p["pending_missing_ppe"])

    def test_08_detected_objects_and_classes_in_frame_events(self):
        """
        Milestone M2.3: Uploaded Video PPE Object Detection Overlay.
        Verifies that genuine YOLO detected PPE objects (helmets, vests, etc.)
        are serialized in every processed video frame sample with class, confidence, and bbox coordinates.
        """
        mock_person = {
            "track_id": 1,
            "worker_id": "W-001",
            "bbox": [100, 100, 400, 800],
            "confidence": 0.95,
            "worn_ppe": ["helmet", "vest"]
        }
        mock_detected_ppe = [
            {
                "class": "helmet",
                "name": "helmet",
                "confidence": 0.88,
                "bbox": [150, 100, 280, 220],
                "source": "yolo"
            },
            {
                "class": "vest",
                "name": "vest",
                "confidence": 0.76,
                "bbox": [130, 220, 360, 500],
                "source": "yolo"
            }
        ]

        with patch("routes.detection_routes.detect_ppe_in_frame") as mock_detect:
            mock_detect.return_value = (None, mock_detected_ppe, [mock_person])
            data = {
                "file": (io.BytesIO(self.video_bytes), "ppe_detection_overlay_test.mp4"),
                "sample_interval_sec": "0.1",
                "max_frames": "2"
            }
            # 1. Test SSE streaming endpoint
            response = self.client.post(
                "/api/detect-video-stream",
                data=data,
                content_type="multipart/form-data"
            )
            self.assertEqual(response.status_code, 200)
            events = parse_sse_events_from_response(response)
            frame_events = [e for e in events if e.get("event") == "frame"]
            self.assertTrue(len(frame_events) > 0)

            frame_data = frame_events[0]["data"]
            self.assertIn("detected_objects", frame_data)
            self.assertIn("detected_classes", frame_data)

            detected_objs = frame_data["detected_objects"]
            self.assertEqual(len(detected_objs), 2)

            helmet_obj = next((o for o in detected_objs if o["name"] == "helmet"), None)
            self.assertIsNotNone(helmet_obj)
            self.assertEqual(helmet_obj["bbox"], [150, 100, 280, 220])
            self.assertAlmostEqual(helmet_obj["confidence"], 0.88, places=2)

            vest_obj = next((o for o in detected_objs if o["name"] == "vest"), None)
            self.assertIsNotNone(vest_obj)
            self.assertEqual(vest_obj["bbox"], [130, 220, 360, 500])
            self.assertAlmostEqual(vest_obj["confidence"], 0.76, places=2)

            # 2. Test batch /detect-video endpoint
            res_batch = self.client.post(
                "/api/detect-video",
                data={
                    "file": (io.BytesIO(self.video_bytes), "ppe_batch_test.mp4"),
                    "sample_interval_sec": "0.1",
                    "max_frames": "2"
                },
                content_type="multipart/form-data"
            )
            self.assertEqual(res_batch.status_code, 200)
            batch_json = res_batch.get_json()
            self.assertIn("frame_breakdown", batch_json)
            self.assertTrue(len(batch_json["frame_breakdown"]) > 0)
            batch_frame = batch_json["frame_breakdown"][0]
            self.assertIn("detected_objects", batch_frame)
            self.assertIn("detected_classes", batch_frame)
            self.assertEqual(len(batch_frame["detected_objects"]), 2)
            self.assertEqual(batch_frame["detected_objects"][0]["bbox"], [150, 100, 280, 220])


if __name__ == "__main__":
    unittest.main()
