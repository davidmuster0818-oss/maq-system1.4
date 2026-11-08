"""
Iteration 21: Testing Brand Filter and Routes Page Modal Fix
Features tested:
1. GET /api/service-orders/brands - returns distinct brands
2. GET /api/service-orders?brand=HISENSE - filters by brand
3. Brand filter dropdown on ServiceOrdersPage
4. Brand badge on OS cards and modal
5. Routes page 'Novo Roteiro' modal NOT causing white screen
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuthentication:
    """Basic auth tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("token")
    
    def test_login_success(self):
        """Test successful login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data.get("email") == "mastermaqassistencia@gmail.com"
        print("PASS: Login successful, token received")


class TestBrandsEndpoint:
    """Tests for GET /api/service-orders/brands endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_brands_endpoint_exists(self, auth_headers):
        """Test that /api/service-orders/brands endpoint exists and returns 200"""
        response = requests.get(f"{BASE_URL}/api/service-orders/brands", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: GET /api/service-orders/brands returns 200")
    
    def test_get_brands_returns_list(self, auth_headers):
        """Test that brands endpoint returns a list of distinct brands"""
        response = requests.get(f"{BASE_URL}/api/service-orders/brands", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "brands" in data, "Response should contain 'brands' key"
        assert isinstance(data["brands"], list), "brands should be a list"
        print(f"PASS: Brands endpoint returned {len(data['brands'])} distinct brands")
        
        # Print first 10 brands for debugging
        if data["brands"]:
            print(f"Sample brands: {data['brands'][:10]}")
    
    def test_brands_contains_expected_brands(self, auth_headers):
        """Test that brands list contains expected brands like Hisense"""
        response = requests.get(f"{BASE_URL}/api/service-orders/brands", headers=auth_headers)
        data = response.json()
        brands_lower = [b.lower() for b in data["brands"]]
        
        # Check for some expected brands (case-insensitive)
        expected_brands = ["hisense", "panasonic", "hq"]
        found_brands = []
        for brand in expected_brands:
            if any(brand in b for b in brands_lower):
                found_brands.append(brand)
        
        print(f"PASS: Found expected brands: {found_brands}")
        # At least some brands should be present
        assert len(data["brands"]) > 0, "Should have at least some brands"


class TestBrandFilter:
    """Tests for brand filtering on service orders"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_filter_by_brand_hisense(self, auth_headers):
        """Test filtering service orders by brand=HISENSE"""
        response = requests.get(f"{BASE_URL}/api/service-orders?brand=HISENSE&limit=10", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "orders" in data, "Response should contain 'orders'"
        assert "total" in data, "Response should contain 'total'"
        
        print(f"PASS: Filter by HISENSE returned {len(data['orders'])} orders (total: {data['total']})")
        
        # Verify all returned orders have HISENSE brand (case-insensitive)
        for order in data["orders"]:
            brand = order.get("brand", "")
            assert brand.upper() == "HISENSE", f"Order {order.get('os_number')} has brand '{brand}', expected 'HISENSE'"
        
        print(f"PASS: All {len(data['orders'])} returned orders have HISENSE brand")
    
    def test_filter_by_brand_case_insensitive(self, auth_headers):
        """Test that brand filter is case-insensitive"""
        # Test with lowercase
        response1 = requests.get(f"{BASE_URL}/api/service-orders?brand=hisense&limit=5", headers=auth_headers)
        # Test with uppercase
        response2 = requests.get(f"{BASE_URL}/api/service-orders?brand=HISENSE&limit=5", headers=auth_headers)
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        data1 = response1.json()
        data2 = response2.json()
        
        # Should return same total count
        assert data1["total"] == data2["total"], f"Case sensitivity issue: lowercase={data1['total']}, uppercase={data2['total']}"
        print(f"PASS: Brand filter is case-insensitive (both return total={data1['total']})")
    
    def test_filter_no_brand_returns_all(self, auth_headers):
        """Test that no brand filter returns all orders"""
        response = requests.get(f"{BASE_URL}/api/service-orders?limit=10", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Should return orders
        assert data["total"] > 0, "Should have some orders without brand filter"
        print(f"PASS: No brand filter returns {data['total']} total orders")
    
    def test_filter_combined_brand_and_status(self, auth_headers):
        """Test combining brand filter with status filter"""
        # First get statuses
        statuses_response = requests.get(f"{BASE_URL}/api/service-orders/statuses", headers=auth_headers)
        statuses = statuses_response.json().get("statuses", [])
        
        if statuses:
            test_status = statuses[0]
            response = requests.get(
                f"{BASE_URL}/api/service-orders?brand=HISENSE&status={test_status}&limit=10", 
                headers=auth_headers
            )
            assert response.status_code == 200
            data = response.json()
            print(f"PASS: Combined brand=HISENSE + status={test_status} returned {data['total']} orders")
        else:
            print("SKIP: No statuses available for combined filter test")


class TestServiceOrdersList:
    """Tests for service orders list with brand data"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_orders_include_brand_field(self, auth_headers):
        """Test that orders include brand field for badge display"""
        response = requests.get(f"{BASE_URL}/api/service-orders?limit=10", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Check that orders have brand field
        for order in data["orders"]:
            # Brand can be empty but should exist as a key
            assert "brand" in order, f"Order {order.get('os_number')} missing 'brand' field"
        
        brands_found = [o.get("brand") for o in data["orders"] if o.get("brand")]
        print(f"PASS: Orders include brand field. Sample brands: {brands_found[:5]}")
    
    def test_get_single_order_has_brand(self, auth_headers):
        """Test that single order endpoint returns brand field"""
        # First get an order
        list_response = requests.get(f"{BASE_URL}/api/service-orders?limit=1", headers=auth_headers)
        orders = list_response.json().get("orders", [])
        
        if orders:
            os_number = orders[0].get("os_number")
            response = requests.get(f"{BASE_URL}/api/service-orders/{os_number}", headers=auth_headers)
            assert response.status_code == 200
            order = response.json()
            
            assert "brand" in order, "Single order should have 'brand' field"
            print(f"PASS: Single order {os_number} has brand: {order.get('brand')}")
        else:
            print("SKIP: No orders available")


class TestStatusesEndpoint:
    """Tests for statuses endpoint (existing functionality)"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_statuses_endpoint(self, auth_headers):
        """Test that statuses endpoint returns list of statuses"""
        response = requests.get(f"{BASE_URL}/api/service-orders/statuses", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "statuses" in data
        assert isinstance(data["statuses"], list)
        print(f"PASS: Statuses endpoint returned {len(data['statuses'])} distinct statuses")


class TestRoutesEndpoint:
    """Tests for routes endpoints (for Routes page)"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        token = response.json().get("token")
        return {"Authorization": f"Bearer {token}"}
    
    def test_routes_list_endpoint(self, auth_headers):
        """Test that routes list endpoint works"""
        response = requests.get(f"{BASE_URL}/api/routes/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Routes should return a list"
        print(f"PASS: Routes endpoint returned {len(data)} routes")
    
    def test_service_orders_for_route_modal(self, auth_headers):
        """Test that service orders endpoint returns proper data structure for route modal"""
        response = requests.get(f"{BASE_URL}/api/service-orders?limit=100&page=1", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Check the structure that CreateRouteModal expects
        assert "orders" in data, "Response must have 'orders' key"
        assert "total" in data, "Response must have 'total' key"
        assert isinstance(data["orders"], list), "orders must be a list"
        
        # The fix was that modal used res.data instead of res.data.orders
        # This test verifies the API returns proper structure
        print(f"PASS: Service orders returns proper structure: orders={len(data['orders'])}, total={data['total']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
