import json
import struct

import pytest
from fastapi.testclient import TestClient

from app import auth, pwa
from app.database import get_conn
from app.main import app, get_db

PASSWORD = "correct horse battery"


@pytest.fixture
def conn():
    c = get_conn(":memory:")
    yield c
    c.close()


@pytest.fixture
def client(monkeypatch, conn):
    """Login switched ON, and nobody is logged in yet."""
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("APP_PASSWORD_HASH", auth.hash_password(PASSWORD, iterations=1000))
    monkeypatch.setenv("SESSION_SECRET", "s" * 40)
    auth.FAILS.clear()

    def override():
        yield conn

    app.dependency_overrides[get_db] = override
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()
    auth.FAILS.clear()


def png_size(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG file"
    return struct.unpack(">II", data[16:24])


# ---------- the files a browser asks for before anyone logs in ----------
def test_manifest_is_public_and_complete(client):
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200 and "manifest+json" in r.headers["content-type"]
    m = json.loads(r.text)
    assert m["name"] == "Spendly" and m["display"] == "standalone" and m["start_url"] == "/"
    sizes = {(i["sizes"], i["purpose"]) for i in m["icons"]}
    assert ("192x192", "any") in sizes and ("512x512", "any") in sizes and ("512x512", "maskable") in sizes


def test_every_icon_in_the_manifest_exists_with_the_right_size(client):
    for icon in json.loads(client.get("/manifest.webmanifest").text)["icons"]:
        r = client.get(icon["src"])
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"
        w, h = (int(n) for n in icon["sizes"].split("x"))
        assert png_size(r.content) == (w, h), icon["src"]


def test_apple_touch_icon_is_180px(client):
    r = client.get("/icons/apple-touch-icon.png")
    assert r.status_code == 200 and png_size(r.content) == (180, 180)


def test_service_worker_is_public_and_only_keeps_the_offline_page(client):
    r = client.get("/sw.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert r.headers["service-worker-allowed"] == "/" and "no-cache" in r.headers["cache-control"]
    assert "/offline" in r.text
    assert "cache.put" not in r.text and "cache.addAll" not in r.text  # no app data is ever stored


def test_offline_page_and_install_script_are_public(client):
    r = client.get("/offline")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"] and "offline" in r.text.lower()
    r = client.get("/pwa.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert "serviceWorker.register" in r.text and "beforeinstallprompt" in r.text


def test_unknown_icons_and_path_tricks_are_refused(client):
    assert client.get("/icons/secret.png").status_code == 404
    assert client.get("/icons/..%2Fauth.py").status_code == 404
    assert client.get("/icons/%2e%2e%2f%2e%2e%2fmain.py").status_code == 404
    assert client.get("/icons/").status_code in (404, 401, 303)


def test_private_things_are_still_private(client):
    assert client.get("/expenses").status_code == 401
    assert client.get("/export.csv").status_code == 401
    assert client.get("/static/index.html").status_code == 401
    assert client.get("/static/pwa/sw.js").status_code == 401  # only the short public addresses are open


# ---------- the install tags ----------
def test_login_page_has_the_install_tags(client):
    html = client.get("/login").text
    assert html.count('rel="manifest"') == 1 and html.count("/pwa.js") == 1
    assert 'name="theme-color"' in html and "apple-touch-icon" in html


def test_home_page_has_the_install_tags_after_login(client):
    assert client.post("/api/login", json={"password": PASSWORD}).status_code == 200
    html = client.get("/", headers={"accept": "text/html"}).text
    assert html.count('rel="manifest"') == 1 and html.count("/pwa.js") == 1
    assert html.index('rel="manifest"') < html.index("</head>")
    assert html.index("/pwa.js") > html.index("<body")
    assert "Spendly" in html  # the real page is still there


def test_add_app_tags_edge_cases():
    page = "<html><head><title>x</title></head><body><p>hi</p></body></html>"
    out = pwa.add_app_tags(page)
    assert out.count('rel="manifest"') == 1 and out.endswith("</body></html>")
    assert pwa.add_app_tags(out) == out  # never added twice
    assert pwa.add_app_tags("just text") == "just text"
    assert pwa.add_app_tags("<body></body>") == "<body></body>"  # no head: left alone


def test_is_public():
    assert pwa.is_public("/sw.js") and pwa.is_public("/icons/icon-192.png")
    assert not pwa.is_public("/expenses") and not pwa.is_public("/static/index.html")
