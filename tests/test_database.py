import pytest

from app import database
from app.database import PgConn, get_conn


class FakeRaw:
    def __init__(self):
        self.calls, self.committed, self.rolled_back = [], 0, 0

    def execute(self, sql, params):
        self.calls.append((sql, params))
        return "cursor"

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1


def test_pgconn_translates_placeholders_and_escapes_percent():
    raw = FakeRaw()
    PgConn(raw).execute("SELECT * FROM t WHERE a = ? AND b LIKE '50%' AND c = ?", (1, 2))
    assert raw.calls == [("SELECT * FROM t WHERE a = %s AND b LIKE '50%%' AND c = %s", (1, 2))]


def test_pgconn_with_block_commits_and_rolls_back():
    raw = FakeRaw()
    with PgConn(raw):
        pass
    assert (raw.committed, raw.rolled_back) == (1, 0)
    with pytest.raises(ValueError):
        with PgConn(raw):
            raise ValueError("boom")
    assert (raw.committed, raw.rolled_back) == (1, 1)


def test_default_is_sqlite_when_no_database_url(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "x.db"))
    conn = get_conn()
    assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0
    conn.close()


def test_wrong_database_url_is_refused(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///expenses.db")
    with pytest.raises(RuntimeError, match="postgresql://"):
        get_conn()


def test_url_check():
    assert database.is_postgres_url("postgresql://u:p@host/db")
    assert database.is_postgres_url("postgres://u:p@host/db")
    assert not database.is_postgres_url("mysql://u:p@host/db")
    assert not database.is_postgres_url("")
