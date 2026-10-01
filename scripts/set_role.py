"""Change the role of an existing account directly in the database.

Use this when you have no super_admin yet (e.g. you registered as a customer):
    python -m scripts.set_role --email you@example.com --role super_admin
Roles: customer, super_admin, operations_manager, support_agent, network_engineer, field_technician
"""
import argparse

from sqlalchemy import select

from app.core.constants import ROLES
from app.db.session import SessionLocal
from app.models.user import User


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", required=True, choices=ROLES)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == args.email.strip().lower()))
        if not user:
            raise SystemExit(f"No user with email {args.email}")
        old, user.role = user.role, args.role
        db.commit()
        print(f"{user.email}: {old} -> {user.role}. Log out and log in again in Swagger.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
