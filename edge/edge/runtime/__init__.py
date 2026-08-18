"""`EdgeRuntime` — ties acquisition, buffering, local rules, connectivity, and transport
together into one running edge controller (Phase 5 brief §1, §31-§33)."""

from edge.runtime.gateway_lock import GatewayLock, GatewayLockHeldError
from edge.runtime.runtime import EdgeRuntime

__all__ = ["EdgeRuntime", "GatewayLock", "GatewayLockHeldError"]
