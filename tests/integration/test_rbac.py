def test_customer_blocked_admin_allowed(client, customer_headers, admin_headers):
    cust = {"full_name": "Walk In", "email": "w@example.com", "password": "Password123", "phone": "9876543210"}
    r = client.post("/api/v1/customers/", json=cust, headers=customer_headers)
    assert r.status_code == 403 and "customer" in r.json()["detail"]
    assert client.post("/api/v1/customers/", json=cust, headers=admin_headers).status_code == 201
    assert client.get("/api/v1/users/", headers=customer_headers).status_code == 403
    assert client.get("/api/v1/users/", headers=admin_headers).status_code == 200


def test_change_role(client, admin_headers, customer_headers):
    me = client.get("/api/v1/auth/me", headers=customer_headers).json()
    assert client.patch(f"/api/v1/users/{me['id']}/role", json={"role": "super_admin"}, headers=customer_headers).status_code == 403
    r = client.patch(f"/api/v1/users/{me['id']}/role", json={"role": "operations_manager"}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["role"] == "operations_manager"
    # role is read from the DB, so the same token is now allowed to create plans
    plan = {"name": "Plan A", "plan_type": "prepaid", "price": 5, "validity_days": 7}
    assert client.post("/api/v1/plans/", json=plan, headers=customer_headers).status_code == 201
    assert client.patch("/api/v1/users/9999/role", json={"role": "customer"}, headers=admin_headers).status_code == 404


def test_cannot_demote_last_super_admin(client, admin_headers):
    me = client.get("/api/v1/auth/me", headers=admin_headers).json()
    assert client.patch(f"/api/v1/users/{me['id']}/role", json={"role": "customer"}, headers=admin_headers).status_code == 409

