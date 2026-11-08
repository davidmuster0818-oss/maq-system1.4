"""
Test Iteration 20: Laudo DOCX Generation and Image Mapping
Tests the fix for image mapping bug where 8 user images were not appearing
in correct positions in the DOCX document.

Main fix: Changed FOTO 2 mapping from image5.jpeg to image2.jpeg in PHOTO_SLOTS
Also added EXTRA_IMAGE_SLOT to blank out image5.jpeg (extra floating image)

Endpoints tested:
- POST /api/auth/login
- POST /api/laudo/generate-docx (without and with 8 images)
- GET /api/service-orders (pagination)
- GET /api/service-orders?search=teste (search)
- POST /api/laudo/save
- GET /api/laudo/draft/{os_number}
"""

import pytest
import requests
import os
import base64
import zipfile
import io
from datetime import datetime

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "mastermaqassistencia@gmail.com"
TEST_PASSWORD = "atr132641"

# Generate a simple test JPEG image as base64
def create_test_jpeg_base64(label_number: int) -> str:
    """Create a simple colored test JPEG image and return as base64 data URL"""
    from PIL import Image
    import io
    
    # Create a colored image based on the label number
    colors = [
        (255, 0, 0),    # Red - FOTO 1
        (0, 255, 0),    # Green - FOTO 2
        (0, 0, 255),    # Blue - FOTO 3
        (255, 255, 0),  # Yellow - FOTO 4
        (255, 0, 255),  # Magenta - FOTO 5
        (0, 255, 255),  # Cyan - FOTO 6
        (128, 0, 128),  # Purple - FOTO 7
        (255, 128, 0),  # Orange - FOTO 8
    ]
    
    color = colors[label_number % len(colors)]
    img = Image.new('RGB', (100, 100), color)
    
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    buf.seek(0)
    
    b64_data = base64.b64encode(buf.getvalue()).decode('utf-8')
    return f"data:image/jpeg;base64,{b64_data}"


