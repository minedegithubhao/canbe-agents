from app.services import chat_service
from app.services.experiment_runtime import (
    ExperimentRuntime,
    FALLBACK_ANSWER,
    OUT_OF_SCOPE_ANSWER,
    OUT_OF_SCOPE_HINTS,
    evidence_from_faq,
)


def test_runtime_returns_trace_sections():
    runtime = ExperimentRuntime(None, None)

    sections = runtime.empty_trace()

    assert sections == [
        "input",
        "query_processing",
        "retrieval",
        "fusion",
        "rerank",
        "generation",
        "judgement",
        "verdict",
    ]


def test_runtime_literals_are_readable_utf8_text():
    assert "order status" in OUT_OF_SCOPE_HINTS
    assert "logistics" in OUT_OF_SCOPE_HINTS
    assert FALLBACK_ANSWER == "No highly relevant public FAQ was found for this question. Try rephrasing it or browse the help center categories."
    assert OUT_OF_SCOPE_ANSWER == "This assistant only answers from public JD Help Center FAQs and cannot access personalized data like orders, logistics, payments, refunds, or account privacy details."
    assert evidence_from_faq({}, 0.5)["source"] == "JD Help Center Public FAQ"


def test_chat_service_does_not_define_extra_all_exports():
    assert not hasattr(chat_service, "__all__")
