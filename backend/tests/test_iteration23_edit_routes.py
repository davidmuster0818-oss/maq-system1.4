"""
Test iteration 23: Edit Route (Roteiro) functionality
Tests:
1. PUT /api/routes/{route_id} - Update route data (name, technician, date, status, orders)
2. Create route → Edit → Verify persistence
3. Reorder OS, add OS, remove OS flows
"""
import pytest
import requests
import os
import uuid
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "mastermaqassistencia@gmail.com"
TEST_PASSWORD = "atr132641"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get authentication token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def authenticated_client(api_client, auth_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


@pytest.fixture(scope="module")
def sample_service_orders(authenticated_client):
    """Get real service orders from database for route creation"""
    response = authenticated_client.get(f"{BASE_URL}/api/service-orders?limit=5&page=1")
    assert response.status_code == 200
    orders = response.json().get("orders", [])
    assert len(orders) >= 2, "Need at least 2 service orders for route testing"
    return orders


@pytest.fixture
def test_route(authenticated_client, sample_service_orders):
    """Create a test route for edit testing, cleanup after test"""
    route_id = f"TEST_EDIT_ROUTE_{uuid.uuid4().hex[:8]}"
    
    # Build order data from service orders
    route_orders = []
    for i, so in enumerate(sample_service_orders[:3]):  # Use 3 orders
        route_orders.append({
            "os_number": so["os_number"],
            "customer_name": so.get("customer_name", ""),
            "neighborhood": so.get("neighborhood", ""),
            "city": so.get("city", ""),
            "address": so.get("address", ""),
            "number": so.get("number", ""),
            "phone1": so.get("phone1", ""),
            "technician": "TEST_TECH",
            "conclusion": "",
            "sequence": i + 1,
            "lat": so.get("lat"),
            "lng": so.get("lng"),
            "attendance_date": so.get("attendance_date", ""),
            "status": so.get("status", ""),
        })
    
    route_data = {
        "name": f"TEST_ROUTE_EDIT_{datetime.now().strftime('%H%M%S')}",
        "technician": "TEST_TECH_ORIGINAL",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "orders": route_orders,
        "total_distance": "10.0 km",
        "total_duration": "30min",
        "status": "Pendente"
    }
    
    # Create route
    response = authenticated_client.post(f"{BASE_URL}/api/routes/", json=route_data)
    assert response.status_code == 200, f"Failed to create route: {response.text}"
    route = response.json()
    
    yield route
    
    # Cleanup: Delete the test route
    authenticated_client.delete(f"{BASE_URL}/api/routes/{route['id']}")


class TestEditRouteBackend:
    """Backend PUT /api/routes/{route_id} endpoint tests"""
    
    def test_update_route_name(self, authenticated_client, test_route):
        """Test updating route name"""
        new_name = f"UPDATED_NAME_{uuid.uuid4().hex[:6]}"
        
        response = authenticated_client.put(
            f"{BASE_URL}/api/routes/{test_route['id']}",
            json={"name": new_name}
        )
        
        assert response.status_code == 200, f"Failed to update: {response.text}"
        data = response.json()
        assert data["name"] == new_name
        
        # Verify persistence with GET
        get_response = authenticated_client.get(f"{BASE_URL}/api/routes/{test_route['id']}")
        assert get_response.status_code == 200
        assert get_response.json()["name"] == new_name
    
    def test_update_route_technician(self, authenticated_client, test_route):
        """Test updating technician name"""
        new_tech = "NEW_TECHNICIAN_NAME"
        
        response = authenticated_client.put(
            f"{BASE_URL}/api/routes/{test_route['id']}",
            json={"technician": new_tech}
        )
        
        assert response.status_code == 200
        assert response.json()["technician"] == new_tech
    
    def test_update_route_status(self, authenticated_client, test_route):
        """Test updating route status to different values"""
        for status in ["Em andamento", "Concluído", "Pendente"]:
            response = authenticated_client.put(
                f"{BASE_URL}/api/routes/{test_route['id']}",
                json={"status": status}
            )
            assert response.status_code == 200
            assert response.json()["status"] == status
    
    def test_update_route_date(self, authenticated_client, test_route):
        """Test updating route date"""
        new_date = "2025-12-31"
        
        response = authenticated_client.put(
            f"{BASE_URL}/api/routes/{test_route['id']}",
            json={"date": new_date}
        )
        
        assert response.status_code == 200
        assert response.json()["date"] == new_date
    
    def test_update_route_orders_reorder(self, authenticated_client, test_route):
        """Test reordering OS in the route (swap sequence)"""
        original_orders = test_route["orders"]
        if len(original_orders) < 2:
            pytest.skip("Need at least 2 orders to test reordering")
        
        # Reverse the order sequence
        reordered = list(reversed(original_orders))
        for i, order in enumerate(reordered):
            order["sequence"] = i + 1
        
        response = authenticated_client.put(
            f"{BASE_URL}/api/routes/{test_route['id']}",
            json={"orders": reordered}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == len(original_orders)
        # Verify first order is now what was last
        assert data["orders"][0]["os_number"] == original_orders[-1]["os_number"]
    
    def test_update_route_remove_os(self, authenticated_client, test_route, sample_service_orders):
        """Test removing an OS from the route"""
        # First, recreate route with 3 orders
        orders = []
        for i, so in enumerate(sample_service_orders[:3]):
            orders.append({
                "os_number": so["os_number"],
                "customer_name": so.get("customer_name", ""),
                "neighborhood": so.get("neighborhood", ""),
                "city": so.get("city", ""),
                "address": so.get("address", ""),
                "number": so.get("number", ""),
                "phone1": so.get("phone1", ""),
                "technician": "TEST_TECH",
                "conclusion": "",
                "sequence": i + 1,
                "lat": so.get("lat"),
                "lng": so.get("lng"),
            })
        
        # Update with 3 orders first
        authenticated_client.put(
            f"{BASE_URL}/api/routes/{test_route['id']}",
            json={"orders": orders}
        )
        
        # Remove last order
        reduced_orders = orders[:2]
        for i, order in enumerate(reduced_orders):
            order["sequence"] = i + 1
        
        response = authenticated_client.put(
            f"{BASE_URL}/api/routes/{test_route['id']}",
            json={"orders": reduced_orders}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == 2
    
    def test_update_route_add_os(self, authenticated_client, test_route, sample_service_orders):
        """Test adding a new OS to the route"""
        if len(sample_service_orders) < 4:
            pytest.skip("Need at least 4 service orders to test adding")
        
        # Get current orders
        get_response = authenticated_client.get(f"{BASE_URL}/api/routes/{test_route['id']}")
        current_orders = get_response.json()["orders"]
        
        # Add a new order
        new_so = sample_service_orders[3]  # 4th service order
        new_order = {
            "os_number": new_so["os_number"],
            "customer_name": new_so.get("customer_name", ""),
            "neighborhood": new_so.get("neighborhood", ""),
            "city": new_so.get("city", ""),
            "address": new_so.get("address", ""),
            "number": new_so.get("number", ""),
            "phone1": new_so.get("phone1", ""),
            "technician": "TEST_TECH",
            "conclusion": "",
            "sequence": len(current_orders) + 1,
            "lat": new_so.get("lat"),
            "lng": new_so.get("lng"),
        }
        
        updated_orders = current_orders + [new_order]
        
        response = authenticated_client.put(
            f"{BASE_URL}/api/routes/{test_route['id']}",
            json={"orders": updated_orders}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["orders"]) == len(current_orders) + 1
        assert any(o["os_number"] == new_so["os_number"] for o in data["orders"])
    
    def test_update_route_distance_duration(self, authenticated_client, test_route):
        """Test updating distance and duration after recalculation"""
        response = authenticated_client.put(
            f"{BASE_URL}/api/routes/{test_route['id']}",
            json={
                "total_distance": "25.5 km",
                "total_duration": "45min"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_distance"] == "25.5 km"
        assert data["total_duration"] == "45min"
    
    def test_update_route_not_found(self, authenticated_client):
        """Test updating non-existent route returns 404"""
        response = authenticated_client.put(
            f"{BASE_URL}/api/routes/non-existent-route-id",
            json={"name": "Test"}
        )
        assert response.status_code == 404
    
    def test_update_route_full_payload(self, authenticated_client, test_route, sample_service_orders):
        """Test updating with full payload (all fields at once)"""
        full_update = {
            "name": "FULL_UPDATE_TEST",
            "technician": "FULL_UPDATE_TECH",
            "date": "2025-06-15",
            "status": "Em andamento",
            "orders": [{
                "os_number": sample_service_orders[0]["os_number"],
                "customer_name": sample_service_orders[0].get("customer_name", ""),
                "neighborhood": sample_service_orders[0].get("neighborhood", ""),
                "city": sample_service_orders[0].get("city", ""),
                "address": sample_service_orders[0].get("address", ""),
                "number": sample_service_orders[0].get("number", ""),
                "phone1": sample_service_orders[0].get("phone1", ""),
                "technician": "FULL_UPDATE_TECH",
                "conclusion": "",
                "sequence": 1,
                "lat": sample_service_orders[0].get("lat"),
                "lng": sample_service_orders[0].get("lng"),
            }],
            "total_distance": "50.0 km",
            "total_duration": "1h 30min"
        }
        
        response = authenticated_client.put(
            f"{BASE_URL}/api/routes/{test_route['id']}",
            json=full_update
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == full_update["name"]
        assert data["technician"] == full_update["technician"]
        assert data["date"] == full_update["date"]
        assert data["status"] == full_update["status"]
        assert len(data["orders"]) == 1
        assert data["total_distance"] == full_update["total_distance"]
        assert data["total_duration"] == full_update["total_duration"]


class TestRouteEndpointsForEdit:
    """Additional route endpoints used by edit functionality"""
    
    def test_get_route_by_id(self, authenticated_client, test_route):
        """Test GET /api/routes/{route_id} returns route data"""
        response = authenticated_client.get(f"{BASE_URL}/api/routes/{test_route['id']}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_route["id"]
        assert "orders" in data
        assert "name" in data
        assert "technician" in data
    
    def test_list_routes(self, authenticated_client, test_route):
        """Test GET /api/routes/ lists all routes including test route"""
        response = authenticated_client.get(f"{BASE_URL}/api/routes/")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Find our test route
        found = any(r["id"] == test_route["id"] for r in data)
        assert found, "Test route not found in list"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
