"""Best-effort duplicate-gateway-identity guard (Phase 5 brief §20: "fail-fast startup
validation... duplicate gateway ID"). A single gateway identity should never be claimed by
two concurrently-running edge processes writing the same SQLite buffer file — an exclusive
`flock` on a sidecar `.lock` file next to the buffer DB detects that case at startup rather
than letting two writers corrupt shared state."""

from __future__ import annotations

import fcntl
from pathlib import Path
from types import TracebackType


class GatewayLockHeldError(RuntimeError):
    """Raised when another process already holds the lock for this gateway_id — i.e. a
    duplicate gateway identity is already running."""


class GatewayLock:
    def __init__(self, db_path: str, gateway_id: str) -> None:
        self._path = Path(db_path).with_suffix(".lock")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._gateway_id = gateway_id
        self._fh: object | None = None

    def acquire(self) -> None:
        fh = open(self._path, "w")  # noqa: SIM115 — held for process lifetime, closed in release()
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            fh.close()
            raise GatewayLockHeldError(
                f"gateway_id={self._gateway_id!r} is already claimed by another running edge "
                f"process (lock file {self._path})"
            ) from exc
        fh.write(self._gateway_id)
        fh.flush()
        self._fh = fh

    def release(self) -> None:
        if self._fh is not None:
            fcntl.flock(self._fh, fcntl.LOCK_UN)  # type: ignore[arg-type]
            self._fh.close()  # type: ignore[attr-defined]
            self._fh = None

    def __enter__(self) -> GatewayLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()
