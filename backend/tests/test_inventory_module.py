"""
Iteration 9 Tests: New Inventory/Estoque Module
Testing all inventory CRUD operations and business logic:
1. Products CRUD (create, read, update, delete)
2. Serial Numbers management
3. Movements with automatic stock updates
4. Suppliers CRUD
5. Dashboard with stats and purchase suggestions
6. Stock validation on exit movements
"""
import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "mastermaqassistencia@gmail.com"
TEST_PASSWORD = "atr132641"

# Unique test identifiers (for cleanup)
TEST_PREFIX = f"TEST_{datetime.now().strftime('%Y%m%d%H%M%S')}"


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
        """Test POST /api/auth/login works with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["email"] == TEST_EMAIL
        print(f"✓ POST /api/auth/login - Login successful")


class TestInventoryProducts:
    """Test Products CRUD - /api/inventory/products"""
    
    def test_get_products_list(self, auth_headers):
        """Test GET /api/inventory/products returns product list"""
        response = requests.get(f"{BASE_URL}/api/inventory/products", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/inventory/products - Returns {len(data)} products")
    
    def test_create_product_full_fields(self, auth_headers):
        """Test POST /api/inventory/products creates a product with all fields"""
        product_code = f"{TEST_PREFIX}_PROD1"
        product_data = {
            "code": product_code,
            "name": "Test Product Full Fields",
            "category": "Peças",
            "brand": "TestBrand",
            "model": "TestModel",
            "description": "Test product for iteration 9",
            "unit": "UN",
            "cost": 150.50,
            "sale_price": 250.00,
            "default_supplier": "Test Supplier Co",
            "min_stock": 10,
            "location": "Prateleira A1",
            "current_stock": 50
        }
        
        response = requests.post(
            f"{BASE_URL}/api/inventory/products",
            json=product_data,
            headers=auth_headers
        )
        assert response.status_code == 200, f"Create failed: {response.text}"
        
        data = response.json()
        assert data["code"] == product_code
        assert data["name"] == "Test Product Full Fields"
        assert data["category"] == "Peças"
        assert data["brand"] == "TestBrand"
        assert data["cost"] == 150.50
        assert data["sale_price"] == 250.00
        assert data["min_stock"] == 10
        assert data["current_stock"] == 50
        assert "created_at" in data
        print(f"✓ POST /api/inventory/products - Created product {product_code} with all fields")
        
        # Verify persistence via GET
        get_response = requests.get(f"{BASE_URL}/api/inventory/products", headers=auth_headers)
        products = get_response.json()
        created_product = next((p for p in products if p["code"] == product_code), None)
        assert created_product is not None, "Product not persisted"
        assert created_product["name"] == "Test Product Full Fields"
        print(f"✓ Product verified in GET /api/inventory/products list")
    
    def test_update_product(self, auth_headers):
        """Test PUT /api/inventory/products/{code} updates a product"""
        # First create a product to update
        product_code = f"{TEST_PREFIX}_PROD_UPDATE"
        create_data = {
            "code": product_code,
            "name": "Original Name",
            "category": "Equipamentos",
            "min_stock": 5,
            "current_stock": 20
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/inventory/products",
            json=create_data,
            headers=auth_headers
        )
        assert create_response.status_code == 200
        
        # Update the product
        update_data = {
            "name": "Updated Product Name",
            "category": "Ferramentas",
            "min_stock": 15,
            "location": "Prateleira B2"
        }
        
        update_response = requests.put(
            f"{BASE_URL}/api/inventory/products/{product_code}",
            json=update_data,
            headers=auth_headers
        )
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        
        updated = update_response.json()
        assert updated["name"] == "Updated Product Name"
        assert updated["category"] == "Ferramentas"
        assert updated["min_stock"] == 15
        assert updated["location"] == "Prateleira B2"
        assert "updated_at" in updated
        print(f"✓ PUT /api/inventory/products/{product_code} - Product updated successfully")
        
        # Verify via GET
        get_response = requests.get(f"{BASE_URL}/api/inventory/products", headers=auth_headers)
        products = get_response.json()
        verified = next((p for p in products if p["code"] == product_code), None)
        assert verified["name"] == "Updated Product Name"
        print(f"✓ Update verified in product list")
    
    def test_delete_product(self, auth_headers):
        """Test DELETE /api/inventory/products/{code} deletes a product"""
        # First create a product to delete
        product_code = f"{TEST_PREFIX}_PROD_DELETE"
        create_data = {
            "code": product_code,
            "name": "Product to Delete",
            "category": "Consumíveis",
            "current_stock": 10
        }
        
        requests.post(
            f"{BASE_URL}/api/inventory/products",
            json=create_data,
            headers=auth_headers
        )
        
        # Delete
        delete_response = requests.delete(
            f"{BASE_URL}/api/inventory/products/{product_code}",
            headers=auth_headers
        )
        assert delete_response.status_code == 200, f"Delete failed: {delete_response.text}"
        
        # Verify deletion via GET
        get_response = requests.get(f"{BASE_URL}/api/inventory/products", headers=auth_headers)
        products = get_response.json()
        deleted_product = next((p for p in products if p["code"] == product_code), None)
        assert deleted_product is None, "Product still exists after deletion"
        print(f"✓ DELETE /api/inventory/products/{product_code} - Product deleted successfully")


class TestInventoryMovements:
    """Test Movements - /api/inventory/movements"""
    
    def test_create_entry_movement_updates_stock(self, auth_headers):
        """Test POST /api/inventory/movements creates entry and updates product stock automatically"""
        # Create a product first
        product_code = f"{TEST_PREFIX}_MOV_ENTRY"
        create_data = {
            "code": product_code,
            "name": "Movement Entry Test Product",
            "category": "Peças",
            "current_stock": 10,
            "min_stock": 5
        }
        requests.post(f"{BASE_URL}/api/inventory/products", json=create_data, headers=auth_headers)
        
        # Create entry movement
        movement_data = {
            "product_code": product_code,
            "quantity": 25,
            "movement_type": "Entrada",
            "reason": "Compra",
            "document": "NF-12345",
            "notes": "Test entry movement"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/inventory/movements",
            json=movement_data,
            headers=auth_headers
        )
        assert response.status_code == 200, f"Movement creation failed: {response.text}"
        
        movement = response.json()
        assert movement["product_code"] == product_code
        assert movement["quantity"] == 25
        assert movement["movement_type"] == "Entrada"
        assert movement["previous_stock"] == 10
        assert movement["new_stock"] == 35  # 10 + 25
        assert "date" in movement
        print(f"✓ POST /api/inventory/movements - Entry created, stock 10→35")
        
        # Verify product stock was updated
        get_response = requests.get(f"{BASE_URL}/api/inventory/products", headers=auth_headers)
        products = get_response.json()
        product = next((p for p in products if p["code"] == product_code), None)
        assert product["current_stock"] == 35, f"Stock not updated: {product['current_stock']}"
        print(f"✓ Product stock automatically updated to 35")
    
    def test_exit_movement_validates_stock(self, auth_headers):
        """Test POST /api/inventory/movements for exit validates stock is sufficient"""
        # Create a product with limited stock
        product_code = f"{TEST_PREFIX}_MOV_EXIT_VAL"
        create_data = {
            "code": product_code,
            "name": "Exit Validation Test Product",
            "category": "Peças",
            "current_stock": 5,
            "min_stock": 2
        }
        requests.post(f"{BASE_URL}/api/inventory/products", json=create_data, headers=auth_headers)
        
        # Try to exit more than available
        movement_data = {
            "product_code": product_code,
            "quantity": 10,  # More than available (5)
            "movement_type": "Saída",
            "reason": "Uso em OS",
            "document": "OS-99999",
            "notes": "Should fail - insufficient stock"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/inventory/movements",
            json=movement_data,
            headers=auth_headers
        )
        assert response.status_code == 400, f"Should return 400, got {response.status_code}"
        assert "insuficiente" in response.text.lower() or "insufficient" in response.text.lower()
        print(f"✓ Exit movement correctly validates insufficient stock (5 < 10)")
        
        # Now test successful exit
        exit_data = {
            "product_code": product_code,
            "quantity": 3,  # Within available
            "movement_type": "Saída",
            "reason": "Venda",
            "document": "NF-VENDA-001",
            "notes": "Valid exit"
        }
        
        exit_response = requests.post(
            f"{BASE_URL}/api/inventory/movements",
            json=exit_data,
            headers=auth_headers
        )
        assert exit_response.status_code == 200, f"Valid exit failed: {exit_response.text}"
        
        exit_mov = exit_response.json()
        assert exit_mov["previous_stock"] == 5
        assert exit_mov["new_stock"] == 2  # 5 - 3
        print(f"✓ Valid exit movement created, stock 5→2")


class TestInventoryDashboard:
    """Test Dashboard - /api/inventory/dashboard"""
    
    def test_dashboard_returns_stats(self, auth_headers):
        """Test GET /api/inventory/dashboard returns stats (total_products, total_value, low_stock, out_of_stock, purchase_suggestions)"""
        response = requests.get(f"{BASE_URL}/api/inventory/dashboard", headers=auth_headers)
        assert response.status_code == 200, f"Dashboard failed: {response.text}"
        
        data = response.json()
        
        # Check required fields exist
        required_fields = ["total_products", "total_value", "low_stock", "out_of_stock", "purchase_suggestions"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Verify types
        assert isinstance(data["total_products"], int)
        assert isinstance(data["total_value"], (int, float))
        assert isinstance(data["low_stock"], int)
        assert isinstance(data["out_of_stock"], int)
        assert isinstance(data["purchase_suggestions"], list)
        
        print(f"✓ GET /api/inventory/dashboard - Returns all required stats:")
        print(f"  - total_products: {data['total_products']}")
        print(f"  - total_value: R$ {data['total_value']:.2f}")
        print(f"  - low_stock: {data['low_stock']}")
        print(f"  - out_of_stock: {data['out_of_stock']}")
        print(f"  - purchase_suggestions: {len(data['purchase_suggestions'])} items")


class TestInventorySuppliers:
    """Test Suppliers CRUD - /api/inventory/suppliers"""
    
    def test_get_suppliers_list(self, auth_headers):
        """Test GET /api/inventory/suppliers returns supplier list"""
        response = requests.get(f"{BASE_URL}/api/inventory/suppliers", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/inventory/suppliers - Returns {len(data)} suppliers")
    
    def test_create_supplier(self, auth_headers):
        """Test POST /api/inventory/suppliers creates a supplier"""
        supplier_name = f"{TEST_PREFIX}_Supplier"
        supplier_data = {
            "name": supplier_name,
            "cnpj": "12.345.678/0001-99",
            "contact": "João Silva",
            "phone": "(31) 99999-1234",
            "email": "joao@testsupplier.com",
            "products_supplied": "Peças de refrigeração"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/inventory/suppliers",
            json=supplier_data,
            headers=auth_headers
        )
        assert response.status_code == 200, f"Create supplier failed: {response.text}"
        
        data = response.json()
        assert data["name"] == supplier_name
        assert data["cnpj"] == "12.345.678/0001-99"
        assert "created_at" in data
        print(f"✓ POST /api/inventory/suppliers - Created supplier {supplier_name}")
        
        # Verify via GET
        get_response = requests.get(f"{BASE_URL}/api/inventory/suppliers", headers=auth_headers)
        suppliers = get_response.json()
        created = next((s for s in suppliers if s["name"] == supplier_name), None)
        assert created is not None, "Supplier not persisted"
        print(f"✓ Supplier verified in list")
    
    def test_delete_supplier(self, auth_headers):
        """Test DELETE /api/inventory/suppliers/{name} deletes a supplier"""
        supplier_name = f"{TEST_PREFIX}_SupplierDelete"
        supplier_data = {
            "name": supplier_name,
            "cnpj": "98.765.432/0001-11"
        }
        
        requests.post(f"{BASE_URL}/api/inventory/suppliers", json=supplier_data, headers=auth_headers)
        
        # Delete
        delete_response = requests.delete(
            f"{BASE_URL}/api/inventory/suppliers/{supplier_name}",
            headers=auth_headers
        )
        assert delete_response.status_code == 200, f"Delete failed: {delete_response.text}"
        
        # Verify deletion
        get_response = requests.get(f"{BASE_URL}/api/inventory/suppliers", headers=auth_headers)
        suppliers = get_response.json()
        deleted = next((s for s in suppliers if s["name"] == supplier_name), None)
        assert deleted is None, "Supplier still exists after deletion"
        print(f"✓ DELETE /api/inventory/suppliers/{supplier_name} - Supplier deleted")


class TestInventorySerials:
    """Test Serial Numbers - /api/inventory/serials"""
    
    def test_get_serials_list(self, auth_headers):
        """Test GET /api/inventory/serials returns serial list"""
        response = requests.get(f"{BASE_URL}/api/inventory/serials", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/inventory/serials - Returns {len(data)} serials")
    
    def test_create_serial(self, auth_headers):
        """Test POST /api/inventory/serials creates a serial number record"""
        # First create a product for the serial
        product_code = f"{TEST_PREFIX}_SERIAL_PROD"
        product_data = {
            "code": product_code,
            "name": "Serial Test Product",
            "category": "Equipamentos",
            "current_stock": 5
        }
        requests.post(f"{BASE_URL}/api/inventory/products", json=product_data, headers=auth_headers)
        
        # Create serial
        serial_number = f"SN-{TEST_PREFIX}-001"
        serial_data = {
            "product_code": product_code,
            "serial_number": serial_number,
            "supplier": "Test Supplier",
            "status": "Em estoque",
            "os_number": ""
        }
        
        response = requests.post(
            f"{BASE_URL}/api/inventory/serials",
            json=serial_data,
            headers=auth_headers
        )
        assert response.status_code == 200, f"Create serial failed: {response.text}"
        
        data = response.json()
        assert data["serial_number"] == serial_number
        assert data["product_code"] == product_code
        assert data["status"] == "Em estoque"
        assert "entry_date" in data
        print(f"✓ POST /api/inventory/serials - Created serial {serial_number}")


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_products(self, auth_headers):
        """Remove test products created during testing"""
        response = requests.get(f"{BASE_URL}/api/inventory/products", headers=auth_headers)
        products = response.json()
        
        deleted_count = 0
        for product in products:
            if product["code"].startswith(TEST_PREFIX):
                requests.delete(
                    f"{BASE_URL}/api/inventory/products/{product['code']}",
                    headers=auth_headers
                )
                deleted_count += 1
        
        print(f"✓ Cleanup: Deleted {deleted_count} test products")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
