import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User
import app.models as _models  # noqa: F401


@pytest.fixture
def db_session():
    url = os.environ.get("TEST_DATABASE_URL")  # optional: run the suite against a real MySQL test database
    if url:
        engine = create_engine(url)
        Base.metadata.drop_all(engine)
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    yield session
    session.close()
    if url:
        Base.metadata.drop_all(engine)
    engine.dispose()


CALLS: list[tuple[str, str, int]] = []


class RecordingClient(TestClient):
    """Records every request so we can report which API operations the tests exercised."""

    def request(self, method, url, *args, **kwargs):
        response = super().request(method, url, *args, **kwargs)
        CALLS.append((method.upper(), str(url).split("?")[0], response.status_code))
        return response


def pytest_sessionfinish(session, exitstatus):
    out = os.environ.get("COVERAGE_OUT")
    if out:
        import json
        with open(out, "w") as fh:
            json.dump(CALLS, fh)


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session
    app.dependency_overrides[get_db] = _get_db
    yield RecordingClient(app)  # no `with`: skips the MySQL startup hook
    app.dependency_overrides.clear()


@pytest.fixture
def admin_headers(client, db_session):
    db_session.add(User(full_name="Admin", email="admin@example.com",
                        password_hash=hash_password("Admin@12345"), role="super_admin"))
    db_session.commit()
    r = client.post("/api/v1/auth/login", data={"username": "admin@example.com", "password": "Admin@12345"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def customer_headers(client):
    client.post("/api/v1/auth/register", json={"full_name": "Cust One", "email": "c1@example.com", "password": "Password123"})
    r = client.post("/api/v1/auth/login", data={"username": "c1@example.com", "password": "Password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def make_headers(client, db_session):
    """make_headers("support_agent") -> auth headers of a fresh user with that role."""
    counter = {"n": 0}

    def _make(role: str):
        counter["n"] += 1
        email = f"{role}{counter['n']}@example.com"
        user = User(full_name=role.title(), email=email, password_hash=hash_password("Password123"), role=role)
        db_session.add(user)
        db_session.commit()
        r = client.post("/api/v1/auth/login", data={"username": email, "password": "Password123"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        h["user_id"] = user.id  # convenience; stripped by helper below
        return h
    return _make
