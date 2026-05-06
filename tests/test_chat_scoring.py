import pytest

from app.models.retrieval import Candidate
from app.services.llm_service import clean_answer
from app.services.chat_service import ChatService, candidate_confidence, candidate_suggestions


def test_exact_standard_question_uses_raw_rerank_confidence_not_weighted_score():
    candidate = Candidate(
        chunk_id="chunk_1",
        faq_id="jd_help_292_553",
        score=0.03,
        source="dense+keyword",
        rerank_score=0.9666,
        ranking_score=1.2083,
        faq={"question": "如何查看自己申请的价格保护记录？"},
    )

    confidence = candidate_confidence(candidate, "如何查看自己申请的价格保护记录？")

    assert confidence == pytest.approx(0.9666)
    assert confidence >= 0.95


def test_candidate_question_candidates_include_stable_id_and_scores():
    candidate = Candidate(
        chunk_id="chunk_1",
        faq_id="jd_help_292_553",
        score=0.03,
        source="dense+keyword",
        rerank_score=0.72,
        ranking_score=0.9,
        faq={
            "id": "jd_help_292_553",
            "question": "如何查看自己申请的价格保护记录？",
            "docType": "operation_guide",
            "sourceUrl": "https://help.jd.com/user/issue/292-553.html",
        },
    )

    suggestions = candidate_suggestions([candidate], "价保记录在哪看")

    assert len(suggestions) == 1
    assert suggestions[0].id == "jd_help_292_553"
    assert suggestions[0].score == pytest.approx(0.72)
    assert suggestions[0].rankingScore == pytest.approx(0.9)
    assert suggestions[0].sourceUrl == "https://help.jd.com/user/issue/292-553.html"


def test_answer_cleaner_removes_internal_evidence_preamble():
    answer = "根据FAQ内容，卖家发货后查不到物流信息或物流跟踪异常，您可以在【我的订单】中点击【催单】。"

    cleaned = clean_answer(answer)

    assert cleaned.startswith("卖家发货后")
    assert "根据FAQ内容" not in cleaned


@pytest.mark.asyncio
async def test_candidate_id_direct_hit_returns_answer_without_retrieval():
    class FakeMongo:
        async def get_faq_by_id(self, faq_id):
            assert faq_id == "jd_help_292_553"
            return {
                "id": faq_id,
                "question": "如何查看自己申请的价格保护记录？",
                "answer": "您可在“我的-客户服务-价格保护-申请记录”里查看。",
                "categoryName": "特色服务 > 价格保护 > 价格保护申请",
                "source": "京东帮助中心公开 FAQ",
                "sourceUrl": "https://help.jd.com/user/issue/292-553.html",
                "docType": "operation_guide",
                "status": "active",
                "searchEnabled": True,
                "enabled": True,
                "suggestedQuestions": [],
            }

        async def save_chat_log(self, log):
            return None

    class FakeDeepSeek:
        status = "not_called"

        async def generate(self, query, evidences):
            self.status = "extractive_test"
            return evidences[0]["answer"]

    service = ChatService(FakeMongo(), retriever=None, deepseek=FakeDeepSeek())

    response = await service.chat(
        "如何查看自己申请的价格保护记录？",
        candidate_id="jd_help_292_553",
    )

    assert response.fallback is False
    assert response.confidence == 1.0
    assert response.sources[0].id == "jd_help_292_553"
    assert "申请记录" in response.answer
