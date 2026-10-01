# Telecom Service & Network Management

FastAPI + SQLAlchemy + MySQL/PyMySQL starter repository.

## Setup
1. Create a MySQL database named `telecom_db`.
2. Copy `.env.example` to `.env` and set credentials and a strong `SECRET_KEY`.
3. Create and activate a Python 3.11 virtual environment.
4. Install: `pip install -r requirements.txt`
5. Start: `python run.py` (tables are created automatically on startup)
6. Create an admin (needed for admin-only endpoints): `python -m scripts.create_admin`
7. Swagger: http://127.0.0.1:8000/docs

## What is implemented
All 21 modules are implemented (118 API operations): auth, users, customers + KYC, plans, addresses, SIM cards,
devices, subscriptions, usage, towers, equipment, outages, technicians, tickets, ticket assignments, SLA,
service requests, notifications, dashboard, reports and audit logs. See `docs/api_endpoints.md`.

Quick start with data: `python -m scripts.seed_demo_data`, then follow `docs/demo_flow.md` in Swagger.

Run the tests: `pytest` (uses an in-memory SQLite database; set `TEST_DATABASE_URL` to run them on MySQL).

Known limits: refresh tokens are stateless (not stored/revoked) and there is no password-reset flow.
Business logic lives in the routers and `app/services/*` helpers used by them; the other empty
`app/services` / `app/repositories` files are unused placeholders. Not production-hardened.

## Database
Use Alembic for schema migrations. Import all model modules in `app/models/__init__.py`
before generating migrations. `create_all` is provided only as a development utility.

## Roles and registration
`POST /api/v1/auth/register` accepts `role`: customer, super_admin, operations_manager,
support_agent, network_engineer, field_technician.
- Anyone can register as `customer`.
- Staff roles need a `super_admin` token (click Authorize in Swagger first).
- Bootstrap: on an empty database the very first account may register as `super_admin`.
  Alternatively run `python -m scripts.create_admin`.

## "Role 'customer' cannot ..." (403)
Swagger uses the account you last logged in with, and the role belongs to the account.
- Fix an existing account: `python -m scripts.set_role --email you@example.com --role super_admin`, then Logout + Authorize again in Swagger.
- A super_admin can also call `PATCH /api/v1/users/{user_id}/role`.

## Register / any endpoint returns "Internal Server Error"
The real cause is now returned in the response `detail` and printed in the uvicorn terminal.
Open `GET /health/db` to check the connection and table schema. Common causes:
- Old tables (missing columns): `python -m scripts.fix_schema` (keeps data) or `python -m scripts.reset_db --yes` (wipes data).
- Wrong DATABASE_URL / MySQL not running / database `telecom_db` not created.
- Emoji or special characters rejected: create the database with `CHARACTER SET utf8mb4`.