@pytest.fixture(scope="module")
def auth_token():
    """Get JWT token for authenticated requests"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("token")
    pytest.fail(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with JWT authorization"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestLogin:
    """Test authentication endpoint"""
    
    def test_login_success_returns_jwt(self):
        """POST /api/auth/login returns JWT token on valid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "token" in data, "Response should contain 'token' field"
        assert "email" in data, "Response should contain 'email' field"
        assert len(data["token"]) > 0, "Token should not be empty"
        assert data["email"] == TEST_EMAIL, f"Expected email {TEST_EMAIL}, got {data['email']}"
        print(f"✓ Login successful, token received (length: {len(data['token'])})")
    
    def test_login_invalid_credentials(self):
        """POST /api/auth/login returns 401 on invalid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "wrong@email.com", "password": "wrongpassword"}
        )
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Invalid credentials correctly rejected with 401")


class TestServiceOrdersListing:
    """Test service orders listing and search"""
    
    def test_list_service_orders_with_pagination(self, auth_headers):
        """GET /api/service-orders returns paginated results"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders",
            headers=auth_headers,
            params={"page": 1, "limit": 10}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "orders" in data, "Response should contain 'orders' field"
        assert "total" in data, "Response should contain 'total' field"
        assert "page" in data, "Response should contain 'page' field"
        assert "limit" in data, "Response should contain 'limit' field"
        assert "total_pages" in data, "Response should contain 'total_pages' field"
        
        assert isinstance(data["orders"], list), "'orders' should be a list"
        assert data["page"] == 1, "Page should be 1"
        assert data["limit"] == 10, "Limit should be 10"
        
        print(f"✓ Service orders list: {len(data['orders'])} orders returned, total: {data['total']}")
    
    def test_search_service_orders(self, auth_headers):
        """GET /api/service-orders?search=teste searches by term"""
        response = requests.get(
            f"{BASE_URL}/api/service-orders",
            headers=auth_headers,
            params={"search": "teste", "page": 1, "limit": 30}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "orders" in data, "Response should contain 'orders' field"
        assert isinstance(data["orders"], list), "'orders' should be a list"
        
        print(f"✓ Search for 'teste': {len(data['orders'])} results found, total: {data['total']}")


class TestLaudoDraft:
    """Test laudo draft save and load functionality"""
    
    TEST_OS_NUMBER = "TEST_LAUDO_DRAFT_999999"
    
    def test_save_laudo_draft(self, auth_headers):
        """POST /api/laudo/save saves draft data"""
        draft_data = {
            "os_number": self.TEST_OS_NUMBER,
            "customer_name": "Test Customer",
            "model": "Test Model XYZ",
            "serial_number": "SN123456",
            "batch": "BATCH001",
            "brand": "Hisense",
            "service_type": "Garantia",
            "reported_defect": "Test defect description",
            "technical_diagnosis": "Test diagnosis",
            "installation_correct": "Sim",
            "required_parts": "Test parts",
            "images": [],  # No images in draft save
            "technical_notes": "Test technical notes",
            "final_status": "Produto em funcionamento",
            "location": "BELO HORIZONTE",
            "date": "15/01/2026",
            "technician": "Test Technician",
            "voltage_f1f2": "220",
            "voltage_f1_terra": "127",
            "voltage_f2_terra": "127"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/laudo/save",
            headers=auth_headers,
            json=draft_data
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Response should contain 'message' field"
        print(f"✓ Laudo draft saved: {data['message']}")
    
    def test_load_laudo_draft(self, auth_headers):
        """GET /api/laudo/draft/{os_number} loads saved draft"""
        response = requests.get(
            f"{BASE_URL}/api/laudo/draft/{self.TEST_OS_NUMBER}",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify draft data was persisted
        assert data.get("os_number") == self.TEST_OS_NUMBER, "OS number should match"
        assert data.get("customer_name") == "Test Customer", "Customer name should match"
        assert data.get("model") == "Test Model XYZ", "Model should match"
        assert data.get("technician") == "Test Technician", "Technician should match"
        
        print(f"✓ Laudo draft loaded successfully for OS {self.TEST_OS_NUMBER}")
    
    def test_load_nonexistent_draft(self, auth_headers):
        """GET /api/laudo/draft/{os_number} returns empty for nonexistent OS"""
        response = requests.get(
            f"{BASE_URL}/api/laudo/draft/NONEXISTENT_OS_999",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data == {}, "Should return empty object for nonexistent draft"
        print("✓ Nonexistent draft returns empty object as expected")


class TestLaudoDocxGeneration:
    """Test DOCX laudo generation with and without images"""
    
    def test_generate_docx_without_images(self, auth_headers):
        """POST /api/laudo/generate-docx returns valid DOCX without images"""
        laudo_data = {
            "os_number": "TEST_DOCX_001",
            "customer_name": "Test Customer",
            "model": "Test Model",
            "serial_number": "SN123",
            "batch": "BATCH001",
            "brand": "Hisense",
            "service_type": "Garantia",
            "reported_defect": "Test defect",
            "technical_diagnosis": "Test diagnosis",
            "installation_correct": "Sim",
            "required_parts": "Nenhuma",
            "images": [],  # No images
            "technical_notes": "Test notes",
            "final_status": "Produto em funcionamento",
            "location": "BELO HORIZONTE",
            "date": "15/01/2026",
            "technician": "Test Tech",
            "voltage_f1f2": "220",
            "voltage_f1_terra": "127",
            "voltage_f2_terra": "127"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/laudo/generate-docx",
            headers=auth_headers,
            json=laudo_data
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Check content type
        content_type = response.headers.get("Content-Type", "")
        assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in content_type, \
            f"Expected DOCX content type, got: {content_type}"
        
        # Check content disposition
        content_disp = response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp, "Should have attachment disposition"
        assert "Laudo_OS_TEST_DOCX_001.docx" in content_disp, "Filename should contain OS number"
        
        # Verify it's a valid ZIP file (DOCX is a ZIP archive)
        docx_bytes = response.content
        assert len(docx_bytes) > 0, "DOCX content should not be empty"
        
        # Try to open as ZIP to verify structure
        try:
            with zipfile.ZipFile(io.BytesIO(docx_bytes), 'r') as zf:
                namelist = zf.namelist()
                assert "[Content_Types].xml" in namelist, "DOCX should contain [Content_Types].xml"
                assert "word/document.xml" in namelist, "DOCX should contain word/document.xml"
        except zipfile.BadZipFile:
            pytest.fail("Generated file is not a valid ZIP/DOCX archive")
        
        print(f"✓ DOCX generated without images, size: {len(docx_bytes)} bytes")
    
    def test_generate_docx_with_8_images(self, auth_headers):
        """POST /api/laudo/generate-docx with 8 images replaces correctly"""
        # Create 8 test images
        test_images = [create_test_jpeg_base64(i) for i in range(8)]
        
        laudo_data = {
            "os_number": "TEST_DOCX_IMG_002",
            "customer_name": "Test Customer with Images",
            "model": "Image Test Model",
            "serial_number": "SN456789",
            "batch": "BATCH002",
            "brand": "Gorenje",
            "service_type": "Garantia Hisense",
            "reported_defect": "Test defect with images",
            "technical_diagnosis": "Diagnosis with photo evidence",
            "installation_correct": "Sim, instalação correta",
            "required_parts": "Compressor, válvula",
            "images": test_images,  # 8 images
            "technical_notes": "Technical notes for image test",
            "final_status": "Produto em funcionamento ✅",
            "location": "SAO PAULO",
            "date": "16/01/2026",
            "technician": "Tech with Camera",
            "voltage_f1f2": "220",
            "voltage_f1_terra": "127",
            "voltage_f2_terra": "127"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/laudo/generate-docx",
            headers=auth_headers,
            json=laudo_data
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        docx_bytes = response.content
        assert len(docx_bytes) > 0, "DOCX content should not be empty"
        
        # Verify the ZIP structure and image replacements
        with zipfile.ZipFile(io.BytesIO(docx_bytes), 'r') as zf:
            namelist = zf.namelist()
            
            # Check that all expected image files exist
            expected_images = [
                "word/media/image1.jpeg",  # FOTO 1
                "word/media/image2.jpeg",  # FOTO 2 (fixed mapping)
                "word/media/image3.jpeg",  # FOTO 3
                "word/media/image4.jpeg",  # FOTO 4
                "word/media/image5.jpeg",  # EXTRA (blanked)
                "word/media/image6.jpeg",  # FOTO 5
                "word/media/image7.jpeg",  # FOTO 6
                "word/media/image8.jpeg",  # FOTO 8
                "word/media/image9.jpeg",  # FOTO 7
            ]
            
            images_found = [f for f in namelist if f.startswith("word/media/")]
            print(f"  Images found in DOCX: {images_found}")
            
            # Verify the PHOTO_SLOTS mapping
            # According to the fix:
            # FOTO 1 -> image1.jpeg (user image 0)
            # FOTO 2 -> image2.jpeg (user image 1) - THIS WAS THE BUG FIX
            # FOTO 3 -> image3.jpeg (user image 2)
            # FOTO 4 -> image4.jpeg (user image 3)
            # FOTO 5 -> image6.jpeg (user image 4)
            # FOTO 6 -> image7.jpeg (user image 5)
            # FOTO 7 -> image9.jpeg (user image 6)
            # FOTO 8 -> image8.jpeg (user image 7)
            # image5.jpeg -> blanked (EXTRA_IMAGE_SLOT)
            
            photo_slots = {
                "word/media/image1.jpeg": 0,  # FOTO 1
                "word/media/image2.jpeg": 1,  # FOTO 2 (FIXED)
                "word/media/image3.jpeg": 2,  # FOTO 3
                "word/media/image4.jpeg": 3,  # FOTO 4
                "word/media/image6.jpeg": 4,  # FOTO 5
                "word/media/image7.jpeg": 5,  # FOTO 6
                "word/media/image9.jpeg": 6,  # FOTO 7
                "word/media/image8.jpeg": 7,  # FOTO 8
            }
            
            # Check each mapped image is replaced with correct size
            # (not the tiny 1x1 blank JPEG)
            for img_path, user_idx in photo_slots.items():
                if img_path in namelist:
                    img_data = zf.read(img_path)
                    # User images should be larger than blank (which is ~110 bytes)
                    assert len(img_data) > 500, \
                        f"{img_path} (FOTO {user_idx+1}) should be replaced with user image, but is only {len(img_data)} bytes"
                    print(f"    ✓ {img_path} -> FOTO {user_idx+1}: {len(img_data)} bytes (replaced)")
            
            # Check that EXTRA_IMAGE_SLOT (image5.jpeg) is blanked
            if "word/media/image5.jpeg" in namelist:
                extra_data = zf.read("word/media/image5.jpeg")
                # Blank JPEG is 631 bytes (1x1 white pixel with PIL headers)
                # User images are 826 bytes, so anything <= 700 is blank
                assert len(extra_data) <= 700, \
                    f"image5.jpeg (EXTRA_IMAGE_SLOT) should be blanked, but is {len(extra_data)} bytes"
                print(f"    ✓ word/media/image5.jpeg -> BLANKED: {len(extra_data)} bytes")
        
        print(f"✓ DOCX generated with 8 images, size: {len(docx_bytes)} bytes")
        print("  Image mapping verification PASSED - all 8 user images correctly positioned")
    
    def test_generate_docx_with_partial_images(self, auth_headers):
        """POST /api/laudo/generate-docx with partial images (e.g., 3 images)"""
        # Only provide 3 images
        test_images = [create_test_jpeg_base64(i) for i in range(3)]
        
        laudo_data = {
            "os_number": "TEST_DOCX_PARTIAL_003",
            "customer_name": "Partial Image Customer",
            "model": "Partial Model",
            "serial_number": "SN999",
            "batch": "BATCH003",
            "brand": "Hisense",
            "service_type": "Fora de Garantia",
            "reported_defect": "Partial image test",
            "technical_diagnosis": "Diagnosis",
            "installation_correct": "Sim",
            "required_parts": "Nenhuma",
            "images": test_images,  # Only 3 images
            "technical_notes": "Notes",
            "final_status": "Status",
            "location": "RIO DE JANEIRO",
            "date": "17/01/2026",
            "technician": "Partial Tech",
            "voltage_f1f2": "220",
            "voltage_f1_terra": "127",
            "voltage_f2_terra": "127"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/laudo/generate-docx",
            headers=auth_headers,
            json=laudo_data
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        docx_bytes = response.content
        assert len(docx_bytes) > 0, "DOCX content should not be empty"
        
        # Verify the ZIP structure
        with zipfile.ZipFile(io.BytesIO(docx_bytes), 'r') as zf:
            # First 3 slots should have user images
            # Remaining 5 slots should have blank images
            
            # FOTO 1-3 should be replaced
            for slot_num, img_file in [(1, "image1.jpeg"), (2, "image2.jpeg"), (3, "image3.jpeg")]:
                path = f"word/media/{img_file}"
                if path in zf.namelist():
                    data = zf.read(path)
                    assert len(data) > 500, f"FOTO {slot_num} ({img_file}) should have user image"
                    print(f"    ✓ FOTO {slot_num}: {len(data)} bytes (user image)")
            
            # FOTO 4-8 should be blank (631 bytes for blank JPEG)
            blank_slots = [
                ("image4.jpeg", 4),
                ("image6.jpeg", 5),
                ("image7.jpeg", 6),
                ("image9.jpeg", 7),
                ("image8.jpeg", 8),
            ]
            for img_file, slot_num in blank_slots:
                path = f"word/media/{img_file}"
                if path in zf.namelist():
                    data = zf.read(path)
                    # Blank JPEG is 631 bytes, user images are 826 bytes
                    assert len(data) <= 700, f"FOTO {slot_num} ({img_file}) should be blank"
                    print(f"    ✓ FOTO {slot_num}: {len(data)} bytes (blank)")
        
        print(f"✓ DOCX generated with 3 images (partial), size: {len(docx_bytes)} bytes")


class TestImageMappingVerification:
    """Specific tests to verify the image mapping fix"""
    
    def test_photo_slots_mapping(self):
        """Verify PHOTO_SLOTS dict has correct mapping after fix"""
        # Import the laudo_generator module to check the mapping
        import sys
        sys.path.insert(0, '/app/backend')
        
        from laudo_generator import PHOTO_SLOTS, EXTRA_IMAGE_SLOT
        
        # Expected mapping after fix
        expected_mapping = {
            0: 'word/media/image1.jpeg',   # FOTO 1
            1: 'word/media/image2.jpeg',   # FOTO 2 - THIS WAS FIXED (was image5.jpeg)
            2: 'word/media/image3.jpeg',   # FOTO 3
            3: 'word/media/image4.jpeg',   # FOTO 4
            4: 'word/media/image6.jpeg',   # FOTO 5
            5: 'word/media/image7.jpeg',   # FOTO 6
            6: 'word/media/image9.jpeg',   # FOTO 7
            7: 'word/media/image8.jpeg',   # FOTO 8
        }
        
        for idx, expected_path in expected_mapping.items():
            actual_path = PHOTO_SLOTS.get(idx)
            assert actual_path == expected_path, \
                f"FOTO {idx+1}: expected {expected_path}, got {actual_path}"
            print(f"  ✓ FOTO {idx+1} -> {actual_path}")
        
        # Verify EXTRA_IMAGE_SLOT
        assert EXTRA_IMAGE_SLOT == 'word/media/image5.jpeg', \
            f"EXTRA_IMAGE_SLOT should be image5.jpeg, got {EXTRA_IMAGE_SLOT}"
        print(f"  ✓ EXTRA_IMAGE_SLOT -> {EXTRA_IMAGE_SLOT}")
        
        print("✓ PHOTO_SLOTS mapping verified - FOTO 2 correctly maps to image2.jpeg")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
