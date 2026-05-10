from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.retrieval import Candidate
from app.schemas.chat import SourceRef, SuggestedQuestionCandidate
from app.services.retrieval_service import normalize_query
from app.settings import get_settings


OUT_OF_SCOPE_HINTS = (
    "order status",
    "current order",
    "check order",
    "logistics",
    "shipping status",
    "tracking number",
    "refund progress",
    "refund arrival",
    "payment record",
    "bound phone",
    "identity number",
    "bank card",
    "account privacy",
    "internal support",
    "internal workflow",
    "ignore previous",
    "ignore rules",
    "bypass restriction",
    "make something up",
    "invent one",
    "do not use knowledge base",
)

FALLBACK_ANSWER = "No highly relevant public FAQ was found for this question. Try rephrasing it or browse the help center categories."
OUT_OF_SCOPE_ANSWER = "This assistant only answers from public JD Help Center FAQs and cannot access personalized data like orders, logistics, payments, refunds, or account privacy details."
DEFAULT_SOURCE_LABEL = "JD Help Center Public FAQ"

TRACE_SECTIONS = [
    "input",
    "query_processing",
    "retrieval",
    "fusion",
    "rerank",
    "generation",
    "judgement",
    "verdict",
]


@dataclass
class RuntimeResult:
    answer: str
    confidence: float
    sources: list[SourceRef]
    suggested_questions: list[str]
    suggested_question_candidates: list[SuggestedQuestionCandidate]
    fallback: bool
    debug: dict[str, Any]
    trace: dict[str, Any]


class ExperimentRuntime:
    def __init__(self, retriever: Any, generator: Any) -> None:
        self.settings = get_settings()
        self.retriever = retriever
        self.generator = generator

    def empty_trace(self) -> list[str]:
        return list(TRACE_SECTIONS)

    async def run(self, query: str, pipeline_snapshot: dict[str, Any] | None = None, top_k: int | None = None) -> RuntimeResult:
        trace = self._base_trace(query=query, pipeline_snapshot=pipeline_snapshot)
        if is_out_of_scope(query):
            trace["judgement"] = {"reason": "out_of_scope"}
            trace["verdict"] = {"fallback": True, "confidence": 0.0}
            return RuntimeResult(
                answer=OUT_OF_SCOPE_ANSWER,
                confidence=0.0,
                sources=[],
                suggested_questions=[],
                suggested_question_candidates=[],
                fallback=True,
                debug={"reason": "out_of_scope"},
                trace=trace,
            )

        candidates, diagnostics = await self.retriever.retrieve_for_runtime(query, pipeline_snapshot=pipeline_snapshot, top_k=top_k)
        trace["query_processing"] = {
            "normalizedQuery": diagnostics.get("normalizedQuery"),
            "expandedQuery": diagnostics.get("expandedQuery"),
            "rewriteQueries": diagnostics.get("rewriteQueries") or [],
            "canonicalTerms": diagnostics.get("canonicalTerms") or [],
            "synonymTerms": diagnostics.get("synonymTerms") or [],
        }
        trace["retrieval"] = {
            "denseHits": diagnostics.get("denseHits", 0),
            "sparseHits": diagnostics.get("sparseHits", 0),
            "keywordHits": diagnostics.get("keywordHits", 0),
            "candidateCount": diagnostics.get("candidateCount", 0),
            "degraded": diagnostics.get("degraded", False),
        }
        trace["fusion"] = {
            "candidateSources": [candidate.source for candidate in candidates],
        }
        trace["rerank"] = {
            "scores": [
                {
                    "faqId": candidate.faq_id,
                    "rerankScore": float(candidate.rerank_score or 0.0),
                    "rankingScore": float(candidate.ranking_score or 0.0),
                    "finalScore": float(candidate.final_score or 0.0),
                }
                for candidate in candidates
            ]
        }

        confidence = candidate_confidence(candidates[0], query) if candidates else 0.0
        if not candidates or confidence < self.settings.retrieval_medium_confidence_threshold:
            suggestions = candidate_suggestions(candidates, query)
            trace["judgement"] = {
                "reason": "low_confidence",
                "threshold": self.settings.retrieval_medium_confidence_threshold,
            }
            trace["verdict"] = {"fallback": True, "confidence": confidence}
            return RuntimeResult(
                answer=FALLBACK_ANSWER,
                confidence=confidence,
                sources=[],
                suggested_questions=[item.question for item in suggestions],
                suggested_question_candidates=suggestions,
                fallback=True,
                debug={**diagnostics, "suggestedFromCandidates": bool(suggestions)},
                trace=trace,
            )

        evidences = [evidence(candidate) for candidate in candidates[: self.settings.retrieval_prompt_top_k] if has_valid_source(candidate)]
        if not evidences:
            suggestions = candidate_suggestions(candidates, query)
            trace["judgement"] = {"reason": "no_valid_source"}
            trace["verdict"] = {"fallback": True, "confidence": confidence}
            return RuntimeResult(
                answer=FALLBACK_ANSWER,
                confidence=confidence,
                sources=[],
                suggested_questions=[item.question for item in suggestions],
                suggested_question_candidates=suggestions,
                fallback=True,
                debug={**diagnostics, "reason": "no_valid_source", "suggestedFromCandidates": bool(suggestions)},
                trace=trace,
            )

        answer = await self.generator.generate(query, evidences)
        trace["generation"] = {
            "evidenceCount": len(evidences),
            "generatorStatus": getattr(self.generator, "status", "unknown"),
        }
        trace["judgement"] = {
            "reason": "answered",
            "confidenceSource": "rerank_score",
        }
        trace["verdict"] = {"fallback": False, "confidence": confidence}
        return RuntimeResult(
            answer=answer,
            confidence=confidence,
            sources=[
                SourceRef(
                    id=item["id"],
                    title=item["question"],
                    category=item.get("categoryName") or "FAQ",
                    source=item.get("source") or DEFAULT_SOURCE_LABEL,
                    sourceUrl=item["sourceUrl"],
                    score=item["score"],
                )
                for item in evidences
            ],
            suggested_questions=[],
            suggested_question_candidates=[],
            fallback=False,
            debug={**diagnostics, "confidenceSource": "rerank_score", "deepseekStatus": getattr(self.generator, "status", "unknown")},
            trace=trace,
        )

    def _base_trace(self, query: str, pipeline_snapshot: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "input": {
                "query": query,
                "pipelineSnapshot": pipeline_snapshot or {},
            },
            "query_processing": {},
            "retrieval": {},
            "fusion": {},
            "rerank": {},
            "generation": {},
            "judgement": {},
            "verdict": {},
        }


def is_out_of_scope(query: str) -> bool:
    normalized = query.replace(" ", "").lower()
    return any(hint.replace(" ", "") in normalized for hint in OUT_OF_SCOPE_HINTS)


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
        "source": faq.get("source") or DEFAULT_SOURCE_LABEL,
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
