from app.services.eval_service import EvalService
from pydantic import ValidationError


class StubEvalRepository:
    def __init__(self) -> None:
        self.create_eval_set_calls: list[dict[str, object]] = []
        self.add_case_calls: list[dict[str, object]] = []
        self.update_case_calls: list[dict[str, object]] = []

    def create_eval_set(
        self,
        *,
        code: str,
        name: str,
        dataset_id: int | None = None,
        description: str | None = None,
        generation_strategy: str | None = None,
    ) -> dict[str, object]:
        self.create_eval_set_calls.append(
            {
                "code": code,
                "name": name,
                "dataset_id": dataset_id,
                "description": description,
                "generation_strategy": generation_strategy,
            }
        )
        return {
            "id": 7,
            "code": code,
            "name": name,
            "dataset_id": dataset_id,
            "description": description,
            "generation_strategy": generation_strategy,
        }

    def add_case(self, *, eval_set_id: int, case_payload: dict[str, object]) -> dict[str, object]:
        self.add_case_calls.append(
            {
                "eval_set_id": eval_set_id,
                "case_payload": case_payload,
            }
        )
        return {
            "id": 101,
            "eval_set_id": eval_set_id,
            "case_payload": case_payload,
        }

    def update_case(self, *, case_id: int, case_payload: dict[str, object]) -> dict[str, object]:
        self.update_case_calls.append(
            {
                "case_id": case_id,
                "case_payload": case_payload,
            }
        )
        return {
            "id": case_id,
            "eval_set_id": 9,
            "case_payload": case_payload,
        }


class NoPersistenceEvalRepository:
    def create_eval_set(
        self,
        *,
        code: str,
        name: str,
        dataset_id: int | None = None,
        description: str | None = None,
        generation_strategy: str | None = None,
    ) -> dict[str, object]:
        return {
            "id": 7,
            "code": code,
            "name": name,
            "dataset_id": dataset_id,
            "description": description,
            "generation_strategy": generation_strategy,
        }


def test_eval_service_generates_basic_case_from_document():
    service = EvalService(None)
    doc = {
        "id": "doc-1",
        "question": "What is the support email?",
        "answer": "Use support@example.com for account help.",
        "sourceUrl": "https://example.com/help/account",
        "category": "support",
    }

    case = service.case_from_document(doc)

    assert case == {
        "external_id": "doc-1",
        "query": "What is the support email?",
        "expected_answer": "Use support@example.com for account help.",
        "source_url": "https://example.com/help/account",
        "labels": {
            "topic": "support",
            "difficulty": "medium",
            "source_type": "cleaned_document",
        },
        "behavior": {
            "should_answer": True,
            "should_cite_sources": True,
            "should_refuse": False,
        },
        "scoring_profile": {
            "profile": "default",
            "answer_correctness_weight": 0.4,
            "faithfulness_weight": 0.3,
            "source_grounding_weight": 0.2,
            "fallback_behavior_weight": 0.1,
        },
    }


def test_create_eval_set_from_documents_creates_eval_set_and_persists_generated_cases():
    repository = StubEvalRepository()
    service = EvalService(repository)

    created = service.create_eval_set_from_documents(
        code="faq-smoke",
        name="FAQ Smoke",
        dataset_id=12,
        description="Smoke coverage for FAQ docs",
        generation_strategy="document_seeded",
        docs=[
            {
                "id": "doc-1",
                "question": "How do I reset my password?",
                "answer": "Use the password reset form.",
                "sourceUrl": "https://example.com/help/reset-password",
            },
            {
                "id": "doc-2",
                "question": "Where can invoices be downloaded?",
                "answer": "Invoices are available on the billing page.",
                "sourceUrl": "https://example.com/help/billing",
            },
        ],
    )

    assert repository.create_eval_set_calls == [
        {
            "code": "faq-smoke",
            "name": "FAQ Smoke",
            "dataset_id": 12,
            "description": "Smoke coverage for FAQ docs",
            "generation_strategy": "document_seeded",
        }
    ]
    assert [call["eval_set_id"] for call in repository.add_case_calls] == [7, 7]
    assert created["eval_set"]["id"] == 7
    assert [case["case_payload"]["external_id"] for case in created["cases"]] == [
        "doc-1",
        "doc-2",
    ]
    assert all(case["case_payload"]["behavior"]["should_cite_sources"] for case in created["cases"])


