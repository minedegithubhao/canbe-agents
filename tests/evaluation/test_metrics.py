from __future__ import annotations

from app.evaluation.metrics import calculate_case_metrics, summarize_metrics


def test_case_metrics_use_first_matched_chunk_for_mrr():
    metrics = calculate_case_metrics(
        expected_chunk_ids=["chunk_a", "chunk_b"],
        retrieved_chunk_ids=["chunk_x", "chunk_b", "chunk_a"],
        configured_k=5,
    )

    assert metrics.hit_at_k == 1
    assert metrics.context_recall_at_k == 1.0
    assert metrics.mrr_at_k == 0.5
    assert metrics.precision_at_configured_k == 0.4
    assert metrics.precision_at_effective_k == 2 / 3


def test_case_metrics_handle_zero_effective_k():
    metrics = calculate_case_metrics(
        expected_chunk_ids=["chunk_a"],
        retrieved_chunk_ids=[],
        configured_k=5,
    )

    assert metrics.hit_at_k == 0
    assert metrics.context_recall_at_k == 0.0
    assert metrics.mrr_at_k == 0.0
    assert metrics.precision_at_configured_k == 0.0
    assert metrics.precision_at_effective_k == 0.0


def test_summarize_metrics_averages_case_metrics_and_tracks_effective_k():
    first = calculate_case_metrics(["chunk_a"], ["chunk_a", "chunk_x"], configured_k=5)
    second = calculate_case_metrics(["chunk_b"], [], configured_k=5)

    summary = summarize_metrics([first, second])

    assert summary.total == 2
    assert summary.hit_at_k == 0.5
    assert summary.context_recall_at_k == 0.5
    assert summary.mrr_at_k == 0.5
    assert summary.precision_at_configured_k == 0.1
    assert summary.precision_at_effective_k == 0.25
    assert summary.avg_effective_k == 1.0
    assert summary.zero_context_rate == 0.5
