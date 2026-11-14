import os
import io
import time
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import jwt
import datetime

from app import create_app
from config import Config, KNOWN_DEFAULT_SECRETS, validate_production_config
from auth import generate_token
from database import mem_cameras, mem_zones, mem_users, mem_detections
from routes.detection_routes import (
    validate_uploaded_video,
    register_session_owner,
    get_session_owner,
    clear_session_owner,
    _session_owners
)


def create_mock_mp4_bytes(size=128):
    """Creates a minimal mock MP4 byte sequence with an ftyp box."""
    # 4 bytes length, 'ftyp', 'isom', minor_version 0, compatible_brands 'isom'
    header = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2mp41"
    padding = b"\x00" * max(0, size - len(header))
    return header + padding


class TestSecurityHardening(unittest.TestCase):
    """
    Milestone M3.3: Security Hardening & Authorization Enforcement Test Suite.
    Validates:
    1. Missing or invalid JWT
    2. Removed hardcoded-password bypass
    3. Administrator vs Supervisor permission boundaries
    4. Unauthorized tracker reset and session isolation
    5. Protected evidence retrieval and path traversal prevention
    6. Invalid, oversized, and malformed video upload rejection
    7. Temporary-file cleanup after upload failures
    8. Explicit CORS origin restrictions
    9. Production secret & debug configuration validation
    """

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

        # Seed test tokens
        cls.admin_token = generate_token("usr_admin", "SUPER_ADMIN", "admin@ppe.com", name="Admin User")
        cls.admin_headers = {"Authorization": f"Bearer {cls.admin_token}"}

        cls.sup1_token = generate_token("usr_sup1", "ZONE_SUPERVISOR", "supervisor@ppe.com", "zone_01", name="Sup 1")
        cls.sup1_headers = {"Authorization": f"Bearer {cls.sup1_token}"}

        cls.sup2_token = generate_token("usr_sup2", "ZONE_SUPERVISOR", "pooja@ppe.com", "zone_02", name="Sup 2")
        cls.sup2_headers = {"Authorization": f"Bearer {cls.sup2_token}"}

        cls.guest_token = generate_token("usr_guest", "GUEST", "guest@ppe.com", name="Guest User")
        cls.guest_headers = {"Authorization": f"Bearer {cls.guest_token}"}

    def setUp(self):
        _session_owners.clear()

    # =========================================================================
    # 1. Missing or Invalid JWT
    # =========================================================================

    def test_missing_jwt_on_sensitive_endpoints_returns_401(self):
        """Strictly protected endpoints reject requests without a JWT with HTTP 401."""
        # Tracker reset
        res = self.client.post("/api/tracker/reset", json={"session_id": "sess_1"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("Authentication token missing", res.get_json()["message"])

        # Evidence access
        res2 = self.client.get("/uploads/evidence/sample.jpg")
        self.assertEqual(res2.status_code, 401)

        # Settings
        res3 = self.client.get("/api/settings")
        self.assertEqual(res3.status_code, 401)

    def test_invalid_or_expired_jwt_returns_401(self):
        """Malformed, tampered, or expired JWTs return HTTP 401."""
        bad_headers = {"Authorization": "Bearer not_a_valid_token.xyz.123"}
        res = self.client.post("/api/tracker/reset", headers=bad_headers, json={"session_id": "sess_1"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("Invalid or expired session token", res.get_json()["message"])

        # Expired token
        expired_payload = {
            "id": "usr_admin",
            "role": "SUPER_ADMIN",
            "email": "admin@ppe.com",
            "exp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        }
        expired_token = jwt.encode(expired_payload, Config.JWT_SECRET, algorithm="HS256")
        res_exp = self.client.post("/api/tracker/reset", headers={"Authorization": f"Bearer {expired_token}"}, json={"session_id": "s"})
        self.assertEqual(res_exp.status_code, 401)

    def test_jwt_supplied_only_via_query_parameter_is_rejected(self):
        """Milestone M3.3-F.1: JWT passed solely via query string is rejected; Bearer header is required."""
        # Query parameter on tracker reset
        res_reset = self.client.post(f"/api/tracker/reset?token={self.sup1_token}", json={"session_id": "sess_q"})
        self.assertEqual(res_reset.status_code, 401)
        self.assertIn("Authentication token missing", res_reset.get_json()["message"])

        # Query parameter on settings
        res_settings = self.client.get(f"/api/settings?token={self.admin_token}")
        self.assertEqual(res_settings.status_code, 401)

        # Same request with proper Authorization Bearer header succeeds
        res_auth = self.client.get("/api/settings", headers=self.admin_headers)
        self.assertEqual(res_auth.status_code, 200)

    # =========================================================================
    # 2. Removed Hardcoded-Password Bypass
    # =========================================================================

    def test_login_rejects_legacy_hardcoded_passwords(self):
        """Login strictly rejects plaintext test passwords (123456, password, admin) if hash doesn't match."""
        bypasses = ["123456", "password", "admin", "admin123", "wrong_pass"]
        for p in bypasses:
            res = self.client.post("/api/auth/login", json={
                "email": "admin@ppe.com",
                "password": p
            })
            self.assertEqual(res.status_code, 401, f"Bypass succeeded for password '{p}'")
            self.assertIn("Invalid workstation", res.get_json()["message"])

    def test_login_succeeds_only_with_authoritative_hashed_password(self):
        """Login succeeds only with the correct user password verified via password_hash."""
        res_admin = self.client.post("/api/auth/login", json={
            "email": "admin@ppe.com",
            "password": "Admin@123"
        })
        self.assertEqual(res_admin.status_code, 200)
        self.assertIn("token", res_admin.get_json())

        res_sup = self.client.post("/api/auth/login", json={
            "email": "supervisor@ppe.com",
            "password": "Supervisor@123"
        })
        self.assertEqual(res_sup.status_code, 200)

    # =========================================================================
    # 3. Administrator vs Supervisor Permission Boundaries
    # =========================================================================

    def test_supervisor_forbidden_from_admin_configuration_endpoints(self):
        """Supervisors are rejected with HTTP 403 when attempting system configuration updates."""
        # 1. Update settings
        r1 = self.client.put("/api/settings", headers=self.sup1_headers, json={"confidence_threshold": 0.5})
        self.assertEqual(r1.status_code, 403)

        # 2. Create camera
        r2 = self.client.post("/api/cameras", headers=self.sup1_headers, json={"name": "Hacked Cam"})
        self.assertEqual(r2.status_code, 403)

        # 3. Toggle camera status
        r3 = self.client.post("/api/cameras/cam_01/toggle-status", headers=self.sup1_headers)
        self.assertEqual(r3.status_code, 403)

        # 4. Create zone
        r4 = self.client.post("/api/zones", headers=self.sup1_headers, json={"name": "Hacked Zone"})
        self.assertEqual(r4.status_code, 403)

        # 5. Update zone
        r5 = self.client.patch("/api/zones/zone_01", headers=self.sup1_headers, json={"name": "Renamed Zone"})
        self.assertEqual(r5.status_code, 403)

    def test_administrator_allowed_to_modify_configuration(self):
        """Administrator successfully updates settings and cameras."""
        res = self.client.put("/api/settings", headers=self.admin_headers, json={"confidence_threshold": 0.40})
        self.assertEqual(res.status_code, 200)

    def test_guest_role_forbidden_from_supervisor_endpoints(self):
        """Users without Supervisor or Admin roles receive 403 on detection endpoints."""
        res = self.client.post("/api/detect", headers=self.guest_headers, json={})
        self.assertEqual(res.status_code, 403)

    # =========================================================================
    # 4. Unauthorized Tracker Reset & Session Isolation
    # =========================================================================

    def test_user_cannot_reset_another_users_tracking_session(self):
        """Supervisor 2 cannot reset a tracking session started by Supervisor 1."""
        session_id = "sup1_live_session_999"
        register_session_owner(session_id, "usr_sup1")

        # Supervisor 2 attempts reset -> 403 Forbidden
        res = self.client.post("/api/tracker/reset", headers=self.sup2_headers, json={"session_id": session_id})
        self.assertEqual(res.status_code, 403)
        self.assertIn("Cannot reset another user's tracking session", res.get_json()["message"])

        # Session remains registered to Supervisor 1
        self.assertEqual(get_session_owner(session_id), "usr_sup1")

        # Supervisor 1 resets own session -> 200 OK
        res_own = self.client.post("/api/tracker/reset", headers=self.sup1_headers, json={"session_id": session_id})
        self.assertEqual(res_own.status_code, 200)
        self.assertIsNone(get_session_owner(session_id))

    def test_administrator_can_reset_any_tracking_session(self):
        """Administrator has global privilege to reset any user's session."""
        session_id = "sup1_session_admin_override"
        register_session_owner(session_id, "usr_sup1")

        res = self.client.post("/api/tracker/reset", headers=self.admin_headers, json={"session_id": session_id})
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(get_session_owner(session_id))

    # =========================================================================
    # 5. Protected Evidence Retrieval & Path Traversal Prevention
    # =========================================================================

    def test_evidence_retrieval_requires_auth_and_rejects_path_traversal(self):
        """Evidence endpoints require auth and block path traversal attempts."""
        # 1. Unauthenticated -> 401
        res = self.client.get("/uploads/evidence/some_file.jpg")
        self.assertEqual(res.status_code, 401)

        # 2. Path traversal attack: ../../config.py
        res_trav = self.client.get("/uploads/../../config.py", headers=self.sup1_headers)
        self.assertIn(res_trav.status_code, [400, 403, 404])

        # 3. Valid authenticated request with query parameter token (?token=...)
        # Create a mock evidence file
        os.makedirs(Config.EVIDENCE_FOLDER, exist_ok=True)
        test_file = os.path.join(Config.EVIDENCE_FOLDER, "test_evidence_m33.jpg")
        with open(test_file, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00")

        try:
            # Milestone M3.3-F.1: Query parameter token is strictly rejected with 401
            res_token_query = self.client.get(f"/uploads/evidence/test_evidence_m33.jpg?token={self.sup1_token}")
            self.assertEqual(res_token_query.status_code, 401)
            self.assertIn("Authentication token missing", res_token_query.get_json()["message"])
            res_token_query.close()

            # Authorized retrieval using Bearer header succeeds
            res_bearer = self.client.get("/uploads/evidence/test_evidence_m33.jpg", headers=self.sup1_headers)
            self.assertEqual(res_bearer.status_code, 200)
            res_bearer.close()

            # Non-existent file with valid Bearer token -> 404
            res_not_found = self.client.get("/uploads/evidence/non_existent_404.jpg", headers=self.sup1_headers)
            self.assertEqual(res_not_found.status_code, 404)
            res_not_found.close()
        finally:
            if os.path.exists(test_file):
                try:
                    os.remove(test_file)
                except Exception:
                    pass

    # =========================================================================
    # 6. Invalid, Oversized, and Malformed Video Uploads
    # =========================================================================

    def test_video_upload_rejects_unsupported_extension(self):
        """Uploading dangerous extensions (.sh, .exe, .html) is rejected with 400."""
        res = self.client.post("/detect-video", headers=self.sup1_headers, data={
            "file": (io.BytesIO(b"echo hack"), "payload.sh")
        }, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)
        self.assertIn("Unsupported video format", res.get_json()["message"])

    def test_video_upload_rejects_empty_file(self):
        """Uploading an empty 0-byte file is rejected with 400."""
        res = self.client.post("/detect-video", headers=self.sup1_headers, data={
            "file": (io.BytesIO(b""), "empty.mp4")
        }, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)
        self.assertIn("empty", res.get_json()["message"])

    def test_video_upload_rejects_oversized_file(self):
        """Uploading a file exceeding MAX_CONTENT_LENGTH is rejected with 400."""
        with patch.object(Config, "MAX_CONTENT_LENGTH", 200): # 200 bytes max
            large_bytes = create_mock_mp4_bytes(size=500)
            res = self.client.post("/detect-video", headers=self.sup1_headers, data={
                "file": (io.BytesIO(large_bytes), "oversized.mp4")
            }, content_type="multipart/form-data")
            self.assertEqual(res.status_code, 400)
            self.assertIn("exceeds maximum limit", res.get_json()["message"])

    def test_video_upload_rejects_corrupted_header(self):
        """Uploading a file with random non-video bytes is rejected with 400."""
        res = self.client.post("/detect-video", headers=self.sup1_headers, data={
            "file": (io.BytesIO(b"GARBAGE_PAYLOAD_NOT_VIDEO_AT_ALL"), "corrupt.mp4")
        }, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)
        self.assertIn("Unsupported or corrupted video file", res.get_json()["message"])

    # =========================================================================
    # 7. Temporary-File Cleanup After Upload Failures
    # =========================================================================

    def test_temporary_files_are_cleaned_up_on_failure(self):
        """Temporary files created during video inspection are deleted even when processing fails."""
        tracked_files = []
        real_mkstemp = tempfile.mkstemp

        def tracking_mkstemp(*args, **kwargs):
            fd, path = real_mkstemp(*args, **kwargs)
            tracked_files.append(path)
            return fd, path

        valid_header_bytes = create_mock_mp4_bytes(size=256)
        with patch("routes.detection_routes.tempfile.mkstemp", side_effect=tracking_mkstemp):
            res = self.client.post("/detect-video", headers=self.sup1_headers, data={
                "file": (io.BytesIO(valid_header_bytes), "mock_corrupt_stream.mp4")
            }, content_type="multipart/form-data")

        # OpenCV fails to open mock ftyp header -> returns 400
        self.assertEqual(res.status_code, 400)
        self.assertTrue(len(tracked_files) > 0)
        for p in tracked_files:
            self.assertFalse(os.path.exists(p), f"Temporary file leaked: {p}")

    # =========================================================================
    # 8. CORS Origin Restrictions
    # =========================================================================

    def test_cors_allows_configured_origins_and_rejects_arbitrary_origins(self):
        """Allowed origins (localhost:5173) receive CORS headers; malicious origins do not."""
        # 1. Allowed origin
        res_allowed = self.client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(res_allowed.headers.get("Access-Control-Allow-Origin"), "http://localhost:5173")

        # 2. Malicious unauthorized origin
        res_evil = self.client.get("/api/health", headers={"Origin": "http://malicious-external-site.com"})
        self.assertNotEqual(res_evil.headers.get("Access-Control-Allow-Origin"), "http://malicious-external-site.com")

    # =========================================================================
    # 9. Production Secret & Debug Configuration Validation
    # =========================================================================

    def test_production_config_rejects_debug_mode_and_weak_secrets(self):
        """validate_production_config strictly enforces DEBUG=False and strong JWT_SECRET."""
        # Mock production config with DEBUG = True
        mock_prod_debug = MagicMock()
        mock_prod_debug.ENV = "production"
        mock_prod_debug.IS_PRODUCTION = True
        mock_prod_debug.DEBUG = True
        mock_prod_debug.JWT_SECRET = "a" * 32

        with self.assertRaises(ValueError) as ctx1:
            validate_production_config(mock_prod_debug)
        self.assertIn("cannot run with Flask DEBUG enabled", str(ctx1.exception))

        # Mock production config with known default JWT secret
        mock_prod_default_secret = MagicMock()
        mock_prod_default_secret.ENV = "production"
        mock_prod_default_secret.IS_PRODUCTION = True
        mock_prod_default_secret.DEBUG = False
        mock_prod_default_secret.JWT_SECRET = "ppe_compliance_jwt_secret_key_2026_enterprise"

        with self.assertRaises(ValueError) as ctx2:
            validate_production_config(mock_prod_default_secret)
        self.assertIn("strong, non-default JWT_SECRET", str(ctx2.exception))

        # Mock production config with short secret
        mock_prod_short_secret = MagicMock()
        mock_prod_short_secret.ENV = "production"
        mock_prod_short_secret.IS_PRODUCTION = True
        mock_prod_short_secret.DEBUG = False
        mock_prod_short_secret.JWT_SECRET = "short_123"

        with self.assertRaises(ValueError) as ctx3:
            validate_production_config(mock_prod_short_secret)
        self.assertIn("at least 32 characters", str(ctx3.exception))

        # Valid production configuration
        mock_valid_prod = MagicMock()
        mock_valid_prod.ENV = "production"
        mock_valid_prod.IS_PRODUCTION = True
        mock_valid_prod.DEBUG = False
        mock_valid_prod.JWT_SECRET = "c98f82a1789b41e8c9d01234567890abcdef1234567890abcdef"
        self.assertTrue(validate_production_config(mock_valid_prod))

        # Development configuration passes regardless
        mock_dev = MagicMock()
        mock_dev.ENV = "development"
        mock_dev.IS_PRODUCTION = False
        self.assertTrue(validate_production_config(mock_dev))


if __name__ == "__main__":
    unittest.main()
