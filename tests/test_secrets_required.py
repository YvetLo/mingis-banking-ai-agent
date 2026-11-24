"""
Secrets and credentials have no built-in default — 2026-11

`backend/src/auth.py` and `frontend/staff_auth.py` used to fall back to a dev-only JWT secret and a
`staff / staff1234` login when the environment variables were missing. The repository is public, so
those fallbacks were published credentials: anyone deploying a fresh clone without setting the
variables would have exposed the staff pages and accepted tokens anyone could forge.

These tests start a fresh interpreter with a controlled environment (the test process itself already
has its own test-only values) and check that the app refuses to start instead.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOOD = {"JWT_SECRET_KEY": "x" * 40, "STAFF_USERNAME": "someone", "STAFF_PASSWORD": "a-real-password"}


def _import_auth(**env):
    clean = {k: v for k, v in os.environ.items()
             if k not in ("JWT_SECRET_KEY", "STAFF_USERNAME", "STAFF_PASSWORD")}
    clean.update(env)
    clean["PYTHONPATH"] = str(ROOT)
    return subprocess.run([sys.executable, "-c", "import backend.src.auth"],
                          cwd=ROOT, env=clean, capture_output=True, text=True)


def test_starts_when_everything_is_set():
    assert _import_auth(**GOOD).returncode == 0


def test_refuses_to_start_without_any_of_the_three():
    for missing in GOOD:
        env = {k: v for k, v in GOOD.items() if k != missing}
        r = _import_auth(**env)
        assert r.returncode != 0 and f"{missing} is not set" in r.stderr, (missing, r.stderr[-300:])


def test_refuses_the_example_values_from_env_example():
    for name, placeholder in (("JWT_SECRET_KEY", "change_me_to_a_random_value"), ("STAFF_PASSWORD", "change_me")):
        r = _import_auth(**{**GOOD, name: placeholder})
        assert r.returncode != 0 and "example value" in r.stderr, (name, r.stderr[-300:])


def test_refuses_a_short_jwt_secret():
    r = _import_auth(**{**GOOD, "JWT_SECRET_KEY": "too-short"})
    assert r.returncode != 0 and "at least" in r.stderr


def test_the_old_published_defaults_are_gone_from_the_source():
    banned = ("dev-only-insecure-secret-change-me", "staff1234")
    hits = []
    for path in list((ROOT / "backend").rglob("*.py")) + list((ROOT / "frontend").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        hits += [(str(path.relative_to(ROOT)), b) for b in banned if b in text]
    assert not hits, hits
