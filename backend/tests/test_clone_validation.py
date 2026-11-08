"""
Clone Validation Tests - validates all endpoints listed in the review request
on the freshly cloned mastermaq-software repo, against the public BACKEND_URL.
"""
import os
import pytest
import requests
from pathlib import Path


def _load_backend_url() -> str:
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if url:
        return url.rstrip("/")
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not configured")


BASE_URL = _load_backend_url()
ADMIN_EMAIL = "mastermaqassistencia@gmail.com"
ADMIN_PASSWORD = "atr132641"


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def token(session):
    r = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data, f"no token in response: {data}"
    return data["token"]


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


# -------- Auth --------
class TestAuth:
    def test_login_success(self, session):
        r = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=30,
        )
        assert r.status_code == 200
        d = r.json()
        assert d.get("token")
        assert d.get("role") == "admin"
        assert d.get("email") == ADMIN_EMAIL

    def test_login_bad_password(self, session):
        r = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": "wrong"},
            timeout=30,
        )
        assert r.status_code in (400, 401, 403)

    def test_verify_token(self, session, auth):
        r = session.get(f"{BASE_URL}/api/auth/verify", headers=auth, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("valid") is True
        assert d.get("role") == "admin"

    def test_refresh_token(self, session, auth):
        r = session.post(f"{BASE_URL}/api/auth/refresh", headers=auth, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("token")


# -------- Service Orders --------
class TestServiceOrders:
    def test_list(self, session, auth):
        r = session.get(f"{BASE_URL}/api/service-orders", headers=auth, timeout=60)
        assert r.status_code == 200
        d = r.json()
        # might be list or paginated dict
        if isinstance(d, dict):
            assert any(k in d for k in ("items", "data", "results", "service_orders", "orders"))
            assert "total" in d
        else:
            assert isinstance(d, list)

    def test_statuses(self, session, auth):
        r = session.get(f"{BASE_URL}/api/service-orders/statuses", headers=auth, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, (list, dict))

    def test_brands(self, session, auth):
        r = session.get(f"{BASE_URL}/api/service-orders/brands", headers=auth, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, (list, dict))


# -------- Dashboard / Notifications / Telecontrol / Scrapers / Users / Webhooks / Health --------
class TestOther:
    def test_dashboard(self, session, auth):
        r = session.get(f"{BASE_URL}/api/dashboard", headers=auth, timeout=60)
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_notifications(self, session, auth):
        r = session.get(f"{BASE_URL}/api/notifications", headers=auth, timeout=30)
        assert r.status_code == 200

    def test_notifications_unread(self, session, auth):
        r = session.get(f"{BASE_URL}/api/notifications/unread-count", headers=auth, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, dict)

    def test_telecontrol_status(self, session, auth):
        r = session.get(f"{BASE_URL}/api/telecontrol/status", headers=auth, timeout=30)
        assert r.status_code == 200

    def test_scrapers_health(self, session, auth):
        r = session.get(f"{BASE_URL}/api/scrapers/health", headers=auth, timeout=30)
        assert r.status_code == 200
        d = r.json()
        # accept either "overall" or "status" keyed response
        assert isinstance(d, dict)

    def test_users_admin(self, session, auth):
        r = session.get(f"{BASE_URL}/api/users", headers=auth, timeout=30)
        assert r.status_code == 200

    def test_webhooks_config(self, session, auth):
        r = session.get(f"{BASE_URL}/api/webhooks/config", headers=auth, timeout=30)
        assert r.status_code == 200

    def test_health(self, session):
        r = session.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200
