"""*** DEMO AUTH — NOT A REAL IDENTITY PROVIDER. ***

Issues a signed demo bearer token for one of the six fixed roles, scoped to the tenant
resolved from `X-Tenant-ID` (Phase 24 brief §24.1/§24.6). A real deployment replaces this
endpoint with a real OIDC/OAuth2 authorization-code or client-credentials flow against an
external IdP — nothing downstream of `app.api.deps.get_current_principal` needs to change
when that happens. See docs/SECURITY.md.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_app_settings, get_current_tenant
from app.api.schemas.auth import DemoLoginRequest, DemoLoginResponse
from app.auth.demo_tokens import DemoTokenProvider
from app.auth.demo_users import DEMO_USERS
from app.core.config import Settings
from app.domain.models import Tenant

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/demo-login", response_model=DemoLoginResponse)
async def demo_login(
    body: DemoLoginRequest,
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> DemoLoginResponse:
    demo_user = DEMO_USERS[body.role]
    provider = DemoTokenProvider(
        secret=settings.demo_auth_secret, ttl_seconds=settings.demo_token_ttl_seconds
    )
    token = provider.issue(
        user_id=demo_user.user_id,
        tenant_id=tenant.id,
        role=demo_user.role,
        display_name=demo_user.display_name,
    )
    return DemoLoginResponse(
        access_token=token,
        role=demo_user.role,
        user_id=demo_user.user_id,
        display_name=demo_user.display_name,
        expires_in_seconds=settings.demo_token_ttl_seconds,
    )
