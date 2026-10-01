"""Create an initial super_admin account.

Interactive:      python -m scripts.create_admin
Non-interactive:  python -m scripts.create_admin --email admin@example.com --name "Admin" --password 'StrongPass123'
"""
import argparse
from getpass import getpass

from sqlalchemy import select

from app.core.security import hash_password
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.user import User


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email")
    parser.add_argument("--name")
    parser.add_argument("--password")
    args = parser.parse_args()

    init_db()
    email = (args.email or input("Admin email: ")).strip().lower()
    name = (args.name or input("Admin name: ")).strip()
    password = args.password or getpass("Password: ")

    db = SessionLocal()
    try:
        if db.scalar(select(User).where(User.email == email)):
            print("User already exists")
            return
        db.add(User(email=email, full_name=name, password_hash=hash_password(password),
                    role="super_admin", is_active=True))
        db.commit()
        print("Admin created")
    finally:
        db.close()


if __name__ == "__main__":
    main()
