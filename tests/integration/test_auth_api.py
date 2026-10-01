P = "/api/v1/auth"
BODY = {"full_name": "Jane Doe", "email": "j@example.com", "password": "Password123"}


def test_register_defaults_to_customer(client):
    r = client.post(f"{P}/register", json=BODY)
    assert r.status_code == 201 and r.json()["role"] == "customer"


def test_first_account_can_be_super_admin(client):
    r = client.post(f"{P}/register", json={**BODY, "role": "super_admin"})
    assert r.status_code == 201 and r.json()["role"] == "super_admin"


def test_staff_role_needs_super_admin(client, customer_headers, admin_headers):
    for role in ("super_admin", "operations_manager", "support_agent", "network_engineer", "field_technician"):
        body = {**BODY, "email": f"{role}@example.com", "role": role}
        assert client.post(f"{P}/register", json=body).status_code == 403                    # anonymous
        assert client.post(f"{P}/register", json=body, headers=customer_headers).status_code == 403
        r = client.post(f"{P}/register", json=body, headers=admin_headers)                   # super_admin
        assert r.status_code == 201 and r.json()["role"] == role


def test_new_staff_can_log_in_and_act(client, admin_headers):
    client.post(f"{P}/register", json={**BODY, "role": "operations_manager"}, headers=admin_headers)
    r = client.post(f"{P}/login", data={"username": "j@example.com", "password": "Password123"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    plan = {"name": "P1", "plan_type": "prepaid", "price": 10, "validity_days": 7}
    assert client.post("/api/v1/plans/", json=plan, headers=h).status_code == 201


def test_invalid_role_rejected(client):
    assert client.post(f"{P}/register", json={**BODY, "role": "string"}).status_code == 422


def test_register_duplicate_email(client):
    client.post(f"{P}/register", json=BODY)
    assert client.post(f"{P}/register", json=BODY).status_code == 409


def test_login_me_refresh(client, customer_headers):
    assert client.get(f"{P}/me", headers=customer_headers).json()["email"] == "c1@example.com"
    assert client.get(f"{P}/me").status_code == 401
    r = client.post(f"{P}/login", data={"username": "c1@example.com", "password": "Password123"})
    assert client.post(f"{P}/refresh", params={"refresh_token": r.json()["refresh_token"]}).status_code == 200
    assert client.post(f"{P}/refresh", params={"refresh_token": r.json()["access_token"]}).status_code == 401


def test_login_bad_password(client, customer_headers):
    assert client.post(f"{P}/login", data={"username": "c1@example.com", "password": "nope"}).status_code == 401