def test_create_eval_set_from_documents_returns_wrapped_cases_when_persistence_is_skipped():
    repository = NoPersistenceEvalRepository()
    service = EvalService(repository)

    created = service.create_eval_set_from_documents(
        code="faq-smoke",
        name="FAQ Smoke",
        docs=[
            {
                "id": "doc-1",
                "question": "How do I reset my password?",
                "answer": "Use the password reset form.",
                "sourceUrl": "https://example.com/help/reset-password",
            }
        ],
    )

    assert created["cases"] == [
        {
            "id": None,
            "eval_set_id": 7,
            "case_payload": {
                "external_id": "doc-1",
                "query": "How do I reset my password?",
                "expected_answer": "Use the password reset form.",
                "source_url": "https://example.com/help/reset-password",
                "labels": {
                    "topic": "general",
                    "difficulty": "medium",
                    "source_type": "cleaned_document",
                },
                "behavior": {
                    "should_answer": True,
                    "should_cite_sources": True,
                    "should_refuse": False,
                },
                "scoring_profile": {
                    "profile": "default",
                    "answer_correctness_weight": 0.4,
                    "faithfulness_weight": 0.3,
                    "source_grounding_weight": 0.2,
                    "fallback_behavior_weight": 0.1,
                },
            },
        }
    ]


def test_add_case_persists_normalized_payload_through_repository():
    repository = StubEvalRepository()
    service = EvalService(repository)

    created = service.add_case(
        eval_set_id=7,
        case={
            "external_id": "case-7",
            "query": "How do I reset my password?",
            "expected_answer": "Use the password reset form.",
            "source_url": "https://example.com/help/reset-password",
        },
    )

    assert repository.add_case_calls == [
        {
            "eval_set_id": 7,
            "case_payload": {
                "external_id": "case-7",
                "query": "How do I reset my password?",
                "expected_answer": "Use the password reset form.",
                "source_url": "https://example.com/help/reset-password",
                "labels": {
                    "topic": "general",
                    "difficulty": "medium",
                    "source_type": "cleaned_document",
                },
                "behavior": {
                    "should_answer": True,
                    "should_cite_sources": True,
                    "should_refuse": False,
                },
                "scoring_profile": {
                    "profile": "default",
                    "answer_correctness_weight": 0.4,
                    "faithfulness_weight": 0.3,
                    "source_grounding_weight": 0.2,
                    "fallback_behavior_weight": 0.1,
                },
            },
        }
    ]
    assert created["id"] == 101
    assert created["eval_set_id"] == 7


def test_update_case_persists_normalized_payload_through_repository():
    repository = StubEvalRepository()
    service = EvalService(repository)

    updated = service.update_case(
        case_id=55,
        replacement={
            "external_id": "case-55",
            "query": "Where can billing invoices be downloaded?",
            "expected_answer": "Invoices are available on the billing page.",
            "source_url": "https://example.com/help/billing",
        },
    )

    assert repository.update_case_calls == [
        {
            "case_id": 55,
            "case_payload": {
                "external_id": "case-55",
                "query": "Where can billing invoices be downloaded?",
                "expected_answer": "Invoices are available on the billing page.",
                "source_url": "https://example.com/help/billing",
                "labels": {
                    "topic": "general",
                    "difficulty": "medium",
                    "source_type": "cleaned_document",
                },
                "behavior": {
                    "should_answer": True,
                    "should_cite_sources": True,
                    "should_refuse": False,
                },
                "scoring_profile": {
                    "profile": "default",
                    "answer_correctness_weight": 0.4,
                    "faithfulness_weight": 0.3,
                    "source_grounding_weight": 0.2,
                    "fallback_behavior_weight": 0.1,
                },
            },
        }
    ]
    assert updated["id"] == 55
    assert updated["case_payload"]["query"] == "Where can billing invoices be downloaded?"


