import pytest


@pytest.fixture(autouse=True)
def _login_off_for_tests(monkeypatch):
    """Normal tests run without the login check. test_auth.py switches it back on."""
    monkeypatch.setenv("AUTH_DISABLED", "1")
