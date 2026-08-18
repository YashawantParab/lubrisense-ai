from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from app.repositories.pagination import Page

ItemT = TypeVar("ItemT")


class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int
    has_more: bool


class PaginatedResponse(BaseModel, Generic[ItemT]):
    items: list[ItemT]
    meta: PageMeta

    @classmethod
    def from_page(cls, page: Page[Any], items: list[ItemT]) -> PaginatedResponse[ItemT]:
        return cls(
            items=items,
            meta=PageMeta(
                total=page.total, limit=page.limit, offset=page.offset, has_more=page.has_more
            ),
        )
