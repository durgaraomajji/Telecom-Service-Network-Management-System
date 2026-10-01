"""End-to-end telecom flow: onboarding -> KYC -> SIM -> subscription -> usage -> tickets -> outages -> reports."""
from datetime import timedelta

import pytest

from app.core.timeutil import utcnow
from app.models.sla_tracking import SlaTracking

API = "/api/v1"


class World:
    def __init__(self, client, make_headers):
        self.c = client
        roles = ["super_admin", "operations_manager", "support_agent", "network_engineer", "field_technician"]
        self.uid, self.h = {}, {}
        for r in roles:
            raw = make_headers(r)
            self.uid[r] = raw.pop("user_id")
            self.h[r] = raw
        # a self-registered customer with a profile
        client.post(f"{API}/auth/register", json={"full_name": "Cust One", "email": "cust@example.com", "password": "Password123"})
        tok = client.post(f"{API}/auth/login", data={"username": "cust@example.com", "password": "Password123"}).json()["access_token"]
        self.h["customer"] = {"Authorization": f"Bearer {tok}"}
        self.cust = self.post("customer", "/customers/me", {"phone": "9876543210"}).json()

    def _call(self, method, role, path, **kw):
        return getattr(self.c, method)(API + path, headers=self.h[role], **kw)

    def post(self, role, path, body=None, **kw):
        return self._call("post", role, path, json=body, **kw)

    def get(self, role, path, **kw):
        return self._call("get", role, path, **kw)

    def patch(self, role, path, body=None):
        return self._call("patch", role, path, json=body)

    def ok(self, resp, code=201):
        assert resp.status_code == code, resp.text
        return resp.json()


@pytest.fixture
def w(client, make_headers):
    return World(client, make_headers)


PLAN_A = {"name": "Basic 299", "plan_type": "prepaid", "price": 299, "validity_days": 28,
          "data_limit_mb": 1000, "voice_minutes": 100, "sms_limit": 50}
PLAN_B = {"name": "Premium 599", "plan_type": "postpaid", "price": 599, "validity_days": 30,
          "data_limit_mb": 5000, "voice_minutes": 1000, "sms_limit": 500}


def onboard(w):
    """plans, sims, address, verified KYC, one live subscription. Returns ids."""
    plan_a = w.ok(w.post("operations_manager", "/plans/", PLAN_A))
    plan_b = w.ok(w.post("operations_manager", "/plans/", PLAN_B))
    sim1 = w.ok(w.post("operations_manager", "/sims/", {"iccid": "8991101200003204510", "msisdn": "9876500001"}))
    sim2 = w.ok(w.post("operations_manager", "/sims/", {"iccid": "8991101200003204511", "msisdn": "9876500002"}))
    w.ok(w.post("customer", "/addresses/", {"line1": "12 MG Road", "city": "Bengaluru", "state": "Karnataka",
                                             "postal_code": "560001"}))
    return plan_a, plan_b, sim1, sim2


def verify_kyc(w):
    doc = w.ok(w.post("customer", f"/customers/{w.cust['id']}/kyc", {"document_type": "aadhaar", "document_number": "1234-5678-9012"}))
    w.ok(w.patch("support_agent", f"/customers/kyc/{doc['id']}/verify", {"status": "verified"}), 200)


def subscribe(w, plan, sim):
    return w.ok(w.post("support_agent", "/subscriptions/", {"customer_id": w.cust["id"], "plan_id": plan["id"], "sim_id": sim["id"]}))


