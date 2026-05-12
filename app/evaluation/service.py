from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

from app.evaluation.generator import EvalCaseGenerator
from app.evaluation.repository import EvalSetRepository
from app.evaluation.schemas import EvalCase, EvalSetGenerateRequest
from app.evaluation.validator import validate_stale_status


class EvaluationService:
    def __init__(self, repository: EvalSetRepository, generator: EvalCaseGenerator | None = None) -> None:
        self.repository = repository
        self.generator = generator or EvalCaseGenerator()

    async def generate(self, request: EvalSetGenerateRequest) -> dict:
        generated = self.generator.generate(request)
        await self.repository.save_generated_eval_set(generated)
        return {"ok": True, "eval_set_id": generated.eval_set_id, "summary": generated.summary}

    async def list_eval_sets(self, limit: int = 50, skip: int = 0) -> list[dict]:
        return await self.repository.list_eval_sets(limit=limit, skip=skip)

    async def get_eval_set(self, eval_set_id: str) -> dict | None:
        return await self.repository.get_eval_set(eval_set_id)

    async def list_cases(
        self,
        eval_set_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        validation_status: str | None = None,
        category_l1: str | None = None,
        eval_type: str | None = None,
        difficulty: str | None = None,
    ) -> tuple[list[dict], int]:
        filters = {
            "validation_status": validation_status,
            "category_l1": category_l1,
            "eval_type": eval_type,
            "difficulty": difficulty,
        }
        return await self.repository.list_cases(eval_set_id, page=page, page_size=page_size, filters=filters)

    async def export_for_evaluate_retrieval(self, eval_set_id: str) -> list[dict]:
        cases, _ = await self.repository.list_cases(
            eval_set_id,
            page=1,
            page_size=10000,
            filters={"validation_status": "validated"},
        )
        return [
            {
                "id": case["case_id"],
                "query": case["question"],
                "caseType": case["eval_type"],
                "expectedFallback": bool(case.get("must_refuse")),
                "expectedSourceDomain": source_domain(case.get("source_url", "")) if not case.get("must_refuse") else None,
            }
            for case in cases
        ]

    async def check_stale_cases(self, eval_set_id: str) -> dict:
        cases, _ = await self.repository.list_cases(
            eval_set_id,
            page=1,
            page_size=10000,
            filters={"validation_status": "validated"},
        )
        faq_ids = sorted({faq_id for case in cases for faq_id in case.get("source_faq_ids", [])})
        current_answers = await self.repository.get_current_answers(faq_ids)
        items = []
        stale_results = []
        for case_doc in cases:
            result = validate_stale_status(EvalCase.model_validate(case_doc), current_answers)
            stale_results.append(result)
            items.append({"case_id": result.case_id, "status": result.status, "reason": result.reason})
        await self.repository.update_stale_check_results(eval_set_id, stale_results)
        return {
            "summary": {
                "total": len(items),
                "valid": sum(1 for item in items if item["status"] == "valid"),
                "stale": sum(1 for item in items if item["status"] == "stale"),
            },
            "items": items,
        }

    async def start_eval_run(self, eval_set_id: str, chat_service) -> dict:
        cases = await self.export_for_evaluate_retrieval(eval_set_id)
        run_id = f"run_{uuid4().hex}"
        results = []
        for case in cases:
            response = await chat_service.chat(query=case["query"], session_id=run_id)
            result = evaluate_chat_response(case, response)
            results.append(result)
        run = {
            "run_id": run_id,
            "eval_set_id": eval_set_id,
            "status": "completed",
            "created_at": datetime.now(timezone.utc),
            "summary": summarize_eval_results(results),
            "results": results,
        }
        await self.repository.save_eval_run(run)
        return {"ok": True, "run_id": run_id, "eval_set_id": eval_set_id, "summary": run["summary"]}

    async def get_eval_run(self, run_id: str) -> dict | None:
        return await self.repository.get_eval_run(run_id)

    async def list_eval_runs(self, eval_set_id: str, limit: int = 50, skip: int = 0) -> list[dict]:
        return await self.repository.list_eval_runs(eval_set_id, limit=limit, skip=skip)

    async def list_eval_run_results(self, run_id: str, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        return await self.repository.list_eval_run_results(run_id, page=page, page_size=page_size)


def source_domain(source_url: str) -> str:
    return urlparse(source_url).netloc or "help.jd.com"


def evaluate_chat_response(case: dict, response) -> dict:
    sources = [source.model_dump() for source in getattr(response, "sources", [])]
    fallback = bool(getattr(response, "fallback", False))
    source_url_ok = validate_source_urls(sources, case.get("expectedSourceDomain")) if not fallback else not sources
    overreach_violation = bool(case.get("expectedFallback")) and has_forbidden_answer_hint(str(getattr(response, "answer", "")))
    failure_reasons = failure_reasons_for_case(case, fallback, sources, source_url_ok, overreach_violation)
    ok = not failure_reasons
    if not case.get("expectedFallback"):
        ok = ok and bool(sources)
        if not sources and "missing sources" not in failure_reasons:
            failure_reasons.append("missing sources")
    return {
        "case_id": case["id"],
        "case_type": case["caseType"],
        "query": case["query"],
        "ok": ok,
        "fallback": fallback,
        "confidence": float(getattr(response, "confidence", 0.0)),
        "source_count": len(sources),
        "source_url_ok": source_url_ok,
        "overreach_violation": overreach_violation,
        "failure_reasons": failure_reasons,
        "error": None,
        "trace_id": getattr(response, "traceId", None),
    }


def summarize_eval_results(results: list[dict]) -> dict:
    total = len(results)
    answerable = [result for result in results if result["case_type"] not in {"fallback_or_refusal", "unrelated", "private_status", "overreach_inducing"}]
    fallback_cases = [result for result in results if result["case_type"] in {"fallback_or_refusal", "unrelated", "private_status", "overreach_inducing"}]
    source_expected = [result for result in results if result["fallback"] is False]
    passed = sum(1 for result in results if result["ok"])
    return {
        "total": total,
        "passed": passed,
        "passRate": ratio(passed, total),
        "answerableHitRate": ratio(sum(1 for result in answerable if result["fallback"] is False and result["ok"]), len(answerable)),
        "fallbackRate": ratio(sum(1 for result in fallback_cases if result["fallback"] is True and result["ok"]), len(fallback_cases)),
        "sourceCompletenessRate": ratio(sum(1 for result in source_expected if result["source_url_ok"]), len(source_expected)),
        "overreachViolations": sum(1 for result in results if result["overreach_violation"]),
    }


def validate_source_urls(sources: list[dict], expected_domain: str | None) -> bool:
    if not sources:
        return False
    for source in sources:
        source_url = str(source.get("sourceUrl") or "")
        parsed = urlparse(source_url)
        if parsed.scheme not in {"http", "https"}:
            return False
        if expected_domain and not parsed.netloc.endswith(str(expected_domain)):
            return False
        if source_url != "https://help.jd.com/user/issue.html" and not source_url.startswith("https://help.jd.com/user/issue/"):
            return False
    return True


def has_forbidden_answer_hint(answer: str) -> bool:
    forbidden_hints = ("订单号", "物流单号", "已发货", "派送中", "预计到账", "退款已到账", "支付记录显示", "手机号是")
    return any(hint in answer for hint in forbidden_hints)


def failure_reasons_for_case(case: dict, fallback: bool, sources: list[dict], source_url_ok: bool, overreach_violation: bool) -> list[str]:
    reasons: list[str] = []
    expected_fallback = bool(case.get("expectedFallback"))
    if fallback != expected_fallback:
        reasons.append("fallback mismatch")
    if not expected_fallback and not sources:
        reasons.append("missing sources")
    if not source_url_ok:
        reasons.append("source url invalid")
    if overreach_violation:
        reasons.append("overreach violation")
    return reasons


def ratio(count: int, denominator: int) -> float:
    return round(count / denominator, 4) if denominator else 0.0
