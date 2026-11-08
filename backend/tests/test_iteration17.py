"""
Iteration 17 Tests: Client search endpoint, visit_fee validation, pagination, and search
Tests new features:
- GET /api/service-orders/search-clients?q=QUERY - returns grouped clients with os_count
- PUT /api/service-orders/{os} with visit_fee='' - should convert to null (no error)
- Pagination and search functionality (from iter 16)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(scope='class')
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("token")
    
    def test_login_returns_token(self):
        """POST /api/auth/login should return token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "email" in data
        assert len(data["token"]) > 0


class TestClientSearch:
    """Client search endpoint tests - NEW in iteration 17"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for all tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_search_clients_returns_grouped_results(self):
        """GET /api/service-orders/search-clients?q=WALDER returns grouped clients with os_count"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders/search-clients?q=WALDER",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "clients" in data
        assert len(data["clients"]) >= 1
        
        # Check client structure
        client = data["clients"][0]
        assert "customer_name" in client
        assert "phone1" in client
        assert "address" in client
        assert "os_count" in client
        assert "WALDER" in client["customer_name"].upper()
    
    def test_search_clients_returns_address_fields(self):
        """Client search returns all address fields for auto-fill"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders/search-clients?q=WALDER",
            headers=self.headers
        )
        data = response.json()
        client = data["clients"][0]
        
        # Verify all address fields are present
        assert "neighborhood" in client
        assert "city" in client
        assert "state" in client
        assert "cep" in client
    
    def test_search_clients_with_short_query(self):
        """GET /api/service-orders/search-clients?q=A returns empty (min 2 chars)"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders/search-clients?q=A",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["clients"] == []
    
    def test_search_clients_by_phone(self):
        """Client search works with phone number"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders/search-clients?q=31991",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        # Should return some results matching phone
        assert "clients" in data


class TestVisitFeeValidation:
    """visit_fee validation tests - NEW in iteration 17"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for all tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    def test_update_with_empty_visit_fee_string(self):
        """PUT /api/service-orders/27578 with visit_fee='' should not return error"""
        response = requests.put(
            f"{BASE_URL}/api/service-orders/27578",
            headers=self.headers,
            json={"visit_fee": ""}
        )
        # Main requirement: empty string should NOT cause validation error
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        # Empty string is converted to None by validator, then filtered out
        # So visit_fee field is not updated (remains unchanged)
        assert "visit_fee" in data  # field exists in response
    
    def test_update_with_valid_visit_fee(self):
        """PUT /api/service-orders/27578 with visit_fee=75.50 works"""
        response = requests.put(
            f"{BASE_URL}/api/service-orders/27578",
            headers=self.headers,
            json={"visit_fee": 75.50}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["visit_fee"] == 75.5
    
    def test_update_with_visit_fee_string_number(self):
        """PUT with visit_fee='100.00' as string should convert to float"""
        response = requests.put(
            f"{BASE_URL}/api/service-orders/27578",
            headers=self.headers,
            json={"visit_fee": "100.00"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["visit_fee"] == 100.0


class TestPagination:
    """Pagination tests - verified in iteration 16, quick retest"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_pagination_returns_correct_structure(self):
        """GET /api/service-orders?page=1&limit=10 returns paginated response"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders?page=1&limit=10",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check structure
        assert "orders" in data
        assert "total" in data
        assert "page" in data
        assert "limit" in data
        assert "total_pages" in data
        
        # Verify values
        assert data["page"] == 1
        assert data["limit"] == 10
        assert len(data["orders"]) <= 10
    
    def test_pagination_page_2_different_orders(self):
        """GET /api/service-orders?page=2&limit=5 returns different orders"""
        response1 = requests.get(
            f"{BASE_URL}/api/service-orders?page=1&limit=5",
            headers=self.headers
        )
        response2 = requests.get(
            f"{BASE_URL}/api/service-orders?page=2&limit=5",
            headers=self.headers
        )
        
        orders1 = [o["os_number"] for o in response1.json()["orders"]]
        orders2 = [o["os_number"] for o in response2.json()["orders"]]
        
        # Page 1 and page 2 should have different orders
        assert orders1 != orders2


class TestSearch:
    """Search tests - verified in iteration 16, quick retest"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        self.token = response.json().get("token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_search_by_neighborhood(self):
        """GET /api/service-orders?search=Barreiro returns results by neighborhood"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders?search=Barreiro",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] > 0
        # At least one result should have Barreiro in neighborhood
        neighborhoods = [o["neighborhood"] for o in data["orders"] if o.get("neighborhood")]
        assert any("BARREIRO" in n.upper() for n in neighborhoods)
    
    def test_search_by_city(self):
        """GET /api/service-orders?search=CONTAGEM returns results by city"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders?search=CONTAGEM",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] > 0
    
    def test_search_by_brand(self):
        """GET /api/service-orders?search=HISENSE returns results by brand"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders?search=HISENSE",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] > 0
        brands = [o["brand"] for o in data["orders"] if o.get("brand")]
        assert any("HISENSE" in b.upper() for b in brands)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
