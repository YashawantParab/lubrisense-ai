from __future__ import annotations

import pytest

from edge.runtime.gateway_lock import GatewayLock, GatewayLockHeldError


def test_lock_can_be_acquired_and_released(tmp_db_path: str) -> None:
    lock = GatewayLock(tmp_db_path, "gw-1")
    lock.acquire()
    lock.release()


def test_duplicate_gateway_id_lock_fails_fast(tmp_db_path: str) -> None:
    first = GatewayLock(tmp_db_path, "gw-1")
    first.acquire()
    try:
        second = GatewayLock(tmp_db_path, "gw-1")
        with pytest.raises(GatewayLockHeldError):
            second.acquire()
    finally:
        first.release()


def test_lock_reusable_after_release(tmp_db_path: str) -> None:
    with GatewayLock(tmp_db_path, "gw-1"):
        pass
    with GatewayLock(tmp_db_path, "gw-1"):
        pass
