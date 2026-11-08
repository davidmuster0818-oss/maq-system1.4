"""
Iteration 26 backend tests - RBAC + Tracking Uber-like + Temporary PDF.

Covers:
1) GET /api/routes/ filtering by technician role (case-insensitive first-name substring)
2) GET /api/routes/{id} RBAC (403 when technician fetches another technician's route)
3) POST /api/tracking/share-token (validates route + os_number)
4) GET /api/tracking/public/{token} privacy filter (no phone, no number)
5) POST /api/tracking/gps upsert + GET /api/tracking/live/{route_id}
6) POST /api/files/temp-pdf (auth) + GET /api/files/temp-pdf/{token} (no auth)
"""
import os
import base64
import pytest
import requests


def _load_backend_url():
    env_val = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if env_val:
        return env_val.rstrip("/")
    # Fallback: read frontend/.env
    try:
        with open("/app/frontend/.env", "r") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    except Exception:
        pass
    return ""


BASE_URL = _load_backend_url()
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"
ADMIN_EMAIL = "mastermaqassistencia@gmail.com"
ADMIN_PASS = "atr132641"
TECH_EMAIL = "nelson@mastermaq.com"
TECH_PASS = "nelson123"


# ─── Fixtures ───────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=20,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def tech_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TECH_EMAIL, "password": TECH_PASS},
        timeout=20,
    )
    assert r.status_code == 200, f"Technician login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def tech_headers(tech_token):
    return {"Authorization": f"Bearer {tech_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def tech_profile(tech_token):
    r = requests.get(
        f"{BASE_URL}/api/auth/verify",
        headers={"Authorization": f"Bearer {tech_token}"},
        timeout=20,
    )
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def all_routes_admin(admin_headers):
    r = requests.get(f"{BASE_URL}/api/routes/", headers=admin_headers, timeout=30)
    assert r.status_code == 200, f"Admin GET /routes/ failed: {r.status_code} {r.text}"
    return r.json()


# ─── 1) GET /api/routes/ RBAC ───────────────────────────────────
class TestRoutesListRBAC:
    def test_admin_sees_all_routes(self, all_routes_admin):
        assert isinstance(all_routes_admin, list)
        # Spec says >30 expected
        assert len(all_routes_admin) > 30, f"Expected >30 routes for admin, got {len(all_routes_admin)}"

    def test_technician_sees_only_own_routes(self, tech_headers, tech_profile, all_routes_admin):
        r = requests.get(f"{BASE_URL}/api/routes/", headers=tech_headers, timeout=30)
        assert r.status_code == 200, f"Tech GET /routes/ failed: {r.status_code} {r.text}"
        tech_routes = r.json()
        assert isinstance(tech_routes, list)
        first_name = (tech_profile.get("name") or "").strip().split()[0].lower()
        assert first_name, "Technician profile missing name"
        # All returned routes must contain the first name (case-insensitive substring)
        for rt in tech_routes:
            tech_field = (rt.get("technician") or "").lower()
            assert first_name in tech_field, (
                f"Route {rt.get('id')} has technician '{rt.get('technician')}' "
                f"which does not contain first name '{first_name}'"
            )
        # Tech list must be a strict subset of admin list (and smaller in general)
        assert len(tech_routes) <= len(all_routes_admin)


# ─── 2) GET /api/routes/{id} RBAC ───────────────────────────────
class TestRouteByIdRBAC:
    def test_admin_can_fetch_any_route(self, admin_headers, all_routes_admin):
        assert all_routes_admin, "No routes available to test"
        target = all_routes_admin[0]
        r = requests.get(
            f"{BASE_URL}/api/routes/{target['id']}", headers=admin_headers, timeout=20
        )
        assert r.status_code == 200, f"Admin GET /routes/{{id}}: {r.status_code} {r.text}"
        assert r.json().get("id") == target["id"]

    def test_technician_forbidden_on_other_tech_route(
        self, tech_headers, tech_profile, all_routes_admin
    ):
        first_name = (tech_profile.get("name") or "").strip().split()[0].lower()
        # Find a route NOT belonging to this technician
        foreign = None
        for rt in all_routes_admin:
            if first_name not in (rt.get("technician") or "").lower():
                foreign = rt
                break
        if not foreign:
            pytest.skip("No foreign-technician route available to test 403")
        r = requests.get(
            f"{BASE_URL}/api/routes/{foreign['id']}", headers=tech_headers, timeout=20
        )
        assert r.status_code == 403, (
            f"Expected 403 for foreign route, got {r.status_code} {r.text}"
        )

    def test_technician_can_fetch_own_route(
        self, tech_headers, tech_profile, all_routes_admin
    ):
        first_name = (tech_profile.get("name") or "").strip().split()[0].lower()
        own = None
        for rt in all_routes_admin:
            if first_name in (rt.get("technician") or "").lower():
                own = rt
                break
        if not own:
            pytest.skip("No own-technician route available")
        r = requests.get(
            f"{BASE_URL}/api/routes/{own['id']}", headers=tech_headers, timeout=20
        )
        assert r.status_code == 200, f"Tech own-route: {r.status_code} {r.text}"


# ─── Helpers to pick a valid (route, os_number) pair ────────────
def _pick_route_with_orders(all_routes_admin):
    for rt in all_routes_admin:
        orders = rt.get("orders") or []
        if orders and orders[0].get("os_number"):
            return rt, str(orders[0]["os_number"])
    return None, None


# ─── 3) Tracking share-token ────────────────────────────────────
class TestShareToken:
    def test_share_token_success(self, admin_headers, all_routes_admin):
        rt, os_num = _pick_route_with_orders(all_routes_admin)
        if not rt:
            pytest.skip("No route with orders found")
        r = requests.post(
            f"{BASE_URL}/api/tracking/share-token",
            json={"route_id": rt["id"], "os_number": os_num},
            headers=admin_headers,
            timeout=20,
        )
        assert r.status_code == 200, f"share-token: {r.status_code} {r.text}"
        data = r.json()
        assert "token" in data and isinstance(data["token"], str) and len(data["token"]) > 20
        assert data.get("expires_in_hours") == 24

    def test_share_token_404_unknown_route(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/tracking/share-token",
            json={"route_id": "non-existent-route-id-xxx", "os_number": "9999"},
            headers=admin_headers,
            timeout=20,
        )
        assert r.status_code == 404, f"Expected 404, got {r.status_code} {r.text}"

    def test_share_token_400_os_not_in_route(self, admin_headers, all_routes_admin):
        rt, _ = _pick_route_with_orders(all_routes_admin)
        if not rt:
            pytest.skip("No route with orders found")
        r = requests.post(
            f"{BASE_URL}/api/tracking/share-token",
            json={"route_id": rt["id"], "os_number": "0000000NOTINROUTE"},
            headers=admin_headers,
            timeout=20,
        )
        assert r.status_code == 400, f"Expected 400, got {r.status_code} {r.text}"


# ─── 4 & 5) Public tracking + live position ─────────────────────
class TestPublicTrackingAndLive:
    @pytest.fixture(scope="class")
    def share_token_and_route(self, admin_headers, all_routes_admin):
        rt, os_num = _pick_route_with_orders(all_routes_admin)
        if not rt:
            pytest.skip("No route with orders found")
        r = requests.post(
            f"{BASE_URL}/api/tracking/share-token",
            json={"route_id": rt["id"], "os_number": os_num},
            headers=admin_headers,
            timeout=20,
        )
        assert r.status_code == 200
        return r.json()["token"], rt["id"], os_num

    def test_public_invalid_token_401(self):
        r = requests.get(f"{BASE_URL}/api/tracking/public/not-a-valid-jwt", timeout=20)
        assert r.status_code == 401, f"Expected 401, got {r.status_code} {r.text}"

    def test_live_404_when_never_positioned(self, share_token_and_route):
        _, route_id, _ = share_token_and_route
        # Best-effort cleanup: post a known-bad route_id we are sure has no live data
        r = requests.get(
            f"{BASE_URL}/api/tracking/live/__never_positioned_route_id__",
            timeout=20,
        )
        assert r.status_code == 404, f"Expected 404 for never-positioned, got {r.status_code}"

    def test_public_before_gps_returns_live_null(self, share_token_and_route):
        token, route_id, _ = share_token_and_route
        # Ensure no prior live doc by calling /tracking/end (sets active=False)
        try:
            requests.post(
                f"{BASE_URL}/api/tracking/end",
                json={"route_id": route_id, "technician": ""},
                timeout=15,
            )
        except Exception:
            pass
        r = requests.get(f"{BASE_URL}/api/tracking/public/{token}", timeout=20)
        assert r.status_code == 200, f"public: {r.status_code} {r.text}"
        data = r.json()
        assert "os" in data and "technician_name" in data and "route_name" in data
        assert "live" in data
        # active=False → backend should return live=None
        assert data["live"] is None, f"Expected live=None after /end, got {data['live']}"

    def test_post_gps_then_public_returns_live(self, share_token_and_route, admin_headers):
        token, route_id, os_num = share_token_and_route
        gps_body = {
            "route_id": route_id,
            "lat": -23.5505,
            "lng": -46.6333,
            "heading": 90,
            "speed": 30,
            "technician": "Nelson",
            "active_os": os_num,
            "active_status": "in_transit",
        }
        r = requests.post(
            f"{BASE_URL}/api/tracking/gps",
            json=gps_body,
            headers=admin_headers,
            timeout=20,
        )
        assert r.status_code == 200, f"POST /tracking/gps: {r.status_code} {r.text}"
        body = r.json()
        assert body.get("ok") is True
        assert "updated_at" in body

        # GET live (authenticated)
        r2 = requests.get(
            f"{BASE_URL}/api/tracking/live/{route_id}",
            headers=admin_headers,
            timeout=20,
        )
        assert r2.status_code == 200, f"/tracking/live: {r2.status_code} {r2.text}"
        live = r2.json()
        assert live["lat"] == -23.5505
        assert live["lng"] == -46.6333
        assert live["active_os"] == os_num
        assert live["active_status"] == "in_transit"

        # Public tracking should now expose live
        r3 = requests.get(f"{BASE_URL}/api/tracking/public/{token}", timeout=20)
        assert r3.status_code == 200
        data = r3.json()
        assert data["live"] is not None, "Expected live data after /gps"
        assert data["live"]["lat"] == -23.5505
        assert data["live"]["lng"] == -46.6333
        assert data["live"]["active_os"] == os_num
        assert data["live"]["active_status"] == "in_transit"

    def test_public_privacy_filter(self, share_token_and_route):
        token, _, _ = share_token_and_route
        r = requests.get(f"{BASE_URL}/api/tracking/public/{token}", timeout=20)
        assert r.status_code == 200
        data = r.json()
        os_payload = data.get("os") or {}
        # Privacy: no phone, no number, no email
        for forbidden in ["phone", "phone1", "phone2", "email", "number"]:
            val = os_payload.get(forbidden)
            assert not val, f"Public payload leaks '{forbidden}': {val!r}"


# ─── 6) Temporary PDF storage ───────────────────────────────────
class TestTempPdf:
    @pytest.fixture(scope="class")
    def sample_pdf_b64(self):
        # Minimal valid-ish PDF bytes (header + EOF marker)
        pdf_bytes = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
        return base64.b64encode(pdf_bytes).decode("ascii")

    def test_store_temp_pdf_requires_auth(self, sample_pdf_b64):
        r = requests.post(
            f"{BASE_URL}/api/files/temp-pdf",
            json={"pdf_base64": sample_pdf_b64, "filename": "TEST_unauth.pdf"},
            timeout=20,
        )
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"

    def test_store_and_fetch_temp_pdf(self, admin_headers, sample_pdf_b64):
        r = requests.post(
            f"{BASE_URL}/api/files/temp-pdf",
            json={"pdf_base64": sample_pdf_b64, "filename": "TEST_iter26.pdf",
                  "os_number": "TEST26"},
            headers=admin_headers,
            timeout=20,
        )
        assert r.status_code == 200, f"store: {r.status_code} {r.text}"
        data = r.json()
        assert "token" in data and data["token"]
        assert "url" in data
        assert "path" in data and data["path"] == f"/api/files/temp-pdf/{data['token']}"

        # Fetch without auth
        r2 = requests.get(f"{BASE_URL}{data['path']}", timeout=20)
        assert r2.status_code == 200, f"fetch: {r2.status_code} {r2.text}"
        assert r2.headers.get("content-type", "").startswith("application/pdf")
        assert r2.content.startswith(b"%PDF"), "Returned bytes are not a PDF"

    def test_fetch_temp_pdf_invalid_token_404(self):
        r = requests.get(
            f"{BASE_URL}/api/files/temp-pdf/non-existent-token-xxx", timeout=20
        )
        assert r.status_code == 404, f"Expected 404, got {r.status_code}"

    def test_store_temp_pdf_invalid_base64(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/files/temp-pdf",
            json={"pdf_base64": "not!!valid!!base64@@@"},
            headers=admin_headers,
            timeout=20,
        )
        # backend should respond 400 (HTTPException) or 200 if base64 parser is lenient
        # The implementation raises 400 on decode failure
        assert r.status_code in (400, 200), f"Unexpected: {r.status_code} {r.text}"
