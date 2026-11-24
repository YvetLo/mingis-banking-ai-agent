"""
Mock Banking API — Sprint 2
Simulates Core Banking / CRM endpoints.
Replace base URL with real bank API in production.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import create_customer_token, require_customer
from .mock_data import get_user_by_credentials, get_user_by_id

router = APIRouter(prefix="/mock-api", tags=["Mock Banking API"])


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/auth/login", summary="User login")
def login(req: LoginRequest):
    """Authenticate with username + password. Returns user_id, name, and
    a JWT — every endpoint below requires it as 'Authorization: Bearer
    <token>', matched against the caller's own user_id server-side."""
    user = get_user_by_credentials(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {
        "user_id": user["user_id"],
        "name": user["name"],
        "token": create_customer_token(user["user_id"]),
    }


# ── Account Data ────────────────────────────────────────────────────────────
# In production this layer maps to the real core-banking / CRM API, called
# server-to-server — never reachable by a customer's own request without a
# verified identity flowing through, which is what require_customer enforces
# here. user_id comes solely from the verified token, never from the caller.

def _get_user_or_404(user_id: str) -> dict:
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.get("/accounts/balance", summary="Get account balances")
def get_balance(user_id: str = Depends(require_customer)):
    """Return all account balances for the authenticated user."""
    return _get_user_or_404(user_id)["accounts"]

@router.get("/accounts/bill", summary="Get credit card bill")
def get_bill(user_id: str = Depends(require_customer)):
    """Return current and last month credit card billing info."""
    return _get_user_or_404(user_id)["bill"]

@router.get("/accounts/transactions", summary="Get recent transactions")
def get_transactions(limit: int = 5, user_id: str = Depends(require_customer)):
    """Return recent transaction history (default: last 5)."""
    txns = _get_user_or_404(user_id)["recent_transactions"]
    return txns[:limit]

@router.get("/accounts/cards", summary="Get credit cards")
def get_cards(user_id: str = Depends(require_customer)):
    """Return all credit cards belonging to the user."""
    return _get_user_or_404(user_id)["cards"]

@router.get("/accounts/profile", summary="Get user profile")
def get_profile(user_id: str = Depends(require_customer)):
    """Return basic user profile (name, phone, email)."""
    user = _get_user_or_404(user_id)
    return {
        "name": user["name"],
        "email": user["email"],
        "phone": user["phone"],
    }
