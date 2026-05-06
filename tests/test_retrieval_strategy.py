import json
from pathlib import Path

from app.services.ingest_service import IngestService
from app.services.retrieval_service import QueryProcessor


def test_query_processor_expands_nonstandard_enterprise_wechat_query():
    plan = QueryProcessor().build_plan("企微能不能走网银？")

    assert plan.normalized_query == "企微能不能走网银"
    assert "企业微信" in plan.canonical_terms
    assert "支付" in plan.canonical_terms
    assert "企微" in plan.synonym_terms
    assert "企业微信是否支持网银支付" in plan.rewrite_queries
    assert "京东企业购企业微信端支持哪些支付方式" in plan.rewrite_queries


def test_cleaned_jsonl_mapping_preserves_retrieval_fields():
    service = IngestService(None, None, None, None, None)
    row = json.loads(Path("exports/jd_help_faq.cleaned.jsonl").read_text(encoding="utf-8").splitlines()[0])

    item = service._cleaned_faq_to_storage_dict(row)

    assert item["id"] == row["id"]
    assert item["answer"] == row["answer_clean"]
    assert item["embeddingText"] == row["embedding_text"]
    assert item["sourceUrl"] == row["url"]
    assert item["categoryL1"] == row["category_l1"]
    assert item["docType"] == row["doc_type"]
    assert item["status"] == row["status"]
    assert item["searchEnabled"] is row["search_enabled"]


def test_cleaned_chunk_mapping_uses_embedding_text_for_dense_and_index_text_for_keyword():
    service = IngestService(None, None, None, None, None)
    row = json.loads(Path("exports/jd_help_faq.chunks.jsonl").read_text(encoding="utf-8").splitlines()[0])

    chunk = service._cleaned_chunk_to_storage_dict(row)

    assert chunk["id"] == row["id"]
    assert chunk["faqId"] == row["parent_id"]
    assert chunk["embeddingText"] == row["embedding_text"]
    assert row["index_text"] in chunk["indexText"]
    assert "答案片段：" in chunk["rerankText"]
    assert chunk["sourceUrl"] == row["url"]
    assert chunk["searchEnabled"] is row["search_enabled"]
