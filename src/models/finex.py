"""Hand-picked pydantic models for the fields tests actually assert on -
not full payload mirrors."""
from typing import List, Optional

from pydantic import BaseModel


class Bank(BaseModel):
    id: int
    is_rsm_mandatory: Optional[int] = None


class BankListData(BaseModel):
    bank_list: List[Bank]


class BankListResponse(BaseModel):
    data: dict  # {"masterdata": BankListData} - kept loose; see test for the drill-down
