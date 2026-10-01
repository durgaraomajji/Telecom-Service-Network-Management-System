# Database design

32 tables (created automatically at startup by `create_all`; use Alembic for production migrations).

- Identity: `users`, `customers`, `addresses`, `kyc_documents`
- Products: `service_plans`, `subscriptions`, `subscription_history`, `usage_records`
- Inventory: `sim_cards`, `sim_replacements`, `devices`, `device_assignments`
- Network: `towers`, `tower_coverages`, `equipment`, `equipment_metrics`, `outages`, `outage_towers`, `outage_customers`
- Field work: `technicians`, `technician_skills`, `technician_assignments`
- Support: `support_tickets`, `ticket_assignments`, `ticket_comments`, `ticket_history`, `sla_rules`, `sla_tracking`, `service_requests`, `service_request_history`
- Platform: `notifications`, `audit_logs`

Key rules: one live subscription per SIM; SIM and ticket status changes follow allowed-transition tables in
`app/core/constants.py`; a customer's KYC must be verified before subscribing; an outage affects customers who have an
address in the same city as an affected tower and an active subscription.
