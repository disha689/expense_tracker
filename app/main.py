from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from app import crud
from app.database import get_conn
from app.schemas import ExpenseCreate, ExpenseOut, ExpenseUpdate

app = FastAPI(title="Expense Tracker API")

INDEX = Path(__file__).parent / "static" / "index.html"
MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


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