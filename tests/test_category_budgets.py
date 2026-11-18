import os
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import crud, database
from app.database import get_conn
from app.main import app, get_db

needs_pg = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").strip(), reason="needs a PostgreSQL database in TEST_DATABASE_URL"
)


@pytest.fixture
def conn():
    c = get_conn(":memory:")
    yield c
    c.close()


@pytest.fixture
def client(conn):
    def override():
        yield conn

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_normalize_category():
    assert crud.normalize_category("  Food ") == "food"
    assert crud.normalize_category("EATING   OUT") == "eating out"
    assert crud.normalize_category("") == "" and crud.normalize_category(None) == ""


def test_add_counts_different_spellings_together(conn):
    crud.add_expense(conn, 100, "Food", date_str="2026-10-01")
    crud.add_expense(conn, 50, " food ", date_str="2026-10-02")
    crud.add_expense(conn, 25, "FOOD", date_str="2026-10-03")
    assert crud.summary(conn) == [("food", 175)]


def test_blank_category_is_rejected(conn):
    with pytest.raises(ValueError, match="Category is required"):
        crud.add_expense(conn, 10, "   ")
    eid = crud.add_expense(conn, 10, "food")
    with pytest.raises(ValueError, match="Category is required"):
        crud.edit_expense(conn, eid, category="  ")


def test_edit_normalizes(conn):
    eid = crud.add_expense(conn, 10, "food")
    crud.edit_expense(conn, eid, category="  Travel ")
    assert crud.get_expense(conn, eid)[2] == "travel"


def test_recurring_category_is_normalized(conn):
    crud.create_recurring(conn, 99, " Wi-Fi ", "", 1, "2026-10", today=date(2026, 10, 20))
    crud.apply_recurring(conn, today=date(2026, 10, 20))
    assert crud.list_recurring(conn)[0][2] == "wi-fi"
    assert crud.list_expenses(conn)[0][2] == "wi-fi"


def test_old_rows_get_tidied_and_it_is_repeatable(conn):
    for cat in ("Food", "FOOD ", "food", "Travel"):  # written the old way, straight into the table
        conn.execute("INSERT INTO expenses (amount, category, note, date) VALUES (?, ?, ?, ?)",
                     (10, cat, "", "2026-10-01"))
    conn.execute("INSERT INTO recurring (amount, category, note, day, start_month) VALUES (?, ?, ?, ?, ?)",
                 (5, "Rent ", "", 1, "2026-10"))
    conn.commit()
    # "Food", "FOOD " and "Travel" in expenses, plus "Rent " in recurring (the plain "food" row was already fine)
    assert crud.normalize_existing_categories(conn) == 4
    assert dict(crud.summary(conn)) == {"food": 30, "travel": 10}
    assert crud.list_recurring(conn)[0][2] == "rent"
    assert crud.normalize_existing_categories(conn) == 0  # nothing left to change


def test_old_rows_are_tidied_when_a_real_database_is_opened(monkeypatch, tmp_path):
    path = str(tmp_path / "old.db")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setattr(database, "_tidied", set())
    first = get_conn(path)
    first.execute("INSERT INTO expenses (amount, category, note, date) VALUES (10, 'Food', '', '2026-10-01')")
    first.commit()
    first.close()
    monkeypatch.setattr(database, "_tidied", set())  # pretend the server restarted
    second = get_conn(path)
    assert crud.list_expenses(second)[0][2] == "food"
    second.close()


def test_api_blank_category_is_a_400_not_a_crash(client):
    r = client.post("/expenses", json={"amount": 5, "category": "   "})
    assert r.status_code == 400 and "Category" in r.json()["detail"]


def test_api_normalizes_and_groups(client):
    client.post("/expenses", json={"amount": 100, "category": "Food", "date": "2026-10-01"})
    client.post("/expenses", json={"amount": 50, "category": "FOOD ", "date": "2026-10-02"})
    data = client.get("/summary?month=2026-10").json()
    assert data["by_category"] == [{"category": "food", "total": 150}]
    eid = client.get("/expenses").json()[0]["id"]
    assert client.put(f"/expenses/{eid}", json={"category": "  Snacks "}).json()["category"] == "snacks"
    assert client.put(f"/expenses/{eid}", json={"category": "  "}).status_code == 400


def test_csv_import_normalizes(client):
    r = client.post("/import", content="amount,category\n10,Food\n20,FOOD \n30,  \n").json()
    assert r["imported"] == 2 and r["skipped_count"] == 1
    assert client.get("/summary").json()["by_category"] == [{"category": "food", "total": 30}]


@needs_pg
def test_postgres_old_rows_are_tidied_when_the_app_opens_it(monkeypatch):
    url = os.environ["TEST_DATABASE_URL"].strip()
    get_conn(":memory:").close()  # empty PostgreSQL schema
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(database, "_tidied", set())
    raw = database.connect_postgres(url)
    raw.execute("INSERT INTO expenses (amount, category, note, date) VALUES (10, 'Food ', '', '2026-10-01')")
    raw.execute("INSERT INTO expenses (amount, category, note, date) VALUES (20, 'FOOD', '', '2026-10-02')")
    raw.commit()
    raw.close()
    conn = get_conn()  # this is what the server does on its first request
    assert crud.summary(conn) == [("food", 30)]
    conn.close()
