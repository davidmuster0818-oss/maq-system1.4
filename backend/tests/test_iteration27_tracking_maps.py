"""
Iteration 27 - Realtime tracking + Google Maps integration tests.

Covers:
  - POST /api/routes/nav-leg (Google Routes API, polyline + traffic intervals)
  - POST /api/routes/geocode
  - GET  /api/tracking/config
  - POST /api/tracking/gps (auth) + GET /api/tracking/live/{route_id}
  - POST /api/tracking/breadcrumb + GET /api/tracking/breadcrumbs/{route_id}
  - POST /api/tracking/share-token + GET /api/tracking/public/{token}
  - POST /api/tracking/session/start, /session/stop-statuses, /session/current
  - E2E: technician posts gps+nav_path -> public endpoint exposes it
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://maq-sync-hub.preview.emergentagent.com"

ADMIN_EMAIL = "mastermaqassistencia@gmail.com"
ADMIN_PASSWORD = "atr132641"
SAMPLE_ROUTE_ID = "171a8f4d-57df-451a-b3a3-da37119db107"


@pytest.fixture(scope="module")
def auth_headers():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    token = r.json().get("token")
    assert token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def sample_route(auth_headers):
    """Return the sample route doc; pick first OS for share-token tests."""
    r = requests.get(
        f"{BASE_URL}/api/routes/{SAMPLE_ROUTE_ID}",
        headers=auth_headers, timeout=20,
    )
    if r.status_code != 200:
        pytest.skip(f"Sample route {SAMPLE_ROUTE_ID} not available ({r.status_code})")
    data = r.json()
    orders = data.get("orders") or []
    if not orders:
        pytest.skip("Sample route has no orders")
    return {"route_id": SAMPLE_ROUTE_ID, "os_number": str(orders[0].get("os_number"))}


# --- nav-leg (Google Routes API) ---
class TestNavLeg:
    def test_nav_leg_returns_polyline_and_traffic(self, auth_headers):
        body = {
            "origin_lat": -22.9068, "origin_lng": -47.0626,   # Campinas
            "dest_lat": -22.9249, "dest_lng": -47.0801,
        }
        r = requests.post(f"{BASE_URL}/api/routes/nav-leg", json=body, headers=auth_headers, timeout=25)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "encoded_polyline" in data and isinstance(data["encoded_polyline"], str) and len(data["encoded_polyline"]) > 20
        assert data.get("distance_meters", 0) > 0
        assert data.get("duration_seconds", 0) > 0
        assert data.get("static_duration_seconds", 0) > 0
        # Traffic-aware duration must differ from static (or at least be >=)
        assert data["duration_seconds"] >= data["static_duration_seconds"] - 5
        assert isinstance(data.get("speed_reading_intervals", []), list)


# --- geocode ---
class TestGeocode:
    def test_geocode_cached_lookup(self, auth_headers):
        """/api/routes/geocode is a CACHE lookup endpoint (os_numbers in body)."""
        r = requests.post(
            f"{BASE_URL}/api/routes/geocode",
            json={"os_numbers": ["NON_EXISTENT_TEST_OS"]},
            headers=auth_headers, timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "results" in data and isinstance(data["results"], list)
        assert data["total"] >= 1
        assert data["results"][0]["cached"] is False


# --- tracking config (public-ish, used to bootstrap Supabase realtime) ---
class TestTrackingConfig:
    def test_get_config(self):
        r = requests.get(f"{BASE_URL}/api/tracking/config", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "supabase_url" in data
        assert "supabase_anon_key" in data


# --- GPS + live mirror ---
class TestGpsAndLive:
    def test_gps_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/tracking/gps",
                          json={"route_id": "TEST_unauth", "lat": 0, "lng": 0}, timeout=15)
        assert r.status_code in (401, 403)

    def test_gps_persists_and_live_returns(self, auth_headers):
        route_id = f"TEST_route_{int(time.time())}"
        payload = {
            "route_id": route_id,
            "lat": -22.9068, "lng": -47.0626,
            "heading": 90, "speed": 14.5,
            "technician": "TEST_tech",
            "active_os": "TEST_OS_1",
            "active_status": "in_transit",
            "nav_path": [{"lat": -22.9068, "lng": -47.0626}, {"lat": -22.9070, "lng": -47.0630}],
            "nav_distance_meters": 3861,
            "nav_duration_seconds": 691,
            "nav_duration_in_traffic_seconds": 691,
            "nav_traffic_color": "green",
            "nav_destination_lat": -22.9249, "nav_destination_lng": -47.0801,
        }
        r = requests.post(f"{BASE_URL}/api/tracking/gps", json=payload, headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        # Read back via /live/{route_id}
        r2 = requests.get(f"{BASE_URL}/api/tracking/live/{route_id}", headers=auth_headers, timeout=15)
        assert r2.status_code == 200, r2.text
        live = r2.json()
        assert live["lat"] == payload["lat"]
        assert live["lng"] == payload["lng"]
        assert live["active_os"] == "TEST_OS_1"
        assert live.get("active_status") == "in_transit"
        assert live.get("nav_path") and len(live["nav_path"]) == 2
        assert live.get("nav_distance_meters") == 3861
        assert "stop_statuses" in live  # dict, may be empty


# --- breadcrumb ---
class TestBreadcrumb:
    def test_breadcrumb_persist_and_fetch(self, auth_headers):
        route_id = f"TEST_bc_{int(time.time())}"
        for i in range(3):
            r = requests.post(
                f"{BASE_URL}/api/tracking/breadcrumb",
                json={"route_id": route_id, "lat": -22.9 + i * 0.001, "lng": -47.0, "heading": 0, "speed": 10},
                headers=auth_headers, timeout=15,
            )
            assert r.status_code == 200, r.text
        r2 = requests.get(f"{BASE_URL}/api/tracking/breadcrumbs/{route_id}", headers=auth_headers, timeout=15)
        assert r2.status_code == 200
        points = r2.json().get("points", [])
        assert len(points) == 3
        # Stored in chronological order
        assert points[0]["lat"] < points[2]["lat"]


# --- share-token + public tracking ---
class TestShareTokenPublic:
    def test_share_token_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/tracking/share-token",
                          json={"route_id": "x", "os_number": "y"}, timeout=15)
        assert r.status_code in (401, 403)

    def test_share_token_for_invalid_route(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/tracking/share-token",
            json={"route_id": "non-existent-route-id-xyz", "os_number": "1"},
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 404

    def test_share_token_and_public_endpoint(self, auth_headers, sample_route):
        # Create share token
        r = requests.post(
            f"{BASE_URL}/api/tracking/share-token",
            json={"route_id": sample_route["route_id"], "os_number": sample_route["os_number"]},
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200, r.text
        token = r.json().get("token")
        assert token and isinstance(token, str)
        assert r.json().get("expires_in_hours") == 24

        # Public endpoint (NO auth)
        r2 = requests.get(f"{BASE_URL}/api/tracking/public/{token}", timeout=15)
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["os"]["os_number"] == sample_route["os_number"]
        # Privacy: no phone/email exposed
        assert "phone" not in body["os"]
        assert "email" not in body["os"]
        assert "technician_name" in body
        # `live` may be None if no GPS, that's fine.

    def test_public_endpoint_invalid_token(self):
        r = requests.get(f"{BASE_URL}/api/tracking/public/garbage.token.value", timeout=15)
        assert r.status_code in (401, 410, 422)


# --- session persistence ---
class TestSession:
    def test_session_start_current_stop_statuses(self, auth_headers, sample_route):
        # Start session
        r = requests.post(
            f"{BASE_URL}/api/tracking/session/start",
            json={"route_id": sample_route["route_id"], "technician_name": "TEST_tech"},
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        # Current session
        r2 = requests.get(f"{BASE_URL}/api/tracking/session/current", headers=auth_headers, timeout=15)
        assert r2.status_code == 200
        cur = r2.json()
        assert cur.get("active") is True
        assert cur["session"]["route_id"] == sample_route["route_id"]

        # Update stop statuses
        r3 = requests.post(
            f"{BASE_URL}/api/tracking/session/stop-statuses",
            json={"route_id": sample_route["route_id"],
                  "stop_statuses": {sample_route["os_number"]: "next"}},
            headers=auth_headers, timeout=15,
        )
        assert r3.status_code == 200

        # Stop session (cleanup)
        r4 = requests.post(
            f"{BASE_URL}/api/tracking/session/stop",
            json={"route_id": sample_route["route_id"]},
            headers=auth_headers, timeout=15,
        )
        assert r4.status_code == 200


# --- E2E: technician → public viewer ---
class TestE2ENavToPublic:
    def test_full_flow_tech_posts_gps_public_sees_it(self, auth_headers, sample_route):
        # 1. technician posts gps with nav path
        gps = {
            "route_id": sample_route["route_id"],
            "lat": -22.9068, "lng": -47.0626,
            "heading": 45, "speed": 12,
            "technician": "TEST_tech_e2e",
            "active_os": sample_route["os_number"],
            "active_status": "in_transit",
            "nav_path": [{"lat": -22.9068, "lng": -47.0626},
                         {"lat": -22.9100, "lng": -47.0700},
                         {"lat": -22.9249, "lng": -47.0801}],
            "nav_distance_meters": 3861,
            "nav_duration_seconds": 691,
            "nav_duration_in_traffic_seconds": 720,
            "nav_traffic_color": "yellow",
        }
        r1 = requests.post(f"{BASE_URL}/api/tracking/gps", json=gps, headers=auth_headers, timeout=15)
        assert r1.status_code == 200, r1.text

        # 2. mint share token
        r2 = requests.post(
            f"{BASE_URL}/api/tracking/share-token",
            json={"route_id": sample_route["route_id"], "os_number": sample_route["os_number"]},
            headers=auth_headers, timeout=15,
        )
        assert r2.status_code == 200
        token = r2.json()["token"]

        # 3. public viewer (no auth) gets the same nav_path
        r3 = requests.get(f"{BASE_URL}/api/tracking/public/{token}", timeout=15)
        assert r3.status_code == 200
        body = r3.json()
        assert body.get("live") is not None, "live must be present when GPS active"
        live = body["live"]
        assert live["lat"] == gps["lat"]
        assert live["lng"] == gps["lng"]
        assert live["active_os"] == sample_route["os_number"]
        assert live.get("nav_path") and len(live["nav_path"]) == 3
        assert live.get("nav_distance_meters") == 3861
        assert live.get("nav_duration_seconds") == 691
        assert live.get("nav_duration_in_traffic_seconds") == 720
        assert live.get("nav_traffic_color") == "yellow"
