# API endpoints

All routes are under `/api/v1`. Open `/docs` (Swagger) for request/response schemas; `/redoc` for a read-only view.
118 operations across 21 modules, all implemented and covered by automated tests (`pytest`).

| Module | Who can do what |
|--------|-----------------|
| auth | register (customer; staff roles need a super_admin), login, refresh, me |
| users | me; super_admin lists users and changes roles |
| customers | staff create/list; customers manage their own profile, KYC upload; support verifies KYC |
| plans | anyone lists active plans; operations create/update/deactivate |
| addresses | customers manage their own; staff can manage any |
| sims | operations add inventory; support changes status (validated transitions) and replaces SIMs |
| devices | support registers, assigns to an active SIM, releases, blocks (lost/stolen) |
| subscriptions | support (or the customer) subscribes; support changes plan, suspends, resumes, cancels; renew; history |
| usage | network/support record usage; customers see usage vs plan limits |
| towers, equipment | network engineers manage towers, coverage, equipment and health metrics (auto-fault on overheating) |
| outages | network engineers report/resolve; affected customers are found and notified automatically |
| technicians | operations manage; dispatch to outages/tickets/equipment; field technicians update their own jobs |
| tickets | customers raise; support assigns; lifecycle with history, comments (internal notes), SLA clock |
| ticket-assignments | support assigns tickets to staff; staff see their own |
| sla | targets per priority, live tracking, breach check |
| service-requests | customers request plan change / disconnection / etc.; support approves; completion applies the change |
| notifications | personal inbox; support sends; operations broadcast |
| dashboard | staff overview; customer overview |
| reports | revenue, tickets, SLA compliance, SIMs, outages, usage (operations) |
| audit-logs | super_admin only |
| health | `/health`, `/health/db` |
