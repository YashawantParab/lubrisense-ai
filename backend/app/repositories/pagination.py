"""Shared pagination contract for every list-returning repository method.

Limit/offset was chosen over cursor-based pagination for Phase 2 — see
TECHNICAL_DECISIONS.md (pagination strategy ADR) for the trade-off and when to revisit it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

ItemT = TypeVar("ItemT")

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


@dataclass(frozen=True)
class PageParams:
    limit: int = DEFAULT_LIMIT
    offset: int = 0

    def __post_init__(self) -> None:
        if self.limit < 1 or self.limit > MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
        if self.offset < 0:
            raise ValueError("offset must be >= 0")


@dataclass(frozen=True)
class Page(Generic[ItemT]):
    items: list[ItemT]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total
