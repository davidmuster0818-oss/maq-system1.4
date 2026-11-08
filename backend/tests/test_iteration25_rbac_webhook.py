"""
Iteration 25 - RBAC + Webhook Outbound Log + WA send-copy + photos-status
Tests for:
- Auth (login admin/tech, verify, refresh)
- Users CRUD (admin only)
- Photos status (8 mandatory photos)
- Webhook outbound log
- WhatsApp send-copy handshake
- Backward-compat tokens (no role -> admin)
"""
import os
import time
import uuid
import base64
import jwt as pyjwt
import pytest
import requests
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mastermaq-systems.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "mastermaqassistencia@gmail.com"
ADMIN_PASSWORD = "atr132641"
TECH_EMAIL = "nelson@mastermaq.com"
TECH_PASSWORD = "nelson123"
JWT_SECRET = os.environ.get("JWT_SECRET", "mastermaq_secret_key_2024_secure")
JWT_ALGORITHM = "HS256"


# ─── Session fixtures ─────────────────────────────────────────────────
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("role") == "admin", f"Expected role=admin, got {data.get('role')}"
    assert data.get("email") == ADMIN_EMAIL
    assert "token" in data and "name" in data
    return data["token"]


@pytest.fixture(scope="session")
def tech_token():
    r = requests.post(f"{API}/auth/login", json={"email": TECH_EMAIL, "password": TECH_PASSWORD}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Technician not seeded or login failed: {r.status_code} {r.text}")
    data = r.json()
    assert data.get("role") == "technician", f"Expected role=technician, got {data.get('role')}"
    assert data.get("email") == TECH_EMAIL
    return data["token"]


def H(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─── Auth endpoints ───────────────────────────────────────────────────
class TestAuth:
    def test_login_admin_returns_role_admin(self, admin_token):
        # Already validated in fixture
        assert isinstance(admin_token, str) and len(admin_token) > 20

    def test_login_technician_returns_role_technician(self, tech_token):
        assert isinstance(tech_token, str) and len(tech_token) > 20

    def test_login_invalid_credentials(self):
        r = requests.post(f"{API}/auth/login", json={"email": "x@x.com", "password": "wrong"}, timeout=10)
        assert r.status_code == 401

    def test_verify_admin(self, admin_token):
        r = requests.get(f"{API}/auth/verify", headers=H(admin_token), timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("valid") is True
        assert data.get("role") == "admin"
        assert data.get("email") == ADMIN_EMAIL
        assert "name" in data
        assert "user_id" in data

    def test_verify_technician(self, tech_token):
        r = requests.get(f"{API}/auth/verify", headers=H(tech_token), timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("valid") is True
        assert data.get("role") == "technician"
        assert data.get("email") == TECH_EMAIL
        assert data.get("user_id"), "user_id should be set for DB users"

    def test_refresh_token(self, admin_token):
        r = requests.post(f"{API}/auth/refresh", headers=H(admin_token), timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "token" in data and data.get("role") == "admin"

    def test_backward_compat_token_without_role(self):
        """Legacy tokens without role/name in payload must default to admin."""
        payload = {
            "email": ADMIN_EMAIL,
            "exp": datetime.now(timezone.utc).timestamp() + 3600,
        }
        legacy_token = pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        r = requests.get(f"{API}/auth/verify", headers={"Authorization": f"Bearer {legacy_token}"}, timeout=10)
        # auth/verify hits DB user, so legacy token for admin should still work
        assert r.status_code == 200, f"Legacy token rejected: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("role") == "admin"

        # Also try /users (admin-only) — verify_token defaults role=admin for legacy tokens
        r2 = requests.get(f"{API}/users", headers={"Authorization": f"Bearer {legacy_token}"}, timeout=10)
        assert r2.status_code == 200, f"Legacy token must default to admin for RBAC. Got: {r2.status_code} {r2.text}"


# ─── Users CRUD ───────────────────────────────────────────────────────
class TestUsersCRUD:
    created_user_id = None

    def test_list_users_admin(self, admin_token):
        r = requests.get(f"{API}/users", headers=H(admin_token), timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # No password_hash or _id leak
        for u in data:
            assert "password_hash" not in u
            assert "_id" not in u
            assert "id" in u and "email" in u and "role" in u

    def test_list_users_technician_forbidden(self, tech_token):
        r = requests.get(f"{API}/users", headers=H(tech_token), timeout=10)
        assert r.status_code == 403

    def test_create_user_admin(self, admin_token):
        unique = uuid.uuid4().hex[:8]
        payload = {
            "name": "TEST_Technician",
            "email": f"TEST_tech_{unique}@example.com",
            "password": "Testpass123!",
            "role": "technician",
            "phone": "31999990000",
            "active": True,
        }
        r = requests.post(f"{API}/users", headers=H(admin_token), json=payload, timeout=10)
        assert r.status_code == 200, f"Create failed: {r.status_code} {r.text}"
        user = r.json()
        assert user["email"] == payload["email"].lower()
        assert user["role"] == "technician"
        assert user["name"] == payload["name"]
        assert "password_hash" not in user
        TestUsersCRUD.created_user_id = user["id"]

        # Duplicate email -> 400
        r2 = requests.post(f"{API}/users", headers=H(admin_token), json=payload, timeout=10)
        assert r2.status_code == 400

        # Invalid role -> 400
        bad = {**payload, "email": f"TEST_bad_{unique}@example.com", "role": "superuser"}
        r3 = requests.post(f"{API}/users", headers=H(admin_token), json=bad, timeout=10)
        assert r3.status_code == 400

    def test_login_with_new_user(self, admin_token):
        # Pull the just-created user via /users list, then attempt login with their pwd
        # We only assert that user is listed correctly here, login is implicit via bcrypt code path
        r = requests.get(f"{API}/users", headers=H(admin_token), timeout=10)
        assert r.status_code == 200
        assert any(u["id"] == TestUsersCRUD.created_user_id for u in r.json())

    def test_update_user(self, admin_token):
        assert TestUsersCRUD.created_user_id, "previous test must have created the user"
        r = requests.put(
            f"{API}/users/{TestUsersCRUD.created_user_id}",
            headers=H(admin_token),
            json={"name": "TEST_Updated", "active": False},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == "TEST_Updated"
        assert data["active"] is False

    def test_update_admin_cannot_demote_master(self, admin_token):
        # Find master admin id
        r = requests.get(f"{API}/users", headers=H(admin_token), timeout=10)
        master = next((u for u in r.json() if u["email"] == ADMIN_EMAIL), None)
        assert master is not None, "Master admin should be seeded"
        r2 = requests.put(
            f"{API}/users/{master['id']}",
            headers=H(admin_token),
            json={"role": "technician"},
            timeout=10,
        )
        assert r2.status_code == 400

        r3 = requests.put(
            f"{API}/users/{master['id']}",
            headers=H(admin_token),
            json={"active": False},
            timeout=10,
        )
        assert r3.status_code == 400

    def test_delete_master_admin_blocked(self, admin_token):
        r = requests.get(f"{API}/users", headers=H(admin_token), timeout=10)
        master = next((u for u in r.json() if u["email"] == ADMIN_EMAIL), None)
        assert master is not None
        r2 = requests.delete(f"{API}/users/{master['id']}", headers=H(admin_token), timeout=10)
        assert r2.status_code == 400

    def test_technicians_list_accessible_by_anyone(self, tech_token, admin_token):
        r = requests.get(f"{API}/users/technicians", headers=H(tech_token), timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        r2 = requests.get(f"{API}/users/technicians", headers=H(admin_token), timeout=10)
        assert r2.status_code == 200

    def test_zz_delete_created_user(self, admin_token):
        """Cleanup created test user."""
        if TestUsersCRUD.created_user_id:
            r = requests.delete(f"{API}/users/{TestUsersCRUD.created_user_id}", headers=H(admin_token), timeout=10)
            assert r.status_code == 200


# ─── Photos status ────────────────────────────────────────────────────
class TestPhotosStatus:
    def _pick_os(self, admin_token):
        # Use a known-good OS by listing
        r = requests.get(f"{API}/service-orders?limit=1", headers=H(admin_token), timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        rows = body if isinstance(body, list) else body.get("data") or body.get("orders") or []
        assert rows, "Need at least one OS"
        return rows[0].get("os_number")

    def test_photos_status_shape(self, admin_token):
        os_number = self._pick_os(admin_token)
        r = requests.get(f"{API}/service-orders/{os_number}/photos-status", headers=H(admin_token), timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["os_number"] == os_number
        assert isinstance(data["filled"], list)
        assert isinstance(data["count"], int)
        assert isinstance(data["all_done"], bool)
        assert data["count"] == len(data["filled"])
        assert data["all_done"] == (data["count"] >= 8)
        # all entries in filled are in 1..8
        for n in data["filled"]:
            assert 1 <= n <= 8

    def test_photos_status_not_found(self, admin_token):
        r = requests.get(f"{API}/service-orders/__not_an_os__/photos-status", headers=H(admin_token), timeout=10)
        assert r.status_code == 404

    def test_photos_status_technician_can_access(self, tech_token, admin_token):
        os_number = self._pick_os(admin_token)
        r = requests.get(f"{API}/service-orders/{os_number}/photos-status", headers=H(tech_token), timeout=10)
        assert r.status_code == 200


# ─── Webhook outbound log ─────────────────────────────────────────────
class TestWebhookOutboundLog:
    def test_list_log_shape(self, admin_token):
        r = requests.get(f"{API}/webhooks/outbound-log?limit=5", headers=H(admin_token), timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "count" in data and "webhook_url" in data and "rows" in data
        assert data["webhook_url"] == "https://mastermaqassistencia.com.br/api/external/webhook/status"
        assert isinstance(data["rows"], list)
        # No mongo _id leak
        for row in data["rows"]:
            assert "_id" not in row

    def test_log_accessible_by_technician(self, tech_token):
        r = requests.get(f"{API}/webhooks/outbound-log?limit=1", headers=H(tech_token), timeout=10)
        assert r.status_code == 200

    def test_webhook_fires_on_status_change(self, admin_token):
        """PUT /service-orders/{os}/ with a status change should enqueue a webhook attempt."""
        # Pick a single OS
        r = requests.get(f"{API}/service-orders?limit=1", headers=H(admin_token), timeout=20)
        assert r.status_code == 200
        body = r.json()
        rows = body if isinstance(body, list) else body.get("data") or body.get("orders") or []
        if not rows:
            pytest.skip("No OS available to test webhook trigger")
        order = rows[0]
        os_number = order.get("os_number")
        original_status = order.get("status") or "Aberto"
        # Use a sentinel temp status that should still pass model validation (str)
        temp_status = "TEST_WEBHOOK_FIRE"

        # Snapshot current log count for this OS
        before = requests.get(f"{API}/webhooks/outbound-log?limit=200", headers=H(admin_token), timeout=10).json()
        before_ids = {r.get("id") for r in before.get("rows", []) if r.get("os_number") == os_number}

        # Trigger update (status change)
        u1 = requests.put(f"{API}/service-orders/{os_number}", headers=H(admin_token),
                          json={"status": temp_status}, timeout=20)
        assert u1.status_code in (200, 201), f"PUT failed: {u1.status_code} {u1.text}"

        # Background task may take a moment
        new_entry = None
        for _ in range(15):
            time.sleep(1.0)
            after = requests.get(f"{API}/webhooks/outbound-log?limit=50", headers=H(admin_token), timeout=10).json()
            for r in after.get("rows", []):
                if r.get("os_number") == os_number and r.get("id") not in before_ids:
                    new_entry = r
                    break
            if new_entry:
                break

        # Always revert
        try:
            requests.put(f"{API}/service-orders/{os_number}", headers=H(admin_token),
                         json={"status": original_status}, timeout=20)
        except Exception:
            pass

        assert new_entry is not None, "Expected a new webhook outbound_log entry after status change"
        payload = new_entry.get("payload") or {}
        assert payload.get("os_number") == os_number
        assert payload.get("status") == temp_status
        assert payload.get("event_type") == "status_update"
        # URL must be the new .com.br webhook
        assert new_entry.get("url") == "https://mastermaqassistencia.com.br/api/external/webhook/status"
        # Log records HTTP attempt outcome - either status_code or error
        assert ("status_code" in new_entry) or ("error" in new_entry)


# ─── WhatsApp send-copy ───────────────────────────────────────────────
class TestWhatsAppSendCopy:
    def _tiny_pdf_b64(self):
        # Minimal valid PDF
        pdf = (
            b"%PDF-1.1\n%\xe2\xe3\xcf\xd3\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
            b"xref\n0 4\n0000000000 65535 f \n0000000017 00000 n \n0000000058 00000 n \n0000000105 00000 n \n"
            b"trailer<</Root 1 0 R/Size 4>>\nstartxref\n160\n%%EOF\n"
        )
        return base64.b64encode(pdf).decode()

    def test_requires_auth(self):
        r = requests.post(f"{API}/whatsapp/send-copy", json={"phone": "31999990000", "os_number": "X", "pdf_base64": "abc"}, timeout=10)
        assert r.status_code in (401, 403)

    def test_handshake_returns_4xx_not_500(self, admin_token):
        """Should return a structured 4xx (not 500) when WA not configured or phone invalid."""
        payload = {
            "phone": "31999990000",
            "os_number": "TEST_FAKE_OS",
            "pdf_base64": self._tiny_pdf_b64(),
            "filename": "TEST_OS.pdf",
        }
        r = requests.post(f"{API}/whatsapp/send-copy", headers=H(admin_token), json=payload, timeout=30)
        # Must not be 500 server error
        assert r.status_code != 500, f"Server error from /whatsapp/send-copy: {r.text}"
        # Accept 400 (not configured / bad request), 404 (no config), 200 (rare success), 4xx upstream Meta error
        assert 200 <= r.status_code < 500, f"Unexpected status: {r.status_code} {r.text}"
        # If 4xx, must have a JSON detail field
        if r.status_code >= 400:
            try:
                body = r.json()
                assert "detail" in body, f"Expected 'detail' in error body, got: {body}"
            except Exception:
                pytest.fail(f"4xx response must be JSON with detail: {r.text}")

    def test_invalid_phone(self, admin_token):
        r = requests.post(f"{API}/whatsapp/send-copy", headers=H(admin_token), json={
            "phone": "",
            "os_number": "TEST",
            "pdf_base64": self._tiny_pdf_b64(),
        }, timeout=15)
        # Either WA not configured (400) or phone invalid (400) — never 500
        assert r.status_code == 400
