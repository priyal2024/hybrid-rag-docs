"""Hybrid retrieval: fuses Postgres full-text (keyword) search with pgvector
semantic similarity via Reciprocal Rank Fusion (RRF).

Why fuse rather than pick one: keyword search nails exact-term queries
("generateStaticParams") that embeddings can blur together with near
synonyms, while vector search nails conceptual queries ("how do I avoid
re-running an effect on every render") that share no vocabulary with the
docs that answer them. RRF combines the two rankings without needing the
scores to be on a comparable scale, which cosine similarity and ts_rank are
not.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.embeddings import embed_query
from app.models import Chunk

RRF_K = 60          # standard RRF damping constant — de-emphasizes rank-1-vs-rank-2 noise
CANDIDATE_POOL = 30  # how many candidates each retrieval method contributes before fusion


@dataclass(frozen=True)
class SearchResult:
    id: int
    source: str
    url: str
    heading_path: str
    content: str
    score: float


def reciprocal_rank_fusion(rank_lists: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    """rank_lists: each a list of ids in descending relevance order.
    Returns {id: fused_score}, higher is more relevant."""
    scores: dict[int, float] = {}
    for ranked_ids in rank_lists:
        for rank, doc_id in enumerate(ranked_ids, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


def _vector_candidate_ids(db: Session, query_embedding: list[float], limit: int) -> list[int]:
    stmt = (
        select(Chunk.id)
        .where(Chunk.embedding.is_not(None))
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def _keyword_candidate_ids(db: Session, query: str, limit: int) -> list[int]:
    tsquery = func.plainto_tsquery("english", query)
    stmt = (
        select(Chunk.id)
        .where(Chunk.content_tsv.op("@@")(tsquery))
        .order_by(text("ts_rank(content_tsv, plainto_tsquery('english', :q)) DESC"))
        .params(q=query)
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def hybrid_search(db: Session, query: str, k: int = 8, candidate_pool: int = CANDIDATE_POOL) -> list[SearchResult]:
    query_embedding = embed_query(query)

    vector_ids = _vector_candidate_ids(db, query_embedding, candidate_pool)
    keyword_ids = _keyword_candidate_ids(db, query, candidate_pool)

    fused = reciprocal_rank_fusion([vector_ids, keyword_ids])
    if not fused:
        return []

    top_ids = sorted(fused, key=fused.get, reverse=True)[:k]

    rows = db.execute(select(Chunk).where(Chunk.id.in_(top_ids))).scalars().all()
    rows_by_id = {row.id: row for row in rows}

    return [
        SearchResult(
            id=chunk_id,
            source=rows_by_id[chunk_id].source,
            url=rows_by_id[chunk_id].url,
            heading_path=rows_by_id[chunk_id].heading_path,
            content=rows_by_id[chunk_id].content,
            score=fused[chunk_id],
        )
        for chunk_id in top_ids
        if chunk_id in rows_by_id
    ]
