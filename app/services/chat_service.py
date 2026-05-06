from __future__ import annotations

import uuid
from typing import Any

from app.models.retrieval import Candidate
from app.schemas.chat import ChatResponse, SourceRef, SuggestedQuestionCandidate
from app.services.llm_service import DeepSeek
from app.services.retrieval_service import Retriever, normalize_query
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
    """问答编排层，负责把“检索结果”变成“可返回给用户的回答”。

    它不直接理解知识库如何检索，也不直接管理数据库连接；它只做三件事：
    1. 先拦截越界问题，避免订单、物流、账号隐私类查询误进入 RAG。
    2. 再调用 Retriever 取候选证据，并根据置信度决定回答还是兜底。
    3. 最后把答案、来源、调试信息和日志统一包装成 API 契约。
    """

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

        """
        处理聊天请求并生成响应。

        Args:
            query (str): 用户输入的查询内容。
            session_id (str | None): 会话ID，用于标识和跟踪特定的聊天会话。如果为None，则可能表示新会话或不需会话跟踪。
            top_k (int | None): 指定返回结果的数量限制，通常用于控制候选答案或相关文档的数量。如果为None，则使用默认值。
            candidate_id (str | None): 候选者ID，可能用于指定特定的回答来源或模型版本。如果为None，则使用默认候选者。

        Returns:
            ChatResponse: 包含聊天响应的对象，具体结构取决于ChatResponse类的定义。
        """

        # 生成一个唯一的跟踪ID，用于跟踪和记录
        trace_id = f"trace_{uuid.uuid4().hex}"

        # candidate_id 是“用户点了建议问题”的快速路径：既然前端已经给出明确 FAQ，
        # 就绕过召回排序，直接用该 FAQ 生成答案，减少误召回和额外延迟。
        if candidate_id:
            response = await self._direct_candidate_response(query, candidate_id, trace_id)
            if response:
                await self._log(trace_id, session_id, query, response, {"reason": "candidate_id_direct"})
                return response

        # RAG 的一个反向概念是“个性化实时查询”：这类问题需要订单系统或账号系统，
        # 不能靠公开 FAQ 回答。这里先做硬拦截，防止模型编造用户状态。
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

        # 置信度低时不强答。此处的“兜底”不是失败，而是产品边界：
        # 宁可给相近问题建议，也不要把弱相关证据包装成确定答案。
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

        # 只有带合法公开来源的候选才允许进入 LLM prompt。
        # 这一步等价于给生成模型加“证据闸门”，避免内部或脏数据成为引用来源。
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
        """根据前端传回的候选 FAQ 直接生成回答。

        仍然调用 faq_answerable 做边界校验，避免前端传入已禁用、历史规则或非法来源。
        """
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
    """粗粒度越界识别：用高风险关键词优先拦截个人化和越权查询。"""
    normalized = query.replace(" ", "")
    return any(hint in normalized for hint in OUT_OF_SCOPE_HINTS)


def source_url_allowed(source_url: str) -> bool:
    return source_url == "https://help.jd.com/user/issue.html" or source_url.startswith("https://help.jd.com/user/issue/")


def candidate_confidence(candidate: Candidate, query: str) -> float:
    """把排序分数折算为对外置信度。

    完全命中标准问题时给下限 0.95；否则沿用 rerank/召回分。
    这里的置信度不是概率校准模型，只是前端和兜底策略使用的工程阈值。
    """
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
    """从弱相关候选里提炼“你是不是想问这些问题”。

    duplicateGroupId/sourceUrl/question 组成去重键，避免同一业务问题以多个 chunk 重复出现。
    """
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
