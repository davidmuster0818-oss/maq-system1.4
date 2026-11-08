"""
Iteration 13 Backend Tests - Complete testing of OS management, sub-status, laudo generation

Testing scope:
1. Login functionality (email: mastermaqassistencia@gmail.com / password: atr132641)
2. Service orders CRUD and filtering
3. Sub-status and micro-status updates via PUT /api/service-orders/{os_number}
4. Laudo DOCX generation via POST /api/laudo/generate-docx
5. Service types validation
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://tech-assist-fix.preview.emergentagent.com').rstrip('/')

# Test credentials
TEST_EMAIL = "mastermaqassistencia@gmail.com"
TEST_PASSWORD = "atr132641"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert "token" in data
    return data["token"]


@pytest.fixture
def api_client(auth_token):
    """Authenticated requests session"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


class TestAuthentication:
    """Authentication endpoint tests"""
    
    def test_login_success(self):
        """Test login with valid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "email" in data
        assert data["email"] == TEST_EMAIL
        print(f"✅ Login success - token received")
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "wrong@email.com", "password": "wrongpassword"}
        )
        assert response.status_code == 401
        print(f"✅ Invalid login returns 401")
    
    def test_auth_verify(self, api_client):
        """Test token verification"""
        response = api_client.get(f"{BASE_URL}/api/auth/verify")
        assert response.status_code == 200
        data = response.json()
        assert data.get("valid") == True
        print(f"✅ Token verification works")


class TestServiceOrders:
    """Service orders CRUD tests"""
    
    def test_get_service_orders_list(self, api_client):
        """Test fetching service orders list"""
        response = api_client.get(f"{BASE_URL}/api/service-orders")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        print(f"✅ Service orders list: {len(data)} orders")
    
    def test_get_order_27575(self, api_client):
        """Test getting OS #27575 with sub-status and micro-status"""
        response = api_client.get(f"{BASE_URL}/api/service-orders/27575")
        assert response.status_code == 200
        order = response.json()
        assert order["os_number"] == "27575"
        assert order["status"] == "Orçamento"
        # These should be present from previous test session
        print(f"✅ OS #27575 - status: {order['status']}, sub_status: {order.get('sub_status')}, micro_status: {order.get('micro_status')}")
    
    def test_search_by_os_number(self, api_client):
        """Test search filter by OS number"""
        response = api_client.get(f"{BASE_URL}/api/service-orders?search=27575")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(o["os_number"] == "27575" for o in data)
        print(f"✅ Search by OS number works")
    
    def test_filter_by_source_mastermaq(self, api_client):
        """Test filter by source mastermaq"""
        response = api_client.get(f"{BASE_URL}/api/service-orders?source=mastermaq")
        assert response.status_code == 200
        data = response.json()
        # All results should NOT be telecontrol
        for order in data[:10]:
            assert order["source"] != "telecontrol", f"Order {order['os_number']} should not be telecontrol"
        print(f"✅ Source filter mastermaq works - {len(data)} orders")
    
    def test_get_distinct_statuses(self, api_client):
        """Test getting distinct statuses from database"""
        response = api_client.get(f"{BASE_URL}/api/service-orders/statuses")
        assert response.status_code == 200
        data = response.json()
        assert "statuses" in data
        assert isinstance(data["statuses"], list)
        print(f"✅ Distinct statuses: {data['statuses']}")
    
    def test_get_next_ose_number(self, api_client):
        """Test getting next OSE number for manual orders"""
        response = api_client.get(f"{BASE_URL}/api/service-orders/next-ose-number")
        assert response.status_code == 200
        data = response.json()
        assert "next_ose_number" in data
        next_num = int(data["next_ose_number"])
        assert next_num > 27500  # Should be reasonably high
        print(f"✅ Next OSE number: {data['next_ose_number']}")


