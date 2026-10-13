import argparse
import sqlite3
from datetime import date

DB = "expenses.db"

def get_conn():
    conn = sqlite3.connect(DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            note TEXT,
            date TEXT NOT NULL
        )
    """)
    return conn

def add_expense(args):
    if args.amount <= 0:
        print("Amount must be greater than 0")
        return
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO expenses (amount, category, note, date) VALUES (?, ?, ?, ?)",
            (args.amount, args.category, args.note, args.date or str(date.today())),
        )
    print("Expense added.")

def list_expenses(args):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, date, category, amount, note FROM expenses ORDER BY date DESC"
        ).fetchall()
    for r in rows:
        print(f"[{r[0]}] {r[1]} | {r[2]:<12} | {r[3]:>9.2f} | {r[4] or ''}")
    if not rows:
        print("No expenses yet.")

def summary(args):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT category, SUM(amount) FROM expenses GROUP BY category ORDER BY 2 DESC"
        ).fetchall()
    total = sum(r[1] for r in rows)
    for cat, amt in rows:
        print(f"{cat:<12} {amt:>9.2f}")
    print(f"{'TOTAL':<12} {total:>9.2f}")

def delete_expense(args):
    with get_conn() as conn:
        conn.execute("DELETE FROM expenses WHERE id = ?", (args.id,))
    print("Deleted.")

def main():
    parser = argparse.ArgumentParser(description="Expense Tracker")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("add")
    p.add_argument("amount", type=float)
    p.add_argument("category")
    p.add_argument("--note", default="")
    p.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p.set_defaults(func=add_expense)

    sub.add_parser("list").set_defaults(func=list_expenses)
    sub.add_parser("summary").set_defaults(func=summary)

    p = sub.add_parser("delete")
    p.add_argument("id", type=int)
    p.set_defaults(func=delete_expense)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()