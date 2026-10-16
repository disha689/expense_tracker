import pytest

from app.database import get_conn
from app import crud


@pytest.fixture
def conn():
    c = get_conn(":memory:")
    yield c
    c.close()


def test_no_budget_is_zero(conn):
    assert crud.get_budget(conn, "2026-10") == 0


def test_set_and_get_budget(conn):
    crud.set_budget(conn, "2026-10", 20000)
    assert crud.get_budget(conn, "2026-10") == 20000


def test_set_budget_overwrites_same_month(conn):
    crud.set_budget(conn, "2026-10", 20000)
    crud.set_budget(conn, "2026-10", 25000)
    assert crud.get_budget(conn, "2026-10") == 25000


def test_budget_carries_forward_to_later_months(conn):
    crud.set_budget(conn, "2026-09", 15000)
    assert crud.get_budget(conn, "2026-10") == 15000
    assert crud.get_budget(conn, "2026-08") == 0


def test_negative_budget_rejected(conn):
    with pytest.raises(ValueError):
        crud.set_budget(conn, "2026-10", -1)