import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from app import auth

COOKIE = "session"
OPEN_PATHS = {"/login", "/api/login"}
LOGIN_PAGE = Path(__file__).parent / "static" / "login.html"


class LoginIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


def _harden(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


def _same_origin(request):
    origin = request.headers.get("origin")
    if not origin:
        return True
    return urlparse(origin).netloc == request.headers.get("host", "")


def install_security(app: FastAPI):
    """Adds the login check in front of the whole app, plus /login, /api/login and /api/logout."""
    auth.load_env()

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        if request.method not in ("GET", "HEAD", "OPTIONS") and not _same_origin(request):
            return _harden(JSONResponse({"detail": "Cross-site request blocked"}, status_code=403))
        if auth.auth_disabled() or path in OPEN_PATHS:
            return _harden(await call_next(request))
        if not auth.is_configured():
            return _harden(Response(
                "Password not set yet. In the project folder run: python make_password.py "
                "and then restart the server.",
                status_code=503, media_type="text/plain",
            ))
        if auth.valid_token(request.cookies.get(COOKIE), auth.session_secret()):
            return _harden(await call_next(request))
        wants_page = request.method == "GET" and "text/html" in request.headers.get("accept", "")
        if wants_page:
            return _harden(RedirectResponse("/login", status_code=303))
        return _harden(JSONResponse({"detail": "Not logged in"}, status_code=401))

    @app.get("/login", include_in_schema=False)
    def login_page(request: Request):
        logged_in = (
            auth.is_configured()
            and not auth.auth_disabled()
            and auth.valid_token(request.cookies.get(COOKIE), auth.session_secret())
        )
        if logged_in:
            return RedirectResponse("/", status_code=303)
        return FileResponse(LOGIN_PAGE)

    @app.post("/api/login", include_in_schema=False)
    def login(payload: LoginIn, request: Request):
        ip = request.client.host if request.client else "unknown"
        if auth.too_many_attempts(ip):
            raise HTTPException(status_code=429, detail="Too many wrong attempts. Try again in 15 minutes.")
        if not auth.is_configured():
            raise HTTPException(status_code=503, detail="Password not set yet. Run make_password.py first.")
        if not auth.verify_password(payload.password, auth.password_hash()):
            auth.record_failure(ip)
            raise HTTPException(status_code=401, detail="Wrong password")
        auth.clear_failures(ip)
        response = JSONResponse({"detail": "Logged in"})
        response.set_cookie(
            COOKIE,
            auth.make_token(auth.session_secret()),
            max_age=auth.SESSION_SECONDS,
            httponly=True,
            samesite="lax",
            secure=os.environ.get("COOKIE_SECURE") == "1" or request.url.scheme == "https",
        )
        return response

    @app.post("/api/logout", include_in_schema=False)
    def logout():
        response = JSONResponse({"detail": "Logged out"})
        response.delete_cookie(COOKIE)
        return response
