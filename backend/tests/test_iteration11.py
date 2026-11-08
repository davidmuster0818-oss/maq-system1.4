"""
Iteration 11 - Testing for Mastermaq OS Management System
Tests: Login, Service Orders, next-ose-number, search, source filter
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
    """Get authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert "token" in data
    return data["token"]


@pytest.fixture
def auth_headers(auth_token):
    """Return headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestAuth:
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
        print(f"✓ Login successful, token received")

    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "wrong@test.com", "password": "wrongpass"}
        )
        assert response.status_code == 401
        print(f"✓ Invalid credentials correctly rejected")


class TestNextOseNumber:
    """Test next OSE number endpoint"""
    
    def test_next_ose_number_returns_27578(self, auth_headers):
        """GET /api/service-orders/next-ose-number should return 27578"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders/next-ose-number",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "next_ose_number" in data
        assert data["next_ose_number"] == "27578"
        print(f"✓ Next OSE number is 27578 as expected")


class TestServiceOrdersList:
    """Test service orders list and search"""
    
    def test_get_service_orders(self, auth_headers):
        """GET /api/service-orders returns migrated orders"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        print(f"✓ Got {len(data)} service orders")
    
    def test_search_by_os_number_27577(self, auth_headers):
        """Search for OS #27577"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders?search=27577",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        order = data[0]
        assert order["os_number"] == "27577"
        assert "registration_date" in order
        assert "attendance_date" in order
        print(f"✓ Found OS #27577: {order['customer_name']}")
    
    def test_search_by_os_number_27576(self, auth_headers):
        """Search for OS #27576"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders?search=27576",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        order = data[0]
        assert order["os_number"] == "27576"
        print(f"✓ Found OS #27576: {order['customer_name']}")
    
    def test_order_has_registration_and_attendance_date(self, auth_headers):
        """Verify migrated orders have registration_date and attendance_date"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders?search=27577",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        order = data[0]
        
        # Check registration_date
        assert "registration_date" in order
        assert order["registration_date"] is not None
        assert order["registration_date"] != ""
        
        # Check attendance_date
        assert "attendance_date" in order
        assert order["attendance_date"] is not None
        assert order["attendance_date"] != ""
        
        print(f"✓ OS has registration_date: {order['registration_date']}, attendance_date: {order['attendance_date']}")


class TestSourceFilter:
    """Test source filtering"""
    
    def test_filter_by_source_mastermaq(self, auth_headers):
        """Filter orders by mastermaq source"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders?source=mastermaq",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # All returned orders should not be telecontrol
        for order in data[:10]:  # Check first 10
            assert order.get("source") != "telecontrol"
        print(f"✓ Mastermaq filter works, got {len(data)} orders")
    
    def test_filter_by_source_telecontrol(self, auth_headers):
        """Filter orders by telecontrol source"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders?source=telecontrol",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # All returned orders should be telecontrol
        for order in data[:10]:  # Check first 10
            assert order.get("source") == "telecontrol"
        print(f"✓ Telecontrol filter works, got {len(data)} orders")


class TestServiceOrderDetail:
    """Test getting single service order"""
    
    def test_get_order_27577(self, auth_headers):
        """GET /api/service-orders/27577"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders/27577",
            headers=auth_headers
        )
        assert response.status_code == 200
        order = response.json()
        assert order["os_number"] == "27577"
        assert order["customer_name"] == "REGIANE MARIA DA SILVA"
        assert "registration_date" in order
        assert "attendance_date" in order
        print(f"✓ Got OS #27577 details correctly")


class TestNotifications:
    """Test notifications endpoint"""
    
    def test_get_unread_count(self, auth_headers):
        """GET /api/notifications/unread-count"""
        response = requests.get(
            f"{BASE_URL}/api/notifications/unread-count",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        print(f"✓ Unread notifications count: {data['count']}")


class TestStatuses:
    """Test statuses endpoint"""
    
    def test_get_distinct_statuses(self, auth_headers):
        """GET /api/service-orders/statuses"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders/statuses",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "statuses" in data
        assert isinstance(data["statuses"], list)
        print(f"✓ Got {len(data['statuses'])} distinct statuses")