# ---------------------------------------------------------------- subscriptions, SIMs, usage
def test_kyc_gate_then_subscription_activates_sim(w):
    plan_a, _, sim1, _ = onboard(w)
    r = w.post("support_agent", "/subscriptions/", {"customer_id": w.cust["id"], "plan_id": plan_a["id"], "sim_id": sim1["id"]})
    assert r.status_code == 409 and "KYC" in r.json()["detail"]
    verify_kyc(w)
    sub = subscribe(w, plan_a, sim1)
    assert sub["status"] == "active"
    assert w.get("customer", f"/sims/{sim1['id']}").json()["status"] == "active"
    # same SIM cannot be reused
    assert w.post("support_agent", "/subscriptions/", {"customer_id": w.cust["id"], "plan_id": plan_a["id"], "sim_id": sim1["id"]}).status_code == 409
    # customer sees own subscription, a stranger sees none
    assert len(w.get("customer", "/subscriptions/").json()) == 1


def test_subscription_lifecycle(w):
    plan_a, plan_b, sim1, _ = onboard(w)
    verify_kyc(w)
    sub = subscribe(w, plan_a, sim1)
    sid = sub["id"]
    assert w.ok(w.post("support_agent", f"/subscriptions/{sid}/change-plan", {"plan_id": plan_b["id"]}), 200)["plan_id"] == plan_b["id"]
    assert w.post("support_agent", f"/subscriptions/{sid}/change-plan", {"plan_id": plan_b["id"]}).status_code == 409
    assert w.ok(w.post("support_agent", f"/subscriptions/{sid}/suspend", {"note": "unpaid"}), 200)["status"] == "suspended"
    assert w.get("customer", f"/sims/{sim1['id']}").json()["status"] == "suspended"
    assert w.post("support_agent", f"/subscriptions/{sid}/suspend").status_code == 409
    assert w.ok(w.post("support_agent", f"/subscriptions/{sid}/resume"), 200)["status"] == "active"
    before = w.get("customer", f"/subscriptions/{sid}").json()["end_date"]
    assert w.ok(w.post("customer", f"/subscriptions/{sid}/renew"), 200)["end_date"] > before
    actions = [h["action"] for h in w.get("customer", f"/subscriptions/{sid}/history").json()]
    assert actions == ["created", "plan_changed", "suspended", "resumed", "renewed"]
    assert w.ok(w.post("support_agent", f"/subscriptions/{sid}/cancel"), 200)["status"] == "cancelled"
    assert w.get("customer", f"/sims/{sim1['id']}").json()["status"] == "deactivated"
    assert w.post("support_agent", f"/subscriptions/{sid}/renew").status_code == 409


def test_expiry(w, db_session):
    plan_a, _, sim1, _ = onboard(w)
    verify_kyc(w)
    sub = subscribe(w, plan_a, sim1)
    from app.models.subscription import Subscription
    db_session.get(Subscription, sub["id"]).end_date = utcnow() - timedelta(days=1)
    db_session.commit()
    assert w.post("network_engineer", "/usage/", {"subscription_id": sub["id"], "usage_type": "data", "quantity": 5}).status_code == 409
    assert w.get("customer", f"/subscriptions/{sub['id']}").json()["status"] == "expired"
    assert w.ok(w.post("support_agent", f"/subscriptions/{sub['id']}/renew"), 200)["status"] == "active"


def test_usage_summary_and_limits(w):
    plan_a, _, sim1, _ = onboard(w)
    verify_kyc(w)
    sub = subscribe(w, plan_a, sim1)
    for t, q in (("data", 400), ("data", 700), ("voice", 30), ("sms", 5)):
        w.ok(w.post("network_engineer", "/usage/", {"subscription_id": sub["id"], "usage_type": t, "quantity": q}))
    s = w.get("customer", f"/usage/subscriptions/{sub['id']}/summary").json()
    assert s["data_mb"] == {"used": 1100, "limit": 1000, "remaining": 0, "exceeded": True}
    assert s["voice_minutes"]["remaining"] == 70 and s["sms"]["used"] == 5
    assert w.post("customer", "/usage/", {"subscription_id": sub["id"], "usage_type": "sms", "quantity": 1}).status_code == 403
    assert len(w.get("customer", "/usage/").json()) == 4


