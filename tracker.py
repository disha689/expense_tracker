import argparse
from datetime import datetime

from app.database import get_conn
from app import crud


def valid_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date '{s}'. Use YYYY-MM-DD")


def valid_month(s):
    try:
        return datetime.strptime(s, "%Y-%m").strftime("%Y-%m")
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid month '{s}'. Use YYYY-MM")


def cmd_add(conn, args):
    crud.add_expense(conn, args.amount, args.category, args.note, args.date)
    print("Expense added.")


def cmd_list(conn, args):
    rows = crud.list_expenses(conn, args.month)
    if not rows:
        print("No expenses found.")
        return
    for r in rows:
        print(f"[{r[0]}] {r[1]} | {r[2]:<12} | {r[3]:>9.2f} | {r[4] or ''}")


def cmd_summary(conn, args):
    rows = crud.summary(conn, args.month)
    if not rows:
        print("No expenses found.")
        return
    for cat, amt in rows:
        print(f"{cat:<12} {amt:>9.2f}")
    print(f"{'TOTAL':<12} {sum(r[1] for r in rows):>9.2f}")


def cmd_edit(conn, args):
    ok = crud.edit_expense(conn, args.id, args.amount, args.category, args.note, args.date)
    print("Expense updated." if ok else f"No expense found with id {args.id}")


def cmd_delete(conn, args):
    ok = crud.delete_expense(conn, args.id)
    print("Deleted." if ok else f"No expense found with id {args.id}")


def main():
    parser = argparse.ArgumentParser(description="Expense Tracker")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("add")
    p.add_argument("amount", type=float)
    p.add_argument("category")
    p.add_argument("--note", default="")
    p.add_argument("--date", type=valid_date)
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list")
    p.add_argument("--month", type=valid_month)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("summary")
    p.add_argument("--month", type=valid_month)
    p.set_defaults(func=cmd_summary)

    p = sub.add_parser("edit")
    p.add_argument("id", type=int)
    p.add_argument("--amount", type=float)
    p.add_argument("--category")
    p.add_argument("--note")
    p.add_argument("--date", type=valid_date)
    p.set_defaults(func=cmd_edit)

    p = sub.add_parser("delete")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_delete)

    args = parser.parse_args()
    conn = get_conn()
    try:
        args.func(conn, args)
    except ValueError as e:
        print(f"Error: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()