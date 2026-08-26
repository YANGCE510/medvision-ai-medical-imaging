from __future__ import annotations

import json
import os
import atexit
import time
from functools import lru_cache
from pathlib import Path
from typing import Optional

from qdrant_client import QdrantClient, models

from .embedding_service import chunk_embedding_text, encode_texts


AI_BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CHUNKS_PATH = AI_BACKEND_DIR / "knowledge_base" / "parsed" / "chunks.jsonl"
DEFAULT_INDEX_PATH = AI_BACKEND_DIR / "knowledge_base" / "index" / "qdrant"
DEFAULT_COLLECTION = "ppgl_knowledge"


def qdrant_path(explicit: Optional[Path] = None) -> Path:
    configured = os.environ.get("PPGL_QDRANT_PATH", "").strip()
    return (explicit or Path(configured) if configured else explicit or DEFAULT_INDEX_PATH).resolve()


def collection_name(explicit: Optional[str] = None) -> str:
    return (explicit or os.environ.get("PPGL_QDRANT_COLLECTION", DEFAULT_COLLECTION)).strip()


def load_chunks(path: Path = DEFAULT_CHUNKS_PATH) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Knowledge chunks not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def build_vector_index(
    *,
    chunks_path: Path = DEFAULT_CHUNKS_PATH,
    index_path: Optional[Path] = None,
    collection: Optional[str] = None,
    model_reference: Optional[str] = None,
    device: Optional[str] = None,
    batch_size: int = 8,
) -> dict:
    chunks = load_chunks(chunks_path.resolve())
    texts = [chunk_embedding_text(chunk) for chunk in chunks]
    embeddings = encode_texts(
        texts,
        model_reference=model_reference,
        device=device,
        batch_size=batch_size,
        show_progress_bar=True,
    )
    if embeddings.shape[0] != len(chunks):
        raise RuntimeError("Embedding count does not match chunk count")

    resolved_path = qdrant_path(index_path)
    resolved_path.mkdir(parents=True, exist_ok=True)
    resolved_collection = collection_name(collection)
    client = QdrantClient(path=str(resolved_path))
    try:
        if client.collection_exists(resolved_collection):
            client.delete_collection(resolved_collection)
        client.create_collection(
            collection_name=resolved_collection,
            vectors_config=models.VectorParams(
                size=int(embeddings.shape[1]),
                distance=models.Distance.COSINE,
            ),
        )
        for start in range(0, len(chunks), 64):
            stop = min(start + 64, len(chunks))
            points = [
                models.PointStruct(
                    id=index,
                    vector=embeddings[index].tolist(),
                    payload=chunks[index],
                )
                for index in range(start, stop)
            ]
            client.upsert(collection_name=resolved_collection, points=points, wait=True)
        count = client.count(collection_name=resolved_collection, exact=True).count
    finally:
        client.close()
    return {
        "collection": resolved_collection,
        "index_path": str(resolved_path),
        "chunks": len(chunks),
        "points": int(count),
        "vector_size": int(embeddings.shape[1]),
    }


@lru_cache(maxsize=2)
def qdrant_client(index_path: str) -> QdrantClient:
    client = QdrantClient(path=index_path)
    atexit.register(client.close)
    return client


def dense_search(query: str, top_k: int = 30) -> list[dict]:
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("Query must not be empty")
    resolved_path = qdrant_path()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Qdrant index not found: {resolved_path}")
    resolved_collection = collection_name()
    client = qdrant_client(str(resolved_path))
    if not client.collection_exists(resolved_collection):
        raise FileNotFoundError(f"Qdrant collection not found: {resolved_collection}")

    query_vector = encode_texts([clean_query], batch_size=1)[0].tolist()
    points = client.query_points(
        collection_name=resolved_collection,
        query=query_vector,
        limit=top_k,
        with_payload=True,
    ).points
    return [
        {
            "score": float(point.score),
            "dense_score": float(point.score),
            **dict(point.payload or {}),
        }
        for point in points
    ]


def search_knowledge_with_metadata(
    query: str,
    top_k: int = 5,
    *,
    retrieve_k: int = 30,
    retrieval_mode: str = "dense",
) -> dict:
    mode = retrieval_mode.strip().lower()
    if mode == "dense":
        started = time.perf_counter()
        results = dense_search(query, top_k)
        latency_ms = (time.perf_counter() - started) * 1000
        return {
            "results": results,
            "metadata": {
                "retrieval_mode": mode,
                "pipeline": "bge-m3",
                "dense_candidates": len(results),
                "bm25_candidates": 0,
                "fused_candidates": 0,
                "reranked_candidates": 0,
                "latency_ms": {
                    "dense": round(latency_ms, 2),
                    "bm25": 0.0,
                    "reranker": 0.0,
                    "total": round(latency_ms, 2),
                },
            },
        }

    if mode not in {"hybrid", "hybrid_rerank"}:
        raise ValueError("retrieval_mode must be dense, hybrid, or hybrid_rerank")

    from .hybrid_retriever import hybrid_search

    payload = hybrid_search(
        query,
        top_k=top_k,
        retrieve_k=max(top_k, retrieve_k),
        use_reranker=mode == "hybrid_rerank",
    )
    payload["metadata"]["retrieval_mode"] = mode
    return payload


def search_knowledge(query: str, top_k: int = 5) -> list[dict]:
    return search_knowledge_with_metadata(query, top_k)["results"]
