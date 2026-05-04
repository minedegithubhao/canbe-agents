from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    id: str
    title: str
    category: str = "FAQ"
    source: str = "JD Help FAQ"
    sourceUrl: str
    score: float = 0.0


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    sessionId: str | None = None
    topK: int | None = Field(default=None, ge=1, le=20)
    candidateId: str | None = Field(default=None, min_length=1, max_length=200)


class SuggestedQuestionCandidate(BaseModel):
    id: str
    question: str
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    rankingScore: float = 0.0
    docType: str = "faq"
    sourceUrl: str


class ChatResponse(BaseModel):
    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[SourceRef] = Field(default_factory=list)
    suggestedQuestions: list[str] = Field(default_factory=list)
    suggestedQuestionCandidates: list[SuggestedQuestionCandidate] = Field(default_factory=list)
    fallback: bool
    traceId: str
    debug: dict[str, Any] | None = None


class FeedbackRequest(BaseModel):
    traceId: str
    feedbackType: Literal["useful", "useless", "unresolved"]
    sessionId: str | None = None
    comment: str | None = None


class FeedbackResponse(BaseModel):
    success: bool
    status: str = "ok"
    traceId: str


class IngestResponse(BaseModel):
    ok: bool
    message: str
    counts: dict[str, int] = Field(default_factory=dict)
    status: dict[str, str] = Field(default_factory=dict)


class IngestTaskResponse(BaseModel):
    ok: bool
    message: str
    task: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    dependencies: dict[str, str]


class CategoryItem(BaseModel):
    id: str
    name: str
    count: int = 0


class HotQuestionItem(BaseModel):
    id: str
    question: str
    category: str = "FAQ"
    sourceUrl: str | None = None
