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


# ---------- crud ----------
def test_no_category_budgets(conn):
    assert crud.get_category_budgets(conn, "2026-10") == []


def test_set_and_get_normalizes_category(conn):
    crud.set_category_budget(conn, "2026-10", "  Food ", 5000)
    assert crud.get_category_budgets(conn, "2026-10") == [("food", 5000)]


def test_overwrite_same_month(conn):
    crud.set_category_budget(conn, "2026-10", "food", 5000)
    crud.set_category_budget(conn, "2026-10", "FOOD", 6000)
    assert crud.get_category_budgets(conn, "2026-10") == [("food", 6000)]


def test_categories_carry_forward_independently(conn):
    crud.set_category_budget(conn, "2026-09", "food", 5000)
    crud.set_category_budget(conn, "2026-10", "travel", 3000)
    assert crud.get_category_budgets(conn, "2026-10") == [("food", 5000), ("travel", 3000)]
    assert crud.get_category_budgets(conn, "2026-09") == [("food", 5000)]
    assert crud.get_category_budgets(conn, "2026-08") == []


def test_changing_a_later_month_keeps_earlier_months(conn):
    crud.set_category_budget(conn, "2026-09", "food", 5000)
    crud.set_category_budget(conn, "2026-10", "food", 7000)
    assert crud.get_category_budgets(conn, "2026-09") == [("food", 5000)]
    assert crud.get_category_budgets(conn, "2026-11") == [("food", 7000)]


def test_zero_removes_from_that_month_onward(conn):
    crud.set_category_budget(conn, "2026-09", "food", 5000)
    crud.set_category_budget(conn, "2026-10", "food", 0)
    assert crud.get_category_budgets(conn, "2026-10") == []
    assert crud.get_category_budgets(conn, "2026-09") == [("food", 5000)]


def test_invalid_values_rejected(conn):
    with pytest.raises(ValueError):
        crud.set_category_budget(conn, "2026-10", "food", -1)
    with pytest.raises(ValueError):
        crud.set_category_budget(conn, "2026-10", "   ", 100)


# ---------- API ----------
def test_api_roundtrip_sorted(client):
    client.put("/category-budgets", json={"month": "2026-10", "category": "travel", "amount": 3000})
    r = client.put("/category-budgets", json={"month": "2026-10", "category": "Food", "amount": 5000})
    assert r.status_code == 200
    assert r.json()["budgets"] == [
        {"category": "food", "amount": 5000},
        {"category": "travel", "amount": 3000},
    ]
    got = client.get("/category-budgets?month=2026-10").json()
    assert [b["category"] for b in got["budgets"]] == ["food", "travel"]


def test_api_carry_forward_and_remove(client):
    client.put("/category-budgets", json={"month": "2026-09", "category": "food", "amount": 5000})
    assert client.get("/category-budgets?month=2026-10").json()["budgets"] == [
        {"category": "food", "amount": 5000}
    ]
    client.put("/category-budgets", json={"month": "2026-10", "category": "food", "amount": 0})
    assert client.get("/category-budgets?month=2026-10").json()["budgets"] == []


def test_api_validation(client):
    ok = {"month": "2026-10", "category": "food", "amount": 100}
    assert client.put("/category-budgets", json={**ok, "month": "bad"}).status_code == 422
    assert client.put("/category-budgets", json={**ok, "amount": -5}).status_code == 422
    assert client.put("/category-budgets", json={**ok, "category": ""}).status_code == 422
    assert client.put("/category-budgets", json={**ok, "category": "   "}).status_code == 400
    assert client.get("/category-budgets").status_code == 422


def test_overall_budget_is_separate(client):
    client.put("/budget", json={"month": "2026-10", "amount": 20000})
    client.put("/category-budgets", json={"month": "2026-10", "category": "food", "amount": 5000})
    assert client.get("/budget?month=2026-10").json()["amount"] == 20000
    assert len(client.get("/category-budgets?month=2026-10").json()["budgets"]) == 1