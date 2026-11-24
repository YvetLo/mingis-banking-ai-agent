"""
Server-side staff auth for the back-office pages (Dashboard, KB
maintenance, Gap management) — Sprint 19 closed off /tickets, /kb/*,
/gap/* to anonymous callers (see tests/security/test_authorization.py).

These pages run entirely in our own Streamlit process, never in a
customer's browser, so they authenticate once per browser session using
STAFF_USERNAME/STAFF_PASSWORD from this process's own .env — there's no
staff login UI yet, which is a known gap for a real public deploy (see
docs/evaluation.md's public-demo checklist).
"""

import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL", "http://localhost:8000")   # test builds point at their own backend


def _staff_credential(name: str) -> str:
    """No built-in fallback: a default here would be a published password (see backend/src/auth.py)."""
    value = os.getenv(name, "").strip()
    if not value:
        st.error(f"{name} is not set. Copy .env.example to .env and set it, then restart the app.")
        st.stop()
    return value


def _staff_login() -> str:
    resp = requests.post(
        f"{API_URL}/auth/staff-login",
        json={
            "username": _staff_credential("STAFF_USERNAME"),
            "password": _staff_credential("STAFF_PASSWORD"),
        },
        timeout=10,
    )
    resp.raise_for_status()
    token = resp.json()["token"]
    st.session_state.staff_token = token
    return token


def staff_session() -> requests.Session:
    """A requests.Session pre-loaded with a valid staff Authorization
    header. Caches the token in st.session_state so each rerun of the
    page doesn't re-authenticate. Staff tokens expire after 12h (and are
    invalidated if the backend's JWT secret changes), so a 401 triggers
    one fresh login and a single retry of the original request."""
    token = st.session_state.get("staff_token") or _staff_login()
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {token}"

    def _relogin_on_401(resp, *args, **kwargs):
        if resp.status_code != 401 or resp.request.headers.get("X-Staff-Retry"):
            return resp
        fresh = _staff_login()
        s.headers["Authorization"] = f"Bearer {fresh}"
        retry = resp.request.copy()
        retry.headers["Authorization"] = f"Bearer {fresh}"
        retry.headers["X-Staff-Retry"] = "1"
        return s.send(retry, **kwargs)

    s.hooks["response"].append(_relogin_on_401)
    return s
