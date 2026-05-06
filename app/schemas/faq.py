from __future__ import annotations

from pydantic import BaseModel


class CategoryItem(BaseModel):
    id: str
    name: str
    count: int = 0


class HotQuestionItem(BaseModel):
    id: str
    question: str
    category: str = "FAQ"
    sourceUrl: str | None = None
