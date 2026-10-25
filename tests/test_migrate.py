import os
import sqlite3
from datetime import date

import pytest

from app import crud
from app.database import SQLITE_SCHEMA, connect_postgres, get_conn
from migrate_to_postgres import MigrationError, migrate

PG = os.environ.get("TEST_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(not PG, reason="needs a PostgreSQL database in TEST_DATABASE_URL")


@pytest.fixture
def clean_pg():
    conn = get_conn(":memory:")  # gives an empty PostgreSQL schema
    conn.close()
    yield PG


@pytest.fixture
def local_db(tmp_path):
    path = str(tmp_path / "expenses.db")
    conn = sqlite3.connect(path)
    for statement in SQLITE_SCHEMA:
        conn.execute(statement)
    crud.add_expense(conn, 250.5, "food", "lunch", "2026-10-14")
    crud.add_expense(conn, 1200, "travel", "", "2026-09-20")
    crud.delete_expense(conn, crud.add_expense(conn, 5, "temp", "", "2026-10-01"))  # leaves a gap in the ids
    crud.add_expense(conn, 90, "food", "tea", "2026-10-15")
    crud.set_budget(conn, "2026-10", 20000)
    crud.set_category_budget(conn, "2026-10", "food", 5000)
    crud.create_recurring(conn, 15000, "rent", "", 5, "2026-10", today=date(2026, 10, 20))
    crud.apply_recurring(conn, today=date(2026, 10, 20))
    conn.close()
    return path


def test_copies_everything_and_keeps_ids(clean_pg, local_db):
    counts = migrate(local_db, clean_pg)
    assert counts == {"expenses": 4, "budgets": 1, "category_budgets": 1, "recurring": 1, "recurring_log": 1}
    src, dst = sqlite3.connect(local_db), get_conn_pg(clean_pg)
    for table in ("expenses", "budgets", "category_budgets", "recurring", "recurring_log"):
        a = sorted(src.execute(f"SELECT * FROM {table}").fetchall())
        b = sorted(dst.execute(f"SELECT * FROM {table}").fetchall())
        assert a == b, table
    dst.close()


def test_new_rows_continue_after_the_copied_ids(clean_pg, local_db):
    migrate(local_db, clean_pg)
    dst = get_conn_pg(clean_pg)
    biggest = dst.execute("SELECT MAX(id) FROM expenses").fetchone()[0]
    assert crud.add_expense(dst, 10, "new", "", "2026-10-20") == biggest + 1
    assert crud.create_recurring(dst, 99, "wifi", "", 1, "2026-10", today=date(2026, 10, 20)) == 2
    dst.close()


def test_refuses_when_online_database_has_data(clean_pg, local_db):
    migrate(local_db, clean_pg)
    with pytest.raises(MigrationError, match="already has data"):
        migrate(local_db, clean_pg)
    dst = get_conn_pg(clean_pg)
    assert dst.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 4  # no duplicates
    dst.close()


def test_missing_local_file(clean_pg, tmp_path):
    with pytest.raises(MigrationError, match="Could not find"):
        migrate(str(tmp_path / "nope.db"), clean_pg)


def test_empty_local_database(clean_pg, tmp_path):
    path = str(tmp_path / "empty.db")
    sqlite3.connect(path).close()  # a file with no tables at all
    assert migrate(path, clean_pg) == {t: 0 for t in ("expenses", "budgets", "category_budgets", "recurring", "recurring_log")}
    dst = get_conn_pg(clean_pg)
    assert crud.add_expense(dst, 5, "x", "", "2026-10-01") == 1
    dst.close()


def get_conn_pg(url):
    return connect_postgres(url)
