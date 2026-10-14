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