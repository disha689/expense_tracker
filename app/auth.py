import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
ITERATIONS = 600_000
SESSION_SECONDS = 30 * 24 * 3600  # stay logged in for 30 days
MAX_FAILS = 5
FAIL_WINDOW = 15 * 60  # seconds
GLOBAL_KEY = "*"
GLOBAL_MAX_FAILS = 20  # all addresses together
FAILS = {}  # ip -> list of failure timestamps


# ---------- settings (read each time, so they can change while testing) ----------
def load_env(path=None):
    """Read KEY=VALUE lines from the .env file into the environment (existing values win)."""
    path = Path(path) if path else ENV_FILE
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def auth_disabled():
    return os.environ.get("AUTH_DISABLED") == "1"


def password_hash():
    return os.environ.get("APP_PASSWORD_HASH", "")


def session_secret():
    return os.environ.get("SESSION_SECRET", "")


def is_configured():
    return bool(password_hash()) and len(session_secret()) >= 16


# ---------- password hashing ----------
def hash_password(password, iterations=ITERATIONS):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        scheme, iterations, salt_hex, hash_hex = stored.split("$")
        if scheme != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError, AttributeError):
        return False


# ---------- login cookie (signed, expires) ----------
def _sign(secret, payload):
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_token(secret, now=None, ttl=SESSION_SECONDS):
    expiry = str(int((time.time() if now is None else now) + ttl))
    return f"{expiry}.{_sign(secret, expiry)}"


def valid_token(token, secret, now=None):
    if not token or not secret or "." not in token:
        return False
    expiry, _, signature = token.partition(".")
    if not (expiry.isascii() and expiry.isdigit()):
        return False
    try:
        good = hmac.compare_digest(signature.encode(), _sign(secret, expiry).encode())
    except (TypeError, UnicodeError):
        return False
    return good and int(expiry) > (time.time() if now is None else now)


# ---------- too many wrong passwords ----------
def _recent_failures(ip, now):
    recent = [t for t in FAILS.get(ip, []) if now - t < FAIL_WINDOW]
    FAILS[ip] = recent
    return recent


def too_many_attempts(ip, now=None):
    now = time.time() if now is None else now
    return (
        len(_recent_failures(ip, now)) >= MAX_FAILS
        or len(_recent_failures(GLOBAL_KEY, now)) >= GLOBAL_MAX_FAILS
    )


def record_failure(ip, now=None):
    now = time.time() if now is None else now
    _recent_failures(ip, now).append(now)
    _recent_failures(GLOBAL_KEY, now).append(now)


def clear_failures(ip):
    FAILS.pop(ip, None)
