"""Covers the read/list/update endpoints not touched by the main flow tests."""
from datetime import timedelta

from app.core.timeutil import utcnow
from tests.integration.test_full_flow import API, PLAN_A, onboard, subscribe, verify_kyc, w  # noqa: F401


def test_customer_and_plan_reads(w):
    assert w.get("customer", "/users/me").json()["email"] == "cust@example.com"
    assert w.get("customer", "/customers/me").json()["id"] == w.cust["id"]
    assert w.patch("customer", f"/customers/{w.cust['id']}", {"phone": "9000011111"}).json()["phone"] == "9000011111"
    plan = w.ok(w.post("operations_manager", "/plans/", PLAN_A))
    assert w.c.get(f"{API}/plans/{plan['id']}").json()["name"] == PLAN_A["name"]
    assert w.c.get(f"{API}/plans/9999").status_code == 404
    verify_kyc(w)
    docs = w.get("support_agent", f"/customers/{w.cust['id']}/kyc").json()
    assert len(docs) == 1 and docs[0]["status"] == "verified"
    # a verified document cannot be verified twice
    assert w.patch("support_agent", f"/customers/kyc/{docs[0]['id']}/verify", {"status": "rejected"}).status_code == 409


def test_sim_device_and_subscription_reads(w, db_session):
    plan_a, _, sim1, sim2 = onboard(w)
    verify_kyc(w)
    sub = subscribe(w, plan_a, sim1)
    assert {s["status"] for s in w.get("support_agent", "/sims/").json()} == {"active", "available"}
    assert [s["id"] for s in w.get("support_agent", "/sims/", params={"status": "available"}).json()] == [sim2["id"]]
    dev = w.ok(w.post("support_agent", "/devices/", {"imei": "356938035643809", "brand": "Apple", "model": "iPhone 15"}))
    assert len(w.get("support_agent", "/devices/").json()) == 1
    assert w.get("support_agent", f"/devices/{dev['id']}").json()["imei"] == "356938035643809"
    w.ok(w.post("support_agent", f"/devices/{dev['id']}/assign", {"sim_id": sim1["id"]}))
    assert w.post("support_agent", f"/devices/{dev['id']}/release").json()["released_at"]
    assert w.post("support_agent", f"/devices/{dev['id']}/release").status_code == 409
    assert len(w.get("support_agent", f"/devices/{dev['id']}/assignments").json()) == 1
    # expire-due sweeps past-due subscriptions
    from app.models.subscription import Subscription
    db_session.get(Subscription, sub["id"]).end_date = utcnow() - timedelta(days=2)
    db_session.commit()
    assert w.ok(w.post("operations_manager", "/subscriptions/expire-due"), 200)["expired"] == 1
    assert w.post("support_agent", "/subscriptions/expire-due").status_code == 403


def test_network_reads_and_updates(w):
    onboard(w)
    tower = w.ok(w.post("network_engineer", "/towers/", {"name": "BLR-02", "city": "Bengaluru", "latitude": 12.9, "longitude": 77.6}))
    assert w.patch("network_engineer", f"/towers/{tower['id']}", {"status": "maintenance", "capacity_users": 5000}).json()["status"] == "maintenance"
    assert w.patch("network_engineer", f"/towers/{tower['id']}", {"name": "BLR-02"}).status_code == 200
    assert len(w.get("network_engineer", "/towers/", params={"city": "Bengaluru", "status": "maintenance"}).json()) == 1
    eq = w.ok(w.post("network_engineer", "/equipment/", {"tower_id": tower["id"], "name": "Router", "equipment_type": "router", "serial_number": "SN-9"}))
    assert w.post("network_engineer", "/equipment/", {"tower_id": tower["id"], "name": "Router2", "equipment_type": "router", "serial_number": "SN-9"}).status_code == 409
    assert len(w.get("network_engineer", "/equipment/", params={"tower_id": tower["id"]}).json()) == 1
    assert w.patch("field_technician", f"/equipment/{eq['id']}/status", {"status": "maintenance"}).json()["status"] == "maintenance"
    w.patch("field_technician", f"/equipment/{eq['id']}/status", {"status": "decommissioned"})
    assert w.patch("network_engineer", f"/equipment/{eq['id']}/status", {"status": "operational"}).status_code == 409
    eq2 = w.ok(w.post("network_engineer", "/equipment/", {"tower_id": tower["id"], "name": "Unit", "equipment_type": "power_unit", "serial_number": "SN-10"}))
    w.ok(w.post("network_engineer", f"/equipment/{eq2['id']}/metrics", {"cpu_load": 20, "temperature_c": 40, "signal_strength_dbm": -70}))
    m = w.get("network_engineer", f"/equipment/{eq2['id']}/metrics").json()
    assert len(m) == 1 and m[0]["signal_strength_dbm"] == -70
    out = w.ok(w.post("network_engineer", "/outages/", {"title": "Maintenance window", "severity": "medium", "tower_ids": [tower["id"]]}))
    assert w.get("customer", "/outages/", params={"status": "open", "severity": "medium"}).json()[0]["id"] == out["id"]
    assert w.get("network_engineer", f"/outages/{out['id']}/affected-customers").json() == []
    assert w.get("customer", f"/outages/{out['id']}/affected-customers").status_code == 403
    assert w.post("network_engineer", "/outages/", {"title": "Ghost", "severity": "low", "tower_ids": [9999]}).status_code == 404


