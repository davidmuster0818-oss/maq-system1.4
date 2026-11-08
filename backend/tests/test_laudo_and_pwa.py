"""
Test Laudo Generation API and PWA Endpoints
Tests for Mastermaq OS Management System - Iteration 4
"""
import pytest
import requests
import os
import json

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://tech-assist-fix.preview.emergentagent.com"

# Test credentials
TEST_EMAIL = "mastermaqassistencia@gmail.com"
TEST_PASSWORD = "atr132641"


class TestAuthentication:
    """Authentication tests"""
    
    def test_login_success(self):
        """Test login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "Token not returned"
        assert len(data["token"]) > 0, "Token is empty"
        print(f"✓ Login successful, token received")

    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "wrong@example.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✓ Invalid login properly rejected")


@pytest.fixture
def auth_token():
    """Get authentication token for protected endpoints"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code == 200:
        return response.json()["token"]
    pytest.skip("Authentication failed")


@pytest.fixture
def auth_headers(auth_token):
    """Get headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestServiceOrdersAPI:
    """Service Orders API Tests"""
    
    def test_get_service_orders(self, auth_headers):
        """Test fetching service orders"""
        response = requests.get(f"{BASE_URL}/api/service-orders", headers=auth_headers)
        assert response.status_code == 200, f"Failed to get orders: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✓ Fetched {len(data)} service orders")
        return data

    def test_get_statuses(self, auth_headers):
        """Test fetching available statuses"""
        response = requests.get(f"{BASE_URL}/api/service-orders/statuses", headers=auth_headers)
        assert response.status_code == 200, f"Failed to get statuses: {response.text}"
        data = response.json()
        assert "statuses" in data, "Statuses key missing"
        assert isinstance(data["statuses"], list), "Statuses should be a list"
        print(f"✓ Fetched {len(data['statuses'])} statuses: {data['statuses'][:5]}...")

    def test_find_em_auditoria_order(self, auth_headers):
        """Find an order with 'Em auditoria' status for Laudo testing"""
        response = requests.get(f"{BASE_URL}/api/service-orders", headers=auth_headers)
        assert response.status_code == 200
        orders = response.json()
        
        em_auditoria_orders = [o for o in orders if o.get('status') == 'Em auditoria']
        print(f"✓ Found {len(em_auditoria_orders)} orders with 'Em auditoria' status")
        
        if em_auditoria_orders:
            print(f"  Sample OS number: {em_auditoria_orders[0].get('os_number')}")
        return em_auditoria_orders


class TestLaudoGeneration:
    """Laudo (Technical Report) Generation API Tests"""
    
    def get_test_laudo_data(self):
        """Create test laudo data"""
        return {
            "os_number": "TEST12345",
            "customer_name": "Test Customer",
            "model": "Test Model",
            "serial_number": "SN123456",
            "batch": "BATCH001",
            "brand": "Test Brand",
            "service_type": "Garantia",
            "reported_defect": "Test defect description",
            "technical_diagnosis": "Test diagnosis",
            "installation_correct": "SIM",
            "required_parts": "Nenhuma",
            "images": [],  # Empty images for basic test
            "technical_notes": "Test technical notes",
            "final_status": "Produto reparado com sucesso",
            "location": "BELO HORIZONTE",
            "date": "15/01/2026",
            "technician": "Test Technician"
        }

    def test_generate_docx_success(self, auth_headers):
        """Test DOCX generation endpoint"""
        laudo_data = self.get_test_laudo_data()
        
        response = requests.post(
            f"{BASE_URL}/api/laudo/generate-docx",
            headers=auth_headers,
            json=laudo_data
        )
        
        assert response.status_code == 200, f"DOCX generation failed: {response.text}"
        assert response.headers.get('content-type') == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', \
            f"Wrong content type: {response.headers.get('content-type')}"
        assert len(response.content) > 0, "DOCX content is empty"
        
        # Verify it's a valid DOCX (starts with PK - ZIP format)
        assert response.content[:2] == b'PK', "Invalid DOCX file format"
        
        print(f"✓ DOCX generated successfully, size: {len(response.content)} bytes")

    def test_generate_pdf_success(self, auth_headers):
        """Test PDF generation endpoint"""
        laudo_data = self.get_test_laudo_data()
        
        response = requests.post(
            f"{BASE_URL}/api/laudo/generate-pdf",
            headers=auth_headers,
            json=laudo_data
        )
        
        assert response.status_code == 200, f"PDF generation failed: {response.text}"
        assert response.headers.get('content-type') == 'application/pdf', \
            f"Wrong content type: {response.headers.get('content-type')}"
        assert len(response.content) > 0, "PDF content is empty"
        
        # Verify it's a valid PDF (starts with %PDF)
        assert response.content[:4] == b'%PDF', "Invalid PDF file format"
        
        print(f"✓ PDF generated successfully, size: {len(response.content)} bytes")

    def test_generate_laudo_unauthorized(self):
        """Test that laudo endpoints require authentication"""
        laudo_data = self.get_test_laudo_data()
        
        # Test without auth header
        response = requests.post(f"{BASE_URL}/api/laudo/generate-docx", json=laudo_data)
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        
        response = requests.post(f"{BASE_URL}/api/laudo/generate-pdf", json=laudo_data)
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        
        print(f"✓ Laudo endpoints properly require authentication")

    def test_generate_docx_with_base64_image(self, auth_headers):
        """Test DOCX generation with a base64 image"""
        laudo_data = self.get_test_laudo_data()
        
        # Small valid 1x1 red PNG image in base64
        test_image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
        laudo_data["images"] = [test_image]
        
        response = requests.post(
            f"{BASE_URL}/api/laudo/generate-docx",
            headers=auth_headers,
            json=laudo_data
        )
        
        assert response.status_code == 200, f"DOCX with image generation failed: {response.text}"
        assert len(response.content) > 0, "DOCX content is empty"
        print(f"✓ DOCX with image generated successfully, size: {len(response.content)} bytes")


class TestPWAEndpoints:
    """PWA (Progressive Web App) Related Tests"""
    
    def test_manifest_accessible(self):
        """Test manifest.json is accessible"""
        response = requests.get(f"{BASE_URL}/manifest.json")
        assert response.status_code == 200, f"Manifest not accessible: {response.status_code}"
        
        data = response.json()
        assert "name" in data, "Manifest missing 'name'"
        assert "short_name" in data, "Manifest missing 'short_name'"
        assert "start_url" in data, "Manifest missing 'start_url'"
        assert "display" in data, "Manifest missing 'display'"
        assert "icons" in data, "Manifest missing 'icons'"
        
        print(f"✓ Manifest.json accessible - App name: {data.get('name')}")

    def test_service_worker_accessible(self):
        """Test service-worker.js is accessible"""
        response = requests.get(f"{BASE_URL}/service-worker.js")
        assert response.status_code == 200, f"Service worker not accessible: {response.status_code}"
        assert len(response.text) > 0, "Service worker is empty"
        assert 'addEventListener' in response.text, "Service worker doesn't look valid"
        print(f"✓ Service worker accessible, size: {len(response.text)} chars")

    def test_offline_page_accessible(self):
        """Test offline.html is accessible"""
        response = requests.get(f"{BASE_URL}/offline.html")
        assert response.status_code == 200, f"Offline page not accessible: {response.status_code}"
        assert "offline" in response.text.lower() or "Sem conexão" in response.text, \
            "Offline page doesn't contain expected content"
        print(f"✓ Offline page accessible")


class TestSyncAndFilters:
    """Test Sync and Filter functionality"""
    
    def test_sync_endpoint(self, auth_headers):
        """Test sync trigger endpoint"""
        response = requests.post(f"{BASE_URL}/api/telecontrol/sync", headers=auth_headers)
        # Sync may return 200 or 202 or 503 (if playwright not available)
        assert response.status_code in [200, 202, 503], f"Unexpected status: {response.status_code}"
        if response.status_code == 503:
            # Sync might fail if Playwright or Telecontrol is unavailable - this is acceptable
            print(f"⚠ Sync endpoint returned 503 (Playwright/Telecontrol may be unavailable)")
        else:
            print(f"✓ Sync endpoint responded: {response.status_code}")

    def test_unread_count(self, auth_headers):
        """Test unread count endpoint"""
        response = requests.get(f"{BASE_URL}/api/notifications/unread-count", headers=auth_headers)
        assert response.status_code == 200, f"Unread count failed: {response.text}"
        data = response.json()
        assert "count" in data, "Count key missing"
        print(f"✓ Unread count: {data['count']}")


class TestAPIBasics:
    """Basic API Health Tests"""
    
    def test_api_root(self):
        """Test API root endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200, f"API root failed: {response.status_code}"
        data = response.json()
        assert "message" in data, "Message key missing"
        print(f"✓ API root accessible: {data.get('message')}")

    def test_frontend_loads(self):
        """Test frontend is accessible"""
        response = requests.get(f"{BASE_URL}/")
        assert response.status_code == 200, f"Frontend not accessible: {response.status_code}"
        assert "Mastermaq" in response.text, "Page doesn't contain expected content"
        print(f"✓ Frontend loads successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
