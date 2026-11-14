"""
Automated Unit Tests for Anonymous Worker Tracker (M2.1B)
=========================================================
Tests the 14 mandatory tracking, ambiguity, recovery, and concurrency behaviors.
"""

import unittest
import time
import threading
import numpy as np
import os
import sys

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_engine.tracker import (
    LightweightIoUTracker,
    Track,
    TrackState,
    SessionTrackerManager,
    get_session_tracker,
    reset_session_tracker,
    cleanup_stale_tracker_sessions,
    compute_box_iou,
    compute_box_centroid
)
from config import Config

class TrackerUnitTestSuite(unittest.TestCase):
    def setUp(self):
        self.tracker = LightweightIoUTracker(
            iou_threshold=0.30,
            centroid_threshold=0.15,
            recovery_timeout_sec=3.0,
            ambiguity_margin=0.08
        )

    # -------------------------------------------------------------
    # 1. Single-worker movement preserves ID
    # -------------------------------------------------------------
    def test_01_single_worker_movement_preserves_id(self):
        t = 0.0
        worker_ids = []
        for i in range(10):
            # Worker moves 12 pixels right per frame
            bbox = [100 + i * 12, 100, 180 + i * 12, 300]
            dets = [{"bbox": bbox, "confidence": 0.88}]
            res = self.tracker.update(dets, t, img_shape=(720, 1280))
            self.assertEqual(len(res), 1)
            worker_ids.append(res[0]["worker_id"])
            t += 0.1

        # Must maintain W-001 throughout all 10 frames
        self.assertTrue(all(wid == "W-001" for wid in worker_ids))
        self.assertEqual(len(set(worker_ids)), 1)

    # -------------------------------------------------------------
    # 2. Two independent workers preserve their IDs
    # -------------------------------------------------------------
    def test_02_two_independent_workers_preserve_ids(self):
        t = 0.0
        for i in range(10):
            dets = [
                {"bbox": [50 + i * 8, 100, 130 + i * 8, 300], "confidence": 0.85},
                {"bbox": [500 - i * 8, 120, 580 - i * 8, 320], "confidence": 0.90}
            ]
            res = self.tracker.update(dets, t, img_shape=(720, 1280))
            self.assertEqual(len(res), 2)
            assigned_ids = set(r["worker_id"] for r in res)
            self.assertEqual(assigned_ids, {"W-001", "W-002"})
            t += 0.1

    # -------------------------------------------------------------
    # 3. Crossing paths with distinct trajectories
    # -------------------------------------------------------------
    def test_03_crossing_paths_preserves_identities(self):
        t = 0.0
        # W1 moves left-to-right (100 -> 320)
        # W2 moves right-to-left (320 -> 100)
        # Crossing occurs around frame 5-6
        for i in range(12):
            x1 = 100 + i * 20
            x2 = 340 - i * 20
            dets = [
                {"bbox": [x1, 100, x1 + 70, 300], "confidence": 0.90},
                {"bbox": [x2, 100, x2 + 70, 300], "confidence": 0.88}
            ]
            res = self.tracker.update(dets, t, img_shape=(720, 1280))
            self.assertEqual(len(res), 2)
            t += 0.1

        # At the end, W-001 should be on the right (x > 250) and W-002 on the left (x < 180)
        final_map = {r["worker_id"]: r["bbox"][0] for r in res}
        self.assertIn("W-001", final_map)
        self.assertIn("W-002", final_map)
        self.assertGreater(final_map["W-001"], 250)
        self.assertLess(final_map["W-002"], 180)

    # -------------------------------------------------------------
    # 4. Brief occlusion recovers the same ID
    # -------------------------------------------------------------
    def test_04_brief_occlusion_recovers_same_id(self):
        t = 0.0
        # Seen for 5 frames
        for i in range(5):
            self.tracker.update([{"bbox": [200, 150, 280, 350], "confidence": 0.90}], t)
            t += 0.1

        # Occluded for 1.5 seconds (under 3.0s timeout)
        t += 1.5
        for _ in range(3):
            res_empty = self.tracker.update([], t)
            self.assertEqual(len(res_empty), 0)
            t += 0.1

        # Reappears slightly shifted
        res_reappear = self.tracker.update([{"bbox": [220, 150, 300, 350], "confidence": 0.85}], t)
        self.assertEqual(len(res_reappear), 1)
        # Must recover original W-001 identity
        self.assertEqual(res_reappear[0]["worker_id"], "W-001")

    # -------------------------------------------------------------
    # 5. Reappearance after > 3 seconds receives a new ID
    # -------------------------------------------------------------
    def test_05_reappearance_after_timeout_receives_new_id(self):
        t = 0.0
        # W-001 appears
        self.tracker.update([{"bbox": [200, 150, 280, 350], "confidence": 0.90}], t)

        # Elapsed time exceeds 3.0s recovery timeout (jump 4.0s)
        t += 4.0
        res_late = self.tracker.update([{"bbox": [205, 150, 285, 350], "confidence": 0.90}], t)
        self.assertEqual(len(res_late), 1)
        # Must receive a brand new ID (W-002), old track must not be revived
        self.assertEqual(res_late[0]["worker_id"], "W-002")

    # -------------------------------------------------------------
    # 6. Exact ambiguous matching does not force an old ID
    # -------------------------------------------------------------
    def test_06_exact_ambiguous_matching_does_not_force_id(self):
        t = 0.0
        # W-001 registered at center
        self.tracker.update([{"bbox": [200, 100, 280, 300], "confidence": 0.90}], t)

        # Disappears for 1 frame
        t += 0.5
        self.tracker.update([], t)

        # Reappears as TWO candidates with EXACT identical IoUs with W-001's last box
        # Candidate 1: left overlap by 30px
        # Candidate 2: right overlap by 30px
        t += 0.2
        exact_tie_dets = [
            {"bbox": [170, 100, 250, 300], "confidence": 0.85},
            {"bbox": [230, 100, 310, 300], "confidence": 0.85}
        ]
        iou1 = compute_box_iou([200, 100, 280, 300], exact_tie_dets[0]["bbox"])
        iou2 = compute_box_iou([200, 100, 280, 300], exact_tie_dets[1]["bbox"])
        self.assertAlmostEqual(iou1, iou2, places=4)

        res = self.tracker.update(exact_tie_dets, t)
        # Ambiguity guard: must NOT force W-001 arbitrarily on a tie
        # Instead, both receive new clean identities (W-002, W-003)
        assigned_ids = [r["worker_id"] for r in res]
        self.assertNotIn("W-001", assigned_ids)
        self.assertEqual(len(assigned_ids), 2)

    # -------------------------------------------------------------
    # 7. Near-tie matching does not force an unreliable identity
    # -------------------------------------------------------------
    def test_07_near_tie_matching_does_not_force_unreliable_id(self):
        t = 0.0
        self.tracker.update([{"bbox": [200, 100, 280, 300], "confidence": 0.90}], t)
        t += 0.5
        self.tracker.update([], t)

        t += 0.2
        # Near tie: difference in IoU is only 0.01 (< ambiguity_margin 0.08)
        near_tie_dets = [
            {"bbox": [180, 100, 260, 300], "confidence": 0.85},
            {"bbox": [182, 100, 262, 300], "confidence": 0.85}
        ]
        res = self.tracker.update(near_tie_dets, t)
        assigned_ids = [r["worker_id"] for r in res]
        # Must decline forced association due to ambiguity
        self.assertNotIn("W-001", assigned_ids)

    # -------------------------------------------------------------
    # 8. New worker entering during occlusion receives new ID
    # -------------------------------------------------------------
    def test_08_new_worker_during_occlusion_receives_new_id(self):
        t = 0.0
        # W-001 at far left
        self.tracker.update([{"bbox": [20, 100, 90, 300], "confidence": 0.90}], t)

        # W-001 temporarily occluded
        t += 1.0
        self.tracker.update([], t)

        # Brand new worker enters at far right (x=600)
        t += 0.5
        res_new = self.tracker.update([{"bbox": [600, 100, 670, 300], "confidence": 0.88}], t)
        self.assertEqual(len(res_new), 1)
        # Must assign W-002, NOT steal lost W-001
        self.assertEqual(res_new[0]["worker_id"], "W-002")

    # -------------------------------------------------------------
    # 9. IDs are never reused within a session
    # -------------------------------------------------------------
    def test_09_ids_are_not_reused_within_session(self):
        t = 0.0
        # Worker 1 appears
        self.tracker.update([{"bbox": [100, 100, 180, 300], "confidence": 0.90}], t)
        self.assertEqual(self.tracker.tracks[0].worker_id, "W-001")

        # Worker 1 expires after 4 seconds
        t += 4.0
        self.tracker.update([], t)
        self.assertEqual(len(self.tracker.tracks), 0)

        # Worker appears again: MUST receive W-002, NEVER W-001
        res = self.tracker.update([{"bbox": [100, 100, 180, 300], "confidence": 0.90}], t)
        self.assertEqual(res[0]["worker_id"], "W-002")

        # Second worker expires
        t += 4.0
        self.tracker.update([], t)

        # Third worker appears: MUST receive W-003
        res3 = self.tracker.update([{"bbox": [100, 100, 180, 300], "confidence": 0.90}], t)
        self.assertEqual(res3[0]["worker_id"], "W-003")

    # -------------------------------------------------------------
    # 10. Independent sessions maintain independent state
    # -------------------------------------------------------------
    def test_10_independent_sessions_maintain_independent_state(self):
        manager = SessionTrackerManager()
        s1 = manager.get_tracker("camera_alpha")
        s2 = manager.get_tracker("camera_beta")

        # Update s1
        r1 = s1.update([{"bbox": [100, 100, 180, 300], "confidence": 0.90}], 0.0)
        # Update s2
        r2 = s2.update([{"bbox": [300, 100, 380, 300], "confidence": 0.85}], 0.0)

        # Both must start at W-001 independently
        self.assertEqual(r1[0]["worker_id"], "W-001")
        self.assertEqual(r2[0]["worker_id"], "W-001")
        self.assertNotEqual(id(s1), id(s2))

    # -------------------------------------------------------------
    # 11. Session reset creates a fresh ID sequence
    # -------------------------------------------------------------
    def test_11_session_reset_creates_fresh_sequence(self):
        manager = SessionTrackerManager()
        tracker = manager.get_tracker("temp_session")
        tracker.update([{"bbox": [100, 100, 180, 300], "confidence": 0.90}], 0.0)
        self.assertEqual(tracker.tracks[0].worker_id, "W-001")

        # Explicit reset
        manager.reset_tracker("temp_session")

        # New call on same session name generates fresh tracker starting at W-001
        fresh_tracker = manager.get_tracker("temp_session")
        res_fresh = fresh_tracker.update([{"bbox": [100, 100, 180, 300], "confidence": 0.90}], 0.0)
        self.assertEqual(res_fresh[0]["worker_id"], "W-001")

    # -------------------------------------------------------------
    # 12. Different frame resolutions produce sensible matching
    # -------------------------------------------------------------
    def test_12_scale_invariant_centroid_thresholds(self):
        # 640x480 resolution (diag = 800)
        tracker_vga = LightweightIoUTracker(centroid_threshold=0.15)
        # 1280x720 resolution (diag ≈ 1468.6)
        tracker_hd = LightweightIoUTracker(centroid_threshold=0.15)

        # Worker moves by 8% of frame diagonal in both cases
        # VGA: 0.08 * 800 = 64px
        tracker_vga.update([{"bbox": [100, 100, 180, 300], "confidence": 0.90}], 0.0, img_shape=(480, 640))
        tracker_vga.update([], 1.0, img_shape=(480, 640)) # occluded
        res_vga = tracker_vga.update([{"bbox": [164, 100, 244, 300], "confidence": 0.85}], 1.5, img_shape=(480, 640))
        self.assertEqual(res_vga[0]["worker_id"], "W-001")

        # HD: 0.08 * 1468.6 ≈ 117.5px
        tracker_hd.update([{"bbox": [200, 200, 360, 600], "confidence": 0.90}], 0.0, img_shape=(720, 1280))
        tracker_hd.update([], 1.0, img_shape=(720, 1280)) # occluded
        res_hd = tracker_hd.update([{"bbox": [318, 200, 478, 600], "confidence": 0.85}], 1.5, img_shape=(720, 1280))
        self.assertEqual(res_hd[0]["worker_id"], "W-001")

    # -------------------------------------------------------------
    # 13. Timestamp reset is handled safely
    # -------------------------------------------------------------
    def test_13_timestamp_reset_handled_safely(self):
        # Normal progression up to t = 20.0s
        self.tracker.update([{"bbox": [100, 100, 180, 300], "confidence": 0.90}], 20.0)
        self.assertEqual(self.tracker.tracks[0].worker_id, "W-001")

        # Timestamp suddenly loops backwards to t = 1.0s (e.g. video loop)
        try:
            res = self.tracker.update([{"bbox": [105, 100, 185, 300], "confidence": 0.90}], 1.0)
            self.assertEqual(len(res), 1)
            # Must handle safely without throwing exceptions or crashing
            self.assertEqual(res[0]["worker_id"], "W-001")
        except Exception as e:
            self.fail(f"Timestamp reset caused crash: {e}")

    # -------------------------------------------------------------
    # 14. Concurrent updates cannot corrupt session state
    # -------------------------------------------------------------
    def test_14_concurrent_updates_thread_safety(self):
        manager = SessionTrackerManager()
        errors = []

        def worker_task(thread_id):
            try:
                for i in range(25):
                    session_key = f"cam_{thread_id % 3}"
                    t = manager.get_tracker(session_key)
                    x = 100 + (i * 5)
                    t.update([{"bbox": [x, 100, x + 80, 300], "confidence": 0.85}], i * 0.1)
                    time.sleep(0.001)
                    if i % 10 == 0:
                        manager.cleanup_stale_sessions(ttl_seconds=100.0)
            except Exception as ex:
                errors.append(ex)

        threads = [threading.Thread(target=worker_task, args=(tid,)) for tid in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        self.assertEqual(len(errors), 0, f"Concurrent tracker update raised errors: {errors}")
        self.assertLessEqual(manager.active_session_count(), 3)

if __name__ == "__main__":
    unittest.main()