def test_technician_management(w):
    tech = w.ok(w.post("operations_manager", "/technicians/", {"name": "Asha", "phone": "9000000002", "region": "Mysuru"}))
    assert w.ok(w.post("operations_manager", f"/technicians/{tech['id']}/skills", {"skill": "Fibre"}))["skills"] == ["fibre"]
    assert w.post("operations_manager", f"/technicians/{tech['id']}/skills", {"skill": "fibre"}).status_code == 409
    assert w.patch("operations_manager", f"/technicians/{tech['id']}/availability", {"is_available": False}).json()["is_available"] is False
    assert w.get("support_agent", "/technicians/", params={"available": False, "region": "Mysuru"}).json()[0]["id"] == tech["id"]
    assert w.post("operations_manager", f"/technicians/{tech['id']}/assignments", {"task": "Job A", "outage_id": 1}).status_code == 409  # unavailable
    w.patch("operations_manager", f"/technicians/{tech['id']}/availability", {"is_available": True})
    assert w.post("operations_manager", f"/technicians/{tech['id']}/assignments", {"task": "Job A"}).status_code == 422  # no target
    assert w.get("support_agent", f"/technicians/{tech['id']}/assignments").json() == []
    assert w.post("support_agent", "/technicians/", {"name": "Bad", "phone": "9000000003", "region": "X1"}).status_code == 403
    assert w.post("operations_manager", "/technicians/", {"name": "Bad", "phone": "9000000003", "region": "X1", "user_id": w.uid["support_agent"]}).status_code == 409


def test_tickets_assignments_sla_and_requests_reads(w):
    t = w.ok(w.post("customer", "/tickets/", {"subject": "Slow internet", "description": "Very slow at night"}))
    w.ok(w.post("support_agent", "/ticket-assignments/", {"ticket_id": t["id"], "assignee_id": w.uid["support_agent"]}))
    assert len(w.get("support_agent", "/ticket-assignments/", params={"ticket_id": t["id"]}).json()) == 1
    assert w.get("operations_manager", "/ticket-assignments/", params={"assignee_id": w.uid["support_agent"]}).json()[0]["ticket_id"] == t["id"]
    assert w.c.put(f"{API}/sla/rules/high", json={"response_minutes": 20, "resolution_minutes": 100}, headers=w.h["operations_manager"]).json()["response_minutes"] == 20
    assert w.c.put(f"{API}/sla/rules/high", json={"response_minutes": 30, "resolution_minutes": 90}, headers=w.h["operations_manager"]).json()["resolution_minutes"] == 90
    assert w.c.put(f"{API}/sla/rules/urgent", json={"response_minutes": 1, "resolution_minutes": 2}, headers=w.h["operations_manager"]).status_code == 404
    assert w.c.put(f"{API}/sla/rules/high", json={"response_minutes": 50, "resolution_minutes": 10}, headers=w.h["operations_manager"]).status_code == 422
    req = w.ok(w.post("customer", "/service-requests/", {"request_type": "address_change", "description": "Moving flat"}))
    assert w.get("customer", f"/service-requests/{req['id']}").json()["request_number"] == req["request_number"]
    assert w.get("support_agent", "/service-requests/", params={"status": "submitted", "request_type": "address_change"}).json()[0]["id"] == req["id"]
    assert w.get("network_engineer", f"/service-requests/{req['id']}").status_code == 403
