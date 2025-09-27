from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from .models import Severity, AudienceType

class AlertCreate(BaseModel):
    title: str
    message: str
    severity: Severity
    audience_type: AudienceType
    audience_ids: Optional[List[int]] = None
    expiry_time: Optional[datetime] = None

class AlertOut(BaseModel):
    id: int
    title: str
    message: str
    severity: Severity
    start_time: datetime
    expiry_time: Optional[datetime]
    audience_type: AudienceType
    audience_ids: Optional[List[int]]

    class Config:
        from_attributes = True

class SnoozeRequest(BaseModel):
    pass  # Placeholder if needed