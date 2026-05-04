from __future__ import annotations

import asyncio
import hashlib
import httpx
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.settings import get_settings


@dataclass(frozen=True)
class QueryPlan:
    raw_query: str
    normalized_query: str
    expanded_query: str
    rewrite_queries: list[str]
    canonical_terms: list[str]
    synonym_terms: list[str]
    allow_historical: bool
    prefer_agreement: bool
    intent: str


@dataclass
class Candidate:
    chunk_id: str
    faq_id: str
    score: float
    source: str
    dense_score: float = 0.0
    sparse_score: float = 0.0
    keyword_score: float = 0.0
    rrf_score: float = 0.0
    rerank_score: float = 0.0
    ranking_score: float = 0.0
    chunk: dict | None = None
    faq: dict | None = None
    matched_sources: set[str] = field(default_factory=set)

    @property
    def final_score(self) -> float:
        return self.ranking_score or self.rerank_score or self.rrf_score or self.score


class QueryProcessor:
    def __init__(self, path: Path | None = None) -> None:
        self.settings = get_settings()
        self.synonyms = load_synonyms(path or self.settings.jd_help_synonyms_path)

    def terms_for_text(self, text: str) -> tuple[list[str], list[str]]:
        normalized = normalize_query(text)
        compact = normalized.replace(" ", "")
        canonical_terms: list[str] = []
        synonym_terms: list[str] = []
        for entry in self.synonyms:
            canonical = str(entry["canonical"])
            aliases = list(entry["aliases"])
            if any(normalize_query(term).replace(" ", "") in compact for term in [canonical, *aliases]):
                canonical_terms.append(canonical)
                synonym_terms.extend(aliases)
        return unique(canonical_terms), unique(synonym_terms)

    def build_plan(self, query: str) -> QueryPlan:
        normalized = normalize_query(query)
        canonical_terms, synonym_terms = self.terms_for_text(normalized)
        expanded = " ".join(unique([normalized, *canonical_terms, *synonym_terms])) if canonical_terms else normalized
        intent = query_intent(normalized)
        return QueryPlan(
            raw_query=query,
            normalized_query=normalized,
            expanded_query=expanded,
            rewrite_queries=rewrite_query(normalized, canonical_terms, synonym_terms),
            canonical_terms=canonical_terms,
            synonym_terms=synonym_terms,
            allow_historical=contains_any(normalized, ["历史", "旧版", "已失效", "失效", "版本"]),
            prefer_agreement=contains_any(normalized, ["协议", "隐私政策", "隐私", "条款", "授权", "服务协议"]),
            intent=intent,
        )


