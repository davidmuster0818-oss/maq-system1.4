"""
Test iteration 22 - Routes compute-route endpoint testing
Tests: POST /api/routes/compute-route for Google Routes API proxy functionality
This is the key endpoint that enables route optimization with polyline/legs data
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "mastermaqassistencia@gmail.com"
TEST_PASSWORD = "atr132641"


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


class TestComputeRouteEndpoint:
    """Tests for POST /api/routes/compute-route - Google Routes API proxy"""
    
    def test_compute_route_with_addresses(self, auth_headers):
        """Test compute-route with address strings"""
        payload = {
            "origin": {"address": "Rua Descalvado, 636A, Renascença, Belo Horizonte, MG"},
            "destination": {"address": "Rua Descalvado, 636A, Renascença, Belo Horizonte, MG"},
            "intermediates": [
                {"address": "Praça Sete de Setembro, Belo Horizonte, MG"},
                {"address": "Savassi, Belo Horizonte, MG"}
            ],
            "optimize_waypoint_order": True
        }
        
        response = requests.post(
            f"{BASE_URL}/api/routes/compute-route",
            json=payload,
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        
        # Check routes array exists
        assert "routes" in data, "Response should have 'routes' array"
        assert len(data["routes"]) > 0, "Should have at least one route"
        
        route = data["routes"][0]
        
        # Check polyline
        assert "polyline" in route, "Route should have polyline"
        assert "encodedPolyline" in route["polyline"], "Polyline should have encodedPolyline"
        polyline = route["polyline"]["encodedPolyline"]
        assert len(polyline) > 50, f"Polyline should be substantial, got length {len(polyline)}"
        
        # Check legs
        assert "legs" in route, "Route should have legs"
        legs = route["legs"]
        assert len(legs) == 3, f"Should have 3 legs (origin->stop1->stop2->dest), got {len(legs)}"
        
        for i, leg in enumerate(legs):
            assert "distanceMeters" in leg, f"Leg {i} should have distanceMeters"
            assert "duration" in leg, f"Leg {i} should have duration"
            assert "startLocation" in leg, f"Leg {i} should have startLocation"
            assert "endLocation" in leg, f"Leg {i} should have endLocation"
            
            # Check location format
            start = leg["startLocation"]
            assert "latLng" in start, f"Leg {i} startLocation should have latLng"
            assert "latitude" in start["latLng"]
            assert "longitude" in start["latLng"]
        
        # Check optimized waypoint order
        assert "optimizedIntermediateWaypointIndex" in route, "Should have waypoint optimization"
        order = route["optimizedIntermediateWaypointIndex"]
        assert isinstance(order, list), "Waypoint order should be list"
        assert len(order) == 2, f"Should have 2 indices for 2 intermediates, got {len(order)}"
        
        # Check total distance and duration
        assert "distanceMeters" in route, "Route should have total distanceMeters"
        assert "duration" in route, "Route should have total duration"
        
        total_dist = route["distanceMeters"]
        assert total_dist > 1000, f"Total distance should be >1km, got {total_dist}m"
        
        print(f"SUCCESS: compute-route with addresses works!")
        print(f"  - Polyline length: {len(polyline)} chars")
        print(f"  - Legs: {len(legs)}")
        print(f"  - Total distance: {total_dist}m")
        print(f"  - Optimized order: {order}")
    
    def test_compute_route_with_coordinates(self, auth_headers):
        """Test compute-route with lat/lng coordinates"""
        payload = {
            "origin": {"lat": -19.8882, "lng": -43.9421},  # Base address
            "destination": {"lat": -19.8882, "lng": -43.9421},
            "intermediates": [
                {"lat": -19.9190, "lng": -43.9387},  # Praça Sete approx
                {"lat": -19.9362, "lng": -43.9323}   # Savassi approx
            ],
            "optimize_waypoint_order": True
        }
        
        response = requests.post(
            f"{BASE_URL}/api/routes/compute-route",
            json=payload,
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "routes" in data
        assert len(data["routes"]) > 0
        
        route = data["routes"][0]
        assert "polyline" in route
        assert "legs" in route
        
        print(f"SUCCESS: compute-route with coordinates works!")
        print(f"  - Total distance: {route.get('distanceMeters', 'N/A')}m")
    
    def test_compute_route_without_optimization(self, auth_headers):
        """Test compute-route without waypoint optimization"""
        payload = {
            "origin": {"address": "Rua Descalvado, 636A, Renascença, Belo Horizonte, MG"},
            "destination": {"address": "Rua Descalvado, 636A, Renascença, Belo Horizonte, MG"},
            "intermediates": [
                {"address": "Praça Sete de Setembro, Belo Horizonte, MG"}
            ],
            "optimize_waypoint_order": False
        }
        
        response = requests.post(
            f"{BASE_URL}/api/routes/compute-route",
            json=payload,
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        route = data["routes"][0]
        
        # When not optimizing, should still return route data
        assert "polyline" in route
        assert "legs" in route
        
        print("SUCCESS: compute-route without optimization works!")
    
    def test_compute_route_single_intermediate(self, auth_headers):
        """Test compute-route with just one intermediate stop"""
        payload = {
            "origin": {"address": "Rua Descalvado, 636A, Renascença, Belo Horizonte, MG"},
            "destination": {"address": "Savassi, Belo Horizonte, MG"},
            "intermediates": [
                {"address": "Praça Sete de Setembro, Belo Horizonte, MG"}
            ],
            "optimize_waypoint_order": False
        }
        
        response = requests.post(
            f"{BASE_URL}/api/routes/compute-route",
            json=payload,
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        route = data["routes"][0]
        
        # With 1 intermediate, should have 2 legs
        assert len(route["legs"]) == 2, f"Should have 2 legs, got {len(route['legs'])}"
        
        print("SUCCESS: compute-route with single intermediate works!")
    
    def test_compute_route_empty_intermediates(self, auth_headers):
        """Test compute-route with no intermediate stops"""
        payload = {
            "origin": {"address": "Rua Descalvado, 636A, Renascença, Belo Horizonte, MG"},
            "destination": {"address": "Savassi, Belo Horizonte, MG"},
            "intermediates": [],
            "optimize_waypoint_order": False
        }
        
        response = requests.post(
            f"{BASE_URL}/api/routes/compute-route",
            json=payload,
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        route = data["routes"][0]
        
        # With no intermediates, should have 1 leg
        assert len(route["legs"]) == 1, f"Should have 1 leg, got {len(route['legs'])}"
        
        print("SUCCESS: compute-route with no intermediates works!")
    
    def test_compute_route_mixed_waypoints(self, auth_headers):
        """Test compute-route with mixed addresses and coordinates"""
        payload = {
            "origin": {"address": "Rua Descalvado, 636A, Renascença, Belo Horizonte, MG"},
            "destination": {"address": "Rua Descalvado, 636A, Renascença, Belo Horizonte, MG"},
            "intermediates": [
                {"lat": -19.9190, "lng": -43.9387},  # Coordinate
                {"address": "Savassi, Belo Horizonte, MG"}  # Address
            ],
            "optimize_waypoint_order": True
        }
        
        response = requests.post(
            f"{BASE_URL}/api/routes/compute-route",
            json=payload,
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "routes" in data
        assert len(data["routes"]) > 0
        
        print("SUCCESS: compute-route with mixed waypoints works!")


class TestComputeRouteValidation:
    """Tests for validation and error handling"""
    
    def test_compute_route_invalid_address(self, auth_headers):
        """Test compute-route with completely invalid address"""
        payload = {
            "origin": {"address": "xyznonexistentaddress12345"},
            "destination": {"address": "xyznonexistentaddress12345"},
            "intermediates": [],
            "optimize_waypoint_order": False
        }
        
        response = requests.post(
            f"{BASE_URL}/api/routes/compute-route",
            json=payload,
            headers=auth_headers
        )
        
        # Should return error (either 400 or proxy the error)
        # Google API may return various error codes for bad addresses
        if response.status_code == 200:
            data = response.json()
            # If it returns 200, check if routes is empty or has error
            routes = data.get("routes", [])
            print(f"INFO: Invalid address returned status 200 with {len(routes)} routes")
        else:
            print(f"SUCCESS: Invalid address rejected with status {response.status_code}")
    
    def test_compute_route_missing_origin(self, auth_headers):
        """Test compute-route without origin"""
        payload = {
            "destination": {"address": "Savassi, Belo Horizonte, MG"},
            "intermediates": [],
            "optimize_waypoint_order": False
        }
        
        response = requests.post(
            f"{BASE_URL}/api/routes/compute-route",
            json=payload,
            headers=auth_headers
        )
        
        # Should fail validation
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print("SUCCESS: Missing origin rejected with 422")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
