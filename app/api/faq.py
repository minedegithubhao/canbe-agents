from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas.faq import CategoryItem, HotQuestionItem

router = APIRouter(prefix="/faq", tags=["faq"])


@router.get("/categories")
async def categories(request: Request) -> dict[str, list[CategoryItem]]:
    rows = await request.app.state.mongo.categories()
    return {"items": [CategoryItem(id=row["id"], name=row["name"], count=row.get("count", 0)) for row in rows]}


@router.get("/hot-questions")
async def hot_questions(request: Request) -> dict[str, list[HotQuestionItem]]:
    rows = await request.app.state.mongo.hot_questions()
    return {
        "items": [
            HotQuestionItem(
                id=row.get("id", ""),
                question=row.get("question", ""),
                category=row.get("categoryName") or row.get("category") or "FAQ",
                sourceUrl=row.get("sourceUrl"),
            )
            for row in rows
        ]
    }
