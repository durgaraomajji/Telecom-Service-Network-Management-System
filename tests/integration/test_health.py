def test_root_and_health(client):
    assert client.get("/").json()["success"] is True
    assert client.get("/health").json()["status"] == "healthy"
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
