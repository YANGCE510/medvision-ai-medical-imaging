from __future__ import annotations

import re
import time
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from .reranker_service import rerank_results
from .vector_store import DEFAULT_CHUNKS_PATH, dense_search, load_chunks


TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-_./][a-z0-9]+)*|[\u3400-\u9fff]", re.IGNORECASE)
RRF_K = 60

# The literature is primarily English while users ask in Chinese. These are
# domain aliases, not generated text: they improve recall without changing the
# question that is ultimately shown to the user.
QUERY_EXPANSION_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("遗传", "检测"),
        "genetic testing germline susceptibility genes targeted next-generation sequencing NGS gene panel SDHA SDHB SDHC SDHD VHL RET NF1 TMEM127 MAX",
    ),
    (
        ("基因", "面板"),
        "genetic testing germline susceptibility genes targeted next-generation sequencing NGS gene panel SDHA SDHB SDHC SDHD VHL RET NF1 TMEM127 MAX",
    ),
    (
        ("临床", "表现", "诊断"),
        "clinical findings symptoms diagnosis biochemical tests",
    ),
    (
        ("手术", "长期", "结局"),
        "long-term outcomes postoperative surgery follow-up recurrence survival",
    ),
    (
        ("术后", "随访"),
        "postoperative long-term follow-up recurrence survival outcomes",
    ),
)


def expand_query(query: str) -> str:
    """Append stable PPGL terminology aliases for cross-lingual retrieval."""
    clean_query = query.strip()
    normalized = clean_query.casefold()
    additions = [
        expansion
        for required_terms, expansion in QUERY_EXPANSION_RULES
        if all(term in normalized for term in required_terms)
    ]
    return " ".join([clean_query, *additions]) if additions else clean_query


def lexical_tokens(text: str) -> list[str]:
    tokens = [token.casefold() for token in TOKEN_RE.findall(text or "")]
    expanded = list(tokens)
    for token in tokens:
        if re.search(r"[-_./]", token):
            expanded.extend(part for part in re.split(r"[-_./]", token) if part)
    return expanded


def lexical_text(chunk: dict) -> str:
    return " ".join(
        [
            str(chunk.get("title", "")),
            str(chunk.get("section", "")),
            str(chunk.get("content", "")),
        ]
    )


@lru_cache(maxsize=1)
def bm25_resources(chunks_path: str = str(DEFAULT_CHUNKS_PATH)) -> tuple[list[dict], BM25Okapi]:
    chunks = load_chunks(Path(chunks_path))
    tokenized_corpus = [lexical_tokens(lexical_text(chunk)) for chunk in chunks]
    return chunks, BM25Okapi(tokenized_corpus)


def bm25_search(query: str, limit: int = 30) -> list[dict]:
    chunks, index = bm25_resources()
    query_tokens = lexical_tokens(query)
    if not query_tokens:
        return []
    scores = index.get_scores(query_tokens)
    ranked_indexes = np.argsort(scores)[::-1]
    results = []
    for rank_index in ranked_indexes:
        score = float(scores[int(rank_index)])
        if score <= 0:
            break
        results.append({"bm25_score": score, **chunks[int(rank_index)]})
        if len(results) >= limit:
            break
    return results


def reciprocal_rank_fusion(
    dense_results: list[dict],
    lexical_results: list[dict],
) -> list[dict]:
    candidates: dict[str, dict] = {}

    for rank, result in enumerate(dense_results, start=1):
        chunk_id = str(result.get("chunk_id"))
        entry = candidates.setdefault(chunk_id, dict(result))
        entry["dense_rank"] = rank
        entry["dense_score"] = float(result.get("dense_score", result.get("score", 0)))
        entry["rrf_score"] = float(entry.get("rrf_score", 0)) + 1 / (RRF_K + rank)

    for rank, result in enumerate(lexical_results, start=1):
        chunk_id = str(result.get("chunk_id"))
        entry = candidates.setdefault(chunk_id, dict(result))
        entry["bm25_rank"] = rank
        entry["bm25_score"] = float(result.get("bm25_score", 0))
        entry["rrf_score"] = float(entry.get("rrf_score", 0)) + 1 / (RRF_K + rank)

    fused = list(candidates.values())
    for entry in fused:
        entry.setdefault("dense_rank", None)
        entry.setdefault("dense_score", None)
        entry.setdefault("bm25_rank", None)
        entry.setdefault("bm25_score", None)
        entry["score"] = float(entry.get("rrf_score", 0))
    fused.sort(key=lambda item: item["rrf_score"], reverse=True)
    return fused


def select_distinct_documents(results: list[dict], top_k: int) -> list[dict]:
    """Return the highest-ranked chunk from each document before filling gaps.

    Supplying five near-identical chunks from one paper crowds out otherwise
    relevant evidence and makes source-level citation coverage weaker.
    """
    selected: list[dict] = []
    selected_ids: set[str] = set()
    for result in results:
        document_id = str(result.get("document_id") or result.get("chunk_id") or "")
        if document_id in selected_ids:
            continue
        selected.append(result)
        selected_ids.add(document_id)
        if len(selected) >= top_k:
            return selected

    for result in results:
        if result in selected:
            continue
        selected.append(result)
        if len(selected) >= top_k:
            break
    return selected


def hybrid_search(
    query: str,
    *,
    top_k: int = 5,
    retrieve_k: int = 30,
    use_reranker: bool = True,
) -> dict:
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("Query must not be empty")
    retrieval_query = expand_query(clean_query)

    started = time.perf_counter()
    dense_started = time.perf_counter()
    dense_results = dense_search(retrieval_query, retrieve_k)
    dense_ms = (time.perf_counter() - dense_started) * 1000

    bm25_started = time.perf_counter()
    lexical_results = bm25_search(retrieval_query, retrieve_k)
    bm25_ms = (time.perf_counter() - bm25_started) * 1000

    fused = reciprocal_rank_fusion(dense_results, lexical_results)
    reranker_ms = 0.0
    if use_reranker:
        rerank_limit = max(top_k, min(retrieve_k, int(os.environ.get("PPGL_RERANK_CANDIDATES", "20"))))
        reranker_started = time.perf_counter()
        reranked = rerank_results(retrieval_query, fused[:rerank_limit], top_k=rerank_limit)
        results = select_distinct_documents(reranked, top_k)
        reranker_ms = (time.perf_counter() - reranker_started) * 1000
        pipeline = "bge-m3 + bm25 + rrf + bge-reranker-v2-m3"
    else:
        results = fused[:top_k]
        pipeline = "bge-m3 + bm25 + rrf"

    total_ms = (time.perf_counter() - started) * 1000
    return {
        "results": results,
        "metadata": {
            "pipeline": pipeline,
            "dense_candidates": len(dense_results),
            "bm25_candidates": len(lexical_results),
            "fused_candidates": len(fused),
            "reranked_candidates": rerank_limit if use_reranker else 0,
            "unique_document_results": len({str(item.get("document_id") or item.get("chunk_id") or "") for item in results}),
            "query_expanded": retrieval_query != clean_query,
            "latency_ms": {
                "dense": round(dense_ms, 2),
                "bm25": round(bm25_ms, 2),
                "reranker": round(reranker_ms, 2),
                "total": round(total_ms, 2),
            },
        },
    }
