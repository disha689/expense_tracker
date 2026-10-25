"""Copies everything from your local expenses.db into the online PostgreSQL database.

Run once:   python migrate_to_postgres.py
It asks you to paste the database connection string (typing is hidden).
It refuses to run if the online database already has data, so it can never create duplicates."""
import getpass
import os
import sqlite3
import sys

from app.database import (
    DB_PATH,
    connect_postgres,
    database_url,
    ensure_postgres_schema,
    is_postgres_url,
)

TABLES = [  # copied in this order
    ("expenses", ["id", "amount", "category", "note", "date"]),
    ("budgets", ["month", "amount"]),
    ("category_budgets", ["month", "category", "amount"]),
    ("recurring", ["id", "amount", "category", "note", "day", "start_month"]),
    ("recurring_log", ["recurring_id", "month"]),
]


class MigrationError(Exception):
    pass


def migrate(sqlite_path, pg_url):
    if not os.path.exists(sqlite_path):
        raise MigrationError(f"Could not find {sqlite_path}. Run this from the expense_tracker folder.")
    source = sqlite3.connect(sqlite_path)
    target = connect_postgres(pg_url)
    try:
        ensure_postgres_schema(target)
        for name, _ in TABLES:
            count = target.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            if count:
                raise MigrationError(
                    f"The online database already has data ('{name}' has {count} rows). Nothing was copied."
                )
        counts = {}
        for name, columns in TABLES:
            try:
                rows = source.execute(f"SELECT {', '.join(columns)} FROM {name}").fetchall()
            except sqlite3.OperationalError:
                rows = []  # an older file may not have this table yet
            marks = ", ".join("?" for _ in columns)
            for row in rows:
                target.execute(f"INSERT INTO {name} ({', '.join(columns)}) VALUES ({marks})", row)
            counts[name] = len(rows)
        for name in ("expenses", "recurring"):  # new rows must continue after the copied ids
            target.execute(
                f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {name}), 1), "
                f"(SELECT MAX(id) FROM {name}) IS NOT NULL)"
            )
        target.commit()  # all or nothing
        return counts
    except Exception:
        target.rollback()
        raise
    finally:
        source.close()
        target.close()


def main():
    url = database_url() or getpass.getpass("Paste the PostgreSQL connection string (hidden): ").strip()
    if not is_postgres_url(url):
        print("That does not look right. It should start with postgresql://")
        return 1
    path = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    try:
        counts = migrate(path, url)
    except MigrationError as e:
        print(e)
        return 1
    print("Done. Copied:")
    for name, count in counts.items():
        print(f"  {name}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