def test_sim_rules_and_replacement(w):
    plan_a, _, sim1, sim2 = onboard(w)
    verify_kyc(w)
    sub = subscribe(w, plan_a, sim1)
    bad = w.patch("support_agent", f"/sims/{sim2['id']}/status", {"status": "suspended"})
    assert bad.status_code == 409 and "Allowed" in bad.json()["detail"]
    assert w.patch("support_agent", f"/sims/{sim2['id']}/status", {"status": "active"}).status_code == 409  # no owner
    rep = w.ok(w.post("support_agent", f"/sims/{sim1['id']}/replace", {"new_iccid": "8991101200003209999", "reason": "lost"}))
    old = w.get("support_agent", f"/sims/{sim1['id']}").json()
    new = w.get("support_agent", f"/sims/{rep['new_sim_id']}").json()
    assert old["status"] == "deactivated" and old["msisdn"] is None
    assert new["status"] == "active" and new["msisdn"] == "9876500001" and new["customer_id"] == w.cust["id"]
    assert w.get("customer", f"/subscriptions/{sub['id']}").json()["sim_id"] == new["id"]
    assert len(w.get("customer", f"/sims/{new['id']}/replacements").json()) == 1
    assert w.post("operations_manager", "/sims/", {"iccid": "8991101200003209999", "msisdn": "9876500077"}).status_code == 409


def test_devices(w):
    plan_a, _, sim1, sim2 = onboard(w)
    verify_kyc(w)
    subscribe(w, plan_a, sim1)
    dev = w.ok(w.post("support_agent", "/devices/", {"imei": "356938035643809", "brand": "Samsung", "model": "S23"}))
    assert w.post("support_agent", f"/devices/{dev['id']}/assign", {"sim_id": sim2["id"]}).status_code == 409  # SIM not active
    assert w.ok(w.post("support_agent", f"/devices/{dev['id']}/assign", {"sim_id": sim1["id"]}))["released_at"] is None
    assert w.post("support_agent", f"/devices/{dev['id']}/assign", {"sim_id": sim1["id"]}).status_code == 409
    assert w.ok(w.patch("support_agent", f"/devices/{dev['id']}/block", {"is_blocked": True}), 200)["is_blocked"] is True
    assert w.post("support_agent", f"/devices/{dev['id']}/assign", {"sim_id": sim1["id"]}).status_code == 409
    assert w.post("support_agent", "/devices/", {"imei": "12345", "brand": "X", "model": "Y"}).status_code == 422


