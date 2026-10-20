import calendar
from datetime import date


def add_expense(conn, amount, category, note="", date_str=None):
    if amount <= 0:
        raise ValueError("Amount must be greater than 0")
    with conn:
        cur = conn.execute(
            "INSERT INTO expenses (amount, category, note, date) VALUES (?, ?, ?, ?)",
            (amount, category, note, date_str or str(date.today())),
        )
    return cur.lastrowid


def list_expenses(conn, month=None):
    query = "SELECT id, date, category, amount, note FROM expenses"
    params = []
    if month:
        query += " WHERE strftime('%Y-%m', date) = ?"
        params.append(month)
    query += " ORDER BY date DESC, id DESC"
    return conn.execute(query, params).fetchall()


def summary(conn, month=None):
    query = "SELECT category, SUM(amount) FROM expenses"
    params = []
    if month:
        query += " WHERE strftime('%Y-%m', date) = ?"
        params.append(month)
    query += " GROUP BY category ORDER BY 2 DESC"
    return conn.execute(query, params).fetchall()


def edit_expense(conn, expense_id, amount=None, category=None, note=None, date_str=None):
    fields = {}
    if amount is not None:
        if amount <= 0:
            raise ValueError("Amount must be greater than 0")
        fields["amount"] = amount
    if category is not None:
        fields["category"] = category
    if note is not None:
        fields["note"] = note
    if date_str is not None:
        fields["date"] = date_str
    if not fields:
        raise ValueError("Nothing to update")

    set_clause = ", ".join(f"{col} = ?" for col in fields)
    values = list(fields.values()) + [expense_id]
    with conn:
        cur = conn.execute(f"UPDATE expenses SET {set_clause} WHERE id = ?", values)
    return cur.rowcount > 0


def delete_expense(conn, expense_id):
    with conn:
        cur = conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    return cur.rowcount > 0


def get_expense(conn, expense_id):
    return conn.execute(
        "SELECT id, date, category, amount, note FROM expenses WHERE id = ?",
        (expense_id,),
    ).fetchone()


def set_budget(conn, month, amount):
    if amount < 0:
        raise ValueError("Budget cannot be negative")
    with conn:
        conn.execute(
            "INSERT INTO budgets (month, amount) VALUES (?, ?) "
            "ON CONFLICT(month) DO UPDATE SET amount = excluded.amount",
            (month, amount),
        )


def get_budget(conn, month):
    """Budget for a month. If none is set, the latest earlier month's budget carries forward."""
    row = conn.execute(
        "SELECT amount FROM budgets WHERE month <= ? ORDER BY month DESC LIMIT 1",
        (month,),
    ).fetchone()
    return row[0] if row else 0


def set_category_budget(conn, month, category, amount):
    """Set a budget for one category from this month onward. Amount 0 removes it."""
    category = (category or "").strip().lower()
    if not category:
        raise ValueError("Category is required")
    if amount < 0:
        raise ValueError("Budget cannot be negative")
    with conn:
        conn.execute(
            "INSERT INTO category_budgets (month, category, amount) VALUES (?, ?, ?) "
            "ON CONFLICT(month, category) DO UPDATE SET amount = excluded.amount",
            (month, category, amount),
        )


def get_category_budgets(conn, month):
    """Each category's latest budget set on or before this month (carries forward). Zero = removed."""
    rows = conn.execute(
        "SELECT category, amount FROM category_budgets cb "
        "WHERE month = (SELECT MAX(month) FROM category_budgets "
        "               WHERE category = cb.category AND month <= ?) "
        "ORDER BY category",
        (month,),
    ).fetchall()
    return [(cat, amt) for cat, amt in rows if amt > 0]


# ---------- Recurring expenses ----------
MAX_BACKFILL_MONTHS = 120


def _month_range(start_month, end_month):
    """Yield (year, month) from start_month to end_month inclusive. Months are 'YYYY-MM'."""
    y, m = map(int, start_month.split("-"))
    end_y, end_m = map(int, end_month.split("-"))
    while (y, m) <= (end_y, end_m):
        yield y, m
        m += 1
        if m > 12:
            y, m = y + 1, 1


def create_recurring(conn, amount, category, note, day, start_month, today=None):
    today = today or date.today()
    category = (category or "").strip()
    if amount <= 0:
        raise ValueError("Amount must be greater than 0")
    if not category:
        raise ValueError("Category is required")
    if not 1 <= day <= 31:
        raise ValueError("Day must be between 1 and 31")
    if len(list(_month_range(start_month, today.strftime("%Y-%m")))) > MAX_BACKFILL_MONTHS:
        raise ValueError("Start month is too far back (max 10 years)")
    with conn:
        cur = conn.execute(
            "INSERT INTO recurring (amount, category, note, day, start_month) VALUES (?, ?, ?, ?, ?)",
            (amount, category, note or "", day, start_month),
        )
    return cur.lastrowid


def list_recurring(conn):
    return conn.execute(
        "SELECT id, amount, category, note, day, start_month FROM recurring ORDER BY id"
    ).fetchall()


def get_recurring(conn, recurring_id):
    return conn.execute(
        "SELECT id, amount, category, note, day, start_month FROM recurring WHERE id = ?",
        (recurring_id,),
    ).fetchone()


def delete_recurring(conn, recurring_id):
    """Stops the rule. Expenses it already created are kept."""
    with conn:
        conn.execute("DELETE FROM recurring_log WHERE recurring_id = ?", (recurring_id,))
        cur = conn.execute("DELETE FROM recurring WHERE id = ?", (recurring_id,))
    return cur.rowcount > 0


def apply_recurring(conn, today=None):
    """Add every recurring expense that is due and not added yet. Safe to run many times."""
    today = today or date.today()
    this_month = today.strftime("%Y-%m")
    created = 0
    for rid, amount, category, note, day, start_month in list_recurring(conn):
        for y, m in _month_range(start_month, this_month):
            month = f"{y:04d}-{m:02d}"
            due = date(y, m, min(day, calendar.monthrange(y, m)[1]))
            if due > today:
                continue
            already = conn.execute(
                "SELECT 1 FROM recurring_log WHERE recurring_id = ? AND month = ?", (rid, month)
            ).fetchone()
            if already:
                continue
            with conn:
                conn.execute(
                    "INSERT INTO expenses (amount, category, note, date) VALUES (?, ?, ?, ?)",
                    (amount, category, note or "Recurring", due.isoformat()),
                )
                conn.execute(
                    "INSERT INTO recurring_log (recurring_id, month) VALUES (?, ?)", (rid, month)
                )
            created += 1
    return created