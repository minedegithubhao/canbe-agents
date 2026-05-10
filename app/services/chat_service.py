from __future__ import annotations

import uuid
from typing import Any

from app.schemas.chat import ChatResponse, SourceRef
from app.services.experiment_runtime import (
    DEFAULT_SOURCE_LABEL,
    ExperimentRuntime,
    candidate_confidence,
    candidate_suggestions,
    evidence_from_faq,
    faq_answerable,
    is_out_of_scope,
)
from app.services.llm_service import DeepSeek
from app.services.retrieval_service import Retriever
from app.settings import get_settings


class ChatService:
    """FAQ chat API adapter over the experiment runtime."""

    def __init__(self, mongo: Any, retriever: Retriever, deepseek: DeepSeek) -> None:
        self.settings = get_settings()
        self.mongo = mongo
        self.retriever = retriever
        self.deepseek = deepseek
        self.runtime = ExperimentRuntime(retriever, deepseek)

    async def chat(
        self,
        query: str,
        session_id: str | None = None,
        top_k: int | None = None,
        candidate_id: str | None = None,
    ) -> ChatResponse:
        trace_id = f"trace_{uuid.uuid4().hex}"

        if candidate_id:
            response = await self._direct_candidate_response(query, candidate_id, trace_id)
            if response:
                await self._log(trace_id, session_id, query, response, {"reason": "candidate_id_direct"})
                return response

        result = await self.runtime.run(query=query, pipeline_snapshot=None, top_k=top_k)
        response = ChatResponse(
            answer=result.answer,
            confidence=result.confidence,
            sources=result.sources,
            suggestedQuestions=result.suggested_questions,
            suggestedQuestionCandidates=result.suggested_question_candidates,
            fallback=result.fallback,
            traceId=trace_id,
            debug=result.debug,
        )
        await self._log(trace_id, session_id, query, response, result.trace)
        return response

    async def _direct_candidate_response(self, query: str, candidate_id: str, trace_id: str) -> ChatResponse | None:
        faq = await self.mongo.get_faq_by_id(candidate_id)
        if not faq or not faq_answerable(faq):
            return None
        item = evidence_from_faq(faq, 1.0)
        answer = await self.deepseek.generate(query, [item])
        return ChatResponse(
            answer=answer,
            confidence=1.0,
            sources=[
                SourceRef(
                    id=item["id"],
                    title=item["question"],
                    category=item.get("categoryName") or "FAQ",
                    source=item.get("source") or DEFAULT_SOURCE_LABEL,
                    sourceUrl=item["sourceUrl"],
                    score=1.0,
                )
            ],
            suggestedQuestions=item.get("suggestedQuestions") or [],
            fallback=False,
            traceId=trace_id,
            debug={"reason": "candidate_id_direct", "candidateId": candidate_id, "deepseekStatus": self.deepseek.status},
        )

    async def _log(self, trace_id: str, session_id: str | None, query: str, response: ChatResponse, diagnostics: dict[str, Any]) -> None:
        await self.mongo.save_chat_log(
            {
                "traceId": trace_id,
                "sessionId": session_id,
                "query": query,
                "answer": response.answer,
                "confidence": response.confidence,
                "fallback": response.fallback,
                "sources": [source.model_dump() for source in response.sources],
                "diagnostics": diagnostics,
            }
        )


async def save_feedback(mongo: Any, trace_id: str, feedback_type: str, session_id: str | None, comment: str | None) -> None:
    await mongo.save_feedback({"traceId": trace_id, "feedbackType": feedback_type, "sessionId": session_id, "comment": comment})