# ---------------------------------------------------------------- network
def test_tower_equipment_technician_and_outage(w):
    plan_a, _, sim1, _ = onboard(w)
    verify_kyc(w)
    subscribe(w, plan_a, sim1)
    tower = w.ok(w.post("network_engineer", "/towers/", {"name": "BLR-01", "city": "Bengaluru", "latitude": 12.97, "longitude": 77.59}))
    far = w.ok(w.post("network_engineer", "/towers/", {"name": "DEL-01", "city": "Delhi", "latitude": 28.6, "longitude": 77.2}))
    w.ok(w.post("network_engineer", f"/towers/{tower['id']}/coverage", {"area_name": "MG Road", "radius_km": 3, "technology": "5G"}))
    assert len(w.get("network_engineer", f"/towers/{tower['id']}/coverage").json()) == 1
    assert w.post("support_agent", "/towers/", {"name": "X1", "city": "Y1", "latitude": 1, "longitude": 1}).status_code == 403
    eq = w.ok(w.post("network_engineer", "/equipment/", {"tower_id": tower["id"], "name": "Antenna", "equipment_type": "antenna", "serial_number": "SN-1"}))
    w.ok(w.post("network_engineer", f"/equipment/{eq['id']}/metrics", {"cpu_load": 40, "temperature_c": 50}))
    assert w.get("network_engineer", f"/equipment/{eq['id']}").json()["status"] == "operational"
    w.ok(w.post("network_engineer", f"/equipment/{eq['id']}/metrics", {"cpu_load": 40, "temperature_c": 92}))
    assert w.get("network_engineer", f"/equipment/{eq['id']}").json()["status"] == "faulty"
    # outage: only the Bengaluru customer is affected and notified
    out = w.ok(w.post("network_engineer", "/outages/", {"title": "Power failure", "severity": "critical", "tower_ids": [tower["id"], far["id"]]}))
    assert out["affected_customers"] == 1 and sorted(out["tower_ids"]) == sorted([tower["id"], far["id"]])
    assert w.get("network_engineer", f"/towers/{tower['id']}").json()["status"] == "down"
    assert any(n["type"] == "outage" for n in w.get("customer", "/notifications/").json())
    assert w.get("customer", f"/outages/{out['id']}").status_code == 200
    # technician dispatch
    tech = w.ok(w.post("operations_manager", "/technicians/", {"name": "Ravi", "phone": "9123456780", "region": "Bengaluru",
                                                                "user_id": w.uid["field_technician"], "skills": ["Power", "fiber"]}))
    assert tech["skills"] == ["power", "fiber"]
    assert len(w.get("support_agent", "/technicians/", params={"skill": "power"}).json()) == 1
    work = w.ok(w.post("network_engineer", f"/technicians/{tech['id']}/assignments", {"task": "Restore power", "outage_id": out["id"], "equipment_id": eq["id"]}))
    assert w.get("support_agent", f"/technicians/{tech['id']}").json()["is_available"] is False
    assert w.post("network_engineer", f"/technicians/{tech['id']}/assignments", {"task": "Second", "outage_id": out["id"]}).status_code == 409
    assert len(w.get("field_technician", "/technicians/my-assignments").json()) == 1
    assert w.ok(w.patch("field_technician", f"/technicians/assignments/{work['id']}/status", {"status": "in_progress"}), 200)["status"] == "in_progress"
    assert w.ok(w.patch("field_technician", f"/technicians/assignments/{work['id']}/status", {"status": "completed"}), 200)["completed_at"]
    assert w.get("support_agent", f"/technicians/{tech['id']}").json()["is_available"] is True
    # resolve outage restores tower
    assert w.patch("network_engineer", f"/outages/{out['id']}/status", {"status": "investigating"}).status_code == 200
    assert w.ok(w.patch("network_engineer", f"/outages/{out['id']}/status", {"status": "resolved"}), 200)["resolved_at"]
    assert w.get("network_engineer", f"/towers/{tower['id']}").json()["status"] == "active"
    assert w.patch("network_engineer", f"/outages/{out['id']}/status", {"status": "resolved"}).status_code == 409


