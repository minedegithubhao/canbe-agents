from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas.chat import ChatRequest, ChatResponse, FeedbackRequest, FeedbackResponse
from app.services.chat_service import save_feedback

router = APIRouter(prefix="/faq", tags=["faq"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    return await request.app.state.chat_service.chat(
        query=payload.query,
        session_id=payload.sessionId,
        top_k=payload.topK,
        candidate_id=payload.candidateId,
    )


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(payload: FeedbackRequest, request: Request) -> FeedbackResponse:
    await save_feedback(request.app.state.mongo, payload.traceId, payload.feedbackType, payload.sessionId, payload.comment)
    return FeedbackResponse(success=True, traceId=payload.traceId)
