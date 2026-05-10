from __future__ import annotations

from typing import Any

from app.schemas.rag_lab.eval import (
    EvalCasePayload,
    EvalCaseRecord,
    EvalDocumentInput,
    EvalSetRecord,
)


class EvalService:
    def __init__(self, eval_repository: Any) -> None:
        self.eval_repository = eval_repository

    def list_eval_sets(self) -> list[dict[str, Any]]:
        repository = self._require_repository()
        list_method = self._get_repository_method(repository, "list_eval_sets")
        if list_method is None:
            raise ValueError("eval_repository must implement list_eval_sets()")
        return [self._serialize_eval_set(item) for item in list_method()]

    def case_from_document(self, doc: dict[str, Any]) -> dict[str, Any]:
        normalized_doc = self._normalize_document(doc)
        source_url = normalized_doc.sourceUrl
        topic = self._derive_topic(normalized_doc)
        payload = EvalCasePayload(
            external_id=str(normalized_doc.id),
            query=normalized_doc.question,
            expected_answer=normalized_doc.answer,
            source_url=source_url,
            labels={
                "topic": topic,
            },
        )
        return payload.model_dump()

    def generate_cases_from_documents(
        self, docs: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return [self.case_from_document(doc) for doc in docs]

    def create_eval_set_from_documents(
        self,
        *,
        code: str,
        name: str,
        docs: list[dict[str, Any]],
        dataset_id: int | None = None,
        description: str | None = None,
        generation_strategy: str | None = None,
    ) -> dict[str, Any]:
        repository = self._require_repository()
        create_eval_set = self._require_repository_method(
            repository, "create_eval_set", "create_eval_set_from_documents"
        )
        eval_set = create_eval_set(
            code=code,
            name=name,
            dataset_id=dataset_id,
            description=description,
            generation_strategy=generation_strategy,
        )
        serialized_eval_set = self._serialize_eval_set(eval_set)
        generated_cases = self.generate_cases_from_documents(docs)

        add_case = self._get_repository_method(repository, "add_case")
        if add_case is not None and serialized_eval_set.get("id") is not None:
            persisted_cases = [
                self._serialize_case(
                    add_case(
                        eval_set_id=serialized_eval_set["id"],
                        case_payload=case_payload,
                    )
                )
                for case_payload in generated_cases
            ]
        else:
            persisted_cases = [
                self._wrap_case_payload(
                    eval_set_id=serialized_eval_set.get("id"),
                    case_payload=case_payload,
                )
                for case_payload in generated_cases
            ]

        return {
            "eval_set": serialized_eval_set,
            "cases": persisted_cases,
        }

    def add_case(
        self,
        *,
        eval_set_id: int,
        case: EvalCasePayload | dict[str, Any],
    ) -> dict[str, Any]:
        payload = self._normalize_case(case)
        repository = self._require_repository()
        add_case = self._require_repository_method(repository, "add_case", "add_case")
        created = add_case(
            eval_set_id=eval_set_id,
            case_payload=payload.model_dump(),
        )
        return self._serialize_case(created)

    def replace_case(
        self,
        *,
        case_id: int,
        replacement: EvalCasePayload | dict[str, Any],
    ) -> dict[str, Any]:
        payload = self._normalize_case(replacement)
        repository = self._require_repository()
        update_case = self._require_repository_method(
            repository, "update_case", "replace_case"
        )
        updated = update_case(
            case_id=case_id,
            case_payload=payload.model_dump(),
        )
        return self._serialize_case(updated)

    def update_case(
        self,
        *,
        case_id: int,
        replacement: EvalCasePayload | dict[str, Any],
    ) -> dict[str, Any]:
        return self.replace_case(case_id=case_id, replacement=replacement)

    def _normalize_case(
        self, case: EvalCasePayload | dict[str, Any]
    ) -> EvalCasePayload:
        if isinstance(case, EvalCasePayload):
            return EvalCasePayload.model_validate(case)
        return EvalCasePayload.model_validate(case)

    def _normalize_document(self, doc: dict[str, Any]) -> EvalDocumentInput:
        return EvalDocumentInput.model_validate(doc)

    def _require_repository(self) -> Any:
        if self.eval_repository is None:
            raise ValueError("eval_repository is required for manual case maintenance")
        return self.eval_repository

    def _require_repository_method(
        self, repository: Any, method_name: str, operation: str
    ) -> Any:
        method = self._get_repository_method(repository, method_name)
        if method is None:
            raise ValueError(
                f"eval_repository must implement {method_name}() for {operation}"
            )
        return method

    def _get_repository_method(self, repository: Any, method_name: str) -> Any | None:
        method = getattr(repository, method_name, None)
        if method is None or not callable(method):
            return None
        return method

    def _serialize_case(self, case: Any) -> dict[str, Any]:
        record = EvalCaseRecord.model_validate(
            case
            if isinstance(case, dict)
            else {
                "id": getattr(case, "id", None),
                "eval_set_id": getattr(case, "eval_set_id", None),
                "case_payload": getattr(case, "case_payload", None),
            }
        )
        return record.model_dump()

    def _wrap_case_payload(
        self, *, eval_set_id: int | None, case_payload: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "id": None,
            "eval_set_id": eval_set_id,
            "case_payload": case_payload,
        }

    def _serialize_eval_set(self, eval_set: Any) -> dict[str, Any]:
        record = EvalSetRecord.model_validate(
            eval_set
            if isinstance(eval_set, dict)
            else {
                "id": getattr(eval_set, "id", None),
                "code": getattr(eval_set, "code", None),
                "name": getattr(eval_set, "name", None),
                "dataset_id": getattr(eval_set, "dataset_id", None),
                "description": getattr(eval_set, "description", None),
                "generation_strategy": getattr(eval_set, "generation_strategy", None),
            }
        )
        return record.model_dump()

    def _derive_topic(self, doc: EvalDocumentInput) -> str:
        for key in ("category", "topic"):
            value = getattr(doc, key)
            if isinstance(value, str):
                normalized = value.strip().lower().replace(" ", "_")
                if normalized:
                    return normalized
        return "general"
