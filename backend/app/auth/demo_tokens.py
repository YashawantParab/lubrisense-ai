"""A self-issued, HMAC-signed bearer token — the demo/reference stand-in for a real
OIDC/OAuth2 identity provider (Phase 24 brief §24.1: "provide a simple deterministic
demo auth provider... do NOT require a paid IdP").

The token shape (base64url header.payload.signature, a JSON claim set, an expiry) is
deliberately JWT-shaped so the seam this replaces is obvious: a production deployment
swaps `DemoTokenProvider` for real OIDC/JWT verification against an external IdP's JWKS
without changing anything downstream of `app.api.deps.get_current_principal` — every
caller only ever sees a verified `Principal` (ADR-150).

*** DEMO AUTH — NOT PRODUCTION IDENTITY. *** See docs/SECURITY.md.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass

from app.auth.models import Principal
from app.domain.enums import AuditActorType, UserRole

_ALGORITHM = "DEMO-HS256"


class InvalidTokenError(Exception):
    """Signature mismatch, malformed payload, or expired token."""


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


@dataclass(frozen=True)
class DemoTokenProvider:
    """Issues and verifies demo bearer tokens signed with `secret`.

    `secret` comes from `Settings.demo_auth_secret` — see `app.core.config` for the
    fail-fast production check that refuses the insecure default outside local/demo use.
    """

    secret: str
    ttl_seconds: int = 3600

    def issue(
        self, *, user_id: str, tenant_id: uuid.UUID, role: UserRole, display_name: str
    ) -> str:
        now = int(time.time())
        payload = {
            "sub": user_id,
            "tenant_id": str(tenant_id),
            "role": role.value,
            "name": display_name,
            "iat": now,
            "exp": now + self.ttl_seconds,
            "jti": str(uuid.uuid4()),
        }
        payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        header_b64 = _b64encode(json.dumps({"alg": _ALGORITHM}).encode("utf-8"))
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        signature = hmac.new(self.secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        return f"{header_b64}.{payload_b64}.{_b64encode(signature)}"

    def verify(self, token: str) -> Principal:
        parts = token.split(".")
        if len(parts) != 3:
            raise InvalidTokenError("Malformed token.")
        header_b64, payload_b64, signature_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_signature = hmac.new(
            self.secret.encode("utf-8"), signing_input, hashlib.sha256
        ).digest()
        try:
            actual_signature = _b64decode(signature_b64)
        except Exception as exc:
            raise InvalidTokenError("Malformed token signature.") from exc
        if not hmac.compare_digest(expected_signature, actual_signature):
            raise InvalidTokenError("Token signature verification failed.")

        try:
            payload = json.loads(_b64decode(payload_b64))
        except Exception as exc:
            raise InvalidTokenError("Malformed token payload.") from exc

        if int(payload.get("exp", 0)) < int(time.time()):
            raise InvalidTokenError("Token has expired.")

        try:
            role = UserRole(payload["role"])
            tenant_id = uuid.UUID(payload["tenant_id"])
        except (KeyError, ValueError) as exc:
            raise InvalidTokenError("Malformed token claims.") from exc

        return Principal(
            user_id=payload["sub"],
            tenant_id=tenant_id,
            role=role,
            display_name=payload.get("name", payload["sub"]),
            actor_type=AuditActorType.HUMAN,
        )
