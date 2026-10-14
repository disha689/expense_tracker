from datetime import date as date_type
from typing import Optional

from pydantic import BaseModel, Field


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