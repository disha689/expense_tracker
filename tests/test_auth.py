import pytest
from fastapi.testclient import TestClient

from app import auth
from app.database import get_conn
from app.main import app, get_db

PASSWORD = "correct horse battery"
SECRET = "s" * 40


@pytest.fixture
def conn():
    c = get_conn(":memory:")
    yield c
    c.close()


@pytest.fixture
def client(monkeypatch, conn):
    """Login switched ON, with a known password."""
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    monkeypatch.setenv("APP_PASSWORD_HASH", auth.hash_password(PASSWORD, iterations=1000))
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    auth.FAILS.clear()

    def override():
        yield conn

    app.dependency_overrides[get_db] = override
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()
    auth.FAILS.clear()


def login(client, password=PASSWORD):
    return client.post("/api/login", json={"password": password})


# ---------- password hashing ----------
def test_hash_and_verify():
    stored = auth.hash_password("hello world", iterations=1000)
    assert stored.startswith("pbkdf2$1000$")
    assert auth.verify_password("hello world", stored)
    assert not auth.verify_password("Hello world", stored)
    assert "hello world" not in stored


def test_same_password_gets_different_hashes():
    assert auth.hash_password("abc12345", 1000) != auth.hash_password("abc12345", 1000)


def test_verify_rejects_broken_hashes():
    for bad in ["", "plain", "pbkdf2$x$y$z", "md5$1$aa$bb", "pbkdf2$1000$zz$zz"]:
        assert auth.verify_password("anything", bad) is False


# ---------- login cookie ----------
def test_token_valid_then_expires():
    token = auth.make_token(SECRET, now=1000, ttl=60)
    assert auth.valid_token(token, SECRET, now=1030)
    assert not auth.valid_token(token, SECRET, now=1061)


def test_token_rejects_tampering_and_garbage():
    token = auth.make_token(SECRET, now=1000, ttl=60)
    expiry, sig = token.split(".")
    assert not auth.valid_token(f"{int(expiry) + 9999}.{sig}", SECRET, now=1030)
    assert not auth.valid_token(token, "another-secret-value", now=1030)
    for bad in ["", None, "nodot", "abc.def", "12.", ".abc", "\u00b2.aa", "99999999999.\u00e9\u00e9"]:
        assert not auth.valid_token(bad, SECRET, now=1030)


# ---------- the guard in front of the app ----------
def test_api_needs_login(client):
    assert client.get("/expenses").status_code == 401
    assert client.post("/expenses", json={"amount": 5, "category": "x"}).status_code == 401
    assert client.get("/export.csv").status_code == 401
    assert client.get("/docs").status_code in (303, 401)


def test_page_redirects_to_login(client):
    r = client.get("/", headers={"accept": "text/html"})
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_login_page_is_open(client):
    r = client.get("/login")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


def test_wrong_password(client):
    r = login(client, "nope")
    assert r.status_code == 401
    assert "session" not in r.headers.get("set-cookie", "")
    assert client.get("/expenses").status_code == 401


def test_login_gives_access_then_logout_removes_it(client):
    r = login(client)
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/expenses").status_code == 200
    assert client.get("/", headers={"accept": "text/html"}).status_code == 200
    assert client.get("/login").status_code == 303  # already logged in
    assert client.post("/api/logout").status_code == 200
    client.cookies.clear()
    assert client.get("/expenses").status_code == 401


def test_forged_and_expired_cookies_are_rejected(client):
    client.cookies.set("session", "99999999999.deadbeef")
    assert client.get("/expenses").status_code == 401
    client.cookies.set("session", auth.make_token(SECRET, now=1, ttl=10))
    assert client.get("/expenses").status_code == 401


def test_cookie_made_with_other_secret_is_rejected(client):
    client.cookies.set("session", auth.make_token("x" * 40))
    assert client.get("/expenses").status_code == 401


def test_lockout_after_five_wrong_attempts(client):
    for _ in range(5):
        assert login(client, "nope").status_code == 401
    assert login(client).status_code == 429  # even the right password waits


def test_success_clears_earlier_failures(client):
    for _ in range(4):
        login(client, "nope")
    assert login(client).status_code == 200
    for _ in range(4):
        assert login(client, "nope").status_code == 401


def test_login_validation(client):
    assert client.post("/api/login", json={"password": ""}).status_code == 422
    assert client.post("/api/login", json={}).status_code == 422
    assert client.post("/api/login", json={"password": "x" * 500}).status_code == 422


def test_cross_site_writes_are_blocked(client):
    login(client)
    body = {"amount": 5, "category": "x"}
    r = client.post("/expenses", json=body, headers={"origin": "http://evil.example"})
    assert r.status_code == 403
    assert client.get("/expenses").json() == []
    r = client.post("/expenses", json=body, headers={"origin": "http://testserver"})
    assert r.status_code == 201


def test_secure_flag_when_asked(client, monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "1")
    assert "secure" in login(client).headers["set-cookie"].lower()


def test_security_headers(client):
    r = client.get("/login")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


def test_not_configured_blocks_everything_except_login_page(monkeypatch, conn):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.delenv("APP_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    c = TestClient(app, follow_redirects=False)
    r = c.get("/", headers={"accept": "text/html"})
    assert r.status_code == 503 and "make_password.py" in r.text
    assert c.get("/expenses").status_code == 503
    assert c.post("/api/login", json={"password": PASSWORD}).status_code == 503
    assert c.get("/login").status_code == 200


def test_short_secret_counts_as_not_configured(monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("APP_PASSWORD_HASH", auth.hash_password("abc12345", 1000))
    monkeypatch.setenv("SESSION_SECRET", "short")
    assert auth.is_configured() is False


def test_auth_disabled_switch_lets_requests_through(monkeypatch, conn):
    monkeypatch.setenv("AUTH_DISABLED", "1")

    def override():
        yield conn

    app.dependency_overrides[get_db] = override
    try:
        assert TestClient(app).get("/expenses").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_load_env_reads_file_and_keeps_existing_values(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("# comment\n\nFOO_TEST=one\nBAR_TEST = two \nEXISTING_TEST=file\nnot a pair\n", encoding="utf-8")
    monkeypatch.delenv("FOO_TEST", raising=False)
    monkeypatch.delenv("BAR_TEST", raising=False)
    monkeypatch.setenv("EXISTING_TEST", "already")
    auth.load_env(f)
    import os
    assert os.environ["FOO_TEST"] == "one" and os.environ["BAR_TEST"] == "two"
    assert os.environ["EXISTING_TEST"] == "already"
    monkeypatch.delenv("FOO_TEST", raising=False)
    monkeypatch.delenv("BAR_TEST", raising=False)