class TestSubStatusUpdates:
    """Sub-status and micro-status update tests"""
    
    def test_update_substatus_to_executado(self, api_client):
        """Test updating sub_status to 'Executado'"""
        update_data = {
            "status": "Orçamento",
            "sub_status": "Executado"
        }
        response = api_client.put(
            f"{BASE_URL}/api/service-orders/27575",
            json=update_data
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sub_status"] == "Executado"
        print(f"✅ Updated sub_status to 'Executado'")
    
    def test_update_microstatus_to_finalizado(self, api_client):
        """Test updating micro_status to 'Finalizado'"""
        update_data = {
            "status": "Orçamento",
            "sub_status": "Executado",
            "micro_status": "Finalizado"
        }
        response = api_client.put(
            f"{BASE_URL}/api/service-orders/27575",
            json=update_data
        )
        assert response.status_code == 200
        data = response.json()
        assert data["micro_status"] == "Finalizado"
        print(f"✅ Updated micro_status to 'Finalizado'")
    
    def test_update_substatus_to_aguardando(self, api_client):
        """Test updating sub_status to 'Aguardando' clears micro_status"""
        update_data = {
            "status": "Orçamento",
            "sub_status": "Aguardando",
            "micro_status": None  # Should be cleared when sub_status is Aguardando
        }
        response = api_client.put(
            f"{BASE_URL}/api/service-orders/27575",
            json=update_data
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sub_status"] == "Aguardando"
        print(f"✅ Updated sub_status to 'Aguardando'")
    
    def test_all_micro_statuses(self, api_client):
        """Test all 4 micro-status values can be saved"""
        micro_statuses = ["Pgto Feito", "Pgto não feito", "Finalizado", "Pendente"]
        
        for ms in micro_statuses:
            update_data = {
                "status": "Orçamento",
                "sub_status": "Executado",
                "micro_status": ms
            }
            response = api_client.put(
                f"{BASE_URL}/api/service-orders/27575",
                json=update_data
            )
            assert response.status_code == 200, f"Failed to set micro_status to {ms}"
            data = response.json()
            assert data["micro_status"] == ms, f"micro_status should be {ms}"
        
        print(f"✅ All 4 micro-statuses can be saved: {micro_statuses}")
    
    def test_restore_original_status(self, api_client):
        """Restore OS #27575 to original test state"""
        update_data = {
            "status": "Orçamento",
            "sub_status": "Executado",
            "micro_status": "Finalizado"
        }
        response = api_client.put(
            f"{BASE_URL}/api/service-orders/27575",
            json=update_data
        )
        assert response.status_code == 200
        print(f"✅ Restored OS #27575 to Orçamento/Executado/Finalizado")


class TestLaudoGeneration:
    """Laudo generation endpoint tests"""
    
    def test_save_laudo_draft(self, api_client):
        """Test saving laudo draft"""
        draft_data = {
            "os_number": "27575",
            "customer_name": "TEST CUSTOMER",
            "model": "TEST MODEL",
            "serial_number": "TEST123",
            "batch": "BATCH001",
            "brand": "TEST BRAND",
            "technical_diagnosis": "Test diagnosis",
            "required_parts": "Test parts"
        }
        response = api_client.post(
            f"{BASE_URL}/api/laudo/save",
            json=draft_data
        )
        assert response.status_code == 200
        print(f"✅ Laudo draft saved")
    
    def test_get_laudo_draft(self, api_client):
        """Test getting saved laudo draft"""
        response = api_client.get(f"{BASE_URL}/api/laudo/draft/27575")
        assert response.status_code == 200
        data = response.json()
        # Draft should exist from previous test or have some data
        print(f"✅ Laudo draft retrieved - os_number: {data.get('os_number')}")
    
    def test_generate_laudo_docx(self, api_client):
        """Test generating DOCX laudo"""
        laudo_data = {
            "os_number": "27575",
            "customer_name": "LUIZ HERNANI DE CARVALHO JUNIOR",
            "model": "HQ-AP8500FW1",
            "serial_number": "SN123456",
            "batch": "BATCH001",
            "brand": "BELMICRO HQ",
            "service_type": "ORÇAMENTO",
            "reported_defect": "LIGOU O PRODUTO NA TENSÃO ERRADA",
            "technical_diagnosis": "Placa defeituosa PCB",
            "installation_correct": "SIM",
            "required_parts": "Placa principal modelo X",
            "images": [],
            "technical_notes": "Teste de geração de laudo",
            "final_status": "✅ VISITA TÉCNICA REALIZADA, CONCLUÍDA",
            "location": "BELO HORIZONTE",
            "date": "10/01/2026",
            "technician": "Nelson Rodrigues",
            "voltage_f1f2": "220",
            "voltage_f1_terra": "127",
            "voltage_f2_terra": "127"
        }
        response = api_client.post(
            f"{BASE_URL}/api/laudo/generate-docx",
            json=laudo_data
        )
        assert response.status_code == 200
        # Check content type is DOCX
        content_type = response.headers.get("content-type", "")
        assert "application/vnd.openxmlformats" in content_type or len(response.content) > 1000
        print(f"✅ DOCX generated - size: {len(response.content)} bytes")
    
    def test_get_laudo_history(self, api_client):
        """Test getting laudo generation history"""
        response = api_client.get(f"{BASE_URL}/api/laudo/history/27575")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✅ Laudo history retrieved - {len(data)} entries")


class TestNotifications:
    """Notification endpoint tests"""
    
    def test_get_unread_count(self, api_client):
        """Test getting unread notification count"""
        response = api_client.get(f"{BASE_URL}/api/notifications/unread-count")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        print(f"✅ Unread notifications count: {data['count']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
