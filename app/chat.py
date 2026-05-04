from __future__ import annotations

import uuid
from typing import Any

from app.llm import DeepSeek
from app.retrieval import Candidate, Retriever, normalize_query
from app.schemas import ChatResponse, SourceRef, SuggestedQuestionCandidate
from app.settings import get_settings


OUT_OF_SCOPE_HINTS = (
    "订单到哪",
    "订单现在",
    "查订单",
    "物流到哪",
    "物流状态",
    "物流单号",
    "退款多久到账",
    "退款进度",
    "支付记录",
    "绑定手机号",
    "身份证",
    "银行卡",
    "用户隐私",
    "内部客服",
    "内部流程",
    "忽略之前",
    "忽略规则",
    "绕过限制",
    "随便编",
    "编一个",
    "不要看知识库",
)

FALLBACK_ANSWER = "暂未找到与该问题高度相关的公开 FAQ。你可以换一种问法，或查看帮助中心分类。"
OUT_OF_SCOPE_ANSWER = "本助手仅基于京东帮助中心公开 FAQ 回答，无法查询订单、物流、支付、退款进度或账号隐私等个人化信息。"


class ChatService:
    def __init__(self, mongo: Any, retriever: Retriever, deepseek: DeepSeek) -> None:
        self.settings = get_settings()
        self.mongo = mongo
        self.retriever = retriever
        self.deepseek = deepseek

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
        if is_out_of_scope(query):
            response = ChatResponse(
                answer=OUT_OF_SCOPE_ANSWER,
                confidence=0.0,
                sources=[],
                suggestedQuestions=[],
                fallback=True,
                traceId=trace_id,
                debug={"reason": "out_of_scope"},
            )
            await self._log(trace_id, session_id, query, response, {"reason": "out_of_scope"})
            return response

        candidates, diagnostics = await self.retriever.retrieve(query, top_k)
        confidence = candidate_confidence(candidates[0], query) if candidates else 0.0
        if not candidates or confidence < self.settings.retrieval_medium_confidence_threshold:
            suggestions = candidate_suggestions(candidates, query)
            response = ChatResponse(
                answer=FALLBACK_ANSWER,
                confidence=confidence,
                sources=[],
                suggestedQuestions=[item.question for item in suggestions],
                suggestedQuestionCandidates=suggestions,
                fallback=True,
                traceId=trace_id,
                debug={**diagnostics, "suggestedFromCandidates": bool(suggestions)},
            )
            await self._log(trace_id, session_id, query, response, diagnostics)
            return response

        evidences = [evidence(candidate) for candidate in candidates[: self.settings.retrieval_prompt_top_k] if has_valid_source(candidate)]
        if not evidences:
            suggestions = candidate_suggestions(candidates, query)
            response = ChatResponse(
                answer=FALLBACK_ANSWER,
                confidence=confidence,
                sources=[],
                suggestedQuestions=[item.question for item in suggestions],
                suggestedQuestionCandidates=suggestions,
                fallback=True,
                traceId=trace_id,
                debug={**diagnostics, "reason": "no_valid_source", "suggestedFromCandidates": bool(suggestions)},
            )
            await self._log(trace_id, session_id, query, response, diagnostics)
            return response

        answer = await self.deepseek.generate(query, evidences)
        response = ChatResponse(
            answer=answer,
            confidence=confidence,
            sources=[
                SourceRef(
                    id=item["id"],
                    title=item["question"],
                    category=item.get("categoryName") or "FAQ",
                    source=item.get("source") or "京东帮助中心公开 FAQ",
                    sourceUrl=item["sourceUrl"],
                    score=item["score"],
                )
                for item in evidences
            ],
            suggestedQuestions=[],
            fallback=False,
            traceId=trace_id,
            debug={**diagnostics, "confidenceSource": "rerank_score", "deepseekStatus": self.deepseek.status},
        )
        await self._log(trace_id, session_id, query, response, diagnostics)
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
                    source=item.get("source") or "京东帮助中心公开 FAQ",
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


def is_out_of_scope(query: str) -> bool:
    normalized = query.replace(" ", "")
    return any(hint in normalized for hint in OUT_OF_SCOPE_HINTS)


def source_url_allowed(source_url: str) -> bool:
    return source_url == "https://help.jd.com/user/issue.html" or source_url.startswith("https://help.jd.com/user/issue/")


def candidate_confidence(candidate: Candidate, query: str) -> float:
    score = min(1.0, max(0.0, float(candidate.rerank_score or candidate.score or 0.0)))
    question = str((candidate.faq or {}).get("question") or "")
    if question and normalize_query(question) == normalize_query(query):
        return max(score, 0.95)
    return score


def has_valid_source(candidate: Candidate) -> bool:
    url = str((candidate.faq or {}).get("sourceUrl") or "")
    return bool(url and source_url_allowed(url))


def evidence(candidate: Candidate) -> dict[str, Any]:
    faq = candidate.faq or {}
    return evidence_from_faq(faq, candidate.final_score, fallback_id=candidate.faq_id)


def evidence_from_faq(faq: dict[str, Any], score: float, fallback_id: str = "") -> dict[str, Any]:
    return {
        "id": faq.get("id") or fallback_id,
        "question": faq.get("question") or "",
        "answer": faq.get("answer") or "",
        "categoryName": faq.get("categoryName") or faq.get("category") or "FAQ",
        "source": faq.get("source") or "京东帮助中心公开 FAQ",
        "sourceUrl": faq.get("sourceUrl") or "",
        "score": score,
        "suggestedQuestions": faq.get("suggestedQuestions") or [],
    }


def candidate_suggestions(candidates: list[Candidate], query: str, limit: int = 3) -> list[SuggestedQuestionCandidate]:
    results: list[SuggestedQuestionCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not has_valid_source(candidate):
            continue
        faq = candidate.faq or {}
        question = str(faq.get("question") or "").strip()
        source_url = str(faq.get("sourceUrl") or "").strip()
        key = str(faq.get("duplicateGroupId") or faq.get("sourceUrl") or question).strip()
        if not question or not source_url or key in seen:
            continue
        seen.add(key)
        results.append(
            SuggestedQuestionCandidate(
                id=str(faq.get("id") or candidate.faq_id),
                question=question,
                score=candidate_confidence(candidate, query),
                rankingScore=float(candidate.final_score or 0.0),
                docType=str(faq.get("docType") or "faq"),
                sourceUrl=source_url,
            )
        )
        if len(results) >= limit:
            break
    return results


def faq_answerable(faq: dict[str, Any]) -> bool:
    return (
        bool(faq.get("enabled", True))
        and bool(faq.get("searchEnabled", True))
        and str(faq.get("status") or "active") == "active"
        and str(faq.get("docType") or "faq") != "compound_qa"
        and source_url_allowed(str(faq.get("sourceUrl") or ""))
    )
