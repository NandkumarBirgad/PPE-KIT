import unittest
import json
from unittest.mock import patch, MagicMock
from app import create_app
from database import mem_cameras, mem_zones, is_mongo_connected
from auth import generate_token
from ai_engine.zone_geometry import (
    validate_polygon_vertices,
    validate_camera_zone_mappings,
    compute_polygon_area,
    segments_intersect
)

class TestCameraPolygonValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

        # Generate tokens
        cls.admin_token = generate_token("admin_test", "SUPER_ADMIN", "admin@ppe.com")
        cls.supervisor_token = generate_token("sup_test", "ZONE_SUPERVISOR", "supervisor@ppe.com")

    def setUp(self):
        self._orig_mem_cameras = list(mem_cameras)
        self._orig_mem_zones = list(mem_zones)
        # Ensure a known zone exists in mem_zones
        self.zone_id = "zone_01"
        self.zone_02 = "zone_02"
        if not any(str(z.get("_id")) == self.zone_id for z in mem_zones):
            mem_zones.append({
                "_id": self.zone_id,
                "name": "Heavy Assembly Bay 01",
                "code": "BAY-01",
                "requiredPPE": ["helmet", "vest"]
            })
        if not any(str(z.get("_id")) == self.zone_02 for z in mem_zones):
            mem_zones.append({
                "_id": self.zone_02,
                "name": "Chemical Line",
                "code": "CHEM-02",
                "requiredPPE": ["goggles", "mask"]
            })

    def tearDown(self):
        mem_cameras.clear()
        mem_cameras.extend(self._orig_mem_cameras)
        mem_zones.clear()
        mem_zones.extend(self._orig_mem_zones)

    # =========================================================================
    # 1. Pure Geometry & Polygon Validation Unit Tests
    # =========================================================================

    def test_valid_convex_polygon(self):
        # Standard rectangle
        poly = [
            {"x": 0.1, "y": 0.1},
            {"x": 0.8, "y": 0.1},
            {"x": 0.8, "y": 0.8},
            {"x": 0.1, "y": 0.8}
        ]
        valid, err, norm = validate_polygon_vertices(poly)
        self.assertTrue(valid)
        self.assertIsNone(err)
        self.assertEqual(len(norm), 4)
        area = compute_polygon_area([(p["x"], p["y"]) for p in norm])
        self.assertAlmostEqual(area, 0.49, places=2)

    def test_valid_concave_polygon(self):
        # Non-convex chevron / L-shape
        poly = [
            {"x": 0.1, "y": 0.1},
            {"x": 0.9, "y": 0.1},
            {"x": 0.9, "y": 0.4},
            {"x": 0.4, "y": 0.4},
            {"x": 0.4, "y": 0.9},
            {"x": 0.1, "y": 0.9}
        ]
        valid, err, norm = validate_polygon_vertices(poly)
        self.assertTrue(valid)
        self.assertIsNone(err)
        self.assertEqual(len(norm), 6)

    def test_triangle_polygon(self):
        # Minimal 3 vertices
        poly = [
            {"x": 0.0, "y": 0.0},
            {"x": 1.0, "y": 0.0},
            {"x": 0.5, "y": 1.0}
        ]
        valid, err, norm = validate_polygon_vertices(poly)
        self.assertTrue(valid)
        self.assertEqual(len(norm), 3)

    def test_too_few_vertices(self):
        # 2 vertices
        poly = [{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.5}]
        valid, err, norm = validate_polygon_vertices(poly)
        self.assertFalse(valid)
        self.assertIn("at least 3 distinct vertices", err)

        # 0 vertices
        valid, err, _ = validate_polygon_vertices([])
        self.assertFalse(valid)

    def test_duplicate_consecutive_vertices(self):
        poly = [
            {"x": 0.1, "y": 0.1},
            {"x": 0.1, "y": 0.1}, # Duplicate
            {"x": 0.8, "y": 0.8},
            {"x": 0.1, "y": 0.8}
        ]
        valid, err, _ = validate_polygon_vertices(poly)
        self.assertFalse(valid)
        self.assertIn("duplicate consecutive vertices", err)

    def test_zero_length_closing_edge(self):
        # Last vertex equals first vertex
        poly = [
            {"x": 0.1, "y": 0.1},
            {"x": 0.8, "y": 0.1},
            {"x": 0.8, "y": 0.8},
            {"x": 0.1, "y": 0.1}
        ]
        valid, err, _ = validate_polygon_vertices(poly)
        self.assertFalse(valid)
        self.assertIn("zero length", err)

    def test_out_of_range_coordinates(self):
        # x < 0
        poly = [{"x": -0.1, "y": 0.1}, {"x": 0.8, "y": 0.1}, {"x": 0.8, "y": 0.8}]
        valid, err, _ = validate_polygon_vertices(poly)
        self.assertFalse(valid)
        self.assertIn("out of bounds", err)

        # y > 1
        poly = [{"x": 0.1, "y": 0.1}, {"x": 0.8, "y": 0.1}, {"x": 0.8, "y": 1.05}]
        valid, err, _ = validate_polygon_vertices(poly)
        self.assertFalse(valid)
        self.assertIn("out of bounds", err)

    def test_nan_and_infinite_coordinates(self):
        poly_nan = [{"x": float('nan'), "y": 0.5}, {"x": 0.8, "y": 0.1}, {"x": 0.8, "y": 0.8}]
        valid, err, _ = validate_polygon_vertices(poly_nan)
        self.assertFalse(valid)
        self.assertIn("NaN or infinite", err)

        poly_inf = [{"x": 0.1, "y": float('inf')}, {"x": 0.8, "y": 0.1}, {"x": 0.8, "y": 0.8}]
        valid, err, _ = validate_polygon_vertices(poly_inf)
        self.assertFalse(valid)
        self.assertIn("NaN or infinite", err)

    def test_boolean_coordinates_rejected(self):
        poly = [{"x": True, "y": 0.5}, {"x": 0.8, "y": 0.1}, {"x": 0.8, "y": 0.8}]
        valid, err, _ = validate_polygon_vertices(poly)
        self.assertFalse(valid)
        self.assertIn("cannot be boolean", err)

    def test_zero_area_collinear_polygon(self):
        # 3 collinear points
        poly = [
            {"x": 0.1, "y": 0.1},
            {"x": 0.5, "y": 0.5},
            {"x": 0.9, "y": 0.9}
        ]
        valid, err, _ = validate_polygon_vertices(poly)
        self.assertFalse(valid)
        self.assertIn("zero or degenerate area", err)

    def test_self_intersecting_bowtie_polygon(self):
        # Classic self-intersecting hourglass
        poly = [
            {"x": 0.1, "y": 0.1},
            {"x": 0.9, "y": 0.9},
            {"x": 0.1, "y": 0.9},
            {"x": 0.9, "y": 0.1}
        ]
        valid, err, _ = validate_polygon_vertices(poly)
        self.assertFalse(valid)
        self.assertIn("self-intersecting", err)

    # =========================================================================
    # 2. Camera Zone Mappings Validation
    # =========================================================================

    def test_valid_camera_zone_mappings(self):
        mappings = [
            {
                "zoneId": "zone_01",
                "polygon": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 0.5, "y": 0.0},
                    {"x": 0.5, "y": 0.5},
                    {"x": 0.0, "y": 0.5}
                ],
                "priority": 1
            },
            {
                "zoneId": "zone_02",
                "polygon": [
                    {"x": 0.5, "y": 0.5},
                    {"x": 1.0, "y": 0.5},
                    {"x": 1.0, "y": 1.0},
                    {"x": 0.5, "y": 1.0}
                ],
                "priority": 2
            }
        ]
        valid, err, validated = validate_camera_zone_mappings(mappings)
        self.assertTrue(valid)
        self.assertIsNone(err)
        self.assertEqual(len(validated), 2)
        self.assertEqual(validated[0]["zoneId"], "zone_01")
        self.assertEqual(validated[1]["priority"], 2)

    def test_unknown_zone_id_rejected(self):
        mappings = [
            {
                "zoneId": "non_existent_zone_99999",
                "polygon": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 0.5, "y": 0.0},
                    {"x": 0.5, "y": 0.5}
                ]
            }
        ]
        valid, err, _ = validate_camera_zone_mappings(mappings)
        self.assertFalse(valid)
        self.assertIn("Referenced zoneId 'non_existent_zone_99999' does not exist", err)

    def test_duplicate_zone_mapping_rejected(self):
        mappings = [
            {
                "zoneId": "zone_01",
                "polygon": [{"x": 0.0, "y": 0.0}, {"x": 0.4, "y": 0.0}, {"x": 0.4, "y": 0.4}]
            },
            {
                "zoneId": "zone_01", # Duplicate zoneId
                "polygon": [{"x": 0.5, "y": 0.5}, {"x": 0.9, "y": 0.5}, {"x": 0.9, "y": 0.9}]
            }
        ]
        valid, err, _ = validate_camera_zone_mappings(mappings)
        self.assertFalse(valid)
        self.assertIn("Duplicate zone mapping for zoneId 'zone_01'", err)

    def test_invalid_priority_rejected(self):
        mappings = [
            {
                "zoneId": "zone_01",
                "polygon": [{"x": 0.0, "y": 0.0}, {"x": 0.4, "y": 0.0}, {"x": 0.4, "y": 0.4}],
                "priority": -5
            }
        ]
        valid, err, _ = validate_camera_zone_mappings(mappings)
        self.assertFalse(valid)
        self.assertIn("non-negative integer", err)

    # =========================================================================
    # 3. HTTP API Endpoints & RBAC Authorization Tests
    # =========================================================================

    def test_create_camera_with_valid_polygons_admin(self):
        payload = {
            "name": "Polygon Test Cam Admin",
            "zoneId": "zone_01",
            "zones": [
                {
                    "zoneId": "zone_01",
                    "polygon": [
                        {"x": 0.1, "y": 0.1},
                        {"x": 0.6, "y": 0.1},
                        {"x": 0.6, "y": 0.6},
                        {"x": 0.1, "y": 0.6}
                    ],
                    "priority": 1
                }
            ]
        }
        res = self.client.post(
            "/api/cameras",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json=payload
        )
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data["name"], "Polygon Test Cam Admin")
        self.assertIn("zones", data)
        self.assertEqual(len(data["zones"]), 1)
        self.assertEqual(data["zones"][0]["zoneId"], "zone_01")
        self.assertEqual(len(data["zones"][0]["polygon"]), 4)

    def test_create_camera_with_invalid_polygons_returns_400(self):
        payload = {
            "name": "Invalid Poly Cam",
            "zoneId": "zone_01",
            "zones": [
                {
                    "zoneId": "zone_01",
                    "polygon": [{"x": 0.1, "y": 0.1}, {"x": 0.2, "y": 0.2}] # Only 2 vertices
                }
            ]
        }
        res = self.client.post(
            "/api/cameras",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json=payload
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("at least 3 distinct vertices", data["message"])

    def test_supervisor_forbidden_to_create_or_update_camera(self):
        # Create attempt by supervisor
        payload = {"name": "Supervisor Hack Cam", "zoneId": "zone_01"}
        res = self.client.post(
            "/api/cameras",
            headers={"Authorization": f"Bearer {self.supervisor_token}"},
            json=payload
        )
        self.assertEqual(res.status_code, 403)

        # Update attempt by supervisor
        res2 = self.client.patch(
            "/api/cameras/cam_01",
            headers={"Authorization": f"Bearer {self.supervisor_token}"},
            json={"zones": []}
        )
        self.assertEqual(res2.status_code, 403)

        # Dedicated zone endpoint attempt by supervisor
        res3 = self.client.put(
            "/api/cameras/cam_01/zones",
            headers={"Authorization": f"Bearer {self.supervisor_token}"},
            json={"zones": []}
        )
        self.assertEqual(res3.status_code, 403)

    def test_legacy_camera_returns_empty_zones_list(self):
        # In-memory legacy camera without zones field
        legacy_id = "cam_legacy_test"
        mem_cameras.append({
            "_id": legacy_id,
            "name": "Legacy Cam Without Zones",
            "zoneId": "zone_01",
            "zoneName": "Heavy Assembly Bay 01",
            "status": "ONLINE"
        })

        res = self.client.get(f"/api/cameras/{legacy_id}")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("zones", data)
        self.assertEqual(data["zones"], [])

        # GET /api/cameras/<id>/zones
        res_zones = self.client.get(f"/api/cameras/{legacy_id}/zones")
        self.assertEqual(res_zones.status_code, 200)
        self.assertEqual(res_zones.get_json(), [])

    def test_update_camera_zones_endpoint(self):
        cam_id = "cam_put_test"
        mem_cameras.append({
            "_id": cam_id,
            "name": "Put Test Cam",
            "zoneId": "zone_01",
            "zones": []
        })

        new_zones = [
            {
                "zoneId": "zone_01",
                "polygon": [
                    {"x": 0.05, "y": 0.05},
                    {"x": 0.45, "y": 0.05},
                    {"x": 0.45, "y": 0.45},
                    {"x": 0.05, "y": 0.45}
                ],
                "priority": 3
            }
        ]

        res = self.client.put(
            f"/api/cameras/{cam_id}/zones",
            headers={"Authorization": f"Bearer {self.admin_token}"},
            json={"zones": new_zones}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data["zones"]), 1)
        self.assertEqual(data["zones"][0]["priority"], 3)
        self.assertEqual(data["zones"][0]["zoneId"], "zone_01")

        # Verify GET returns the updated zones
        res_get = self.client.get(f"/api/cameras/{cam_id}/zones")
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(len(res_get.get_json()), 1)

    def test_mongodb_mock_camera_zones_persistence(self):
        # Verify persistence and query path when MongoDB is connected
        mock_cam_doc = {
            "_id": "507f1f77bcf86cd799439011",
            "name": "Mongo Cam Test",
            "zoneId": "zone_01",
            "zones": [
                {
                    "zoneId": "zone_01",
                    "polygon": [{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.1}, {"x": 0.5, "y": 0.5}],
                    "priority": 1
                }
            ]
        }

        mock_cameras_col = MagicMock()
        mock_cameras_col.find_one.return_value = dict(mock_cam_doc)
        mock_cameras_col.update_one.return_value = MagicMock(matched_count=1)

        mock_zones_col = MagicMock()
        mock_zones_col.find_one.return_value = {"_id": "zone_01", "name": "Heavy Assembly Bay 01"}

        with patch("routes.camera_routes.is_mongo_connected", True), \
             patch("routes.camera_routes.get_cameras_col", return_value=mock_cameras_col), \
             patch("ai_engine.zone_geometry.is_mongo_connected", True), \
             patch("ai_engine.zone_geometry.get_zones_col", return_value=mock_zones_col):

            # GET camera by ID
            res = self.client.get(f"/api/cameras/{mock_cam_doc['_id']}")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(len(data["zones"]), 1)
            self.assertEqual(data["zones"][0]["zoneId"], "zone_01")

            # PUT camera zones
            update_payload = {
                "zones": [
                    {
                        "zoneId": "zone_01",
                        "polygon": [
                            {"x": 0.2, "y": 0.2},
                            {"x": 0.7, "y": 0.2},
                            {"x": 0.7, "y": 0.7},
                            {"x": 0.2, "y": 0.7}
                        ],
                        "priority": 2
                    }
                ]
            }
            res_put = self.client.put(
                f"/api/cameras/{mock_cam_doc['_id']}/zones",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                json=update_payload
            )
            self.assertEqual(res_put.status_code, 200)
            mock_cameras_col.update_one.assert_called_once()
            call_args = mock_cameras_col.update_one.call_args[0]
            self.assertIn("zones", call_args[1]["$set"])
            self.assertEqual(len(call_args[1]["$set"]["zones"]), 1)
            self.assertEqual(call_args[1]["$set"]["zones"][0]["priority"], 2)

if __name__ == "__main__":
    unittest.main()
