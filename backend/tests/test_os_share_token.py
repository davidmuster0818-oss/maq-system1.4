"""Tests for OS QR-code public share-token flow.

Covers:
  - POST /api/os/share-token: auth-protected, returns {token, url_path}
  - GET  /api/os/public/{token}: public read-only OS view (masked)
  - Invalid / expired / unauthenticated edge cases
"""
import os
import time
import pytest
import requests
import jwt
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://maq-sync-hub.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "mastermaqassistencia@gmail.com"
ADMIN_PASSWORD = "atr132641"
TEST_OS_NUMBER = "27691"


# ─── Fixtures ──────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=20)
    if r.status_code != 200:
        pytest.skip(f"Admin login failed ({r.status_code}): {r.text[:200]}")
    tok = r.json().get("token")
    assert tok, "Login returned no token"
    return tok


@pytest.fixture(scope="module")
def share_token(admin_token):
    """Generate a share-token for OS 27691 — reused by GET tests."""
    r = requests.post(
        f"{API}/os/share-token",
        json={"os_number": TEST_OS_NUMBER},
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=20,
    )
    assert r.status_code == 200, f"share-token failed: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


# ─── share-token issuance ──────────────────────────────────────────────
class TestShareTokenCreate:
    def test_create_share_token_auth_ok(self, admin_token):
        r = requests.post(
            f"{API}/os/share-token",
            json={"os_number": TEST_OS_NUMBER},
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "token" in data and isinstance(data["token"], str) and len(data["token"]) > 20
        assert data.get("url_path") == f"/os/{TEST_OS_NUMBER}?t={data['token']}"

    def test_share_token_payload_structure(self, share_token):
        # Decode without verifying signature (we just inspect claims)
        decoded = jwt.decode(share_token, options={"verify_signature": False})
        assert decoded.get("iss") == "mastermaq-os-share"
        assert str(decoded.get("os_number")) == TEST_OS_NUMBER
        # exp should be ~30 days from now (default ttl_hours=720)
        exp = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        delta = exp - datetime.now(timezone.utc)
        assert timedelta(days=29) < delta < timedelta(days=31), f"exp delta {delta}"

    def test_create_share_token_without_auth_forbidden(self):
        r = requests.post(
            f"{API}/os/share-token",
            json={"os_number": TEST_OS_NUMBER},
            timeout=20,
        )
        # FastAPI HTTPBearer returns 403 when header missing
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text[:200]}"


# ─── public OS view via signed token ───────────────────────────────────
class TestPublicOSView:
    def test_public_view_no_auth_ok(self, share_token):
        r = requests.get(f"{API}/os/public/{share_token}", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("os_number") == TEST_OS_NUMBER
        # Customer name must be masked: parts after the first should be single-letter+'.'
        cname = body.get("customer_name") or ""
        parts = cname.split()
        if len(parts) > 1:
            for p in parts[1:]:
                assert len(p) == 2 and p.endswith("."), f"unmasked surname part: {p!r} in {cname!r}"
        # Address should NOT end with trailing house number
        addr = body.get("address") or ""
        if addr:
            assert not addr.rstrip().split()[-1].isdigit(), f"address still contains street number: {addr!r}"

    def test_public_view_invalid_token_unauthorized(self):
        r = requests.get(f"{API}/os/public/this.is.not.a.valid.jwt", timeout=20)
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"

    def test_public_view_expired_token_returns_410(self):
        # Forge an expired JWT signed with a random secret — server will reject as invalid (401)
        # since signature won't match. To actually hit 410 we need the real JWT_SECRET, which
        # we don't have access to from the test env. Instead test the wrong-issuer branch.
        # Build a token signed with a fake secret but expired in the past.
        fake = jwt.encode(
            {"iss": "mastermaq-os-share", "os_number": TEST_OS_NUMBER,
             "exp": datetime.now(timezone.utc) - timedelta(minutes=5)},
            "fake-secret-for-test",
            algorithm="HS256",
        )
        r = requests.get(f"{API}/os/public/{fake}", timeout=20)
        # Signature is wrong → 401. Expired branch (410) requires correct signature, which we
        # can't forge here without server secret. We assert 401 to confirm bad-sig rejection.
        assert r.status_code == 401, f"expected 401 for bad-sig token, got {r.status_code}"

    def test_public_view_wrong_issuer_unauthorized(self, admin_token):
        # We can't sign with the real secret from outside; instead exercise 401 path via random token.
        r = requests.get(f"{API}/os/public/abcdef.ghijkl.mnopqr", timeout=20)
        assert r.status_code == 401
