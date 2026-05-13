from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.evaluation.generator import EvalCaseGenerator, source_file_hash
from app.evaluation.metrics import calculate_case_metrics, summarize_metrics
from app.evaluation.repository import EvalSetRepository
from app.evaluation.schemas import EvalRunConfig, EvalSetGenerateRequest
from app.evaluation.text_repair import repair_text


class EvalSourceChangedError(RuntimeError):
    pass


CHUNK_EVAL_TYPES = {"single_chunk", "multi_chunk"}


class EvaluationService:
    def __init__(self, repository: EvalSetRepository, generator: EvalCaseGenerator | None = None, retriever: Any | None = None) -> None:
        self.repository = repository
        self.generator = generator or EvalCaseGenerator()
        self.retriever = retriever
        self.eval_case_concurrency = 5
        self.eval_result_commit_batch_size = 10

    async def generate(self, request: EvalSetGenerateRequest) -> dict:
        generated = self.generator.generate(request)
        await self.repository.save_generated_eval_set(generated)
        return {"ok": True, "eval_set_id": generated.eval_set_id, "summary": generated.summary}

    async def list_eval_sets(self, limit: int = 50, skip: int = 0) -> list[dict]:
        items = await self.repository.list_eval_sets(limit=limit, skip=skip)
        return [item for item in items if is_chunk_eval_set(item)]

    async def get_eval_set(self, eval_set_id: str) -> dict | None:
        return await self.repository.get_eval_set(eval_set_id)

    async def delete_eval_set(self, eval_set_id: str) -> dict:
        return await self.repository.delete_eval_set(eval_set_id)

    async def list_cases(
        self,
        eval_set_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
        eval_type: str | None = None,
        difficulty: str | None = None,
        question_style: str | None = None,
    ) -> tuple[list[dict], int]:
        filters = {
            "category": category,
            "eval_type": eval_type,
            "difficulty": difficulty,
            "question_style": question_style,
        }
        return await self.repository.list_cases(eval_set_id, page=page, page_size=page_size, filters=filters)

    async def start_eval_run(self, eval_set_id: str, config: EvalRunConfig | None = None) -> dict:
        if self.retriever is None:
            raise RuntimeError("retriever is required for evaluation runs")
        run_config = config or EvalRunConfig()
        eval_set = await self.repository.get_eval_set(eval_set_id)
        if not eval_set:
            raise ValueError(f"eval_set not found: {eval_set_id}")
        current_hash = source_file_hash(run_config_path(eval_set))
        if current_hash != eval_set.get("source_hash"):
            raise EvalSourceChangedError("evaluation source has changed")
        cases, _ = await self.repository.list_cases(eval_set_id, page=1, page_size=10000, filters={})
        run_id = f"run_{uuid4().hex}"
        result_docs: list[dict[str, Any]] = []
        metric_items = []
        for case in cases:
            result, _elapsed_ms = await self._evaluate_case(run_id, eval_set_id, case, run_config)
            result_docs.append(result)
            metric_items.append(result["metrics_model"])
        summary = summarize_metrics(metric_items).model_dump()
        run = {
            "_id": run_id,
            "run_id": run_id,
            "eval_set_id": eval_set_id,
            "rag_config": run_config.model_dump(),
            "summary": summary,
            "created_at": datetime.now(timezone.utc),
        }
        await self.repository.save_eval_run(run)
        await self.repository.save_eval_run_results(run_id, [strip_internal_fields(item) for item in result_docs])
        return {"ok": True, "run_id": run_id, "eval_set_id": eval_set_id, "summary": summary}

    async def create_eval_run(self, eval_set_id: str, config: EvalRunConfig | None = None) -> dict:
        if self.retriever is None:
            raise RuntimeError("retriever is required for evaluation runs")
        run_config = config or EvalRunConfig()
        resolved_case_concurrency = run_config.case_concurrency_override or self.eval_case_concurrency
        resolved_commit_batch_size = run_config.commit_batch_size_override or self.eval_result_commit_batch_size
        eval_set = await self.repository.get_eval_set(eval_set_id)
        if not eval_set:
            raise ValueError(f"eval_set not found: {eval_set_id}")
        current_hash = source_file_hash(run_config_path(eval_set))
        if current_hash != eval_set.get("source_hash"):
            raise EvalSourceChangedError("evaluation source has changed")
        cases, total = await self.repository.list_cases(eval_set_id, page=1, page_size=10000, filters={})
        run_id = f"run_{uuid4().hex}"
        summary = summarize_metrics([]).model_dump()
        summary["total"] = total
        run = {
            "_id": run_id,
            "run_id": run_id,
            "eval_set_id": eval_set_id,
            "status": "running",
            "rag_config": {
                **run_config.model_dump(),
                "case_concurrency": resolved_case_concurrency,
                "commit_batch_size": resolved_commit_batch_size,
            },
            "summary": summary,
            "created_at": datetime.now(timezone.utc),
            "started_at": datetime.now(timezone.utc),
            "case_count": len(cases),
            "progress": {
                "completed_cases": 0,
                "total_cases": total,
                "percent": 0.0,
                "updated_at": datetime.now(timezone.utc),
            },
        }
        await self.repository.save_eval_run(run)
        return {"ok": True, "run_id": run_id, "eval_set_id": eval_set_id, "status": "running", "summary": summary}

    async def complete_eval_run(self, run_id: str) -> dict:
        run = await self.repository.get_eval_run(run_id)
        if not run:
            raise ValueError(f"eval_run not found: {run_id}")
        if run.get("status") == "completed":
            return {"ok": True, "run_id": run_id, "eval_set_id": run["eval_set_id"], "status": "completed", "summary": run["summary"]}
        if run.get("status") == "failed":
            return {"ok": False, "run_id": run_id, "eval_set_id": run["eval_set_id"], "status": "failed", "summary": run.get("summary", {})}
        try:
            result = await self._execute_eval_run(run_id, run["eval_set_id"], EvalRunConfig(**(run.get("rag_config") or {})))
            return {"ok": True, "run_id": run_id, "eval_set_id": run["eval_set_id"], "status": "completed", "summary": result["summary"]}
        except Exception as exc:
            await self.repository.update_eval_run(
                run_id,
                {
                    "status": "failed",
                    "error_message": str(exc),
                    "completed_at": datetime.now(timezone.utc),
                },
            )
            raise

    async def _execute_eval_run(self, run_id: str, eval_set_id: str, run_config: EvalRunConfig) -> dict:
        started_at = time.perf_counter()
        cases, _ = await self.repository.list_cases(eval_set_id, page=1, page_size=10000, filters={})
        resolved_case_concurrency = run_config.case_concurrency_override or self.eval_case_concurrency
        resolved_commit_batch_size = run_config.commit_batch_size_override or self.eval_result_commit_batch_size
        semaphore = asyncio.Semaphore(resolved_case_concurrency)
        pending_results: list[dict[str, Any]] = []
        completed_count = 0
        total_cases = len(cases)
        flush_lock = asyncio.Lock()
        retrieve_ms = 0.0
        commit_ms = 0.0

        async def evaluate(case: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                result, elapsed_ms = await self._evaluate_case(run_id, eval_set_id, case, run_config)
            nonlocal retrieve_ms
            retrieve_ms += elapsed_ms
            await commit_progress(result)
            return result

        async def commit_progress(result: dict[str, Any]) -> None:
            nonlocal completed_count
            async with flush_lock:
                pending_results.append(strip_internal_fields(result))
                completed_count += 1
                should_flush = len(pending_results) >= resolved_commit_batch_size or completed_count == total_cases
                if not should_flush:
                    return
                batch = list(pending_results)
                pending_results.clear()
                commit_started = time.perf_counter()
                await self.repository.save_eval_run_results(run_id, batch)
                await self.repository.update_eval_run(
                    run_id,
                    {
                        "progress": {
                            "completed_cases": completed_count,
                            "total_cases": total_cases,
                            "percent": (completed_count / total_cases) if total_cases else 0.0,
                            "updated_at": datetime.now(timezone.utc),
                        }
                    },
                )
                nonlocal commit_ms
                commit_ms += elapsed_ms(commit_started)

        result_docs = await asyncio.gather(*(evaluate(case) for case in cases))
        metric_items = [result["metrics_model"] for result in result_docs]
        summary_started = time.perf_counter()
        summary = summarize_metrics(metric_items).model_dump()
        summary_ms = elapsed_ms(summary_started)
        timing = {
            "total_ms": elapsed_ms(started_at),
            "retrieve_ms": round(retrieve_ms, 2),
            "commit_ms": round(commit_ms, 2),
            "summary_ms": round(summary_ms, 2),
            "cases": total_cases,
        }
        await self.repository.update_eval_run(
            run_id,
            {
                "status": "completed",
                "summary": summary,
                "timing": timing,
                "progress": {
                    "completed_cases": total_cases,
                    "total_cases": total_cases,
                    "percent": 1.0 if total_cases else 0.0,
                    "updated_at": datetime.now(timezone.utc),
                },
                "completed_at": datetime.now(timezone.utc),
            },
        )
        return {"summary": summary, "timing": timing}

    async def _evaluate_case(self, run_id: str, eval_set_id: str, case: dict[str, Any], config: EvalRunConfig) -> tuple[dict[str, Any], float]:
        retrieve_started = time.perf_counter()
        candidates, _diagnostics = await self.retriever.retrieve(case["question"], top_k=config.retrieval_top_n)
        kept = [candidate for candidate in candidates if candidate_score(candidate) >= config.similarity_threshold][: config.configured_k]
        retrieved_chunk_ids = [str(candidate.chunk_id) for candidate in kept]
        expected_chunk_ids = list(case.get("expected_retrieved_chunk_ids") or [])
        metrics = calculate_case_metrics(expected_chunk_ids, retrieved_chunk_ids, configured_k=config.configured_k)
        failure_reasons = failure_reasons_for(metrics, config.configured_k)
        diagnostics = {
            "configured_k": config.configured_k,
            "effective_k": metrics.effective_k,
            "similarity_threshold": config.similarity_threshold,
            "expected_chunk_ids": expected_chunk_ids,
            "retrieved_chunk_ids": retrieved_chunk_ids,
            "matched_chunk_ids": metrics.matched_chunk_ids,
            "retrieved_contexts": [retrieved_context(candidate, expected_chunk_ids) for candidate in kept],
            "failure_reasons": failure_reasons,
        }
        return {
            "_id": f"{run_id}:{case['case_id']}",
            "run_id": run_id,
            "eval_set_id": eval_set_id,
            "case_id": case["case_id"],
            "question": case["question"],
            "eval_type": case["eval_type"],
            "question_style": case["question_style"],
            "difficulty": case["difficulty"],
            "category": case["category"],
            "metrics": metrics.model_dump(exclude={"effective_k", "matched_chunk_ids"}),
            "metrics_model": metrics,
            "diagnostics": diagnostics,
            "created_at": datetime.now(timezone.utc),
        }, elapsed_ms(retrieve_started)

    async def get_eval_run(self, run_id: str) -> dict | None:
        return await self.repository.get_eval_run(run_id)

    async def list_eval_runs(self, eval_set_id: str, limit: int = 50, skip: int = 0) -> list[dict]:
        return await self.repository.list_eval_runs(eval_set_id, limit=limit, skip=skip)

    async def list_eval_run_results(self, run_id: str, page: int = 1, page_size: int = 20, filters: dict[str, Any] | None = None) -> tuple[list[dict], int]:
        return await self.repository.list_eval_run_results(run_id, page=page, page_size=page_size, filters=filters)


def run_config_path(eval_set: dict[str, Any]):
    from pathlib import Path

    return Path(str(eval_set["source_path"]))


def is_chunk_eval_set(eval_set: dict[str, Any]) -> bool:
    eval_type_distribution = (eval_set.get("config") or {}).get("eval_type_distribution") or {}
    keys = set(eval_type_distribution)
    return bool(keys) and keys.issubset(CHUNK_EVAL_TYPES)


def candidate_score(candidate: Any) -> float:
    return float(getattr(candidate, "final_score", 0.0) or 0.0)


def retrieved_context(candidate: Any, expected_chunk_ids: list[str]) -> dict[str, Any]:
    chunk = getattr(candidate, "chunk", None) or {}
    faq = getattr(candidate, "faq", None) or {}
    chunk_id = str(candidate.chunk_id)
    return {
        "chunk_id": chunk_id,
        "parent_faq_id": str(getattr(candidate, "faq_id", "") or ""),
        "score": candidate_score(candidate),
        "matched": chunk_id in set(expected_chunk_ids),
            "content": repair_text(str(chunk.get("chunkText") or chunk.get("chunk_text") or chunk.get("content") or "")),
        "source_url": str(chunk.get("sourceUrl") or chunk.get("source_url") or faq.get("sourceUrl") or ""),
    }


def failure_reasons_for(metrics, configured_k: int) -> list[str]:
    reasons: list[str] = []
    if metrics.hit_at_k == 0:
        reasons.append("miss")
    if metrics.context_recall_at_k < 1.0:
        reasons.append("low_recall")
    if metrics.mrr_at_k and metrics.mrr_at_k < 1.0:
        reasons.append("low_rank")
    if metrics.effective_k == 0:
        reasons.append("zero_effective_k")
    if metrics.precision_at_configured_k < metrics.precision_at_effective_k and metrics.effective_k < configured_k:
        reasons.append("threshold_filtered")
    if metrics.hit_at_k and metrics.precision_at_effective_k < 0.5:
        reasons.append("too_many_noise_chunks")
    return reasons


def strip_internal_fields(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "metrics_model"}


def elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)
