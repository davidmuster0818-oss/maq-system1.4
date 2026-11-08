"""
Test Iteration 5 - Status Fixes, Gerar Laudo for All, LaudoModal Layout
Tests for Mastermaq OS Management System

Focus:
1. Multiple statuses in filter (was only Em auditoria/Finalizada, now 7+)
2. Gerar Laudo button now available for all OS statuses
3. LaudoModal Avançar button now visible without scrolling
4. Print layout uses flex instead of fixed heights
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://tech-assist-fix.preview.emergentagent.com"

# Test credentials
TEST_EMAIL = "mastermaqassistencia@gmail.com"
TEST_PASSWORD = "atr132641"


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


class TestStatusFeatures:
    """Tests for improved status detection and filtering"""
    
    def test_statuses_endpoint_returns_multiple_statuses(self, auth_headers):
        """Verify the statuses endpoint returns 5+ distinct statuses"""
        response = requests.get(f"{BASE_URL}/api/service-orders/statuses", headers=auth_headers)
        
        assert response.status_code == 200, f"Failed to get statuses: {response.text}"
        data = response.json()
        
        assert "statuses" in data, "Statuses key missing"
        statuses = data["statuses"]
        assert isinstance(statuses, list), "Statuses should be a list"
        
        # Should have 5+ distinct statuses (per requirement)
        assert len(statuses) >= 5, f"Expected at least 5 statuses, got {len(statuses)}: {statuses}"
        
        print(f"✓ Statuses endpoint returns {len(statuses)} distinct statuses: {statuses}")
    
    def test_service_orders_have_diverse_statuses(self, auth_headers):
        """Verify service orders have multiple different statuses in the database"""
        response = requests.get(f"{BASE_URL}/api/service-orders", headers=auth_headers)
        
        assert response.status_code == 200, f"Failed to get orders: {response.text}"
        orders = response.json()
        
        # Get unique statuses from orders
        statuses = set()
        for order in orders:
            status = order.get('status', '')
            if status:  # Filter empty statuses
                statuses.add(status)
        
        # Should have multiple different statuses (not just Em auditoria/Finalizada)
        assert len(statuses) >= 5, f"Expected at least 5 different statuses, got {len(statuses)}: {statuses}"
        
        print(f"✓ Orders have {len(statuses)} distinct statuses: {statuses}")
    
    def test_fup_statuses_present(self, auth_headers):
        """Verify F/Up statuses are correctly captured by the scraper"""
        response = requests.get(f"{BASE_URL}/api/service-orders/statuses", headers=auth_headers)
        
        assert response.status_code == 200
        statuses = response.json().get("statuses", [])
        
        # Check for F/Up statuses (these should be captured by improved scraper)
        fup_statuses = [s for s in statuses if s.startswith("F/Up")]
        assert len(fup_statuses) >= 1, f"Expected at least one F/Up status, got: {fup_statuses}"
        
        print(f"✓ F/Up statuses captured: {fup_statuses}")


class TestLaudoAvailability:
    """Tests for Laudo button availability for all statuses"""
    
    def test_laudo_docx_works_for_any_order(self, auth_headers):
        """Test DOCX generation works for any order (not status-restricted)"""
        # Get first available order (regardless of status)
        response = requests.get(f"{BASE_URL}/api/service-orders", headers=auth_headers)
        assert response.status_code == 200
        orders = response.json()
        assert len(orders) > 0, "No orders found"
        
        order = orders[0]
        os_number = order.get('os_number')
        status = order.get('status', 'unknown')
        
        # Generate laudo for this order (should work regardless of status)
        laudo_data = {
            "os_number": os_number,
            "customer_name": order.get('customer_name', ''),
            "model": order.get('model', ''),
            "serial_number": order.get('serial_number', ''),
            "batch": order.get('batch', ''),
            "brand": order.get('brand', ''),
            "service_type": order.get('service_type', ''),
            "reported_defect": order.get('reported_defect', ''),
            "technical_diagnosis": "Test diagnosis",
            "installation_correct": "SIM",
            "required_parts": "Nenhuma",
            "images": [],
            "technical_notes": "Test notes",
            "final_status": "Test status",
            "location": "BELO HORIZONTE",
            "date": "06/03/2026",
            "technician": "Test Tech"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/laudo/generate-docx",
            headers=auth_headers,
            json=laudo_data
        )
        
        assert response.status_code == 200, f"DOCX generation failed for order {os_number} (status: {status}): {response.text}"
        assert response.content[:2] == b'PK', "Invalid DOCX format"
        
        print(f"✓ DOCX generated successfully for OS #{os_number} with status '{status}'")
    
    def test_laudo_pdf_works_for_any_order(self, auth_headers):
        """Test PDF generation works for any order (not status-restricted)"""
        response = requests.get(f"{BASE_URL}/api/service-orders", headers=auth_headers)
        orders = response.json()
        
        order = orders[0]
        os_number = order.get('os_number')
        
        laudo_data = {
            "os_number": os_number,
            "customer_name": order.get('customer_name', ''),
            "model": order.get('model', ''),
            "technical_diagnosis": "Test",
            "installation_correct": "SIM",
            "required_parts": "Nenhuma",
            "images": [],
            "technical_notes": "",
            "final_status": "Test",
            "location": "BELO HORIZONTE",
            "date": "06/03/2026",
            "technician": "Test"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/laudo/generate-pdf",
            headers=auth_headers,
            json=laudo_data
        )
        
        assert response.status_code == 200, f"PDF generation failed: {response.text}"
        assert response.content[:4] == b'%PDF', "Invalid PDF format"
        
        print(f"✓ PDF generated successfully for OS #{os_number}")


class TestSyncAndDataIntegrity:
    """Tests for sync functionality and data integrity"""
    
    def test_orders_have_required_fields(self, auth_headers):
        """Verify all orders have required fields populated"""
        response = requests.get(f"{BASE_URL}/api/service-orders", headers=auth_headers)
        orders = response.json()
        
        required_fields = ['os_number', 'customer_name', 'registration_date', 'source']
        
        for order in orders[:5]:  # Check first 5
            for field in required_fields:
                assert field in order, f"Order missing field: {field}"
        
        # Count orders by source
        telecontrol_count = sum(1 for o in orders if o.get('source') == 'telecontrol')
        local_count = sum(1 for o in orders if o.get('source') != 'telecontrol')
        
        print(f"✓ Orders have required fields. Telecontrol: {telecontrol_count}, Local: {local_count}")
    
    def test_telecontrol_orders_have_updated_statuses(self, auth_headers):
        """Verify Telecontrol orders have updated statuses (not just Em auditoria)"""
        response = requests.get(f"{BASE_URL}/api/service-orders", headers=auth_headers)
        orders = response.json()
        
        telecontrol_orders = [o for o in orders if o.get('source') == 'telecontrol']
        assert len(telecontrol_orders) > 0, "No Telecontrol orders found"
        
        # Get statuses of telecontrol orders
        tc_statuses = set(o.get('status', '') for o in telecontrol_orders)
        tc_statuses.discard('')  # Remove empty
        
        # Should have variety of statuses (not just Em auditoria)
        assert len(tc_statuses) > 2, f"Expected more than 2 statuses for Telecontrol orders, got: {tc_statuses}"
        
        print(f"✓ Telecontrol orders have {len(tc_statuses)} distinct statuses: {tc_statuses}")


class TestBackendBasics:
    """Basic backend tests"""
    
    def test_login_success(self):
        """Test login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        assert "token" in response.json()
        print("✓ Login successful")
    
    def test_api_root(self):
        """Test API root endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        print("✓ API root accessible")
    
    def test_frontend_loads(self):
        """Test frontend is accessible"""
        response = requests.get(f"{BASE_URL}/")
        assert response.status_code == 200
        assert "Mastermaq" in response.text
        print("✓ Frontend loads")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
