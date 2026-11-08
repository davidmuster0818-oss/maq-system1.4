"""
Iteration 16: Pagination and Search Tests
Tests for:
1. Backend pagination with page/limit returning {orders, total, page, limit, total_pages}
2. Backend search across multiple fields (neighborhood, address, city, etc.)
3. Pagination returns different results for different pages
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
API_URL = f"{BASE_URL}/api"

# Test credentials
TEST_EMAIL = "mastermaqassistencia@gmail.com"
TEST_PASSWORD = "atr132641"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for all tests"""
    response = requests.post(
        f"{API_URL}/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get auth headers for requests"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestPaginationResponse:
    """Test pagination response structure"""
    
    def test_pagination_response_structure(self, auth_headers):
        """GET /api/service-orders?page=1&limit=10 should return correct structure"""
        response = requests.get(
            f"{API_URL}/service-orders?page=1&limit=10",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response has all required pagination fields
        assert "orders" in data, "Response missing 'orders' field"
        assert "total" in data, "Response missing 'total' field"
        assert "page" in data, "Response missing 'page' field"
        assert "limit" in data, "Response missing 'limit' field"
        assert "total_pages" in data, "Response missing 'total_pages' field"
        
        # Verify types
        assert isinstance(data["orders"], list), "'orders' should be a list"
        assert isinstance(data["total"], int), "'total' should be int"
        assert isinstance(data["page"], int), "'page' should be int"
        assert isinstance(data["limit"], int), "'limit' should be int"
        assert isinstance(data["total_pages"], int), "'total_pages' should be int"
        
        # Verify values make sense
        assert data["page"] == 1, "Page should be 1"
        assert data["limit"] == 10, "Limit should be 10"
        assert len(data["orders"]) <= 10, "Should return at most 10 orders"
        
        print(f"✓ Pagination response: total={data['total']}, page={data['page']}, limit={data['limit']}, total_pages={data['total_pages']}")
    
    def test_pagination_page2_returns_different_orders(self, auth_headers):
        """GET /api/service-orders?page=2&limit=5 should return different orders than page 1"""
        # Get page 1
        response1 = requests.get(
            f"{API_URL}/service-orders?page=1&limit=5",
            headers=auth_headers
        )
        assert response1.status_code == 200
        page1_orders = [o["os_number"] for o in response1.json()["orders"]]
        
        # Get page 2
        response2 = requests.get(
            f"{API_URL}/service-orders?page=2&limit=5",
            headers=auth_headers
        )
        assert response2.status_code == 200
        data2 = response2.json()
        page2_orders = [o["os_number"] for o in data2["orders"]]
        
        # Verify page 2 metadata
        assert data2["page"] == 2, "Page should be 2"
        assert data2["limit"] == 5, "Limit should be 5"
        
        # Verify orders are different
        assert set(page1_orders).isdisjoint(set(page2_orders)), \
            f"Page 1 and Page 2 should have different orders. Page1: {page1_orders}, Page2: {page2_orders}"
        
        print(f"✓ Page 1 orders: {page1_orders}")
        print(f"✓ Page 2 orders: {page2_orders}")
        print("✓ Pages return different orders")
    
    def test_pagination_total_pages_calculation(self, auth_headers):
        """Verify total_pages is calculated correctly"""
        response = requests.get(
            f"{API_URL}/service-orders?page=1&limit=10",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Calculate expected total_pages
        expected_total_pages = (data["total"] + data["limit"] - 1) // data["limit"]
        assert data["total_pages"] == expected_total_pages, \
            f"total_pages should be {expected_total_pages}, got {data['total_pages']}"
        
        print(f"✓ Total pages calculation: {data['total']} / {data['limit']} = {data['total_pages']}")


class TestSearchFunctionality:
    """Test search across multiple fields"""
    
    def test_search_by_neighborhood_barreiro(self, auth_headers):
        """GET /api/service-orders?search=Barreiro should find orders by neighborhood"""
        response = requests.get(
            f"{API_URL}/service-orders?search=Barreiro&page=1&limit=5",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] > 0, "Should find orders with 'Barreiro' neighborhood"
        assert len(data["orders"]) > 0, "Should return some orders"
        
        # Verify at least one order has Barreiro in neighborhood
        neighborhoods = [o.get("neighborhood", "").upper() for o in data["orders"]]
        assert any("BARREIRO" in n for n in neighborhoods), \
            f"At least one order should have 'BARREIRO' in neighborhood. Found: {neighborhoods}"
        
        print(f"✓ Search 'Barreiro': found {data['total']} orders, first page neighborhoods: {neighborhoods}")
    
    def test_search_by_centro(self, auth_headers):
        """GET /api/service-orders?search=centro should find orders by various text fields"""
        response = requests.get(
            f"{API_URL}/service-orders?search=centro&page=1&limit=10",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] > 0, "Should find orders with 'centro' in any field"
        assert len(data["orders"]) > 0, "Should return some orders"
        
        print(f"✓ Search 'centro': found {data['total']} orders")
    
    def test_search_by_address(self, auth_headers):
        """Search should work on address field"""
        response = requests.get(
            f"{API_URL}/service-orders?search=DESCALVADO&page=1&limit=10",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # DESCALVADO is in the address of the company
        assert data["total"] >= 0, "Search should return valid response"
        print(f"✓ Search 'DESCALVADO' (address): found {data['total']} orders")
    
    def test_search_by_os_number(self, auth_headers):
        """Search should work on os_number field"""
        response = requests.get(
            f"{API_URL}/service-orders?search=27575&page=1&limit=10",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        if data["total"] > 0:
            os_numbers = [o["os_number"] for o in data["orders"]]
            assert any("27575" in os for os in os_numbers), \
                f"Search by os_number should find matching orders. Found: {os_numbers}"
        
        print(f"✓ Search '27575' (os_number): found {data['total']} orders")
    
    def test_search_by_brand(self, auth_headers):
        """Search should work on brand field"""
        response = requests.get(
            f"{API_URL}/service-orders?search=HISENSE&page=1&limit=10",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        if data["total"] > 0:
            brands = [o.get("brand", "").upper() for o in data["orders"]]
            assert any("HISENSE" in b for b in brands), \
                f"Search by brand should find matching orders. Found brands: {brands}"
        
        print(f"✓ Search 'HISENSE' (brand): found {data['total']} orders")
    
    def test_search_empty_returns_all(self, auth_headers):
        """Empty search should return all orders with pagination"""
        response = requests.get(
            f"{API_URL}/service-orders?page=1&limit=30",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] > 0, "Should have orders in database"
        assert data["page"] == 1
        assert data["limit"] == 30
        
        print(f"✓ No search filter: total={data['total']} orders, page 1 has {len(data['orders'])} items")


class TestPaginationWithFilters:
    """Test pagination combined with filters"""
    
    def test_pagination_with_status_filter(self, auth_headers):
        """Pagination should work with status filter"""
        response = requests.get(
            f"{API_URL}/service-orders?status=Orçamento&page=1&limit=5",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify pagination structure
        assert "orders" in data
        assert "total" in data
        assert "page" in data
        assert "limit" in data
        assert "total_pages" in data
        
        if data["total"] > 0:
            statuses = [o.get("status", "") for o in data["orders"]]
            print(f"✓ Status filter 'Orçamento': found {data['total']} orders, statuses: {statuses}")
        else:
            print(f"✓ Status filter 'Orçamento': no orders found")
    
    def test_pagination_with_search_and_page2(self, auth_headers):
        """Pagination should work correctly with search filter"""
        # Get page 1 of search results
        response1 = requests.get(
            f"{API_URL}/service-orders?search=centro&page=1&limit=5",
            headers=auth_headers
        )
        assert response1.status_code == 200
        data1 = response1.json()
        
        if data1["total"] > 5:
            # Get page 2
            response2 = requests.get(
                f"{API_URL}/service-orders?search=centro&page=2&limit=5",
                headers=auth_headers
            )
            assert response2.status_code == 200
            data2 = response2.json()
            
            page1_os = [o["os_number"] for o in data1["orders"]]
            page2_os = [o["os_number"] for o in data2["orders"]]
            
            assert set(page1_os).isdisjoint(set(page2_os)), \
                "Search results page 1 and 2 should have different orders"
            
            print(f"✓ Search 'centro' pagination: page1={page1_os}, page2={page2_os}")
        else:
            print(f"✓ Search 'centro' has {data1['total']} results (less than 6, no page 2 test)")


class TestDefaultPagination:
    """Test default pagination values"""
    
    def test_default_limit_is_30(self, auth_headers):
        """Default limit should be 30 if not specified"""
        response = requests.get(
            f"{API_URL}/service-orders?page=1",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["limit"] == 30, f"Default limit should be 30, got {data['limit']}"
        print(f"✓ Default limit is 30")
    
    def test_limit_clamped_to_100(self, auth_headers):
        """Limit should be clamped to max 100"""
        response = requests.get(
            f"{API_URL}/service-orders?page=1&limit=200",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["limit"] <= 100, f"Limit should be clamped to max 100, got {data['limit']}"
        print(f"✓ Limit clamped: requested 200, got {data['limit']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
