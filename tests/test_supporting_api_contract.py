from conftest import get_json, post_json


def test_categories_contract(require_api, api_base_url: str) -> None:
    response = get_json(api_base_url, "/faq/categories")
    assert isinstance(response, (list, dict))

    categories = response.get("items", response) if isinstance(response, dict) else response
    assert isinstance(categories, list)
    if not categories:
        return

    first = categories[0]
    assert isinstance(first, dict)
    assert "id" in first or "category" in first
    assert "name" in first or "categoryName" in first


def test_hot_questions_contract(require_api, api_base_url: str) -> None:
    response = get_json(api_base_url, "/faq/hot-questions")
    assert isinstance(response, (list, dict))

    questions = response.get("items", response) if isinstance(response, dict) else response
    assert isinstance(questions, list)
    if not questions:
        return

    first = questions[0]
    assert isinstance(first, dict)
    assert "question" in first or "title" in first


def test_feedback_contract(require_api, api_base_url: str) -> None:
    chat = post_json(api_base_url, "/faq/chat", {"query": "忘记密码怎么办？", "sessionId": "pytest_feedback"})
    trace_id = chat["traceId"]

    response = post_json(
        api_base_url,
        "/faq/feedback",
        {
            "traceId": trace_id,
            "sessionId": "pytest_feedback",
            "feedbackType": "useful",
            "comment": "pytest contract check",
        },
    )

    assert isinstance(response, dict)
    assert response.get("success") is True or response.get("status") in {"ok", "success"}


def test_build_index_starts_background_task(require_api, api_base_url: str) -> None:
    response = post_json(api_base_url, "/admin/ingest/build-index", {}, timeout=30)

    assert response.get("ok") is True
    task = response.get("task")
    assert isinstance(task, dict)
    task_id = task.get("taskId")
    assert isinstance(task_id, str)
    assert task_id.startswith("idx_")
    assert task.get("status") in {"running", "completed"}

    status = get_json(api_base_url, f"/admin/ingest/tasks/{task_id}", timeout=10)
    assert isinstance(status, dict)
    assert status.get("ok") is True
    assert status.get("task", {}).get("taskId") == task_id
