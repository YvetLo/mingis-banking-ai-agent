"""
Shared pytest fixtures — Sprint 8.

BANKING_DB_PATH must be set BEFORE `backend.src.database` (and therefore
`backend.main`) is first imported, since DB_PATH is resolved once at
import time. That's why the env var is set at module load here, above
the `from backend.main import app` import — conftest.py is always
loaded before any test module in the same directory, so this guarantees
tests never touch the real demo data/banking.db.
"""

import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).parent / "test.db"
os.environ["BANKING_DB_PATH"] = str(TEST_DB_PATH)
# Test-only credentials. The app refuses to start without these (backend/src/auth.py has no
# defaults), and tests must never depend on — or leak — the real values in a developer's .env.
os.environ["JWT_SECRET_KEY"] = "test-only-jwt-secret-0123456789-abcdefghijklmnop"
os.environ["STAFF_USERNAME"] = "test-staff"
os.environ["STAFF_PASSWORD"] = "test-only-staff-password"

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.src.auth import create_customer_token, create_staff_token


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    """Create the schema up front. Tests that call the model directly (verifier, intent
    classifier) record cost rows through backend.src.tracing; without this they only worked
    when some earlier test had already started the app, and failed with "no such table:
    llm_calls" when run on their own."""
    from backend.src.database import init_db
    init_db()
    yield


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_db():
    yield
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest.fixture(scope="session")
def client():
    # `with` triggers the real FastAPI startup event once for the whole
    # session: init_db() against test.db, RAG retrievers loaded, agent
    # graph built — same code path as production, just pointed at test.db.
    with TestClient(app) as c:
        yield c


@pytest.fixture
def customer_headers():
    """customer_headers("user_001") -> a valid Authorization header for
    that user_id, as issued by /mock-api/auth/login (Sprint 19)."""
    def _make(user_id: str) -> dict:
        return {"Authorization": f"Bearer {create_customer_token(user_id)}"}
    return _make


@pytest.fixture
def staff_headers():
    return {"Authorization": f"Bearer {create_staff_token('staff')}"}
