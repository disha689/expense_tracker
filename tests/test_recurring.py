from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import crud
from app.database import get_conn
from app.main import app, get_db


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


TODAY = date(2026, 10, 20)


# ---------- crud ----------
def test_create_and_list(conn):
    rid = crud.create_recurring(conn, 15000, "rent", "", 5, "2026-10", today=TODAY)
    rows = crud.list_recurring(conn)
    assert rows == [(rid, 15000, "rent", "", 5, "2026-10")]


def test_creates_expense_when_day_has_passed(conn):
    crud.create_recurring(conn, 15000, "rent", "", 5, "2026-10", today=TODAY)
    assert crud.apply_recurring(conn, today=TODAY) == 1
    row = crud.list_expenses(conn)[0]
    assert row[1] == "2026-10-05" and row[2] == "rent" and row[3] == 15000
    assert row[4] == "Recurring"


def test_custom_note_is_kept(conn):
    crud.create_recurring(conn, 499, "wifi", "Jio Fiber", 1, "2026-10", today=TODAY)
    crud.apply_recurring(conn, today=TODAY)
    assert crud.list_expenses(conn)[0][4] == "Jio Fiber"


def test_not_created_before_due_day(conn):
    crud.create_recurring(conn, 500, "gym", "", 25, "2026-10", today=TODAY)
    assert crud.apply_recurring(conn, today=TODAY) == 0
    assert crud.list_expenses(conn) == []
    assert crud.apply_recurring(conn, today=date(2026, 10, 25)) == 1


def test_backfills_from_earlier_start_month(conn):
    crud.create_recurring(conn, 100, "netflix", "", 1, "2026-08", today=TODAY)
    assert crud.apply_recurring(conn, today=TODAY) == 3
    dates = sorted(r[1] for r in crud.list_expenses(conn))
    assert dates == ["2026-08-01", "2026-09-01", "2026-10-01"]


def test_running_twice_does_not_duplicate(conn):
    crud.create_recurring(conn, 100, "netflix", "", 1, "2026-09", today=TODAY)
    assert crud.apply_recurring(conn, today=TODAY) == 2
    assert crud.apply_recurring(conn, today=TODAY) == 0
    assert len(crud.list_expenses(conn)) == 2


def test_new_month_adds_only_the_new_one(conn):
    crud.create_recurring(conn, 100, "netflix", "", 1, "2026-10", today=TODAY)
    crud.apply_recurring(conn, today=TODAY)
    assert crud.apply_recurring(conn, today=date(2026, 11, 3)) == 1
    assert len(crud.list_expenses(conn)) == 2


def test_deleted_expense_is_not_recreated(conn):
    crud.create_recurring(conn, 100, "netflix", "", 1, "2026-10", today=TODAY)
    crud.apply_recurring(conn, today=TODAY)
    crud.delete_expense(conn, crud.list_expenses(conn)[0][0])
    assert crud.apply_recurring(conn, today=TODAY) == 0
    assert crud.list_expenses(conn) == []


def test_day_31_uses_last_day_of_short_month(conn):
    crud.create_recurring(conn, 100, "loan", "", 31, "2027-02", today=date(2027, 2, 28))
    assert crud.apply_recurring(conn, today=date(2027, 2, 28)) == 1
    assert crud.list_expenses(conn)[0][1] == "2027-02-28"


def test_future_start_month_creates_nothing(conn):
    crud.create_recurring(conn, 100, "gym", "", 1, "2026-12", today=TODAY)
    assert crud.apply_recurring(conn, today=TODAY) == 0


def test_stopping_keeps_old_expenses_and_stops_new_ones(conn):
    rid = crud.create_recurring(conn, 100, "gym", "", 1, "2026-10", today=TODAY)
    crud.apply_recurring(conn, today=TODAY)
    assert crud.delete_recurring(conn, rid) is True
    assert crud.delete_recurring(conn, rid) is False
    assert crud.apply_recurring(conn, today=date(2026, 11, 5)) == 0
    assert len(crud.list_expenses(conn)) == 1


def test_validation(conn):
    with pytest.raises(ValueError):
        crud.create_recurring(conn, 0, "x", "", 1, "2026-10", today=TODAY)
    with pytest.raises(ValueError):
        crud.create_recurring(conn, 10, "  ", "", 1, "2026-10", today=TODAY)
    with pytest.raises(ValueError):
        crud.create_recurring(conn, 10, "x", "", 0, "2026-10", today=TODAY)
    with pytest.raises(ValueError):
        crud.create_recurring(conn, 10, "x", "", 32, "2026-10", today=TODAY)
    with pytest.raises(ValueError):
        crud.create_recurring(conn, 10, "x", "", 1, "2001-01", today=TODAY)


# ---------- API ----------
def test_api_create_applies_immediately(client):
    month = date.today().strftime("%Y-%m")
    r = client.post("/recurring", json={"amount": 15000, "category": "rent", "day": 1})
    assert r.status_code == 201
    assert r.json()["start_month"] == month and r.json()["created"] == 1
    expenses = client.get("/expenses").json()
    assert len(expenses) == 1 and expenses[0]["category"] == "rent"
    assert client.post("/recurring/apply").json() == {"created": 0}


def test_api_list_and_stop(client):
    rid = client.post("/recurring", json={"amount": 99, "category": "wifi", "day": 1}).json()["id"]
    assert [r["id"] for r in client.get("/recurring").json()] == [rid]
    assert client.delete(f"/recurring/{rid}").status_code == 200
    assert client.delete(f"/recurring/{rid}").status_code == 404
    assert client.get("/recurring").json() == []
    assert len(client.get("/expenses").json()) == 1


def test_api_validation(client):
    ok = {"amount": 10, "category": "x", "day": 5}
    assert client.post("/recurring", json={**ok, "amount": -1}).status_code == 422
    assert client.post("/recurring", json={**ok, "day": 0}).status_code == 422
    assert client.post("/recurring", json={**ok, "day": 32}).status_code == 422
    assert client.post("/recurring", json={**ok, "category": ""}).status_code == 422
    assert client.post("/recurring", json={**ok, "start_month": "bad"}).status_code == 422
    assert client.post("/recurring", json={**ok, "category": "   "}).status_code == 400
    assert client.post("/recurring", json={**ok, "start_month": "2001-01"}).status_code == 400