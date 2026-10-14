import pytest

from app.database import get_conn
from app import crud


@pytest.fixture
def conn():
    c = get_conn(":memory:")
    yield c
    c.close()


def test_add_and_list(conn):
    crud.add_expense(conn, 250, "food", "lunch", "2026-10-14")
    rows = crud.list_expenses(conn)
    assert len(rows) == 1
    assert rows[0][2] == "food"
    assert rows[0][3] == 250


def test_add_rejects_non_positive_amount(conn):
    with pytest.raises(ValueError):
        crud.add_expense(conn, 0, "food")
    with pytest.raises(ValueError):
        crud.add_expense(conn, -5, "food")


def test_month_filter(conn):
    crud.add_expense(conn, 100, "food", date_str="2026-10-01")
    crud.add_expense(conn, 200, "travel", date_str="2026-09-20")
    assert len(crud.list_expenses(conn, "2026-10")) == 1
    assert len(crud.list_expenses(conn, "2026-09")) == 1
    assert len(crud.list_expenses(conn, "2026-08")) == 0


def test_summary_totals_by_category(conn):
    crud.add_expense(conn, 100, "food", date_str="2026-10-01")
    crud.add_expense(conn, 50, "food", date_str="2026-10-02")
    crud.add_expense(conn, 300, "travel", date_str="2026-10-03")
    result = dict(crud.summary(conn))
    assert result == {"food": 150, "travel": 300}


def test_edit_updates_fields(conn):
    eid = crud.add_expense(conn, 100, "food", "lunch", "2026-10-01")
    assert crud.edit_expense(conn, eid, amount=300, note="dinner") is True
    row = crud.list_expenses(conn)[0]
    assert row[3] == 300
    assert row[4] == "dinner"


def test_edit_missing_id_returns_false(conn):
    assert crud.edit_expense(conn, 999, amount=10) is False


def test_edit_with_no_fields_raises(conn):
    eid = crud.add_expense(conn, 100, "food")
    with pytest.raises(ValueError):
        crud.edit_expense(conn, eid)


def test_delete(conn):
    eid = crud.add_expense(conn, 100, "food")
    assert crud.delete_expense(conn, eid) is True
    assert crud.delete_expense(conn, eid) is False
    assert crud.list_expenses(conn) == []