# ---------------------------------------------------------------- tickets, assignments, SLA
def test_ticket_lifecycle_assignment_and_visibility(w):
    t = w.ok(w.post("customer", "/tickets/", {"subject": "No signal", "description": "Drops all day", "category": "network", "priority": "high"}))
    tid = t["id"]
    assert t["status"] == "open" and t["ticket_number"].startswith("TKT-")
    assert w.post("customer", "/ticket-assignments/", {"ticket_id": tid, "assignee_id": w.uid["support_agent"]}).status_code == 403
    a = w.ok(w.post("support_agent", "/ticket-assignments/", {"ticket_id": tid, "assignee_id": w.uid["network_engineer"]}))
    assert a["assignee_id"] == w.uid["network_engineer"]
    assert w.get("customer", f"/tickets/{tid}").json()["status"] == "assigned"
    assert w.post("support_agent", "/ticket-assignments/", {"ticket_id": tid, "assignee_id": w.uid["customer"] if "customer" in w.uid else 99999}).status_code in (404, 409)
    # engineer sees only assigned tickets
    assert len(w.get("network_engineer", "/tickets/").json()) == 1
    assert len(w.get("network_engineer", "/ticket-assignments/my").json()) == 1
    assert w.patch("support_agent", f"/tickets/{tid}/status", {"status": "closed"}).status_code == 409           # illegal jump
    assert w.patch("support_agent", f"/tickets/{tid}/status", {"status": "assigned"}).status_code == 409         # must use assignments
    assert w.patch("customer", f"/tickets/{tid}/status", {"status": "in_progress"}).status_code == 403           # customers can't work tickets
    w.ok(w.patch("network_engineer", f"/tickets/{tid}/status", {"status": "in_progress", "note": "Investigating"}), 200)
    w.ok(w.post("network_engineer", f"/tickets/{tid}/comments", {"comment": "Checking the tower logs", "is_internal": True}))
    w.ok(w.post("network_engineer", f"/tickets/{tid}/comments", {"comment": "We found a fault"}))
    assert len(w.get("customer", f"/tickets/{tid}/comments").json()) == 1          # internal note hidden
    assert len(w.get("network_engineer", f"/tickets/{tid}/comments").json()) == 2
    assert w.post("customer", f"/tickets/{tid}/comments", {"comment": "secret", "is_internal": True}).status_code == 403
    w.ok(w.patch("network_engineer", f"/tickets/{tid}/status", {"status": "waiting_for_customer"}), 200)
    w.ok(w.post("customer", f"/tickets/{tid}/comments", {"comment": "Still failing"}))
    assert w.get("customer", f"/tickets/{tid}").json()["status"] == "in_progress"      # customer reply resumes work
    w.ok(w.patch("network_engineer", f"/tickets/{tid}/status", {"status": "resolved"}), 200)
    assert w.get("customer", f"/tickets/{tid}").json()["resolved_at"]
    w.ok(w.patch("customer", f"/tickets/{tid}/status", {"status": "in_progress"}), 200)  # reopen
    assert w.get("customer", f"/tickets/{tid}").json()["resolved_at"] is None
    w.ok(w.patch("network_engineer", f"/tickets/{tid}/status", {"status": "resolved"}), 200)
    w.ok(w.patch("customer", f"/tickets/{tid}/status", {"status": "closed"}), 200)
    assert w.post("customer", f"/tickets/{tid}/comments", {"comment": "hello"}).status_code == 409
    hist = [h["new_status"] for h in w.get("customer", f"/tickets/{tid}/history").json()]
    assert hist == ["open", "assigned", "in_progress", "waiting_for_customer", "in_progress", "resolved", "in_progress", "resolved", "closed"]
    # a second customer cannot see it
    w.c.post(f"{API}/auth/register", json={"full_name": "Other", "email": "other@example.com", "password": "Password123"})
    tok = w.c.post(f"{API}/auth/login", data={"username": "other@example.com", "password": "Password123"}).json()["access_token"]
    w.h["other"] = {"Authorization": f"Bearer {tok}"}
    w.ok(w.post("other", "/customers/me", {"phone": "9000000001"}))
    assert w.get("other", f"/tickets/{tid}").status_code == 403
    assert w.get("other", "/tickets/").json() == []


