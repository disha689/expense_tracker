import pytest
from fastapi.testclient import TestClient

from app.database import get_conn
from app.main import app, get_db


@pytest.fixture
def client():
    conn = get_conn(":memory:")

    def override():
        yield conn

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()
    conn.close()


def add(client, **kw):
    body = {"amount": 100, "category": "food", "date": "2026-10-05", **kw}
    r = client.post("/expenses", json=body)
    assert r.status_code == 201
    return r.json()


def test_home_page_loads(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_create_and_list(client):
    created = add(client, amount=250, note="lunch")
    assert created["category"] == "food"
    rows = client.get("/expenses").json()
    assert len(rows) == 1 and rows[0]["amount"] == 250


def test_create_rejects_bad_data(client):
    assert client.post("/expenses", json={"amount": -5, "category": "food"}).status_code == 422
    assert client.post("/expenses", json={"amount": 5, "category": ""}).status_code == 422
    assert client.post("/expenses", json={"amount": 5, "category": "x", "date": "2026-13-45"}).status_code == 422


def test_month_filter_and_bad_month(client):
    add(client, date="2026-10-01")
    add(client, date="2026-09-20")
    assert len(client.get("/expenses?month=2026-10").json()) == 1
    assert client.get("/expenses?month=2026-13").status_code == 422


def test_summary(client):
    add(client, amount=100, category="food")
    add(client, amount=50, category="food")
    add(client, amount=300, category="travel")
    data = client.get("/summary?month=2026-10").json()
    assert data["total"] == 450
    assert {c["category"]: c["total"] for c in data["by_category"]} == {"food": 150, "travel": 300}


def test_update_expense(client):
    eid = add(client)["id"]
    r = client.put(f"/expenses/{eid}", json={"amount": 300, "note": "dinner"})
    assert r.status_code == 200
    assert r.json()["amount"] == 300 and r.json()["note"] == "dinner"


def test_update_changes_date_and_category(client):
    eid = add(client)["id"]
    r = client.put(f"/expenses/{eid}", json={"category": "travel", "date": "2026-09-01"})
    assert r.json()["category"] == "travel" and r.json()["date"] == "2026-09-01"


def test_update_missing_and_empty(client):
    assert client.put("/expenses/999", json={"amount": 5}).status_code == 404
    eid = add(client)["id"]
    assert client.put(f"/expenses/{eid}", json={}).status_code == 400
    assert client.put(f"/expenses/{eid}", json={"amount": -1}).status_code == 422


def test_delete(client):
    eid = add(client)["id"]
    assert client.delete(f"/expenses/{eid}").status_code == 200
    assert client.delete(f"/expenses/{eid}").status_code == 404


def test_budget_roundtrip_and_carry_forward(client):
    assert client.get("/budget?month=2026-10").json()["amount"] == 0
    assert client.put("/budget", json={"month": "2026-09", "amount": 15000}).status_code == 200
    assert client.get("/budget?month=2026-10").json()["amount"] == 15000
    client.put("/budget", json={"month": "2026-10", "amount": 20000})
    assert client.get("/budget?month=2026-10").json()["amount"] == 20000
    assert client.get("/budget?month=2026-09").json()["amount"] == 15000


def test_budget_validation(client):
    assert client.put("/budget", json={"month": "2026-10", "amount": -5}).status_code == 422
    assert client.put("/budget", json={"month": "bad", "amount": 5}).status_code == 422
    assert client.get("/budget").status_code == 422


def test_export_csv(client):
    add(client, amount=250, category="food", note="lunch", date="2026-10-14")
    r = client.get("/export.csv?month=2026-10")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    lines = r.text.lstrip("\ufeff").strip().splitlines()
    assert lines[0] == "date,category,amount,note"
    assert lines[1] == "2026-10-14,food,250.0,lunch"


def test_export_blocks_formula_injection(client):
    add(client, category="=cmd", note="+evil")
    text = client.get("/export.csv").text
    assert "'=cmd" in text and "'+evil" in text


def test_import_valid_csv(client):
    csv_text = "date,category,amount,note\n2026-10-01,food,120.5,tea\n2026-10-02,travel,\"1,200\",bus\n"
    r = client.post("/import", content=csv_text, headers={"Content-Type": "text/csv"})
    assert r.status_code == 200
    assert r.json()["imported"] == 2 and r.json()["skipped_count"] == 0
    assert len(client.get("/expenses").json()) == 2
    assert client.get("/summary").json()["total"] == 1320.5


def test_import_skips_bad_rows(client):
    csv_text = (
        "date,category,amount,note\n"
        "2026-10-01,food,100,ok\n"
        "2026-13-45,food,100,bad date\n"
        "2026-10-03,food,abc,bad amount\n"
        "2026-10-04,food,-5,negative\n"
        "2026-10-05,,50,no category\n"
        "2026-10-06,food,nan,nan amount\n"
    )
    r = client.post("/import", content=csv_text).json()
    assert r["imported"] == 1 and r["skipped_count"] == 5
    assert len(client.get("/expenses").json()) == 1


def test_import_missing_columns_and_bad_file(client):
    assert client.post("/import", content="foo,bar\n1,2\n").status_code == 400
    assert client.post("/import", content=b"\xff\xfe\x00bad").status_code == 400
    assert client.post("/import", content="").status_code == 400


def test_import_without_date_uses_today(client):
    r = client.post("/import", content="amount,category\n80,snacks\n").json()
    assert r["imported"] == 1
    assert len(client.get("/expenses").json()) == 1


def test_export_then_import_roundtrip(client):
    add(client, category="=weird", note="@note", amount=77, date="2026-10-10")
    exported = client.get("/export.csv").content
    client.delete("/expenses/1")
    assert client.post("/import", content=exported).json()["imported"] == 1
    row = client.get("/expenses").json()[0]
    assert row["category"] == "=weird" and row["note"] == "@note" and row["amount"] == 77