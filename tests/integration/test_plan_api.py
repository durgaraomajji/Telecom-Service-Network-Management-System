PLAN = {"name": "Basic 299", "plan_type": "prepaid", "price": 299.0, "validity_days": 28,
        "data_limit_mb": 2048, "voice_minutes": 100, "sms_limit": 100}


def test_plans(client, admin_headers, customer_headers):
    assert client.post("/api/v1/plans/", json=PLAN, headers=customer_headers).status_code == 403
    assert client.post("/api/v1/plans/", json=PLAN, headers=admin_headers).status_code == 201
    assert client.post("/api/v1/plans/", json=PLAN, headers=admin_headers).status_code == 409
    assert client.get("/api/v1/plans/").json()[0]["name"] == "Basic 299"