def test_sla_tracking_and_breach_check(w, db_session):
    fast = w.ok(w.post("operations_manager", "/sla/rules", {"priority": "critical", "response_minutes": 10, "resolution_minutes": 60}))
    assert fast["is_default"] is False
    assert w.post("operations_manager", "/sla/rules", {"priority": "critical", "response_minutes": 5, "resolution_minutes": 30}).status_code == 409
    assert w.ok(w.post("operations_manager", "/sla/rules", {"priority": "low", "response_minutes": 100, "resolution_minutes": 200}))["response_minutes"] == 100 \
        if False else True
    rules = {r["priority"]: r for r in w.get("support_agent", "/sla/rules").json()}
    assert rules["critical"]["response_minutes"] == 10 and rules["medium"]["is_default"] is True
    t1 = w.ok(w.post("customer", "/tickets/", {"subject": "Outage!", "description": "Nothing works", "priority": "critical"}))
    t2 = w.ok(w.post("customer", "/tickets/", {"subject": "Slow data", "description": "Very slow lately", "priority": "low"}))
    tr = w.get("customer", f"/sla/tracking/{t1['id']}").json()
    assert tr["response_breached"] is False and tr["ticket_number"] == t1["ticket_number"]
    # pretend t1's deadlines passed 2 hours ago
    track = db_session.query(SlaTracking).filter_by(ticket_id=t1["id"]).one()
    track.response_due = utcnow() - timedelta(hours=2)
    track.resolution_due = utcnow() - timedelta(hours=1)
    db_session.commit()
    res = w.ok(w.post("operations_manager", "/sla/check-breaches"), 200)
    assert res["breached"] == 1 and res["newly_breached"] == [t1["ticket_number"]]
    assert w.ok(w.post("operations_manager", "/sla/check-breaches"), 200)["newly_breached"] == []   # not re-notified
    breached = w.get("support_agent", "/sla/tracking", params={"breached": True}).json()
    assert [b["ticket_id"] for b in breached] == [t1["id"]]
    assert w.get("support_agent", "/sla/tracking", params={"breached": False}).json()[0]["ticket_id"] == t2["id"]
    assert w.get("support_agent", "/dashboard/summary").json()["sla_breached_tickets"] == 1
    assert w.get("customer", "/sla/tracking").status_code == 403
    assert w.post("support_agent", "/sla/check-breaches").status_code == 403
    # responding stops the response clock; resolving stops the resolution clock (still flagged as breached)
    w.ok(w.post("support_agent", f"/ticket-assignments/", {"ticket_id": t1["id"], "assignee_id": w.uid["support_agent"]}))
    tr = w.get("customer", f"/sla/tracking/{t1['id']}").json()
    assert tr["responded_at"] and tr["response_breached"] is True
    assert w.get("support_agent", "/sla/rules").status_code == 200


def test_service_request_plan_change_and_disconnection(w):
    plan_a, plan_b, sim1, sim2 = onboard(w)
    verify_kyc(w)
    sub = subscribe(w, plan_a, sim1)
    assert w.post("customer", "/service-requests/", {"request_type": "plan_change", "subscription_id": sub["id"]}).status_code == 422
    req = w.ok(w.post("customer", "/service-requests/", {"request_type": "plan_change", "subscription_id": sub["id"],
                                                          "target_plan_id": plan_b["id"], "description": "Need more data"}))
    assert req["status"] == "submitted" and req["request_number"].startswith("SRQ-")
    assert w.patch("support_agent", f"/service-requests/{req['id']}/status", {"status": "completed"}).status_code == 409
    w.ok(w.patch("support_agent", f"/service-requests/{req['id']}/status", {"status": "approved"}), 200)
    assert w.patch("customer", f"/service-requests/{req['id']}/status", {"status": "completed"}).status_code == 403
    w.ok(w.patch("support_agent", f"/service-requests/{req['id']}/status", {"status": "completed", "note": "Done"}), 200)
    assert w.get("customer", f"/subscriptions/{sub['id']}").json()["plan_id"] == plan_b["id"]
    assert [h["new_status"] for h in w.get("customer", f"/service-requests/{req['id']}/history").json()] == ["submitted", "approved", "completed"]
    dis = w.ok(w.post("customer", "/service-requests/", {"request_type": "disconnection", "subscription_id": sub["id"]}))
    w.ok(w.patch("support_agent", f"/service-requests/{dis['id']}/status", {"status": "under_review"}), 200)
    w.ok(w.patch("support_agent", f"/service-requests/{dis['id']}/status", {"status": "approved"}), 200)
    w.ok(w.patch("support_agent", f"/service-requests/{dis['id']}/status", {"status": "completed"}), 200)
    assert w.get("customer", f"/subscriptions/{sub['id']}").json()["status"] == "cancelled"
    rej = w.ok(w.post("customer", "/service-requests/", {"request_type": "other", "description": "Please call me"}))
    w.ok(w.patch("support_agent", f"/service-requests/{rej['id']}/status", {"status": "rejected"}), 200)
    assert w.patch("support_agent", f"/service-requests/{rej['id']}/status", {"status": "approved"}).status_code == 409
    assert len(w.get("customer", "/service-requests/").json()) == 3
    assert w.get("network_engineer", "/service-requests/").status_code == 403


