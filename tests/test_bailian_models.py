import httpx

from app.retrieval import Candidate, Embedder, Reranker
from app.settings import get_settings


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def test_bailian_embedder_uses_compatible_embeddings_api(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("BAILIAN_API_KEY", "")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("BAILIAN_EMBEDDING_MODEL", "text-embedding-v4")
    monkeypatch.setenv("BAILIAN_EMBEDDING_DIMENSION", "4")
    monkeypatch.setenv("BAILIAN_EMBEDDING_BATCH_SIZE", "1")

    calls = []

    def fake_post(self, url, headers=None, json=None):
        calls.append({"url": url, "headers": headers, "json": json})
        embedding = [0.1, 0.2, 0.3, 0.4] if len(calls) == 1 else [0.4, 0.3, 0.2, 0.1]
        return FakeResponse(
            {
                "data": [
                    {"index": 0, "embedding": embedding},
                ]
            }
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    embedder = Embedder()
    vectors = embedder.encode_dense(["企微能不能网银支付", "退货邮费谁出"])

    assert vectors == [[0.1, 0.2, 0.3, 0.4], [0.4, 0.3, 0.2, 0.1]]
    assert embedder.status == "bailian_ok"
    assert len(calls) == 2
    assert calls[0]["url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
    assert calls[0]["headers"]["Authorization"] == "Bearer test-key"
    assert calls[0]["json"]["model"] == "text-embedding-v4"
    assert calls[0]["json"]["dimensions"] == 4
    assert calls[0]["json"]["input"] == ["企微能不能网银支付"]
    assert calls[1]["json"]["input"] == ["退货邮费谁出"]

    get_settings.cache_clear()


def test_bailian_reranker_maps_scores_to_candidates(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("BAILIAN_API_KEY", "")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("BAILIAN_RERANK_MODEL", "qwen3-rerank")

    calls = []

    def fake_post(self, url, headers=None, json=None):
        calls.append({"url": url, "headers": headers, "json": json})
        return FakeResponse(
            {
                "results": [
                    {"index": 1, "relevance_score": 0.92},
                    {"index": 0, "relevance_score": 0.31},
                ]
            }
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    candidates = [
        Candidate(
            chunk_id="c1",
            faq_id="f1",
            score=0.1,
            source="dense",
            chunk={"rerankText": "企业微信支持微信支付"},
        ),
        Candidate(
            chunk_id="c2",
            faq_id="f2",
            score=0.1,
            source="dense",
            chunk={"rerankText": "企业微信后续可支持网银支付"},
        ),
    ]

    reranker = Reranker()
    ranked = reranker.rerank("企微能不能用网银", candidates)

    assert [item.chunk_id for item in ranked] == ["c2", "c1"]
    assert ranked[0].rerank_score == 0.92
    assert reranker.status == "bailian_ok"
    assert calls[0]["url"] == "https://dashscope.aliyuncs.com/compatible-api/v1/reranks"
    assert calls[0]["headers"]["Authorization"] == "Bearer test-key"
    assert calls[0]["json"]["model"] == "qwen3-rerank"
    assert calls[0]["json"]["top_n"] == 2

    get_settings.cache_clear()
