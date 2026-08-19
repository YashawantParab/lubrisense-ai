"""Centralized authorization checks (Phase 24 brief §24.4 — "Do not scatter raw role
string comparisons across endpoints")."""

from __future__ import annotations

from fastapi import status

from app.auth.models import Principal
from app.auth.permissions import Permission, permissions_for
from app.core.errors import ApplicationError
from app.observability.http_metrics import HTTP_METRICS


class AuthorizationService:
    @staticmethod
    def require(principal: Principal, permission: Permission) -> None:
        if permission not in permissions_for(principal.role):
            HTTP_METRICS.increment("authorization_failures_total")
            raise ApplicationError(
                "FORBIDDEN",
                f"Role '{principal.role.value}' does not have permission '{permission.value}'.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
