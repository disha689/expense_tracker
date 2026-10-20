from datetime import date as date_type
from typing import Optional

from pydantic import BaseModel, Field

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class ExpenseCreate(BaseModel):
    amount: float = Field(gt=0)
    category: str = Field(min_length=1)
    note: str = ""
    date: Optional[date_type] = None


class ExpenseUpdate(BaseModel):
    amount: Optional[float] = Field(default=None, gt=0)
    category: Optional[str] = Field(default=None, min_length=1)
    note: Optional[str] = None
    date: Optional[date_type] = None


class ExpenseOut(BaseModel):
    id: int
    date: str
    category: str
    amount: float
    note: Optional[str] = None


class BudgetIn(BaseModel):
    month: str = Field(pattern=MONTH_PATTERN)
    amount: float = Field(ge=0)


class BudgetOut(BaseModel):
    month: str
    amount: float


class CategoryBudgetIn(BaseModel):
    month: str = Field(pattern=MONTH_PATTERN)
    category: str = Field(min_length=1, max_length=100)
    amount: float = Field(ge=0)


class CategoryBudgetItem(BaseModel):
    category: str
    amount: float


class CategoryBudgetsOut(BaseModel):
    month: str
    budgets: list[CategoryBudgetItem]


class RecurringCreate(BaseModel):
    amount: float = Field(gt=0)
    category: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=500)
    day: int = Field(ge=1, le=31)
    start_month: Optional[str] = Field(default=None, pattern=MONTH_PATTERN)


class RecurringOut(BaseModel):
    id: int
    amount: float
    category: str
    note: str
    day: int
    start_month: str


class RecurringCreatedOut(RecurringOut):
    created: int