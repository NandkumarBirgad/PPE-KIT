import unittest
import time
import math
from ai_engine.zone_assignment import (
    compute_worker_bottom_center_anchor,
    is_point_on_segment,
    is_point_on_polygon_boundary,
    is_point_in_polygon_ray_casting,
    evaluate_single_frame_zone,
    TrackSpatialState,
    SessionSpatialZoneResolver,
    get_session_spatial_resolver,
    reset_session_spatial_zones,
    purge_expired_spatial_sessions,
    assign_persons_spatial_zones
)

class TestSpatialZoneAssignment(unittest.TestCase):
    def setUp(self):
        reset_session_spatial_zones("test_session_1")
        reset_session_spatial_zones("test_session_2")
        reset_session_spatial_zones("test_session_iso")

    # =========================================================================
    # 1. Anchor Point & Normalization Tests
    # =========================================================================

    def test_bottom_center_anchor_calculation(self):
        # Box from (100, 100) to (200, 300) in 1000x1000 frame
        # anchor_x = (100 + 200) / 2 = 150
        # anchor_y = 100 + 0.95 * (300 - 100) = 100 + 190 = 290
        bbox = [100, 100, 200, 300]
        norm_x, norm_y = compute_worker_bottom_center_anchor(bbox, (1000, 1000))
        self.assertAlmostEqual(norm_x, 0.15, places=5)
        self.assertAlmostEqual(norm_y, 0.29, places=5)

    def test_normalization_across_resolutions(self):
        # 480p: 640 x 480. Box: [64, 48, 128, 144] (10% to 20% width, 10% to 30% height)
        # 720p: 1280 x 720. Box: [128, 72, 256, 216]
        # 1080p: 1920 x 1080. Box: [192, 108, 384, 324]
        res_480 = compute_worker_bottom_center_anchor([64, 48, 128, 144], (480, 640))
        res_720 = compute_worker_bottom_center_anchor([128, 72, 256, 216], (720, 1280))
        res_1080 = compute_worker_bottom_center_anchor([192, 108, 384, 324], (1080, 1920))

        self.assertAlmostEqual(res_480[0], res_720[0], places=4)
        self.assertAlmostEqual(res_720[0], res_1080[0], places=4)
        self.assertAlmostEqual(res_480[1], res_720[1], places=4)
        self.assertAlmostEqual(res_720[1], res_1080[1], places=4)

    # =========================================================================
    # 2. Point-in-Polygon & Boundary Tests
    # =========================================================================

    def test_inside_and_outside_polygon_points(self):
        # Square: (0.2, 0.2) to (0.6, 0.6)
        square = [(0.2, 0.2), (0.6, 0.2), (0.6, 0.6), (0.2, 0.6)]

        # Center: (0.4, 0.4) -> Inside
        self.assertTrue(is_point_in_polygon_ray_casting(0.4, 0.4, square))

        # Outside points
        self.assertFalse(is_point_in_polygon_ray_casting(0.1, 0.4, square)) # Left
        self.assertFalse(is_point_in_polygon_ray_casting(0.7, 0.4, square)) # Right
        self.assertFalse(is_point_in_polygon_ray_casting(0.4, 0.1, square)) # Above
        self.assertFalse(is_point_in_polygon_ray_casting(0.4, 0.7, square)) # Below

    def test_concave_polygon_assignment(self):
        # L-shaped polygon
        # (0.1, 0.1) -> (0.9, 0.1) -> (0.9, 0.5) -> (0.5, 0.5) -> (0.5, 0.9) -> (0.1, 0.9)
        l_poly = [(0.1, 0.1), (0.9, 0.1), (0.9, 0.5), (0.5, 0.5), (0.5, 0.9), (0.1, 0.9)]

        # Inside upper horizontal leg: (0.7, 0.3)
        self.assertTrue(is_point_in_polygon_ray_casting(0.7, 0.3, l_poly))

        # Inside lower vertical leg: (0.3, 0.7)
        self.assertTrue(is_point_in_polygon_ray_casting(0.3, 0.7, l_poly))

        # Cut-out empty corner (outside): (0.7, 0.7)
        self.assertFalse(is_point_in_polygon_ray_casting(0.7, 0.7, l_poly))

    def test_boundary_detection_returns_uncertain(self):
        square = [{"x": 0.2, "y": 0.2}, {"x": 0.6, "y": 0.2}, {"x": 0.6, "y": 0.6}, {"x": 0.2, "y": 0.6}]
        zones = [{"zoneId": "z1", "zoneName": "Zone 1", "polygon": square, "priority": 1}]

        # Point exactly on top edge: (0.4, 0.2)
        status, zid, zname, exp = evaluate_single_frame_zone(0.4, 0.2, zones, boundary_eps=1e-5)
        self.assertEqual(status, "UNCERTAIN")
        self.assertIn("boundary", exp)

    # =========================================================================
    # 3. Overlapping Zones & Priority Resolution
    # =========================================================================

    def test_different_priority_overlapping_polygons(self):
        # Zone A: priority 1
        zone_a = {
            "zoneId": "zA", "zoneName": "General Assembly",
            "polygon": [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1}, {"x": 0.9, "y": 0.9}, {"x": 0.1, "y": 0.9}],
            "priority": 1
        }
        # Zone B (nested hazard area): priority 5
        zone_b = {
            "zoneId": "zB", "zoneName": "Crane Hazard Sub-Zone",
            "polygon": [{"x": 0.3, "y": 0.3}, {"x": 0.7, "y": 0.3}, {"x": 0.7, "y": 0.7}, {"x": 0.3, "y": 0.7}],
            "priority": 5
        }

        # Point inside both (0.5, 0.5): Zone B has higher priority (5 > 1)
        status, zid, zname, _ = evaluate_single_frame_zone(0.5, 0.5, [zone_a, zone_b])
        self.assertEqual(status, "ASSIGNED")
        self.assertEqual(zid, "zB")
        self.assertEqual(zname, "Crane Hazard Sub-Zone")

        # Point inside Zone A only (0.2, 0.2): Zone A selected
        status_a, zid_a, _, _ = evaluate_single_frame_zone(0.2, 0.2, [zone_a, zone_b])
        self.assertEqual(status_a, "ASSIGNED")
        self.assertEqual(zid_a, "zA")

    def test_equal_priority_overlap_returns_uncertain(self):
        # Two zones overlapping with equal priority = 2
        zone_1 = {
            "zoneId": "z1", "zoneName": "Zone One",
            "polygon": [{"x": 0.1, "y": 0.1}, {"x": 0.6, "y": 0.1}, {"x": 0.6, "y": 0.6}, {"x": 0.1, "y": 0.6}],
            "priority": 2
        }
        zone_2 = {
            "zoneId": "z2", "zoneName": "Zone Two",
            "polygon": [{"x": 0.4, "y": 0.4}, {"x": 0.9, "y": 0.4}, {"x": 0.9, "y": 0.9}, {"x": 0.4, "y": 0.9}],
            "priority": 2
        }

        # Point in intersection (0.5, 0.5): must return UNCERTAIN
        status, zid, zname, exp = evaluate_single_frame_zone(0.5, 0.5, [zone_1, zone_2])
        self.assertEqual(status, "UNCERTAIN")
        self.assertIn("equal priority", exp)

    def test_unassigned_worker_outside_all_polygons(self):
        zone_1 = {
            "zoneId": "z1", "zoneName": "Zone One",
            "polygon": [{"x": 0.1, "y": 0.1}, {"x": 0.4, "y": 0.1}, {"x": 0.4, "y": 0.4}, {"x": 0.1, "y": 0.4}],
            "priority": 1
        }
        # Point at (0.8, 0.8) is outside
        status, zid, zname, exp = evaluate_single_frame_zone(0.8, 0.8, [zone_1])
        self.assertEqual(status, "UNASSIGNED")
        self.assertIsNone(zid)
        self.assertIsNone(zname)
        self.assertIn("Outside", exp)

    # =========================================================================
    # 4. Temporal Assignment Stabilization & Debouncing
    # =========================================================================

    def test_three_observation_transition_stabilization(self):
        state = TrackSpatialState(track_id=1)

        # Initial state: UNASSIGNED
        self.assertEqual(state.committed_status, "UNASSIGNED")

        # Frame 1: Candidate Zone A
        st1, zid1, _, _ = state.update("ASSIGNED", "zA", "Zone A", debounce_frames=3)
        self.assertEqual(st1, "UNASSIGNED") # Preserving unassigned
        self.assertIsNone(zid1)
        self.assertEqual(state.consecutive_observations, 1)

        # Frame 2: Candidate Zone A
        st2, zid2, _, _ = state.update("ASSIGNED", "zA", "Zone A", debounce_frames=3)
        self.assertEqual(st2, "UNASSIGNED") # Still preserving unassigned
        self.assertEqual(state.consecutive_observations, 2)

        # Frame 3: Candidate Zone A (threshold reached!)
        st3, zid3, zname3, exp3 = state.update("ASSIGNED", "zA", "Zone A", debounce_frames=3)
        self.assertEqual(st3, "ASSIGNED")
        self.assertEqual(zid3, "zA")
        self.assertEqual(zname3, "Zone A")
        self.assertIn("Committed transition", exp3)
        self.assertEqual(state.committed_status, "ASSIGNED")

        # Frame 4: Candidate Zone B (transient fluctuation)
        st4, zid4, zname4, exp4 = state.update("ASSIGNED", "zB", "Zone B", debounce_frames=3)
        self.assertEqual(st4, "ASSIGNED") # Preserves Zone A!
        self.assertEqual(zid4, "zA")
        self.assertEqual(zname4, "Zone A")
        self.assertIn("Preserving Zone A", exp4)

        # Frame 5: Candidate Zone B
        st5, zid5, _, _ = state.update("ASSIGNED", "zB", "Zone B", debounce_frames=3)
        self.assertEqual(zid5, "zA") # Still Zone A

        # Frame 6: Candidate Zone B (3rd observation of Zone B: transition commits!)
        st6, zid6, zname6, _ = state.update("ASSIGNED", "zB", "Zone B", debounce_frames=3)
        self.assertEqual(st6, "ASSIGNED")
        self.assertEqual(zid6, "zB")
        self.assertEqual(zname6, "Zone B")

    def test_candidate_changes_reset_observation_counter(self):
        state = TrackSpatialState(track_id=2)
        state.update("ASSIGNED", "zA", "Zone A", debounce_frames=3)
        state.update("ASSIGNED", "zA", "Zone A", debounce_frames=3)
        state.update("ASSIGNED", "zA", "Zone A", debounce_frames=3)
        self.assertEqual(state.committed_zone_id, "zA")

        # Frame 1: Candidate Zone B
        state.update("ASSIGNED", "zB", "Zone B", debounce_frames=3)
        self.assertEqual(state.consecutive_observations, 1)

        # Frame 2: Candidate Zone B
        state.update("ASSIGNED", "zB", "Zone B", debounce_frames=3)
        self.assertEqual(state.consecutive_observations, 2)

        # Frame 3: Fluctuation to Zone C! Counter must reset to 1 for Zone C
        _, zid, _, _ = state.update("ASSIGNED", "zC", "Zone C", debounce_frames=3)
        self.assertEqual(zid, "zA") # Preserves Zone A
        self.assertEqual(state.pending_candidate_id, "zC")
        self.assertEqual(state.consecutive_observations, 1)

    def test_ambiguous_observation_exposes_uncertainty(self):
        state = TrackSpatialState(track_id=3)
        # Establish committed Zone A
        for _ in range(3):
            state.update("ASSIGNED", "zA", "Zone A", debounce_frames=3)
        self.assertEqual(state.committed_zone_id, "zA")

        # Worker lands on a boundary: candidate status is UNCERTAIN
        st, zid, zname, exp = state.update("UNCERTAIN", None, None, debounce_frames=3)
        self.assertEqual(st, "UNCERTAIN")
        self.assertIn("ambiguous", exp)

    # =========================================================================
    # 5. Session & Track Isolation
    # =========================================================================

    def test_session_isolation(self):
        res1 = get_session_spatial_resolver("session_alpha", debounce_frames=3)
        res2 = get_session_spatial_resolver("session_beta", debounce_frames=3)

        # Establish track 1 in session_alpha as Zone A
        for _ in range(3):
            res1.resolve_track(1, "ASSIGNED", "zA", "Zone A")

        # Establish track 1 in session_beta as Zone B
        for _ in range(3):
            res2.resolve_track(1, "ASSIGNED", "zB", "Zone B")

        # Verify completely independent states
        st1, zid1, _, _ = res1.resolve_track(1, "ASSIGNED", "zA", "Zone A")
        st2, zid2, _, _ = res2.resolve_track(1, "ASSIGNED", "zB", "Zone B")

        self.assertEqual(zid1, "zA")
        self.assertEqual(zid2, "zB")

    def test_track_isolation_within_session(self):
        res = get_session_spatial_resolver("session_multi", debounce_frames=3)

        for _ in range(3):
            res.resolve_track(10, "ASSIGNED", "z10", "Zone 10")
            res.resolve_track(20, "ASSIGNED", "z20", "Zone 20")

        _, zid10, _, _ = res.resolve_track(10, "ASSIGNED", "z10", "Zone 10")
        _, zid20, _, _ = res.resolve_track(20, "ASSIGNED", "z20", "Zone 20")

        self.assertEqual(zid10, "z10")
        self.assertEqual(zid20, "z20")

    def test_session_reset_and_purge(self):
        res = get_session_spatial_resolver("session_to_clear")
        for _ in range(3):
            res.resolve_track(1, "ASSIGNED", "zA", "Zone A")
        self.assertEqual(res.track_count(), 1)

        reset_session_spatial_zones("session_to_clear")
        self.assertEqual(res.track_count(), 0)

        # Test purge with synthetic past timestamp
        res_stale = get_session_spatial_resolver("session_stale")
        res_stale.last_accessed = time.monotonic() - 400.0 # 400s ago

        purged_count = purge_expired_spatial_sessions(max_age_sec=300.0)
        self.assertGreaterEqual(purged_count, 1)

    # =========================================================================
    # 6. High-level Batch Resolver & Legacy Camera Behavior
    # =========================================================================

    def test_legacy_camera_retains_camera_level_zone(self):
        legacy_cam = {
            "_id": "cam_legacy",
            "zoneId": "zone_default",
            "zoneName": "Default Factory Zone",
            "zones": [] # No polygon mappings
        }
        persons = [
            {"bbox": [100, 100, 200, 300], "track_id": 1},
            {"bbox": [400, 400, 500, 600], "track_id": 2}
        ]

        resolved = assign_persons_spatial_zones(
            persons, legacy_cam, img_shape=(1080, 1920), session_id="test_legacy"
        )
        self.assertEqual(len(resolved), 2)
        for p in resolved:
            self.assertEqual(p["zone_id"], "zone_default")
            self.assertEqual(p["zone_name"], "Default Factory Zone")
            self.assertEqual(p["zone_assignment_status"], "ASSIGNED")
            self.assertIn("Camera-level default zone", p["zone_assignment_confidence"])
            self.assertIn("zone_anchor", p)

    def test_batch_resolver_with_polygons(self):
        cam_with_poly = {
            "_id": "cam_poly",
            "zones": [
                {
                    "zoneId": "z_left", "zoneName": "Left Deck",
                    "polygon": [{"x": 0.0, "y": 0.0}, {"x": 0.5, "y": 0.0}, {"x": 0.5, "y": 1.0}, {"x": 0.0, "y": 1.0}],
                    "priority": 1
                },
                {
                    "zoneId": "z_right", "zoneName": "Right Deck",
                    "polygon": [{"x": 0.5, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 1.0, "y": 1.0}, {"x": 0.5, "y": 1.0}],
                    "priority": 1
                }
            ]
        }
        # Worker 1 on Left: box center x=0.25
        # Worker 2 on Right: box center x=0.75
        persons = [
            {"bbox": [200, 200, 300, 400], "track_id": 1}, # in 1000x1000 -> x in [0.2, 0.3], center 0.25
            {"bbox": [700, 200, 800, 400], "track_id": 2}  # in 1000x1000 -> x in [0.7, 0.8], center 0.75
        ]

        # Feed 3 times to commit
        for _ in range(3):
            resolved = assign_persons_spatial_zones(
                persons, cam_with_poly, img_shape=(1000, 1000), session_id="test_batch"
            )

        self.assertEqual(resolved[0]["zone_id"], "z_left")
        self.assertEqual(resolved[0]["zone_assignment_status"], "ASSIGNED")
        self.assertEqual(resolved[1]["zone_id"], "z_right")
        self.assertEqual(resolved[1]["zone_assignment_status"], "ASSIGNED")

    # =========================================================================
    # 7. Benchmark: 10 Workers x 5 Zones x 8 Vertices across 1,000 Frames
    # =========================================================================

    def test_spatial_resolution_benchmark(self):
        # Construct 5 synthetic 8-vertex zones
        synthetic_zones = []
        for z_idx in range(5):
            cx = 0.2 * z_idx + 0.1
            cy = 0.5
            r = 0.08
            vertices = []
            for v_idx in range(8):
                angle = 2.0 * 3.1415926535 * v_idx / 8.0
                vx = cx + r * math.cos(angle)
                vy = cy + r * math.sin(angle)
                vertices.append({"x": round(vx, 4), "y": round(vy, 4)})
            synthetic_zones.append({
                "zoneId": f"bench_zone_{z_idx}",
                "zoneName": f"Bench Zone {z_idx}",
                "polygon": vertices,
                "priority": z_idx + 1
            })

        cam_doc = {"_id": "cam_bench", "zones": synthetic_zones}

        # Construct 10 workers at various positions
        synthetic_workers = []
        for w_idx in range(10):
            x1 = 100 * w_idx + 50
            synthetic_workers.append({
                "bbox": [x1, 300, x1 + 60, 500],
                "track_id": w_idx + 1
            })

        frames = 1000
        start_t = time.perf_counter()
        for f in range(frames):
            assign_persons_spatial_zones(
                synthetic_workers, cam_doc, img_shape=(1080, 1920), session_id="benchmark_session"
            )
        duration_sec = time.perf_counter() - start_t

        ms_per_frame = (duration_sec / frames) * 1000.0
        fps_throughput = frames / duration_sec

        print(f"\n[BENCHMARK] 10 workers x 5 zones x 8 vertices across {frames} frames:")
        print(f"Total time: {duration_sec:.4f}s | Latency per frame: {ms_per_frame:.4f}ms | Throughput: {fps_throughput:.1f} FPS")

        # Enforce that 1 frame takes less than 5ms on CPU (leaving 95ms+ for YOLO at 10 FPS)
        self.assertLess(ms_per_frame, 5.0)

if __name__ == "__main__":
    unittest.main()
