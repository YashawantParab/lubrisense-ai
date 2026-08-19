from __future__ import annotations

from pydantic import BaseModel

from app.domain.enums import UserRole


class DemoLoginRequest(BaseModel):
    role: UserRole


class DemoLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    user_id: str
    display_name: str
    expires_in_seconds: int
