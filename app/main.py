import csv
import io
import math
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app import crud
from app.database import get_conn
from app.schemas import (
    MONTH_PATTERN,
    BudgetIn,
    BudgetOut,
    ExpenseCreate,
    ExpenseOut,
    ExpenseUpdate,
)

app = FastAPI(title="Expense Tracker API")

STATIC_DIR = Path(__file__).parent / "static"
INDEX = STATIC_DIR / "index.html"

MAX_IMPORT_BYTES = 1_000_000
MAX_IMPORT_ROWS = 5000
FORMULA_CHARS = ("=", "+", "-", "@")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def get_db():
    conn = get_conn()
    try:
        yield conn
    finally:
        conn.close()


def row_to_dict(r):
    return {"id": r[0], "date": r[1], "category": r[2], "amount": r[3], "note": r[4]}


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(INDEX)


# ---------- Expenses ----------
@app.post("/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(payload: ExpenseCreate, conn=Depends(get_db)):
    new_id = crud.add_expense(
        conn,
        payload.amount,
        payload.category,
        payload.note,
        str(payload.date) if payload.date else None,
    )
    return row_to_dict(crud.get_expense(conn, new_id))


@app.get("/expenses", response_model=list[ExpenseOut])
def read_expenses(
    month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
    conn=Depends(get_db),
):
    return [row_to_dict(r) for r in crud.list_expenses(conn, month)]


@app.get("/summary")
def read_summary(
    month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
    conn=Depends(get_db),
):
    rows = crud.summary(conn, month)
    return {
        "month": month,
        "total": sum(r[1] for r in rows),
        "by_category": [{"category": r[0], "total": r[1]} for r in rows],
    }


@app.put("/expenses/{expense_id}", response_model=ExpenseOut)
def update_expense(expense_id: int, payload: ExpenseUpdate, conn=Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    try:
        ok = crud.edit_expense(
            conn,
            expense_id,
            amount=data.get("amount"),
            category=data.get("category"),
            note=data.get("note"),
            date_str=str(data["date"]) if data.get("date") else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="Expense not found")
    return row_to_dict(crud.get_expense(conn, expense_id))


@app.delete("/expenses/{expense_id}")
def remove_expense(expense_id: int, conn=Depends(get_db)):
    if not crud.delete_expense(conn, expense_id):
        raise HTTPException(status_code=404, detail="Expense not found")
    return {"detail": "Deleted"}


# ---------- Budget (saved per month) ----------
@app.get("/budget", response_model=BudgetOut)
def read_budget(month: str = Query(pattern=MONTH_PATTERN), conn=Depends(get_db)):
    return {"month": month, "amount": crud.get_budget(conn, month)}


@app.put("/budget", response_model=BudgetOut)
def save_budget(payload: BudgetIn, conn=Depends(get_db)):
    try:
        crud.set_budget(conn, payload.month, payload.amount)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"month": payload.month, "amount": payload.amount}


# ---------- CSV export / import ----------
def safe_cell(value):
    """Stop Excel from running text like '=SUM(...)' as a formula."""
    value = "" if value is None else str(value)
    return "'" + value if value.startswith(FORMULA_CHARS) else value


def unsafe_cell(value):
    value = (value or "").strip()
    if len(value) > 1 and value[0] == "'" and value[1] in "=+-@":
        return value[1:]
    return value


@app.get("/export.csv")
def export_csv(
    month: Optional[str] = Query(default=None, pattern=MONTH_PATTERN),
    conn=Depends(get_db),
):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["date", "category", "amount", "note"])
    for r in crud.list_expenses(conn, month):
        writer.writerow([r[1], safe_cell(r[2]), r[3], safe_cell(r[4])])
    filename = f"expenses-{month or 'all'}.csv"
    return Response(
        "\ufeff" + out.getvalue(),  # BOM so Excel shows symbols like the rupee sign correctly
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/import")
async def import_csv(request: Request, conn=Depends(get_db)):
    raw = await request.body()
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 1 MB)")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be a UTF-8 CSV")

    reader = csv.DictReader(io.StringIO(text))
    columns = {c.strip().lower() for c in (reader.fieldnames or []) if c}
    if not {"amount", "category"} <= columns:
        raise HTTPException(
            status_code=400, detail="CSV needs at least 'amount' and 'category' columns"
        )

    imported, skipped = 0, []
    for line_no, row in enumerate(reader, start=2):
        if line_no - 1 > MAX_IMPORT_ROWS:
            skipped.append({"row": line_no, "reason": f"Row limit ({MAX_IMPORT_ROWS}) reached"})
            break
        r = {(k or "").strip().lower(): v for k, v in row.items() if k}
        try:
            amount = float((r.get("amount") or "").replace(",", "").strip())
            if not math.isfinite(amount):
                raise ValueError("Invalid amount")
            category = unsafe_cell(r.get("category"))
            if not category or len(category) > 100:
                raise ValueError("Category is missing or too long")
            note = unsafe_cell(r.get("note"))[:500]
            date_str = (r.get("date") or "").strip() or None
            if date_str:
                datetime.strptime(date_str, "%Y-%m-%d")
            crud.add_expense(conn, amount, category, note, date_str)
            imported += 1
        except ValueError as e:
            reason = str(e)
            if reason.startswith("could not convert") or reason.startswith("time data"):
                reason = "Invalid amount" if "float" in reason else "Date must be YYYY-MM-DD"
            skipped.append({"row": line_no, "reason": reason})

    return {"imported": imported, "skipped_count": len(skipped), "skipped": skipped[:20]}