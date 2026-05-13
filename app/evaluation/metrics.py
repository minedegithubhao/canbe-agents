from __future__ import annotations

from app.evaluation.schemas import EvalCaseMetrics, EvalRunSummary


def calculate_case_metrics(
    expected_chunk_ids: list[str],
    retrieved_chunk_ids: list[str],
    configured_k: int,
) -> EvalCaseMetrics:
    expected = list(dict.fromkeys(expected_chunk_ids))
    retrieved = list(dict.fromkeys(retrieved_chunk_ids))
    expected_set = set(expected)
    matched_chunk_ids = [chunk_id for chunk_id in retrieved if chunk_id in expected_set]
    matched_count = len(matched_chunk_ids)
    effective_k = len(retrieved)
    first_match_rank = next((index for index, chunk_id in enumerate(retrieved, start=1) if chunk_id in expected_set), None)
    return EvalCaseMetrics(
        hit_at_k=1 if matched_count else 0,
        context_recall_at_k=_ratio(matched_count, len(expected)),
        mrr_at_k=(1 / first_match_rank) if first_match_rank else 0.0,
        precision_at_configured_k=_ratio(matched_count, configured_k),
        precision_at_effective_k=_ratio(matched_count, effective_k),
        effective_k=effective_k,
        matched_chunk_ids=matched_chunk_ids,
    )


def summarize_metrics(metrics: list[EvalCaseMetrics]) -> EvalRunSummary:
    total = len(metrics)
    return EvalRunSummary(
        total=total,
        hit_at_k=_average([item.hit_at_k for item in metrics]),
        context_recall_at_k=_average([item.context_recall_at_k for item in metrics]),
        mrr_at_k=_average([item.mrr_at_k for item in metrics]),
        precision_at_configured_k=_average([item.precision_at_configured_k for item in metrics]),
        precision_at_effective_k=_average([item.precision_at_effective_k for item in metrics]),
        avg_effective_k=_average([item.effective_k for item in metrics]),
        zero_context_rate=_ratio(sum(1 for item in metrics if item.effective_k == 0), total),
    )


def _ratio(count: int | float, denominator: int | float) -> float:
    return float(count) / float(denominator) if denominator else 0.0


def _average(values: list[int | float]) -> float:
    return sum(float(value) for value in values) / len(values) if values else 0.0
