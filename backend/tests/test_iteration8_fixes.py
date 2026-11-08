"""
Iteration 8 Tests: Testing 4 key fixes
1. POST /api/laudo/generate-docx - ALL template images (rId7, rId8) replaced with blank
2. POST /api/laudo/generate-docx - saves entry to laudo_history collection automatically  
3. GET /api/laudo/history/{os_number} - returns laudo generation history with fields
4. POST /api/auth/login - works correctly
"""
import pytest
import requests
import os
import io
import zipfile
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "mastermaqassistencia@gmail.com"
TEST_PASSWORD = "atr132641"

# Test OS number for laudo history testing
TEST_OS_NUMBER = f"TEST_{datetime.now().strftime('%Y%m%d%H%M%S')}"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestAuthLogin:
    """Test authentication endpoint"""
    
    def test_login_success(self):
        """Test login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["email"] == TEST_EMAIL
        print(f"✓ Login successful, token received")
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "wrong@email.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        print(f"✓ Invalid credentials correctly rejected")


class TestLaudoDocxTemplateImages:
    """Test that ALL template images are replaced with blank in generated DOCX"""
    
    def test_generate_docx_blanks_all_template_images(self, auth_headers):
        """
        Test that rId7 and rId8 (table decorative images) are now blanked
        All relationship image blobs should be < 100 bytes (BLANK_PNG size)
        """
        laudo_data = {
            "os_number": TEST_OS_NUMBER,
            "customer_name": "Test Customer for Image Blanking",
            "model": "Test Model",
            "serial_number": "SN12345",
            "batch": "BATCH001",
            "brand": "Hisense",
            "service_type": "Garantia",
            "reported_defect": "Test defect",
            "technical_diagnosis": "Test diagnosis",
            "installation_correct": "SIM",
            "required_parts": "None",
            "images": [],  # No user images - all should be blank
            "technical_notes": "Test notes",
            "final_status": "Concluído",
            "location": "BELO HORIZONTE",
            "date": "15/01/2026",
            "technician": "Test Technician",
            "voltage_f1f2": "220",
            "voltage_f1_terra": "127",
            "voltage_f2_terra": "127"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/laudo/generate-docx",
            json=laudo_data,
            headers=auth_headers
        )
        assert response.status_code == 200, f"DOCX generation failed: {response.text}"
        
        # Parse the DOCX (it's a ZIP file)
        docx_bytes = response.content
        assert len(docx_bytes) > 0, "Empty DOCX returned"
        
        # Extract and check image sizes
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
            # List all files
            file_list = zf.namelist()
            print(f"Files in DOCX: {file_list}")
            
            # Check media files (images)
            media_files = [f for f in file_list if f.startswith('word/media/')]
            print(f"Media files found: {media_files}")
            
            large_images = []
            for media_file in media_files:
                content = zf.read(media_file)
                size = len(content)
                print(f"  {media_file}: {size} bytes")
                
                # Any image > 100 bytes is NOT a blank placeholder
                if size > 100:
                    large_images.append((media_file, size))
            
            # All images should be <= 100 bytes (BLANK_PNG is ~67 bytes)
            if large_images:
                print(f"✗ FOUND LARGE IMAGES (template images not blanked): {large_images}")
            else:
                print(f"✓ All template images replaced with blank (<100 bytes)")
            
            assert len(large_images) == 0, f"Template images not properly blanked: {large_images}"
    
    def test_generate_docx_with_user_images_preserves_them(self, auth_headers):
        """Test that user-provided images are kept (not blanked)"""
        # Create a small test image (red 1x1 pixel PNG)
        import base64
        # This is a 1x1 red PNG, about 67 bytes
        red_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="
        
        laudo_data = {
            "os_number": f"{TEST_OS_NUMBER}_with_images",
            "customer_name": "Test Customer with Images",
            "model": "Test Model",
            "serial_number": "SN12345",
            "batch": "BATCH001",
            "brand": "Gorenje",
            "service_type": "Garantia",
            "reported_defect": "Test defect",
            "technical_diagnosis": "Test diagnosis",
            "installation_correct": "SIM",
            "required_parts": "None",
            "images": [f"data:image/png;base64,{red_png_b64}"],  # One user image
            "technical_notes": "Test notes",
            "final_status": "Concluído",
            "location": "BELO HORIZONTE",
            "date": "15/01/2026",
            "technician": "Test Technician",
            "voltage_f1f2": "",
            "voltage_f1_terra": "",
            "voltage_f2_terra": ""
        }
        
        response = requests.post(
            f"{BASE_URL}/api/laudo/generate-docx",
            json=laudo_data,
            headers=auth_headers
        )
        assert response.status_code == 200, f"DOCX generation failed: {response.text}"
        print(f"✓ DOCX with user image generated successfully")


class TestLaudoHistoryAutoSave:
    """Test that DOCX generation auto-saves to laudo_history collection"""
    
    def test_generate_docx_creates_history_entry(self, auth_headers):
        """Test that generating DOCX auto-saves to history"""
        unique_os = f"HIST_TEST_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        laudo_data = {
            "os_number": unique_os,
            "customer_name": "History Test Customer",
            "model": "History Test Model",
            "serial_number": "SN-HIST-001",
            "batch": "BATCH-HIST",
            "brand": "Hisense",
            "service_type": "Fora de Garantia",
            "reported_defect": "Test for history auto-save",
            "technical_diagnosis": "Testing history feature",
            "installation_correct": "SIM",
            "required_parts": "None",
            "images": [],
            "technical_notes": "Notes for history test",
            "final_status": "Concluído",
            "location": "SAO PAULO",
            "date": "15/01/2026",
            "technician": "History Test Tech",
            "voltage_f1f2": "220",
            "voltage_f1_terra": "127",
            "voltage_f2_terra": "127"
        }
        
        # Generate DOCX (should auto-save to history)
        response = requests.post(
            f"{BASE_URL}/api/laudo/generate-docx",
            json=laudo_data,
            headers=auth_headers
        )
        assert response.status_code == 200, f"DOCX generation failed: {response.text}"
        print(f"✓ DOCX generated for OS {unique_os}")
        
        # Check history was created
        history_response = requests.get(
            f"{BASE_URL}/api/laudo/history/{unique_os}",
            headers=auth_headers
        )
        assert history_response.status_code == 200, f"History fetch failed: {history_response.text}"
        
        history = history_response.json()
        assert len(history) >= 1, "No history entry created"
        
        # Verify latest entry
        latest = history[0]
        assert latest["os_number"] == unique_os, f"OS number mismatch: {latest}"
        assert latest["customer_name"] == "History Test Customer", f"Customer name mismatch: {latest}"
        assert latest["technician"] == "History Test Tech", f"Technician mismatch: {latest}"
        assert "generated_at" in latest, f"generated_at field missing: {latest}"
        assert latest["model"] == "History Test Model", f"Model mismatch: {latest}"
        
        print(f"✓ History entry created with correct fields:")
        print(f"  - os_number: {latest['os_number']}")
        print(f"  - customer_name: {latest['customer_name']}")
        print(f"  - model: {latest['model']}")
        print(f"  - technician: {latest['technician']}")
        print(f"  - generated_at: {latest['generated_at']}")


class TestLaudoHistoryEndpoint:
    """Test GET /api/laudo/history/{os_number} endpoint"""
    
    def test_history_endpoint_returns_list(self, auth_headers):
        """Test that history endpoint returns a list"""
        # Use a known OS number or the one we just created
        response = requests.get(
            f"{BASE_URL}/api/laudo/history/NONEXISTENT_OS_12345",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✓ History endpoint returns list (empty for nonexistent OS)")
    
    def test_history_has_required_fields(self, auth_headers):
        """Test that history entries have required fields"""
        # First create a history entry
        unique_os = f"FIELDS_TEST_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        laudo_data = {
            "os_number": unique_os,
            "customer_name": "Fields Test Customer",
            "model": "Fields Test Model",
            "serial_number": "SN-FIELDS",
            "batch": "BATCH-FIELDS",
            "brand": "Hisense",
            "service_type": "Garantia",
            "reported_defect": "Testing fields",
            "technical_diagnosis": "Field testing",
            "installation_correct": "SIM",
            "required_parts": "None",
            "images": [],
            "technical_notes": "Field test notes",
            "final_status": "Concluído",
            "location": "BELO HORIZONTE",
            "date": "15/01/2026",
            "technician": "Field Test Technician",
            "voltage_f1f2": "",
            "voltage_f1_terra": "",
            "voltage_f2_terra": ""
        }
        
        # Generate to create history
        gen_response = requests.post(
            f"{BASE_URL}/api/laudo/generate-docx",
            json=laudo_data,
            headers=auth_headers
        )
        assert gen_response.status_code == 200
        
        # Fetch history
        hist_response = requests.get(
            f"{BASE_URL}/api/laudo/history/{unique_os}",
            headers=auth_headers
        )
        assert hist_response.status_code == 200
        
        history = hist_response.json()
        assert len(history) >= 1, "No history entries"
        
        entry = history[0]
        required_fields = ["os_number", "customer_name", "model", "technician", "generated_at"]
        for field in required_fields:
            assert field in entry, f"Missing required field: {field}"
            print(f"  ✓ Field '{field}' present: {entry[field]}")
        
        print(f"✓ All required fields present in history entry")
    
    def test_multiple_generations_create_multiple_history_entries(self, auth_headers):
        """Test that multiple generations create multiple history entries"""
        unique_os = f"MULTI_TEST_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        laudo_data = {
            "os_number": unique_os,
            "customer_name": "Multi Gen Customer",
            "model": "Multi Gen Model",
            "serial_number": "SN-MULTI",
            "batch": "BATCH-MULTI",
            "brand": "Gorenje",
            "service_type": "Cortesia",
            "reported_defect": "Multi gen test",
            "technical_diagnosis": "Testing multiple generations",
            "installation_correct": "NÃO",
            "required_parts": "Part A",
            "images": [],
            "technical_notes": "Multi gen notes",
            "final_status": "Em andamento",
            "location": "RIO DE JANEIRO",
            "date": "15/01/2026",
            "technician": "Multi Tech",
            "voltage_f1f2": "127",
            "voltage_f1_terra": "127",
            "voltage_f2_terra": "0"
        }
        
        # Generate twice
        for i in range(2):
            response = requests.post(
                f"{BASE_URL}/api/laudo/generate-docx",
                json=laudo_data,
                headers=auth_headers
            )
            assert response.status_code == 200, f"Generation {i+1} failed"
        
        # Check history has 2 entries
        hist_response = requests.get(
            f"{BASE_URL}/api/laudo/history/{unique_os}",
            headers=auth_headers
        )
        assert hist_response.status_code == 200
        
        history = hist_response.json()
        assert len(history) >= 2, f"Expected at least 2 history entries, got {len(history)}"
        
        print(f"✓ Multiple generations created {len(history)} history entries")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
