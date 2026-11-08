"""
Iteration 19: Test Digital Signature (Assinafy) Feature
Tests for:
- POST /api/service-orders/{os_number}/sign - Sign an OS with tech and client signatures
- GET /api/service-orders/{os_number}/signatures - Get signature data for an OS
- Error handling for already signed OS
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL')
if BASE_URL:
    BASE_URL = BASE_URL.rstrip('/')

# Test data - small valid PNG base64 
TEST_SIGNATURE_B64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


class TestSignatureEndpoints:
    """Tests for digital signature API endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test fixtures"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get auth token
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "mastermaqassistencia@gmail.com",
            "password": "atr132641"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
    
    def test_get_signatures_unsigned_os(self):
        """GET /api/service-orders/{os_number}/signatures returns signed=false for unsigned OS"""
        # First find an unsigned OS
        orders_resp = self.session.get(f"{BASE_URL}/api/service-orders?limit=10")
        assert orders_resp.status_code == 200
        orders = orders_resp.json().get("orders", [])
        
        unsigned_os = None
        for order in orders:
            if not order.get("signature_technician") and not order.get("signature_client"):
                unsigned_os = order
                break
        
        if not unsigned_os:
            pytest.skip("No unsigned OS found for testing")
        
        os_number = unsigned_os["os_number"]
        resp = self.session.get(f"{BASE_URL}/api/service-orders/{os_number}/signatures")
        
        assert resp.status_code == 200, f"Failed to get signatures: {resp.text}"
        data = resp.json()
        
        # Verify response structure
        assert "signed" in data, "Response missing 'signed' field"
        assert data["signed"] == False, f"Expected signed=false for unsigned OS, got {data['signed']}"
        assert "order_summary" in data, "Response missing 'order_summary' field"
        assert data["order_summary"]["os_number"] == os_number
        print(f"PASS: GET /api/service-orders/{os_number}/signatures returns signed=false")
    
    def test_get_signatures_returns_order_summary(self):
        """GET /api/service-orders/{os_number}/signatures returns order_summary with key fields"""
        orders_resp = self.session.get(f"{BASE_URL}/api/service-orders?limit=1")
        assert orders_resp.status_code == 200
        orders = orders_resp.json().get("orders", [])
        
        if not orders:
            pytest.skip("No orders found")
        
        os_number = orders[0]["os_number"]
        resp = self.session.get(f"{BASE_URL}/api/service-orders/{os_number}/signatures")
        
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify order_summary has expected fields
        summary = data.get("order_summary", {})
        expected_fields = ["os_number", "customer_name", "product", "status"]
        for field in expected_fields:
            assert field in summary, f"order_summary missing field: {field}"
        
        print(f"PASS: GET /api/service-orders/{os_number}/signatures returns order_summary with key fields")
    
    def test_get_signatures_404_invalid_os(self):
        """GET /api/service-orders/{os_number}/signatures returns 404 for invalid OS"""
        resp = self.session.get(f"{BASE_URL}/api/service-orders/INVALID_OS_99999/signatures")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("PASS: GET /api/service-orders/INVALID_OS_99999/signatures returns 404")
    
    def test_sign_os_success(self):
        """POST /api/service-orders/{os_number}/sign accepts signatures and updates OS to Finalizada"""
        # First create a test OS that we can sign
        # Get next OSE number
        next_resp = self.session.get(f"{BASE_URL}/api/service-orders/next-ose-number")
        assert next_resp.status_code == 200
        test_os_number = f"TEST_SIG_{next_resp.json()['next_ose_number']}"
        
        # Create the test OS
        create_payload = {
            "os_number": test_os_number,
            "customer_name": "TEST_SIGNATURE_CLIENT",
            "registration_date": "2025-01-15",
            "cep": "30130-000",
            "address": "Rua Teste",
            "number": "123",
            "neighborhood": "Centro",
            "city": "Belo Horizonte",
            "state": "MG",
            "phone1": "31999999999",
            "product": "TESTE ASSINATURA",
            "brand": "TESTE",
            "model": "SIG-001",
            "reported_defect": "Teste de assinatura digital",
            "status": "Aguardando Conserto",
            "technician": "Tecnico Teste"
        }
        
        create_resp = self.session.post(f"{BASE_URL}/api/service-orders", json=create_payload)
        if create_resp.status_code == 400 and "já cadastrada" in create_resp.text:
            # OS exists, try to delete and recreate
            self.session.delete(f"{BASE_URL}/api/service-orders/{test_os_number}")
            create_resp = self.session.post(f"{BASE_URL}/api/service-orders", json=create_payload)
        
        assert create_resp.status_code == 200, f"Failed to create test OS: {create_resp.text}"
        
        # Now sign the OS
        sign_payload = {
            "signature_technician": TEST_SIGNATURE_B64,
            "signature_client": TEST_SIGNATURE_B64
        }
        
        sign_resp = self.session.post(f"{BASE_URL}/api/service-orders/{test_os_number}/sign", json=sign_payload)
        
        assert sign_resp.status_code == 200, f"Failed to sign OS: {sign_resp.text}"
        result = sign_resp.json()
        
        # Verify the response
        assert result.get("signature_technician") == TEST_SIGNATURE_B64, "signature_technician not saved"
        assert result.get("signature_client") == TEST_SIGNATURE_B64, "signature_client not saved"
        assert result.get("signature_date") is not None, "signature_date not set"
        assert result.get("status") == "Finalizada", f"Expected status 'Finalizada', got {result.get('status')}"
        
        print(f"PASS: POST /api/service-orders/{test_os_number}/sign accepts signatures and updates status to Finalizada")
        
        # Cleanup - delete the test OS
        self.session.delete(f"{BASE_URL}/api/service-orders/{test_os_number}")
    
    def test_sign_os_already_signed_returns_400(self):
        """POST /api/service-orders/{os_number}/sign returns 400 for already signed OS"""
        # Create and sign a test OS first
        next_resp = self.session.get(f"{BASE_URL}/api/service-orders/next-ose-number")
        assert next_resp.status_code == 200
        test_os_number = f"TEST_DOUBLE_SIG_{next_resp.json()['next_ose_number']}"
        
        create_payload = {
            "os_number": test_os_number,
            "customer_name": "TEST_DOUBLE_SIGN",
            "registration_date": "2025-01-15",
            "cep": "30130-000",
            "address": "Rua Teste",
            "number": "456",
            "neighborhood": "Centro",
            "city": "Belo Horizonte",
            "state": "MG",
            "phone1": "31999999999",
            "product": "TESTE DUPLA ASSINATURA",
            "brand": "TESTE",
            "model": "SIG-002",
            "reported_defect": "Teste de erro em dupla assinatura",
            "status": "Aguardando Conserto"
        }
        
        create_resp = self.session.post(f"{BASE_URL}/api/service-orders", json=create_payload)
        if create_resp.status_code == 400:
            self.session.delete(f"{BASE_URL}/api/service-orders/{test_os_number}")
            create_resp = self.session.post(f"{BASE_URL}/api/service-orders", json=create_payload)
        
        assert create_resp.status_code == 200, f"Failed to create test OS: {create_resp.text}"
        
        # Sign it once
        sign_payload = {
            "signature_technician": TEST_SIGNATURE_B64,
            "signature_client": TEST_SIGNATURE_B64
        }
        sign_resp = self.session.post(f"{BASE_URL}/api/service-orders/{test_os_number}/sign", json=sign_payload)
        assert sign_resp.status_code == 200, "First sign should succeed"
        
        # Try to sign it again - should fail with 400
        second_sign_resp = self.session.post(f"{BASE_URL}/api/service-orders/{test_os_number}/sign", json=sign_payload)
        
        assert second_sign_resp.status_code == 400, f"Expected 400 for already signed OS, got {second_sign_resp.status_code}"
        assert "já foi assinada" in second_sign_resp.text.lower() or "already" in second_sign_resp.text.lower(), \
            f"Expected error message about already signed, got: {second_sign_resp.text}"
        
        print(f"PASS: POST /api/service-orders/{test_os_number}/sign returns 400 for already signed OS")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/service-orders/{test_os_number}")
    
    def test_get_signatures_after_signing(self):
        """GET /api/service-orders/{os_number}/signatures returns signed=true with signature data after signing"""
        # Create and sign a test OS
        next_resp = self.session.get(f"{BASE_URL}/api/service-orders/next-ose-number")
        assert next_resp.status_code == 200
        test_os_number = f"TEST_GET_SIG_{next_resp.json()['next_ose_number']}"
        
        create_payload = {
            "os_number": test_os_number,
            "customer_name": "TEST_GET_SIGNATURES",
            "registration_date": "2025-01-15",
            "cep": "30130-000",
            "address": "Rua Teste",
            "number": "789",
            "neighborhood": "Centro",
            "city": "Belo Horizonte",
            "state": "MG",
            "phone1": "31999999999",
            "product": "TESTE GET ASSINATURAS",
            "brand": "TESTE",
            "model": "SIG-003",
            "reported_defect": "Teste de recuperacao de assinaturas",
            "status": "Aguardando Conserto",
            "technician": "Tecnico Verificacao"
        }
        
        create_resp = self.session.post(f"{BASE_URL}/api/service-orders", json=create_payload)
        if create_resp.status_code == 400:
            self.session.delete(f"{BASE_URL}/api/service-orders/{test_os_number}")
            create_resp = self.session.post(f"{BASE_URL}/api/service-orders", json=create_payload)
        
        assert create_resp.status_code == 200
        
        # Sign it
        sign_payload = {
            "signature_technician": TEST_SIGNATURE_B64,
            "signature_client": TEST_SIGNATURE_B64
        }
        sign_resp = self.session.post(f"{BASE_URL}/api/service-orders/{test_os_number}/sign", json=sign_payload)
        assert sign_resp.status_code == 200
        
        # Now get signatures
        get_resp = self.session.get(f"{BASE_URL}/api/service-orders/{test_os_number}/signatures")
        assert get_resp.status_code == 200
        data = get_resp.json()
        
        # Verify signed is true and has signature data
        assert data["signed"] == True, f"Expected signed=true, got {data['signed']}"
        assert data["signature_technician"] == TEST_SIGNATURE_B64, "signature_technician not returned correctly"
        assert data["signature_client"] == TEST_SIGNATURE_B64, "signature_client not returned correctly"
        assert data["signature_date"] is not None, "signature_date not returned"
        
        # Verify order_summary reflects finalized status
        assert data["order_summary"]["status"] == "Finalizada", "order_summary.status should be Finalizada"
        
        print(f"PASS: GET /api/service-orders/{test_os_number}/signatures returns signed=true with signature data")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/service-orders/{test_os_number}")
    
    def test_sign_os_404_invalid_os(self):
        """POST /api/service-orders/{os_number}/sign returns 404 for invalid OS"""
        sign_payload = {
            "signature_technician": TEST_SIGNATURE_B64,
            "signature_client": TEST_SIGNATURE_B64
        }
        resp = self.session.post(f"{BASE_URL}/api/service-orders/INVALID_OS_99999/sign", json=sign_payload)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("PASS: POST /api/service-orders/INVALID_OS_99999/sign returns 404")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
