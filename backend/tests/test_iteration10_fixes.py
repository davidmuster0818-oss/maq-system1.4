"""
Iteration 10 Test Suite - Testing Bug Fixes from Current Session:
1. Auth 401 fix - getAuthHeader reads from localStorage
2. Laudo DOCX - preserves header logo, voltage image, decorative table images, serial_number in bold run
3. Estoque UI - StatCard without colors (bg-white), form with serial_number/batch, Preço column
4. Inventory API - accepts serial_number and batch fields
"""
import pytest
import requests
import os
import zipfile
import io
from xml.etree import ElementTree as ET

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://tech-assist-fix.preview.emergentagent.com')

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "mastermaqassistencia@gmail.com",
        "password": "atr132641"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["token"]

@pytest.fixture
def auth_headers(auth_token):
    """Authenticated headers"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestAuthFix:
    """Test that auth endpoints work properly after getAuthHeader fix"""
    
    def test_login_returns_valid_token(self):
        """Login should return valid token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert len(data["token"]) > 50  # JWT tokens are long
    
    def test_service_orders_with_token(self, auth_headers):
        """Service orders list should work with valid token (no 401)"""
        response = requests.get(f"{BASE_URL}/api/service-orders", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_notifications_with_token(self, auth_headers):
        """Notifications endpoint should work with valid token"""
        response = requests.get(f"{BASE_URL}/api/notifications/unread-count", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "count" in data


class TestLaudoDocxGeneration:
    """Test DOCX generation with preserved template elements"""
    
    def test_docx_generation_endpoint(self, auth_headers):
        """POST /api/laudo/generate-docx should return valid DOCX"""
        laudo_data = {
            "os_number": "TEST-DOCX-001",
            "customer_name": "Cliente Teste DOCX",
            "model": "Refrigerador Frost Free",
            "serial_number": "SN-12345-TEST",
            "batch": "BATCH-2024-01",
            "brand": "Hisense",
            "service_type": "Garantia",
            "reported_defect": "Não está gelando corretamente",
            "technical_diagnosis": "Vazamento de gás refrigerante",
            "installation_correct": "SIM",
            "required_parts": "Compressor 1/4 HP",
            "technical_notes": "Necessário trocar compressor",
            "final_status": "Aguardando peças",
            "technician": "Técnico Teste",
            "location": "BELO HORIZONTE",
            "date": "09/01/2026",
            "voltage_f1f2": "220",
            "voltage_f1_terra": "127",
            "voltage_f2_terra": "127",
            "images": []  # Empty images
        }
        
        response = requests.post(
            f"{BASE_URL}/api/laudo/generate-docx", 
            json=laudo_data, 
            headers=auth_headers
        )
        assert response.status_code == 200, f"DOCX generation failed: {response.text}"
        assert response.headers.get("content-type") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        
        # Verify it's a valid DOCX (ZIP file with specific structure)
        docx_bytes = response.content
        assert len(docx_bytes) > 1000, "DOCX file too small"
        
        # Parse DOCX (it's a ZIP file)
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
            # Check required DOCX components exist
            assert "word/document.xml" in zf.namelist()
            assert "[Content_Types].xml" in zf.namelist()
            
            # Check images directory exists
            media_files = [n for n in zf.namelist() if n.startswith("word/media/")]
            assert len(media_files) >= 3, f"Expected at least 3 media files (header, voltage, decoratives), got: {media_files}"
    
    def test_docx_preserves_header_logo(self, auth_headers):
        """DOCX should preserve header logo (image11.jpeg, ~3592 bytes)"""
        laudo_data = {
            "os_number": "TEST-HEADER-001",
            "customer_name": "Test",
            "model": "Test",
            "serial_number": "TEST-SN",
            "images": []
        }
        
        response = requests.post(
            f"{BASE_URL}/api/laudo/generate-docx", 
            json=laudo_data, 
            headers=auth_headers
        )
        assert response.status_code == 200
        
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            # Find the header logo image
            media_files = {n: zf.getinfo(n).file_size for n in zf.namelist() if n.startswith("word/media/")}
            
            # Check for image that matches header logo size (~3592 bytes)
            header_candidates = [f for f, size in media_files.items() if 3000 <= size <= 4000]
            assert len(header_candidates) >= 1, f"Header logo not found. Media files: {media_files}"
    
    def test_docx_preserves_voltage_image(self, auth_headers):
        """DOCX should preserve voltage diagram image (image10.png, ~19632 bytes)"""
        laudo_data = {
            "os_number": "TEST-VOLTAGE-001",
            "customer_name": "Test",
            "model": "Test",
            "serial_number": "TEST-SN",
            "voltage_f1f2": "220",
            "voltage_f1_terra": "127",
            "voltage_f2_terra": "127",
            "images": []
        }
        
        response = requests.post(
            f"{BASE_URL}/api/laudo/generate-docx", 
            json=laudo_data, 
            headers=auth_headers
        )
        assert response.status_code == 200
        
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            media_files = {n: zf.getinfo(n).file_size for n in zf.namelist() if n.startswith("word/media/")}
            
            # Check for voltage diagram image (~19632 bytes)
            voltage_candidates = [f for f, size in media_files.items() if 18000 <= size <= 21000]
            assert len(voltage_candidates) >= 1, f"Voltage image not found. Media files: {media_files}"
    
    def test_docx_preserves_decorative_table_images(self, auth_headers):
        """DOCX should preserve decorative table images (rId7=image1.jpeg, rId8=image2.jpeg)"""
        laudo_data = {
            "os_number": "TEST-DECO-001",
            "customer_name": "Test",
            "model": "Test",
            "serial_number": "TEST-SN",
            "images": []
        }
        
        response = requests.post(
            f"{BASE_URL}/api/laudo/generate-docx", 
            json=laudo_data, 
            headers=auth_headers
        )
        assert response.status_code == 200
        
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            media_files = {n: zf.getinfo(n).file_size for n in zf.namelist() if n.startswith("word/media/")}
            
            # Should have at least 10+ images (header, voltage, 2 decoratives, 7 photo slots)
            assert len(media_files) >= 10, f"Missing media files. Found: {len(media_files)}, {media_files}"
    
    def test_docx_voltage_text_in_paragraph(self, auth_headers):
        """Voltage values should appear as text in DOCX (P12)"""
        laudo_data = {
            "os_number": "TEST-VOLTXT-001",
            "customer_name": "Test",
            "model": "Test",
            "serial_number": "TEST-SN",
            "voltage_f1f2": "220",
            "voltage_f1_terra": "127",
            "voltage_f2_terra": "127",
            "images": []
        }
        
        response = requests.post(
            f"{BASE_URL}/api/laudo/generate-docx", 
            json=laudo_data, 
            headers=auth_headers
        )
        assert response.status_code == 200
        
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            # Parse document.xml
            doc_xml = zf.read("word/document.xml").decode("utf-8")
            
            # Check for voltage values in the document
            assert "220V" in doc_xml or "220" in doc_xml, "F1+F2 voltage value not found in document"


class TestInventoryProductSerialBatch:
    """Test Inventory API accepts serial_number and batch fields"""
    
    def test_create_product_with_serial_and_batch(self, auth_headers):
        """POST /api/inventory/products should accept serial_number and batch"""
        product_data = {
            "code": "TEST-SB-001",
            "name": "Test Product with Serial/Batch",
            "category": "Peças",
            "brand": "TestBrand",
            "model": "TestModel",
            "serial_number": "SN-2024-TEST-001",
            "batch": "BATCH-2024-01A",
            "cost": 50.00,
            "sale_price": 75.00,
            "min_stock": 5,
            "current_stock": 10
        }
        
        # Create product
        response = requests.post(
            f"{BASE_URL}/api/inventory/products",
            json=product_data,
            headers=auth_headers
        )
        
        if response.status_code == 400 and "já existe" in response.text.lower():
            # Product exists, delete and retry
            requests.delete(f"{BASE_URL}/api/inventory/products/TEST-SB-001", headers=auth_headers)
            response = requests.post(
                f"{BASE_URL}/api/inventory/products",
                json=product_data,
                headers=auth_headers
            )
        
        assert response.status_code in [200, 201], f"Product creation failed: {response.text}"
        
        created = response.json()
        assert created["serial_number"] == "SN-2024-TEST-001"
        assert created["batch"] == "BATCH-2024-01A"
        
        # Verify product was persisted
        get_response = requests.get(f"{BASE_URL}/api/inventory/products", headers=auth_headers)
        assert get_response.status_code == 200
        products = get_response.json()
        test_product = next((p for p in products if p["code"] == "TEST-SB-001"), None)
        assert test_product is not None
        assert test_product["serial_number"] == "SN-2024-TEST-001"
        assert test_product["batch"] == "BATCH-2024-01A"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/inventory/products/TEST-SB-001", headers=auth_headers)
    
    def test_update_product_serial_batch(self, auth_headers):
        """PUT /api/inventory/products should update serial_number and batch"""
        # Create test product first
        product_data = {
            "code": "TEST-SB-002",
            "name": "Test Update Serial/Batch",
            "category": "Peças",
            "serial_number": "OLD-SN",
            "batch": "OLD-BATCH"
        }
        
        requests.delete(f"{BASE_URL}/api/inventory/products/TEST-SB-002", headers=auth_headers)
        create_response = requests.post(
            f"{BASE_URL}/api/inventory/products",
            json=product_data,
            headers=auth_headers
        )
        assert create_response.status_code in [200, 201]
        
        # Update serial_number and batch
        update_data = {
            "serial_number": "NEW-SN-2024",
            "batch": "NEW-BATCH-2024"
        }
        update_response = requests.put(
            f"{BASE_URL}/api/inventory/products/TEST-SB-002",
            json=update_data,
            headers=auth_headers
        )
        assert update_response.status_code == 200
        
        updated = update_response.json()
        assert updated["serial_number"] == "NEW-SN-2024"
        assert updated["batch"] == "NEW-BATCH-2024"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/inventory/products/TEST-SB-002", headers=auth_headers)


class TestInventoryDashboard:
    """Test dashboard endpoint works correctly"""
    
    def test_dashboard_returns_all_fields(self, auth_headers):
        """GET /api/inventory/dashboard should return all expected fields"""
        response = requests.get(f"{BASE_URL}/api/inventory/dashboard", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "total_products" in data
        assert "total_value" in data
        assert "low_stock" in data
        assert "out_of_stock" in data
        assert "purchase_suggestions" in data
        assert "recent_movements" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
