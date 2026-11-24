"""
Session auth — Sprint 19.

Closes the IDOR gap tests/security/test_authorization.py documents:
previously any caller could set ChatRequest.user_id (or a mock-api
user_id query param) to someone else's id and the backend just trusted
it, and /tickets + /kb/* + /gap/* had no access control at all. Now
user_id (or staff identity) can only come from a JWT this backend
itself issued — at customer login (/mock-api/auth/login) or staff login
(/auth/staff-login) — and verified on every request that touches
customer data or back-office tooling.

There's no real staff directory here (this is a demo), so
STAFF_USERNAME/STAFF_PASSWORD is a single shared credential, same
security posture as the mock customer accounts in mock_api/mock_data.py.
"""

import os
import time

import jwt
from fastapi import Header, HTTPException

# Secrets and credentials have NO built-in fallback. A fallback would be a published
# password: anyone who clones the repo and forgets to set the variable would get a
# staff login and forgeable tokens that everyone on GitHub already knows. Missing or
# placeholder values stop the app at start-up instead (2026-11).
_PLACEHOLDERS = {"change_me", "change_me_to_a_random_value", "your_api_key_here", "changeme", "password"}
MIN_JWT_SECRET_LENGTH = 32


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value.lower() in _PLACEHOLDERS:
        raise RuntimeError(
            f"{name} is not set (or still holds the example value). Copy .env.example to .env and "
            f"give it a real value; there is deliberately no default. "
            f"Generate a secret with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    return value


SECRET_KEY = _required("JWT_SECRET_KEY")
if len(SECRET_KEY) < MIN_JWT_SECRET_LENGTH:
    raise RuntimeError(f"JWT_SECRET_KEY must be at least {MIN_JWT_SECRET_LENGTH} characters long.")
ALGORITHM = "HS256"
CUSTOMER_TTL_SECONDS = 60 * 60 * 8   # 8h — long enough for one demo session
STAFF_TTL_SECONDS = 60 * 60 * 12

STAFF_USERNAME = _required("STAFF_USERNAME")
STAFF_PASSWORD = _required("STAFF_PASSWORD")


def _encode(sub: str, role: str, ttl: int) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": sub, "role": role, "iat": now, "exp": now + ttl},
        SECRET_KEY, algorithm=ALGORITHM,
    )


def create_customer_token(user_id: str) -> str:
    return _encode(user_id, "customer", CUSTOMER_TTL_SECONDS)


def create_staff_token(username: str) -> str:
    return _encode(username, "staff", STAFF_TTL_SECONDS)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def _bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Expected 'Authorization: Bearer <token>'")
    return authorization[len("Bearer "):]


def get_current_user_id(authorization: str | None = Header(default=None)) -> str | None:
    """Optional customer auth — None for guests. Use where anonymous
    access is legitimate (e.g. /chat)."""
    token = _bearer_token(authorization)
    if token is None:
        return None
    payload = _decode(token)
    if payload.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Not a customer session")
    return payload["sub"]


def require_customer(authorization: str | None = Header(default=None)) -> str:
    """Mandatory customer auth — for endpoints where a guest must never
    be able to reach any customer's data (e.g. the mock core-banking API)."""
    user_id = get_current_user_id(authorization)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def require_staff(authorization: str | None = Header(default=None)) -> str:
    """Mandatory staff/back-office auth."""
    token = _bearer_token(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="Staff authentication required")
    payload = _decode(token)
    if payload.get("role") != "staff":
        raise HTTPException(status_code=403, detail="Staff role required")
    return payload["sub"]
