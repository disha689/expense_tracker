"""Run this once:  python make_password.py
It asks for a password and saves only its hash (never the password) in the .env file."""
import getpass
import secrets
from pathlib import Path

from app.auth import hash_password

ENV = Path(__file__).resolve().parent / ".env"


def main():
    password = getpass.getpass("New password (at least 8 characters): ")
    if len(password) < 8:
        print("That is too short. Use at least 8 characters.")
        return False
    if getpass.getpass("Type it again: ") != password:
        print("The two passwords do not match. Nothing was changed.")
        return False

    lines = ENV.read_text(encoding="utf-8-sig").splitlines() if ENV.exists() else []
    keep = [l for l in lines if not l.startswith(("APP_PASSWORD_HASH=", "SESSION_SECRET="))]
    keep.append("APP_PASSWORD_HASH=" + hash_password(password))
    keep.append("SESSION_SECRET=" + secrets.token_hex(32))  # new secret logs out every old session
    ENV.write_text("\n".join(keep) + "\n", encoding="utf-8")
    print("Done. Password saved in .env. Restart the server (and never upload .env to GitHub).")
    return True


if __name__ == "__main__":
    main()
