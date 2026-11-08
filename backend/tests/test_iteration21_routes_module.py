"""
Test iteration 21 - Routes Module Testing for Roteiro functionality
Tests: GET/POST /api/routes/, POST /api/routes/geocode, POST /api/routes/cache-coords
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "mastermaqassistencia@gmail.com"
TEST_PASSWORD = "atr132641"


class TestAuth:
    """Authentication tests"""
    
    def test_login_success(self):
        """Test login returns JWT token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "Token not in response"
        assert len(data["token"]) > 0, "Token is empty"
        print(f"SUCCESS: Login returned token (length={len(data['token'])})")


@pytest.fixture(scope="class")
def auth_token():
    """Get authentication token for tests"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture
def auth_headers(auth_token):
    """Return headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestRoutesListEndpoint:
    """Tests for GET /api/routes/"""
    
    def test_list_routes(self, auth_headers):
        """Test GET /api/routes/ returns list"""
        response = requests.get(f"{BASE_URL}/api/routes/", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"SUCCESS: GET /api/routes/ returned {len(data)} routes")


class TestRoutesCreateEndpoint:
    """Tests for POST /api/routes/"""
    
    def test_create_route_success(self, auth_headers):
        """Test creating a new route"""
        route_data = {
            "name": f"TEST_ROUTE_{uuid.uuid4().hex[:8]}",
            "technician": "Test Technician",
            "date": "2026-01-16",
            "orders": [
                {
                    "os_number": "TEST001",
                    "customer_name": "Customer 1",
                    "neighborhood": "Centro",
                    "city": "Belo Horizonte",
                    "sequence": 1
                },
                {
                    "os_number": "TEST002",
                    "customer_name": "Customer 2",
                    "neighborhood": "Savassi",
                    "city": "Belo Horizonte",
                    "sequence": 2
                }
            ],
            "total_distance": "10 km",
            "total_duration": "30min",
            "status": "Pendente"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/routes/",
            json=route_data,
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "id" in data, "Response should contain route ID"
        assert data["name"] == route_data["name"], "Name mismatch"
        assert data["technician"] == route_data["technician"], "Technician mismatch"
        assert len(data["orders"]) == 2, "Should have 2 orders"
        assert data["status"] == "Pendente", "Status should be Pendente"
        
        # Cleanup - delete the test route
        route_id = data["id"]
        delete_response = requests.delete(
            f"{BASE_URL}/api/routes/{route_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == 200, "Cleanup failed"
        
        print(f"SUCCESS: Created and deleted test route {route_id}")
    
    def test_create_route_missing_technician(self, auth_headers):
        """Test creating route without required technician field"""
        route_data = {
            "name": "TEST_ROUTE_NO_TECH",
            "date": "2026-01-16",
            "orders": [{"os_number": "TEST001", "sequence": 1}]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/routes/",
            json=route_data,
            headers=auth_headers
        )
        # Should fail with 422 (validation error) because technician is required
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("SUCCESS: Missing technician correctly rejected with 422")


class TestRoutesGeocodeEndpoint:
    """Tests for POST /api/routes/geocode - cached coordinates lookup"""
    
    def test_geocode_uncached_os(self, auth_headers):
        """Test geocode endpoint returns uncached status for unknown OS"""
        os_numbers = ["TEST_UNKNOWN_OS_1", "TEST_UNKNOWN_OS_2"]
        
        response = requests.post(
            f"{BASE_URL}/api/routes/geocode",
            json={"os_numbers": os_numbers},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "results" in data, "Response should have results"
        assert "total" in data, "Response should have total"
        assert "cached" in data, "Response should have cached count"
        assert "uncached" in data, "Response should have uncached count"
        
        assert data["total"] == 2, "Should have 2 results"
        assert data["cached"] == 0, "Unknown OS should not be cached"
        assert data["uncached"] == 2, "Both should be uncached"
        
        # Check each result
        for result in data["results"]:
            assert "os_number" in result
            assert "lat" in result
            assert "lng" in result
            assert "cached" in result
            assert result["cached"] is False, "Should not be cached"
        
        print("SUCCESS: Geocode endpoint correctly returns uncached for unknown OS")
    
    def test_geocode_empty_list(self, auth_headers):
        """Test geocode endpoint with empty list"""
        response = requests.post(
            f"{BASE_URL}/api/routes/geocode",
            json={"os_numbers": []},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert data["total"] == 0
        assert data["cached"] == 0
        assert data["uncached"] == 0
        
        print("SUCCESS: Geocode handles empty list correctly")


class TestRoutesCacheCoordsEndpoint:
    """Tests for POST /api/routes/cache-coords - store coordinates"""
    
    def test_cache_coords_for_nonexistent_os(self, auth_headers):
        """Test caching coords for OS that doesn't exist"""
        coords = [
            {"os_number": "TEST_CACHE_NONEXISTENT", "lat": -19.92, "lng": -43.94}
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/routes/cache-coords",
            json={"coords": coords},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "updated" in data
        assert "total" in data
        # Will be 0 because OS doesn't exist in DB
        assert data["total"] == 1
        assert data["updated"] == 0, "Should not update non-existent OS"
        
        print("SUCCESS: Cache-coords handles non-existent OS correctly")
    
    def test_cache_coords_empty_list(self, auth_headers):
        """Test caching with empty coords list"""
        response = requests.post(
            f"{BASE_URL}/api/routes/cache-coords",
            json={"coords": []},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert data["updated"] == 0
        assert data["total"] == 0
        
        print("SUCCESS: Cache-coords handles empty list correctly")


class TestRoutesUpdateDeleteEndpoints:
    """Tests for PUT/DELETE /api/routes/{route_id}"""
    
    def test_update_and_delete_route(self, auth_headers):
        """Test create -> update -> delete flow"""
        # Create
        route_data = {
            "name": f"TEST_UPDATE_ROUTE_{uuid.uuid4().hex[:8]}",
            "technician": "Original Tech",
            "date": "2026-01-16",
            "orders": [{"os_number": "TEST_UPDATE_001", "sequence": 1}],
            "status": "Pendente"
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/routes/",
            json=route_data,
            headers=auth_headers
        )
        assert create_response.status_code == 200
        route_id = create_response.json()["id"]
        print(f"  Created route: {route_id}")
        
        # Update
        update_response = requests.put(
            f"{BASE_URL}/api/routes/{route_id}",
            json={"technician": "Updated Tech", "status": "Em andamento"},
            headers=auth_headers
        )
        assert update_response.status_code == 200
        updated_data = update_response.json()
        assert updated_data["technician"] == "Updated Tech"
        assert updated_data["status"] == "Em andamento"
        print(f"  Updated route: technician='Updated Tech', status='Em andamento'")
        
        # Verify with GET
        get_response = requests.get(
            f"{BASE_URL}/api/routes/{route_id}",
            headers=auth_headers
        )
        assert get_response.status_code == 200
        fetched_data = get_response.json()
        assert fetched_data["technician"] == "Updated Tech"
        print(f"  Verified: GET returns updated data")
        
        # Delete
        delete_response = requests.delete(
            f"{BASE_URL}/api/routes/{route_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == 200
        assert "message" in delete_response.json()
        print(f"  Deleted route")
        
        # Verify deleted
        verify_response = requests.get(
            f"{BASE_URL}/api/routes/{route_id}",
            headers=auth_headers
        )
        assert verify_response.status_code == 404
        print(f"SUCCESS: Full CRUD flow passed")
    
    def test_delete_nonexistent_route(self, auth_headers):
        """Test deleting a route that doesn't exist"""
        fake_id = "nonexistent-route-id-12345"
        
        response = requests.delete(
            f"{BASE_URL}/api/routes/{fake_id}",
            headers=auth_headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("SUCCESS: Delete non-existent route returns 404")


class TestRoutesDuplicateEndpoint:
    """Tests for POST /api/routes/{route_id}/duplicate"""
    
    def test_duplicate_route(self, auth_headers):
        """Test duplicating a route"""
        # Create original
        route_data = {
            "name": "TEST_ORIGINAL_ROUTE",
            "technician": "Tech 1",
            "date": "2026-01-16",
            "orders": [
                {"os_number": "TEST_DUP_001", "customer_name": "Customer 1", "sequence": 1},
                {"os_number": "TEST_DUP_002", "customer_name": "Customer 2", "sequence": 2}
            ],
            "total_distance": "5 km",
            "status": "Concluído"
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/routes/",
            json=route_data,
            headers=auth_headers
        )
        assert create_response.status_code == 200
        original_id = create_response.json()["id"]
        print(f"  Created original route: {original_id}")
        
        # Duplicate
        dup_response = requests.post(
            f"{BASE_URL}/api/routes/{original_id}/duplicate",
            headers=auth_headers
        )
        assert dup_response.status_code == 200
        
        dup_data = dup_response.json()
        assert dup_data["id"] != original_id, "Duplicate should have new ID"
        assert "(Copia)" in dup_data["name"], "Duplicate name should have (Copia)"
        assert dup_data["status"] == "Pendente", "Duplicate should reset to Pendente"
        assert len(dup_data["orders"]) == 2, "Duplicate should have same orders"
        print(f"  Duplicated route: {dup_data['id']}")
        
        # Cleanup both
        requests.delete(f"{BASE_URL}/api/routes/{original_id}", headers=auth_headers)
        requests.delete(f"{BASE_URL}/api/routes/{dup_data['id']}", headers=auth_headers)
        
        print("SUCCESS: Route duplication works correctly")


class TestServiceOrdersEndpoint:
    """Test service orders endpoint used by routes page"""
    
    def test_get_service_orders(self, auth_headers):
        """Test GET /api/service-orders returns data for routes"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders?limit=10&page=1",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "orders" in data, "Response should have orders"
        assert "total" in data, "Response should have total"
        assert isinstance(data["orders"], list), "Orders should be a list"
        
        if len(data["orders"]) > 0:
            order = data["orders"][0]
            # Check order has fields needed for routes
            assert "os_number" in order
            print(f"SUCCESS: Service orders endpoint returns {len(data['orders'])} orders, total={data['total']}")
        else:
            print("SUCCESS: Service orders endpoint works (no data)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
