import os
import sqlite3
import time

from app.auth import load_env

load_env()  # lets a DATABASE_URL written in the .env file work for every script

DB_PATH = "expenses.db"
TABLES = ("recurring_log", "recurring", "category_budgets", "budgets", "expenses")

SQLITE_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        amount REAL NOT NULL,
        category TEXT NOT NULL,
        note TEXT,
        date TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses (date)",
    "CREATE TABLE IF NOT EXISTS budgets (month TEXT PRIMARY KEY, amount REAL NOT NULL)",
    """CREATE TABLE IF NOT EXISTS category_budgets (
        month TEXT NOT NULL,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        PRIMARY KEY (month, category)
    )""",
    """CREATE TABLE IF NOT EXISTS recurring (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        amount REAL NOT NULL,
        category TEXT NOT NULL,
        note TEXT,
        day INTEGER NOT NULL,
        start_month TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS recurring_log (
        recurring_id INTEGER NOT NULL,
        month TEXT NOT NULL,
        PRIMARY KEY (recurring_id, month)
    )""",
]

POSTGRES_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS expenses (
        id BIGSERIAL PRIMARY KEY,
        amount DOUBLE PRECISION NOT NULL,
        category TEXT NOT NULL,
        note TEXT,
        date TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses (date)",
    "CREATE TABLE IF NOT EXISTS budgets (month TEXT PRIMARY KEY, amount DOUBLE PRECISION NOT NULL)",
    """CREATE TABLE IF NOT EXISTS category_budgets (
        month TEXT NOT NULL,
        category TEXT NOT NULL,
        amount DOUBLE PRECISION NOT NULL,
        PRIMARY KEY (month, category)
    )""",
    """CREATE TABLE IF NOT EXISTS recurring (
        id BIGSERIAL PRIMARY KEY,
        amount DOUBLE PRECISION NOT NULL,
        category TEXT NOT NULL,
        note TEXT,
        day INTEGER NOT NULL,
        start_month TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS recurring_log (
        recurring_id BIGINT NOT NULL,
        month TEXT NOT NULL,
        PRIMARY KEY (recurring_id, month)
    )""",
]

_pg_ready = set()  # connection strings whose tables were already checked in this run


def database_url():
    return os.environ.get("DATABASE_URL", "").strip()


def is_postgres_url(url):
    return url.startswith(("postgres://", "postgresql://"))


class PgConn:
    """Makes a PostgreSQL connection behave like the sqlite3 one the rest of the code expects:
    '?' placeholders, 'with conn:' = one transaction (commit or rollback, connection stays open)."""

    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, params=()):
        return self.raw.execute(sql.replace("%", "%%").replace("?", "%s"), params)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.raw.commit()
        else:
            self.raw.rollback()
        return False


def connect_postgres(url):
    import psycopg  # only needed when PostgreSQL is really used

    last_error = None
    for attempt in range(3):  # a sleeping free database may need a moment to wake up
        try:
            # prepare_threshold=None: works with poolers too, and our queries are tiny anyway
            return PgConn(psycopg.connect(url, connect_timeout=15, prepare_threshold=None))
        except psycopg.OperationalError as e:
            last_error = e
            time.sleep(1.5)
    raise last_error


def ensure_postgres_schema(conn, url=None):
    if url is not None and url in _pg_ready:
        return
    for statement in POSTGRES_SCHEMA:
        conn.execute(statement)
    conn.commit()
    if url is not None:
        _pg_ready.add(url)


def _reset_postgres(conn):
    conn.execute("DROP TABLE IF EXISTS " + ", ".join(TABLES))
    ensure_postgres_schema(conn)


def get_conn(db_path=None):
    # Tests ask for ":memory:". If TEST_DATABASE_URL is set they get a clean PostgreSQL instead.
    test_url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if db_path == ":memory:" and test_url:
        conn = connect_postgres(test_url)
        _reset_postgres(conn)
        return conn

    url = database_url()
    if db_path is None and url:
        if not is_postgres_url(url):
            raise RuntimeError("DATABASE_URL must start with postgresql:// (check the value you pasted).")
        conn = connect_postgres(url)
        ensure_postgres_schema(conn, url)
        return conn

    conn = sqlite3.connect(db_path or DB_PATH, check_same_thread=False)
    for statement in SQLITE_SCHEMA:
        conn.execute(statement)
    return conn