class Embedder:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.status = "bailian_configured" if self.settings.bailian_effective_api_key else "bailian_unconfigured"
        self.dimension = self.settings.bailian_embedding_dimension

    def encode_dense(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        api_key = self.settings.bailian_effective_api_key
        if not api_key:
            raise RuntimeError("BAILIAN_API_KEY or DASHSCOPE_API_KEY is required")
        batch_size = max(1, self.settings.bailian_embedding_batch_size)
        if len(texts) > batch_size:
            vectors: list[list[float]] = []
            for start in range(0, len(texts), batch_size):
                vectors.extend(self.encode_dense(texts[start : start + batch_size]))
            return vectors
        url = f"{self.settings.bailian_embedding_base_url.rstrip('/')}/embeddings"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.settings.bailian_embedding_model,
            "input": texts,
            "dimensions": self.dimension,
            "encoding_format": "float",
        }
        with httpx.Client(timeout=self.settings.bailian_embedding_timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        vectors_by_index: dict[int, list[float]] = {}
        for position, item in enumerate(data.get("data") or []):
            vector = item.get("embedding")
            if isinstance(vector, list):
                vectors_by_index[int(item.get("index", position))] = [float(value) for value in vector]
        vectors = [vectors_by_index.get(index) for index in range(len(texts))]
        if any(vector is None for vector in vectors):
            self.status = "bailian_invalid_response"
            raise RuntimeError("Bailian embedding response does not contain all requested vectors")
        self.status = "bailian_ok"
        return [vector for vector in vectors if vector is not None]

    def encode_sparse(self, texts: list[str]) -> list[dict[int, float]]:
        return [sparse_tokens(text) for text in texts]


class Reranker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.status = "bailian_configured" if self.settings.bailian_effective_api_key else "bailian_unconfigured"

    def rerank(self, query: str, candidates: list[Candidate]) -> list[Candidate]:
        if not candidates:
            return []
        try:
            ranked = self._rerank_bailian(query, candidates)
            self.status = "bailian_ok"
            return ranked
        except Exception as exc:
            self.status = f"fallback_overlap_reranker: {type(exc).__name__}: {exc}"
            for candidate in candidates:
                candidate.rerank_score = overlap_score(query, candidate_text(candidate))
            return sorted(candidates, key=lambda item: item.rerank_score, reverse=True)

    def _rerank_bailian(self, query: str, candidates: list[Candidate]) -> list[Candidate]:
        api_key = self.settings.bailian_effective_api_key
        if not api_key:
            raise RuntimeError("BAILIAN_API_KEY or DASHSCOPE_API_KEY is required")
        payload = {
            "model": self.settings.bailian_rerank_model,
            "query": query,
            "documents": [candidate_text(candidate) for candidate in candidates],
            "top_n": len(candidates),
            "return_documents": False,
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=self.settings.bailian_rerank_timeout_seconds) as client:
            response = client.post(f"{self.settings.bailian_rerank_base_url.rstrip('/')}/reranks", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        scores: dict[int, float] = {}
        for item in extract_rerank_results(data):
            try:
                scores[int(item.get("index"))] = float(item.get("relevance_score", item.get("relevanceScore", item.get("score", 0.0))))
            except (AttributeError, TypeError, ValueError):
                continue
        if not scores:
            raise RuntimeError("Bailian rerank response does not contain scores")
        for index, candidate in enumerate(candidates):
            candidate.rerank_score = scores.get(index, 0.0)
        return sorted(candidates, key=lambda item: item.rerank_score, reverse=True)


class Retriever:
    def __init__(self, mongo: Any, milvus: Any, es: Any, embedder: Embedder, reranker: Reranker) -> None:
        self.settings = get_settings()
        self.mongo = mongo
        self.milvus = milvus
        self.es = es
        self.embedder = embedder
        self.reranker = reranker
        self.query_processor = QueryProcessor()

    async def retrieve(self, query: str, top_k: int | None = None) -> tuple[list[Candidate], dict[str, Any]]:
        final_top_k = top_k or self.settings.retrieval_final_top_k
        plan = self.query_processor.build_plan(query)
        dense_queries = unique([plan.normalized_query, *plan.rewrite_queries])
        keyword_queries = unique([plan.expanded_query, *plan.rewrite_queries])
        dense_lists: list[list[dict[str, Any]]] = []
        dense_hits = 0
        for dense_query in dense_queries:
            vector = (await asyncio.to_thread(self.embedder.encode_dense, [dense_query]))[0]
            hits = await self.milvus.dense_search(vector, self.settings.retrieval_dense_top_k)
            dense_hits += len(hits)
            dense_lists.append(hits)
        sparse_vector = (await asyncio.to_thread(self.embedder.encode_sparse, [plan.expanded_query]))[0]
        sparse_hits = await self.milvus.sparse_search(sparse_vector, self.settings.retrieval_sparse_top_k)
        keyword_lists: list[list[dict[str, Any]]] = []
        keyword_hits = 0
        for keyword_query in keyword_queries:
            hits = await self.es.keyword_search(
                keyword_query,
                self.settings.retrieval_keyword_top_k,
                allow_historical=plan.allow_historical,
                prefer_agreement=plan.prefer_agreement,
            )
            keyword_hits += len(hits)
            keyword_lists.append(hits)
        degraded = False
        if not any(dense_lists) and not sparse_hits and not any(keyword_lists):
            degraded = True
            keyword_lists = [await self.local_chunk_search(plan.expanded_query, self.settings.retrieval_keyword_top_k)]
        candidates = rrf([*dense_lists, sparse_hits, *keyword_lists], self.settings.retrieval_rrf_k)
        candidates = candidates[: max(final_top_k * self.settings.retrieval_rerank_candidate_multiplier, 20)]
        await self.hydrate(candidates)
        candidates = [candidate for candidate in candidates if candidate.chunk and candidate.faq and allowed(candidate, plan)]
        candidates = self.reranker.rerank(plan.normalized_query, candidates)
        apply_doc_type_weights(candidates, plan)
        candidates = group_by_business(candidates)[:final_top_k]
        return candidates, {
            "normalizedQuery": plan.normalized_query,
            "expandedQuery": plan.expanded_query,
            "rewriteQueries": plan.rewrite_queries,
            "canonicalTerms": plan.canonical_terms,
            "synonymTerms": plan.synonym_terms,
            "denseHits": dense_hits,
            "sparseHits": len(sparse_hits),
            "keywordHits": keyword_hits,
            "candidateCount": len(candidates),
            "degraded": degraded,
            "embedderStatus": self.embedder.status,
            "rerankerStatus": self.reranker.status,
            "milvusStatus": self.milvus.status,
            "elasticsearchStatus": self.es.status,
        }

    async def hydrate(self, candidates: list[Candidate]) -> None:
        chunks = {chunk["id"]: chunk for chunk in await self.mongo.get_chunks_by_ids([candidate.chunk_id for candidate in candidates])}
        faqs = await self.mongo.get_faqs_by_ids(list({candidate.faq_id for candidate in candidates}))
        for candidate in candidates:
            candidate.chunk = chunks.get(candidate.chunk_id)
            candidate.faq = faqs.get(candidate.faq_id)

    async def local_chunk_search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        scored = []
        for chunk in await self.mongo.list_enabled_chunks(limit=1000):
            score = text_score(query, str(chunk.get("indexText") or chunk.get("rerankText") or ""))
            if score > 0:
                scored.append({"chunkId": chunk["id"], "faqId": chunk["faqId"], "score": score, "source": "keyword"})
        return sorted(scored, key=lambda item: item["score"], reverse=True)[:top_k]


def normalize_query(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    chars: list[str] = []
    for char in normalized:
        if char.isascii() and char.isalnum():
            chars.append(char.lower())
        elif "\u4e00" <= char <= "\u9fff" or (not char.isascii() and char.isalnum()):
            chars.append(char)
        else:
            chars.append(" ")
    return re.sub(r"\s+", " ", "".join(chars)).strip()


def load_synonyms(path: Path) -> list[dict[str, list[str] | str]]:
    if not path.exists():
        return []
    entries: list[dict[str, list[str] | str]] = []
    current: dict[str, list[str] | str] | None = None
    in_aliases = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" ") and line.endswith(":"):
            if current:
                entries.append(current)
            current = {"canonical": line[:-1].strip(), "aliases": []}
            in_aliases = False
        elif current is not None:
            stripped = line.strip()
            if stripped.startswith("canonical:"):
                current["canonical"] = stripped.split(":", 1)[1].strip()
                in_aliases = False
            elif stripped.startswith("aliases:"):
                in_aliases = True
            elif in_aliases and stripped.startswith("-") and isinstance(current.get("aliases"), list):
                current["aliases"].append(stripped[1:].strip())
    if current:
        entries.append(current)
    return entries


def query_intent(normalized: str) -> str:
    if contains_any(normalized, ["怎么", "如何", "流程", "步骤", "怎样", "入口", "设置"]):
        return "operation"
    if contains_any(normalized, ["收费", "费用", "运费", "邮费", "服务费", "补偿", "赔付", "补差价"]):
        return "fee"
    if contains_any(normalized, ["协议", "隐私", "条款", "授权"]):
        return "agreement"
    return "general"


def rewrite_query(normalized: str, canonical_terms: list[str], synonym_terms: list[str]) -> list[str]:
    compact = normalized.replace(" ", "")
    rewrites: list[str] = []
    if ("企业微信" in canonical_terms or "企微" in synonym_terms or "企微" in compact) and "网银" in compact:
        rewrites.extend(["企业微信是否支持网银支付", "京东企业购企业微信端支持哪些支付方式"])
    if "企业微信" in canonical_terms or "企微" in compact:
        rewrites.append("企业微信支付方式有哪些")
    if "运费" in canonical_terms or "邮费" in synonym_terms:
        rewrites.append(compact.replace("邮费", "运费"))
    if "价格保护" in canonical_terms:
        rewrites.append(compact.replace("买贵了", "价格保护").replace("补差价", "价格保护"))
    if "发票" in canonical_terms:
        rewrites.append(compact.replace("开票", "发票"))
    return [item[:60] for item in unique(rewrites) if item and item != normalized][:3]


def rrf(lists: list[list[dict]], k: int) -> list[Candidate]:
    by_chunk: dict[str, Candidate] = {}
    for ranked in lists:
        for rank, item in enumerate(ranked, start=1):
            chunk_id = item.get("chunkId")
            faq_id = item.get("faqId")
            if not chunk_id or not faq_id:
                continue
            candidate = by_chunk.setdefault(chunk_id, Candidate(chunk_id=chunk_id, faq_id=faq_id, score=0.0, source=item.get("source") or "unknown"))
            source = item.get("source") or "unknown"
            candidate.matched_sources.add(source)
            candidate.rrf_score += 1.0 / (k + rank)
            score = float(item.get("score") or 0.0)
            if source == "dense":
                candidate.dense_score = max(candidate.dense_score, score)
            elif source == "sparse":
                candidate.sparse_score = max(candidate.sparse_score, score)
            elif source == "keyword":
                candidate.keyword_score = max(candidate.keyword_score, score)
    for candidate in by_chunk.values():
        candidate.score = candidate.rrf_score
        candidate.source = "+".join(sorted(candidate.matched_sources)) or candidate.source
    return sorted(by_chunk.values(), key=lambda item: item.rrf_score, reverse=True)


def allowed(candidate: Candidate, plan: QueryPlan) -> bool:
    faq = candidate.faq or {}
    chunk = candidate.chunk or {}
    doc_type = str(chunk.get("docType") or faq.get("docType") or "")
    if doc_type == "compound_qa":
        return False
    if plan.allow_historical and doc_type == "historical_rule":
        return True
    status = str(chunk.get("status") or faq.get("status") or "active")
    search_enabled = bool(chunk.get("searchEnabled", faq.get("searchEnabled", True)))
    return search_enabled and status == "active"


def apply_doc_type_weights(candidates: list[Candidate], plan: QueryPlan) -> None:
    weights = {
        "operation_guide": 1.15,
        "fee_standard": 1.15,
        "faq": 1.0,
        "policy_rule": 1.0,
        "service_intro": 0.9,
        "agreement": 0.65,
        "historical_rule": 0.0,
        "compound_qa": 0.0,
    }
    for candidate in candidates:
        faq = candidate.faq or {}
        chunk = candidate.chunk or {}
        doc_type = str(chunk.get("docType") or faq.get("docType") or "faq")
        weight = weights.get(doc_type, 1.0)
        if plan.intent == "operation" and doc_type == "operation_guide":
            weight = 1.25
        elif plan.intent == "fee" and doc_type == "fee_standard":
            weight = 1.25
        elif plan.prefer_agreement and doc_type == "agreement":
            weight = 1.1
        elif plan.allow_historical and doc_type == "historical_rule":
            weight = 1.0
        candidate.ranking_score = float(candidate.rerank_score or candidate.score) * weight


def group_by_business(candidates: list[Candidate]) -> list[Candidate]:
    best: dict[str, Candidate] = {}
    for candidate in candidates:
        key = business_key(candidate)
        if key not in best or candidate.final_score > best[key].final_score:
            best[key] = candidate
    return sorted(best.values(), key=lambda item: item.final_score, reverse=True)


def business_key(candidate: Candidate) -> str:
    faq = candidate.faq or {}
    chunk = candidate.chunk or {}
    for value in (faq.get("duplicateGroupId"), chunk.get("duplicateGroupId"), faq.get("parentId"), chunk.get("parentId"), faq.get("sourceUrl"), chunk.get("sourceUrl"), faq.get("question"), candidate.faq_id):
        text = str(value or "").strip()
        if text:
            return text
    return candidate.chunk_id


def sparse_tokens(text: str) -> dict[int, float]:
    weights: dict[int, float] = {}
    normalized = "".join(char.lower() if char.isalnum() else " " for char in text)
    tokens = [word for word in normalized.split() if word]
    tokens.extend(char for char in text if "\u4e00" <= char <= "\u9fff")
    for token in tokens:
        index = int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:4], "big") % 30000
        weights[index] = weights.get(index, 0.0) + 1.0
    return weights


def extract_rerank_results(data: dict[str, Any]) -> list[Any]:
    if isinstance(data.get("results"), list):
        return data["results"]
    output = data.get("output")
    if isinstance(output, dict) and isinstance(output.get("results"), list):
        return output["results"]
    if isinstance(data.get("data"), list):
        return data["data"]
    return []


def candidate_text(candidate: Candidate) -> str:
    chunk = candidate.chunk or {}
    return str(chunk.get("rerankText") or chunk.get("indexText") or chunk.get("chunkText") or "")


def overlap_score(query: str, text: str) -> float:
    q_chars = {char for char in query if char.strip()}
    t_chars = {char for char in text if char.strip()}
    return 0.0 if not q_chars or not t_chars else len(q_chars & t_chars) / len(q_chars | t_chars)


def text_score(query: str, text: str) -> float:
    q_chars = {char for char in query if char.strip()}
    t_chars = {char for char in text if char.strip()}
    return 0.0 if not q_chars or not t_chars else float(len(q_chars & t_chars) / math.sqrt(len(q_chars) * len(t_chars)))


def contains_any(text: str, terms: list[str]) -> bool:
    compact = text.replace(" ", "")
    return any(term in compact for term in terms)


def unique(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item or "").strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
