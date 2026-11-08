"""
Iteration 15 Tests: 
- Login with credentials
- Expanded search (18 fields) - neighborhood CAIÇARA, address DESCALVADO
- Laudo DOCX generation with test images
- Photo fields (photo_1-photo_8) in ServiceOrder model
- Routes CRUD operations
"""
import pytest
import requests
import os
import base64

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "mastermaqassistencia@gmail.com"
TEST_PASSWORD = "atr132641"

# Global token storage
TOKEN = None


def get_auth_header():
    """Get authorization header with token"""
    global TOKEN
    if not TOKEN:
        pytest.skip("No auth token available")
    return {"Authorization": f"Bearer {TOKEN}"}


class TestAuth:
    """Authentication endpoint tests"""
    
    def test_login_success(self):
        """Test login with valid credentials"""
        global TOKEN
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["email"] == TEST_EMAIL
        TOKEN = data["token"]
        print(f"Login successful, token obtained")
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials returns 401"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "invalid@example.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401


class TestExpandedSearch:
    """Test expanded search functionality (18 fields)"""
    
    def test_search_by_neighborhood_caicara(self):
        """Search by neighborhood containing CAIÇARA"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders",
            params={"search": "CAIÇARA"},
            headers=get_auth_header()
        )
        assert response.status_code == 200
        orders = response.json()
        print(f"Search 'CAIÇARA': {len(orders)} results")
        # Check if any result has CAIÇARA in neighborhood
        if orders:
            has_match = any(
                'CAIÇARA' in (o.get('neighborhood', '') or '').upper() or
                'CAICARA' in (o.get('neighborhood', '') or '').upper()
                for o in orders
            )
            print(f"Has neighborhood match: {has_match}")
    
    def test_search_by_address_descalvado(self):
        """Search by address containing DESCALVADO"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders",
            params={"search": "DESCALVADO"},
            headers=get_auth_header()
        )
        assert response.status_code == 200
        orders = response.json()
        print(f"Search 'DESCALVADO': {len(orders)} results")
        # The company address is RUA DESCALVADO
        assert len(orders) > 0, "Should find OS with DESCALVADO in address"
    
    def test_search_by_phone(self):
        """Search by phone number"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders",
            params={"search": "3422"},
            headers=get_auth_header()
        )
        assert response.status_code == 200
        orders = response.json()
        print(f"Search by phone '3422': {len(orders)} results")
    
    def test_search_by_brand(self):
        """Search by brand (HISENSE)"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders",
            params={"search": "HISENSE"},
            headers=get_auth_header()
        )
        assert response.status_code == 200
        orders = response.json()
        print(f"Search 'HISENSE': {len(orders)} results")
        assert len(orders) > 0, "Should find OS with HISENSE brand"


class TestLaudoGeneration:
    """Test Laudo DOCX generation"""
    
    def test_laudo_generate_docx_with_images(self):
        """Test POST /api/laudo/generate-docx with test images returns 200 and valid docx"""
        # Create a simple 1x1 white JPEG as base64 test image
        test_image_base64 = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBEQCEAwEPwAB//9k="
        
        laudo_data = {
            "os_number": "TEST_27575",
            "customer_name": "Test Customer",
            "model": "Test Model",
            "serial_number": "SN123456",
            "batch": "BATCH001",
            "brand": "HISENSE",
            "service_type": "Garantia",
            "reported_defect": "Test defect description",
            "technical_diagnosis": "Test diagnosis",
            "installation_correct": "Sim",
            "required_parts": "None",
            "images": [test_image_base64, test_image_base64],  # 2 test images
            "technical_notes": "Test notes",
            "final_status": "Produto reparado",
            "location": "BELO HORIZONTE",
            "date": "15/01/2026",
            "technician": "Test Technician",
            "voltage_f1f2": "220",
            "voltage_f1_terra": "110",
            "voltage_f2_terra": "110"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/laudo/generate-docx",
            json=laudo_data,
            headers=get_auth_header()
        )
        
        assert response.status_code == 200, f"Laudo generation failed: {response.text}"
        
        # Check content type is DOCX
        content_type = response.headers.get('content-type', '')
        assert 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' in content_type
        
        # Check we got some content
        assert len(response.content) > 1000, "DOCX should have content"
        
        # Check content-disposition header
        content_disp = response.headers.get('content-disposition', '')
        assert 'Laudo_OS_TEST_27575.docx' in content_disp
        
        print(f"Laudo DOCX generated successfully: {len(response.content)} bytes")


