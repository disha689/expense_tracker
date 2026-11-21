"""Makes Spendly installable on a phone (a "progressive web app").

Everything here is public on purpose: the browser asks for these files before you are logged in,
and none of them contains anything private (just the logo, a manifest and a tiny offline page)."""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

PWA_DIR = Path(__file__).parent / "static" / "pwa"

PUBLIC_PATHS = {"/manifest.webmanifest", "/sw.js", "/pwa.js", "/offline"}
PUBLIC_PREFIXES = ("/icons/",)

ICONS = {"icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png"}

HEAD_TAGS = """<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#1c72bd">
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Spendly">
"""
SCRIPT_TAG = '<script src="/pwa.js" defer></script>\n'


def is_public(path):
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


def add_app_tags(html):
    """Adds the install tags to a page. Pages that already have them, or have no head/body, stay unchanged."""
    if 'rel="manifest"' in html:
        return html
    head_end = html.find("</head>")
    body_end = html.rfind("</body>")
    if head_end == -1 or body_end == -1:
        return html
    return html[:head_end] + HEAD_TAGS + html[head_end:body_end] + SCRIPT_TAG + html[body_end:]


def install_pwa(app: FastAPI):
    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest():
        return FileResponse(PWA_DIR / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/sw.js", include_in_schema=False)
    def service_worker():
        return FileResponse(
            PWA_DIR / "sw.js",
            media_type="text/javascript",
            headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
        )

    @app.get("/pwa.js", include_in_schema=False)
    def pwa_script():
        return FileResponse(PWA_DIR / "pwa.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})

    @app.get("/offline", include_in_schema=False)
    def offline_page():
        return FileResponse(PWA_DIR / "offline.html", media_type="text/html")

    @app.get("/icons/{name}", include_in_schema=False)
    def icon(name: str):
        if name not in ICONS:
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(PWA_DIR / "icons" / name, media_type="image/png")