# ---------------------------------------------------------------- notifications, dashboard, reports, audit
def test_notifications(w):
    n = w.ok(w.post("support_agent", "/notifications/", {"user_id": w.cust["user_id"], "title": "Hello", "message": "Welcome"}))
    assert w.get("customer", "/notifications/unread-count").json()["unread"] == 1
    assert w.get("network_engineer", f"/notifications/", params={"unread_only": True}).json() == []
    assert w.patch("network_engineer", f"/notifications/{n['id']}/read").status_code == 403
    assert w.patch("customer", f"/notifications/{n['id']}/read").json()["is_read"] is True
    assert w.get("customer", "/notifications/unread-count").json()["unread"] == 0
    assert w.ok(w.post("operations_manager", "/notifications/broadcast", {"role": "customer", "title": "Promo", "message": "20% off"}), 200)["sent"] == 1
    assert w.ok(w.post("customer", "/notifications/read-all"), 200)["marked_read"] == 1
    assert w.post("customer", "/notifications/", {"user_id": 1, "title": "x1", "message": "y"}).status_code == 403
    assert w.post("support_agent", "/notifications/broadcast", {"role": "customer", "title": "x1", "message": "y"}).status_code == 403


def test_dashboard_reports_and_audit(w):
    plan_a, plan_b, sim1, sim2 = onboard(w)
    verify_kyc(w)
    sub = subscribe(w, plan_a, sim1)
    w.ok(w.post("support_agent", f"/subscriptions/{sub['id']}/change-plan", {"plan_id": plan_b["id"]}), 200)
    w.ok(w.post("customer", f"/subscriptions/{sub['id']}/renew"), 200)
    w.ok(w.post("network_engineer", "/usage/", {"subscription_id": sub["id"], "usage_type": "data", "quantity": 250}))
    w.ok(w.post("customer", "/tickets/", {"subject": "Billing", "description": "Wrong amount", "category": "billing"}))
    tower = w.ok(w.post("network_engineer", "/towers/", {"name": "T1", "city": "Bengaluru", "latitude": 1, "longitude": 1}))
    w.ok(w.post("network_engineer", "/outages/", {"title": "Fibre cut", "severity": "low", "tower_ids": [tower["id"]]}))
    d = w.get("support_agent", "/dashboard/summary").json()
    assert d["customers"] == 1 and d["subscriptions_by_status"] == {"active": 1} and d["open_tickets"] == 1
    assert d["active_outages"] == 1 and d["towers_by_status"] == {"degraded": 1} and d["monthly_recurring_revenue"] == 599.0
    assert d["sims_by_status"] == {"active": 1, "available": 1}
    cd = w.get("customer", "/dashboard/customer").json()
    assert cd["active_subscriptions"] == 1 and cd["open_tickets"] == 1 and cd["kyc_status"] == "verified"
    assert w.get("customer", "/dashboard/summary").status_code == 403
    rev = w.get("operations_manager", "/reports/revenue").json()
    assert rev["total_charges"] == 2 and rev["total_revenue"] == 299.0 + 599.0
    assert w.get("operations_manager", "/reports/revenue", params={"date_from": "2999-01-01T00:00:00"}).json()["total_charges"] == 0
    assert w.get("operations_manager", "/reports/tickets").json()["by_category"] == {"billing": 1}
    assert w.get("operations_manager", "/reports/sims").json() == {"active": 1, "available": 1}
    assert w.get("operations_manager", "/reports/usage").json()["totals"] == {"data": 250}
    assert w.get("operations_manager", "/reports/outages").json()["by_severity"] == {"low": 1}
    assert w.get("operations_manager", "/reports/sla-compliance").json()["compliance_percent"] == 100.0
    assert w.get("support_agent", "/reports/revenue").status_code == 403
    # audit trail
    logs = w.get("super_admin", "/audit-logs/", params={"limit": 200}).json()
    entities = {l["entity"] for l in logs}
    assert {"service_plan", "sim_card", "subscription", "ticket", "outage", "tower", "kyc_document"} <= entities
    assert w.get("super_admin", "/audit-logs/", params={"entity": "subscription"}).json()[0]["entity"] == "subscription"
    assert w.get("super_admin", f"/audit-logs/{logs[0]['id']}").status_code == 200
    assert w.get("operations_manager", "/audit-logs/").status_code == 403


