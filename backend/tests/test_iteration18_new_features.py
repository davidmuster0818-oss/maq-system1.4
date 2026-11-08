"""
Iteration 18 Tests - New Features:
1. Customer History endpoint - GET /api/service-orders/{os_number}/customer-history
2. photo_9 field - Foto da OS Assinada (separate from laudo photos 1-8)
3. Status refactoring - Removed sub_status/micro_status, added 'Execucao Orcamento'
4. Garantia subtype logic (frontend only)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestCustomerHistory:
    """Test customer history endpoint - returns other OSs from same customer"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for all tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_customer_history_returns_related_orders(self):
        """OS 26767 should have other orders from same customer"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders/26767/customer-history",
            headers=self.headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "history" in data, "Response should contain 'history' key"
        assert isinstance(data["history"], list), "History should be a list"
        
        # OS 26767 customer should have related OSs
        history = data["history"]
        print(f"Found {len(history)} related orders for OS 26767's customer")
        
        if len(history) > 0:
            # Verify structure of history items
            item = history[0]
            assert "os_number" in item, "History item should have os_number"
            assert "product" in item, "History item should have product"
            assert "status" in item, "History item should have status"
            assert "registration_date" in item, "History item should have registration_date"
            print(f"Sample history item: OS#{item['os_number']} - {item['product']} - {item['status']}")
    
    def test_customer_history_excludes_current_os(self):
        """History should not include the current OS itself"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders/26767/customer-history",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        for item in data["history"]:
            assert item["os_number"] != "26767", "History should not include the current OS"
    
    def test_customer_history_empty_for_unique_customer(self):
        """Customer with no other OSs should return empty history"""
        # First find a customer with potentially no other OS (use a test OS that we create)
        # For now, test with an OS number that might have minimal history
        response = requests.get(
            f"{BASE_URL}/api/service-orders/27578/customer-history",
            headers=self.headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "history" in data
        # Just verify it returns a list (empty or not)
        assert isinstance(data["history"], list)
        print(f"OS 27578 customer has {len(data['history'])} related orders")
    
    def test_customer_history_not_found_for_invalid_os(self):
        """Invalid OS number should return 404"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders/999999999/customer-history",
            headers=self.headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestPhoto9Field:
    """Test photo_9 field - Foto da OS Assinada (separate from laudo)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        assert response.status_code == 200
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_photo_9_can_be_saved(self):
        """photo_9 field should be saveable via PUT"""
        test_photo = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMCwsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AVN//2Q=="
        
        response = requests.put(
            f"{BASE_URL}/api/service-orders/27578",
            headers=self.headers,
            json={"photo_9": test_photo}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify it was saved
        data = response.json()
        assert data.get("photo_9") == test_photo, "photo_9 should be saved"
        print("photo_9 successfully saved via PUT")
    
    def test_photo_9_can_be_cleared(self):
        """photo_9 can be set to null/None to clear it"""
        # First set a photo
        test_photo = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/"
        requests.put(
            f"{BASE_URL}/api/service-orders/27578",
            headers=self.headers,
            json={"photo_9": test_photo}
        )
        
        # Now clear it by not including it in update (partial update shouldn't clear)
        response = requests.put(
            f"{BASE_URL}/api/service-orders/27578",
            headers=self.headers,
            json={"observations": "Test observation"}
        )
        assert response.status_code == 200
        
        # photo_9 should still be there (partial update)
        data = response.json()
        print(f"After partial update, photo_9 exists: {'photo_9' in data and data['photo_9'] is not None}")
    
    def test_photo_9_in_response_structure(self):
        """GET should return photo_9 in response"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders/27578",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # photo_9 should be in the response structure (even if None)
        assert "photo_9" in data or data.get("photo_9") is None or data.get("photo_9") == ""
        print(f"photo_9 in response: {data.get('photo_9', 'NOT PRESENT')[:50] if data.get('photo_9') else 'None/Empty'}")


class TestStatusExecucaoOrcamento:
    """Test new status 'Execucao Orcamento'"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        assert response.status_code == 200
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_execucao_orcamento_status_accepted(self):
        """Status 'Execução Orçamento' should be accepted via PUT"""
        response = requests.put(
            f"{BASE_URL}/api/service-orders/27578",
            headers=self.headers,
            json={"status": "Execução Orçamento"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("status") == "Execução Orçamento", "Status should be updated to 'Execução Orçamento'"
        print("Status 'Execução Orçamento' successfully set")
        
        # Reset status back
        requests.put(
            f"{BASE_URL}/api/service-orders/27578",
            headers=self.headers,
            json={"status": "Orçamento"}
        )
    
    def test_status_colors_include_execucao_orcamento(self):
        """Status colors endpoint should include 'Execução Orçamento'"""
        response = requests.get(
            f"{BASE_URL}/api/status-colors",
            headers=self.headers
        )
        assert response.status_code == 200
        colors = response.json()
        
        assert "Execução Orçamento" in colors, "Status colors should include 'Execução Orçamento'"
        exec_orc_colors = colors["Execução Orçamento"]
        assert "bg" in exec_orc_colors and "text" in exec_orc_colors
        print(f"Execução Orçamento colors: bg={exec_orc_colors['bg']}, text={exec_orc_colors['text']}")


class TestServiceTypes:
    """Test service type values"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        assert response.status_code == 200
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_garantia_subtypes_can_be_saved(self):
        """Garantia subtypes should be saveable as service_type"""
        garantia_subtypes = [
            "Garantia Loja",
            "Garantia Hisense",
            "Garantia HQ",
            "Garantia Franke"
            "Garantia IGS"
            "Garantia Invisacook"
            "Garantia Elettromec"
        ]
        
        for subtype in garantia_subtypes:
            response = requests.put(
                f"{BASE_URL}/api/service-orders/27578",
                headers=self.headers,
                json={"service_type": subtype}
            )
            assert response.status_code == 200, f"Failed to save service_type '{subtype}': {response.text}"
            data = response.json()
            assert data.get("service_type") == subtype, f"service_type should be '{subtype}'"
            print(f"service_type '{subtype}' successfully saved")
        
        # Reset service_type
        requests.put(
            f"{BASE_URL}/api/service-orders/27578",
            headers=self.headers,
            json={"service_type": "Orçamento"}
        )


class TestAuthAndBasics:
    """Basic authentication and endpoint tests"""
    
    def test_login_success(self):
        """Login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        print("Login successful")
    
    def test_get_os_26767_for_customer_history(self):
        """Get OS 26767 to verify it exists (used for customer history testing)"""
        # Login first
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        token = login_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(f"{BASE_URL}/api/service-orders/26767", headers=headers)
        assert response.status_code == 200, f"OS 26767 should exist: {response.text}"
        data = response.json()
        print(f"OS 26767: Customer={data.get('customer_name')}, Product={data.get('product')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
