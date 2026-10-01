# Architecture

Modular monolith: API routers -> services -> repositories -> SQLAlchemy models. Authentication and permissions are centralized. Migrations are managed by Alembic.
