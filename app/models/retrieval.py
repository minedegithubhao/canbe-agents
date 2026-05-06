from __future__ import annotations

from dataclasses import dataclass, field


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