def test_update_case_rejects_partial_payloads():
    repository = StubEvalRepository()
    service = EvalService(repository)

    try:
        service.update_case(
            case_id=55,
            replacement={
                "query": "Where can billing invoices be downloaded?",
            },
        )
    except ValidationError as exc:
        assert "external_id" in str(exc)
        assert "expected_answer" in str(exc)
    else:
        raise AssertionError("Expected update_case to reject partial payloads")


def test_create_eval_set_from_documents_rejects_malformed_repository_eval_set_payload():
    class MalformedEvalSetRepository(NoPersistenceEvalRepository):
        def create_eval_set(
            self,
            *,
            code: str,
            name: str,
            dataset_id: int | None = None,
            description: str | None = None,
            generation_strategy: str | None = None,
        ) -> dict[str, object]:
            return {
                "id": "not-an-int",
                "code": code,
                "name": name,
                "dataset_id": dataset_id,
                "description": description,
                "generation_strategy": generation_strategy,
            }

    service = EvalService(MalformedEvalSetRepository())

    try:
        service.create_eval_set_from_documents(
            code="faq-smoke",
            name="FAQ Smoke",
            docs=[],
        )
    except ValidationError as exc:
        assert "id" in str(exc)
    else:
        raise AssertionError("Expected malformed eval set payload to be rejected")


def test_add_case_rejects_malformed_repository_case_payload():
    class MalformedCaseRepository(StubEvalRepository):
        def add_case(
            self, *, eval_set_id: int, case_payload: dict[str, object]
        ) -> dict[str, object]:
            return {
                "id": 101,
                "eval_set_id": eval_set_id,
                "case_payload": {
                    "query": "missing required fields",
                },
            }

    service = EvalService(MalformedCaseRepository())

    try:
        service.add_case(
            eval_set_id=7,
            case={
                "external_id": "case-7",
                "query": "How do I reset my password?",
                "expected_answer": "Use the password reset form.",
                "source_url": "https://example.com/help/reset-password",
            },
        )
    except ValidationError as exc:
        assert "external_id" in str(exc)
        assert "expected_answer" in str(exc)
    else:
        raise AssertionError("Expected malformed case payload to be rejected")


def test_case_from_document_uses_schema_defaults_even_without_source_url():
    service = EvalService(None)

    case = service.case_from_document(
        {
            "id": "doc-2",
            "question": "What changed in the migration?",
            "answer": "The migration added a composite index.",
        }
    )

    assert case["source_url"] is None
    assert case["labels"]["source_type"] == "cleaned_document"
    assert case["behavior"]["should_cite_sources"] is True
    assert case["scoring_profile"]["profile"] == "default"


def test_case_from_document_rejects_malformed_document_input_cleanly():
    service = EvalService(None)

    try:
        service.case_from_document(
            {
                "id": "doc-3",
                "question": "What changed in the migration?",
            }
        )
    except ValidationError as exc:
        assert "answer" in str(exc)
    else:
        raise AssertionError("Expected malformed document input to be rejected")


def test_add_case_rejects_repository_missing_required_method_cleanly():
    service = EvalService(NoPersistenceEvalRepository())

    try:
        service.add_case(
            eval_set_id=7,
            case={
                "external_id": "case-7",
                "query": "How do I reset my password?",
                "expected_answer": "Use the password reset form.",
                "source_url": "https://example.com/help/reset-password",
            },
        )
    except ValueError as exc:
        assert "add_case" in str(exc)
    else:
        raise AssertionError("Expected repository contract violation to be rejected")
