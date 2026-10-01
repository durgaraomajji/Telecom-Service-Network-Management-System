# Demo flow (Swagger, http://127.0.0.1:8000/docs)

Run once: `python -m scripts.seed_demo_data` (creates a user for every role, plans, SIMs, a tower, a verified customer).
Password for every demo user: `Demo@12345`. To switch user: **Authorize -> Logout -> log in as the other user**.

| # | Log in as | Call | What happens |
|---|-----------|------|--------------|
| 1 | ops@telecom.demo | `GET /plans/`, `GET /sims/?status=available` | see the seeded plans and free SIMs |
| 2 | support@telecom.demo | `GET /customers/` | find the demo customer's `id` |
| 3 | support@telecom.demo | `POST /subscriptions/` `{customer_id, plan_id, sim_id}` | KYC is already verified -> subscription active, SIM becomes `active`, customer notified |
| 4 | network@telecom.demo | `POST /usage/` `{subscription_id, usage_type: "data", quantity: 300}` | usage recorded |
| 5 | customer@telecom.demo | `GET /usage/subscriptions/{id}/summary` | used vs plan limit, remaining, exceeded |
| 6 | customer@telecom.demo | `POST /tickets/` `{subject, description, priority: "high"}` | ticket `open`, SLA clock starts |
| 7 | support@telecom.demo | `POST /ticket-assignments/` `{ticket_id, assignee_id}` (use the network engineer's user id from `GET /users/` as admin) | ticket -> `assigned` |
| 8 | network@telecom.demo | `PATCH /tickets/{id}/status` `in_progress` -> `resolved` | history + SLA timestamps recorded |
| 9 | customer@telecom.demo | `PATCH /tickets/{id}/status` `closed` | ticket closed |
| 10 | network@telecom.demo | `POST /outages/` `{title, severity: "critical", tower_ids: [1]}` | tower marked `down`, customers in the tower's city with an active subscription are notified |
| 11 | customer@telecom.demo | `GET /notifications/` | outage notification arrives |
| 12 | ops@telecom.demo | `POST /technicians/{id}/assignments` `{task, outage_id}` | technician dispatched (becomes unavailable) |
| 13 | tech@telecom.demo | `GET /technicians/my-assignments`, then `PATCH /technicians/assignments/{id}/status` `completed` | technician available again |
| 14 | network@telecom.demo | `PATCH /outages/{id}/status` `resolved` | tower back to `active`, customers told |
| 15 | customer@telecom.demo | `POST /service-requests/` `{request_type: "plan_change", subscription_id, target_plan_id}` | request `submitted` |
| 16 | support@telecom.demo | `PATCH /service-requests/{id}/status` `approved`, then `completed` | plan actually changed on the subscription |
| 17 | ops@telecom.demo | `GET /reports/revenue`, `/reports/tickets`, `/reports/sla-compliance`, `/dashboard/summary` | management reports |
| 18 | admin@telecom.demo | `GET /audit-logs/` | every change above, with who did it |

Business rules to try (each returns a clear 403/409 message):
- Subscribing a customer whose KYC is not verified.
- Moving a ticket `open -> closed` in one jump, or a SIM `available -> suspended`.
- A customer opening another customer's ticket, SIM or subscription.
- A support agent creating a tower, or an operations manager reading audit logs.
