"""Pydantic schemas for Scan History and Private Records."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class UserScanSummaryItem(BaseModel):
    id: str
    input_type: str
    input_reference: Optional[str] = None
    status: str
    created_at: datetime
    risk_score: Optional[float] = None
    risk_category: Optional[str] = None
    claimed_company_name: Optional[str] = None

    class Config:
        from_attributes = True


class UserScanListResponse(BaseModel):
    scans: List[UserScanSummaryItem]
    total: int
    limit: int
    offset: int
