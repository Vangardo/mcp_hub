from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class RefreshToken(BaseModel):
    id: int
    user_id: int
    token_hash: str
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}
