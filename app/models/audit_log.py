from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class AuditLogBase(BaseModel):
    provider: Optional[str] = None
    action: str
    status: str
    error_text: Optional[str] = None


class AuditLogCreate(AuditLogBase):
    user_id: Optional[int] = None
    request_json: Optional[str] = None
    response_json: Optional[str] = None


class AuditLog(AuditLogBase):
    id: int
    user_id: Optional[int] = None
    request_json: Optional[str] = None
    response_json: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
