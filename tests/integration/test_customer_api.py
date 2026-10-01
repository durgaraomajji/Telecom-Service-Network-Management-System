def test_create_and_list_customers(client, admin_headers):
    body = {"full_name": "Walk In", "email": "w@example.com", "password": "Password123", "phone": "9876543210"}
    r = client.post("/api/v1/customers/", json=body, headers=admin_headers)
    assert r.status_code == 201 and r.json()["customer_number"].startswith("CUS-")
    assert client.post("/api/v1/customers/", json=body, headers=admin_headers).status_code == 409
    assert len(client.get("/api/v1/customers/", headers=admin_headers).json()) == 1
