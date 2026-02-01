from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Any


class OAuthConnectionBase(BaseModel):
    provider: str
    is_connected: bool = True
    scope: Optional[str] = None
    meta_json: Optional[str] = None


class OAuthConnectionCreate(OAuthConnectionBase):
    user_id: int
    access_token_enc: str
    refresh_token_enc: Optional[str] = None
    expires_at: Optional[datetime] = None


class OAuthConnection(OAuthConnectionBase):
    id: int
    user_id: int
    access_token_enc: str
    refresh_token_enc: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OAuthConnectionPublic(BaseModel):
    provider: str
    is_connected: bool
    connected_at: Optional[datetime] = None
    meta: Optional[dict[str, Any]] = None
