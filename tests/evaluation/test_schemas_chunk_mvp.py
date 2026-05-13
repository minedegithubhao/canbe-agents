from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.evaluation.schemas import EvalRunConfig, EvalSetGenerateRequest


def test_generate_request_defaults_to_chunk_retrieval_distributions():
    request = EvalSetGenerateRequest()

    assert request.eval_type_distribution == {"single_chunk": 0.7, "multi_chunk": 0.3}
    assert request.question_style_distribution == {
        "original": 0.3,
        "colloquial": 0.4,
        "synonym": 0.2,
        "abbreviated": 0.1,
    }
    assert request.difficulty_distribution == {"easy": 0.3, "medium": 0.5, "hard": 0.2}


def test_generate_request_rejects_legacy_eval_type():
    with pytest.raises(ValidationError) as exc:
        EvalSetGenerateRequest(eval_type_distribution={"single_faq_equivalent": 1.0})

    assert "unsupported eval_type" in str(exc.value)


def test_generate_request_rejects_distribution_that_does_not_sum_to_one():
    with pytest.raises(ValidationError) as exc:
        EvalSetGenerateRequest(question_style_distribution={"original": 0.6, "colloquial": 0.6})

    assert "must sum to 1.0" in str(exc.value)


def test_eval_run_config_defaults_match_mvp_retrieval_settings():
    config = EvalRunConfig()

    assert config.configured_k == 5
    assert config.retrieval_top_n == 20
    assert config.similarity_threshold == 0.72
    assert config.rerank_enabled is True
