import argparse
import sqlite3
from datetime import date, datetime

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


# ---------- Validation ----------
def valid_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date '{s}'. Use YYYY-MM-DD (e.g. 2026-10-14)")


def valid_month(s):
    try:
        return datetime.strptime(s, "%Y-%m").strftime("%Y-%m")
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid month '{s}'. Use YYYY-MM (e.g. 2026-10)")


# ---------- Commands ----------
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
    query = "SELECT id, date, category, amount, note FROM expenses"
    params = []
    if args.month:
        query += " WHERE strftime('%Y-%m', date) = ?"
        params.append(args.month)
    query += " ORDER BY date DESC"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        print("No expenses found.")
        return
    for r in rows:
        print(f"[{r[0]}] {r[1]} | {r[2]:<12} | {r[3]:>9.2f} | {r[4] or ''}")


def summary(args):
    query = "SELECT category, SUM(amount) FROM expenses"
    params = []
    if args.month:
        query += " WHERE strftime('%Y-%m', date) = ?"
        params.append(args.month)
    query += " GROUP BY category ORDER BY 2 DESC"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        print("No expenses found.")
        return
    total = sum(r[1] for r in rows)
    for cat, amt in rows:
        print(f"{cat:<12} {amt:>9.2f}")
    print(f"{'TOTAL':<12} {total:>9.2f}")


def edit_expense(args):
    fields = {}
    if args.amount is not None:
        if args.amount <= 0:
            print("Amount must be greater than 0")
            return
        fields["amount"] = args.amount
    if args.category is not None:
        fields["category"] = args.category
    if args.note is not None:
        fields["note"] = args.note
    if args.date is not None:
        fields["date"] = args.date

    if not fields:
        print("Nothing to update. Use --amount, --category, --note or --date")
        return

    set_clause = ", ".join(f"{col} = ?" for col in fields)
    values = list(fields.values()) + [args.id]

    with get_conn() as conn:
        cur = conn.execute(f"UPDATE expenses SET {set_clause} WHERE id = ?", values)
    if cur.rowcount == 0:
        print(f"No expense found with id {args.id}")
    else:
        print("Expense updated.")


def delete_expense(args):
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM expenses WHERE id = ?", (args.id,))
    if cur.rowcount == 0:
        print(f"No expense found with id {args.id}")
    else:
        print("Deleted.")


# ---------- CLI ----------
def main():
    parser = argparse.ArgumentParser(description="Expense Tracker")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("add", help="Add an expense")
    p.add_argument("amount", type=float)
    p.add_argument("category")
    p.add_argument("--note", default="")
    p.add_argument("--date", type=valid_date, help="YYYY-MM-DD (default: today)")
    p.set_defaults(func=add_expense)

    p = sub.add_parser("list", help="List expenses")
    p.add_argument("--month", type=valid_month, help="Filter by month, YYYY-MM")
    p.set_defaults(func=list_expenses)

    p = sub.add_parser("summary", help="Totals by category")
    p.add_argument("--month", type=valid_month, help="Filter by month, YYYY-MM")
    p.set_defaults(func=summary)

    p = sub.add_parser("edit", help="Edit an expense")
    p.add_argument("id", type=int)
    p.add_argument("--amount", type=float)
    p.add_argument("--category")
    p.add_argument("--note")
    p.add_argument("--date", type=valid_date)
    p.set_defaults(func=edit_expense)

    p = sub.add_parser("delete", help="Delete an expense")
    p.add_argument("id", type=int)
    p.set_defaults(func=delete_expense)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()