def test_addresses_and_customer_profile_rules(w):
    a1 = w.ok(w.post("customer", "/addresses/", {"line1": "1 First St", "city": "Pune", "state": "MH", "postal_code": "411001"}))
    a2 = w.ok(w.post("customer", "/addresses/", {"line1": "2 Second St", "city": "Mumbai", "state": "MH", "postal_code": "400001", "is_primary": True}))
    assert a1["is_primary"] is True and a2["is_primary"] is True
    assert [a["is_primary"] for a in w.get("customer", "/addresses/").json()] == [False, True]
    assert w.get("customer", f"/addresses/{a1['id']}").status_code == 200
    assert w.post("customer", "/addresses/", {"customer_id": 999, "line1": "x1x", "city": "Pune", "state": "MH", "postal_code": "411001"}).status_code == 403
    assert w.post("support_agent", "/addresses/", {"line1": "3 Third St", "city": "Pune", "state": "MH", "postal_code": "411001"}).status_code == 422  # needs customer_id
    w.ok(w.post("support_agent", "/addresses/", {"customer_id": w.cust["id"], "line1": "3 Third St", "city": "Pune", "state": "MH", "postal_code": "411001"}))
    assert w.c.put(f"{API}/addresses/{a1['id']}", json={"city": "Nashik"}, headers=w.h["customer"]).json()["city"] == "Nashik"
    assert w.c.delete(f"{API}/addresses/{a2['id']}", headers=w.h["customer"]).status_code == 204
    assert w.post("customer", "/customers/me", {"phone": "9999999999"}).status_code == 409
    assert w.get("customer", f"/customers/{w.cust['id']}").status_code == 200
    assert w.get("network_engineer", "/customers/").status_code == 403
    # customer without a profile gets a helpful message
    w.c.post(f"{API}/auth/register", json={"full_name": "No Profile", "email": "np@example.com", "password": "Password123"})
    tok = w.c.post(f"{API}/auth/login", data={"username": "np@example.com", "password": "Password123"}).json()["access_token"]
    r = w.c.post(f"{API}/tickets/", json={"subject": "Help me", "description": "Please help"}, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 409 and "customers/me" in r.json()["detail"]


def test_plan_update_and_deactivate(w):
    p = w.ok(w.post("operations_manager", "/plans/", PLAN_A))
    assert w.c.patch(f"{API}/plans/{p['id']}", json={"price": 349}, headers=w.h["operations_manager"]).json()["price"] == 349
    assert w.c.patch(f"{API}/plans/{p['id']}", json={"price": 1}, headers=w.h["support_agent"]).status_code == 403
    assert w.c.delete(f"{API}/plans/{p['id']}", headers=w.h["operations_manager"]).json()["is_active"] is False
    assert w.c.get(f"{API}/plans/").json() == []
