import make_password
from app import auth


def feed(monkeypatch, *answers):
    answers = iter(answers)
    monkeypatch.setattr(make_password.getpass, "getpass", lambda prompt="": next(answers))


def read_env(path):
    return dict(l.split("=", 1) for l in path.read_text(encoding="utf-8").splitlines() if "=" in l)


def test_writes_hash_and_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(make_password, "ENV", tmp_path / ".env")
    feed(monkeypatch, "my long password", "my long password")
    assert make_password.main() is True
    env = read_env(tmp_path / ".env")
    assert auth.verify_password("my long password", env["APP_PASSWORD_HASH"])
    assert len(env["SESSION_SECRET"]) >= 32
    assert "my long password" not in (tmp_path / ".env").read_text(encoding="utf-8")


def test_changing_password_keeps_other_lines_and_rotates_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(make_password, "ENV", tmp_path / ".env")
    (tmp_path / ".env").write_text("OTHER=keep-me\n", encoding="utf-8")
    feed(monkeypatch, "first password", "first password")
    make_password.main()
    first = read_env(tmp_path / ".env")
    feed(monkeypatch, "second password", "second password")
    make_password.main()
    second = read_env(tmp_path / ".env")
    assert second["OTHER"] == "keep-me"
    assert second["SESSION_SECRET"] != first["SESSION_SECRET"]
    assert auth.verify_password("second password", second["APP_PASSWORD_HASH"])
    assert not auth.verify_password("first password", second["APP_PASSWORD_HASH"])
    assert (tmp_path / ".env").read_text(encoding="utf-8").count("APP_PASSWORD_HASH=") == 1


def test_short_or_mismatched_password_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(make_password, "ENV", tmp_path / ".env")
    feed(monkeypatch, "short")
    assert make_password.main() is False
    feed(monkeypatch, "long enough one", "long enough two")
    assert make_password.main() is False
    assert not (tmp_path / ".env").exists()