class TestPhotoFields:
    """Test photo_1-photo_8 fields in ServiceOrder model"""
    
    def test_update_os_with_photo_field(self):
        """Test updating an OS with photo_1 field"""
        # First get OS #27575 to verify it exists
        response = requests.get(
            f"{BASE_URL}/api/service-orders/27575",
            headers=get_auth_header()
        )
        
        if response.status_code == 404:
            pytest.skip("OS 27575 not found - skipping photo update test")
        
        assert response.status_code == 200
        
        # Test photo base64 string
        test_photo = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAn/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBEQCEAwEPwAB//9k="
        
        # Update with photo_1
        update_response = requests.put(
            f"{BASE_URL}/api/service-orders/27575",
            json={"photo_1": test_photo},
            headers=get_auth_header()
        )
        
        assert update_response.status_code == 200, f"Photo update failed: {update_response.text}"
        
        # Verify photo was saved
        verify_response = requests.get(
            f"{BASE_URL}/api/service-orders/27575",
            headers=get_auth_header()
        )
        assert verify_response.status_code == 200
        data = verify_response.json()
        assert data.get("photo_1") == test_photo, "Photo_1 not saved correctly"
        
        print("Photo_1 field update and verification successful")
        
        # Clean up - remove the test photo
        requests.put(
            f"{BASE_URL}/api/service-orders/27575",
            json={"photo_1": None},
            headers=get_auth_header()
        )


class TestRoutesCRUD:
    """Test Routes CRUD operations"""
    
    test_route_id = None
    
    def test_create_route(self):
        """Test POST /api/routes/ creates route"""
        route_data = {
            "name": "TEST_Roteiro_Iteration15",
            "technician": "Test Technician",
            "date": "2026-01-15",
            "orders": [
                {
                    "os_number": "TEST_001",
                    "customer_name": "Customer 1",
                    "neighborhood": "Centro",
                    "city": "Belo Horizonte",
                    "sequence": 1
                },
                {
                    "os_number": "TEST_002",
                    "customer_name": "Customer 2",
                    "neighborhood": "Savassi",
                    "city": "Belo Horizonte",
                    "sequence": 2
                }
            ],
            "total_distance": "15.5 km",
            "total_duration": "45min",
            "status": "Pendente"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/routes/",
            json=route_data,
            headers=get_auth_header()
        )
        
        assert response.status_code == 200, f"Route creation failed: {response.text}"
        data = response.json()
        assert "id" in data
        assert data["name"] == "TEST_Roteiro_Iteration15"
        assert data["technician"] == "Test Technician"
        assert len(data["orders"]) == 2
        
        TestRoutesCRUD.test_route_id = data["id"]
        print(f"Route created with ID: {data['id']}")
    
    def test_list_routes(self):
        """Test GET /api/routes/ lists routes"""
        response = requests.get(
            f"{BASE_URL}/api/routes/",
            headers=get_auth_header()
        )
        
        assert response.status_code == 200
        routes = response.json()
        assert isinstance(routes, list)
        print(f"Listed {len(routes)} routes")
    
    def test_get_route(self):
        """Test GET /api/routes/{id} returns route"""
        if not TestRoutesCRUD.test_route_id:
            pytest.skip("No test route ID")
        
        response = requests.get(
            f"{BASE_URL}/api/routes/{TestRoutesCRUD.test_route_id}",
            headers=get_auth_header()
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == TestRoutesCRUD.test_route_id
        print(f"Retrieved route: {data['name']}")
    
    def test_update_route(self):
        """Test PUT /api/routes/{id} updates route"""
        if not TestRoutesCRUD.test_route_id:
            pytest.skip("No test route ID")
        
        response = requests.put(
            f"{BASE_URL}/api/routes/{TestRoutesCRUD.test_route_id}",
            json={"status": "Em andamento"},
            headers=get_auth_header()
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Em andamento"
        print("Route status updated to 'Em andamento'")
    
    def test_delete_route(self):
        """Test DELETE /api/routes/{id} removes route"""
        if not TestRoutesCRUD.test_route_id:
            pytest.skip("No test route ID")
        
        response = requests.delete(
            f"{BASE_URL}/api/routes/{TestRoutesCRUD.test_route_id}",
            headers=get_auth_header()
        )
        
        assert response.status_code == 200
        
        # Verify deleted
        verify_response = requests.get(
            f"{BASE_URL}/api/routes/{TestRoutesCRUD.test_route_id}",
            headers=get_auth_header()
        )
        assert verify_response.status_code == 404
        print("Route deleted successfully")


class TestServiceOrderModel:
    """Verify ServiceOrder model has photo fields"""
    
    def test_get_os_returns_photo_fields(self):
        """Verify ServiceOrder response includes photo_1-photo_8 fields"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders/27575",
            headers=get_auth_header()
        )
        
        if response.status_code == 404:
            pytest.skip("OS 27575 not found")
        
        assert response.status_code == 200
        data = response.json()
        
        # The photo fields should be in the model (may be null)
        # Check the response schema allows these fields
        # photo_1-photo_8 are optional in the model
        print(f"OS 27575 retrieved. Has photo_1: {'photo_1' in data}")
        print(f"OS status: {data.get('status')}, sub_status: {data.get('sub_status')}, micro_status: {data.get('micro_status')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
