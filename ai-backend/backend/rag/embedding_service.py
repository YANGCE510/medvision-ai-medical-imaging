from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
from sentence_transformers import SentenceTransformer


AI_BACKEND_DIR = Path(__file__).resolve().parents[2]
LOCAL_MODEL_DIR = AI_BACKEND_DIR / "models" / "bge-m3"
DEFAULT_MODEL_ID = "BAAI/bge-m3"


def embedding_model_reference(explicit: Optional[str] = None) -> str:
    configured = (explicit or os.environ.get("PPGL_EMBEDDING_MODEL", "")).strip()
    if configured:
        return configured
    if LOCAL_MODEL_DIR.exists():
        return str(LOCAL_MODEL_DIR.resolve())
    return DEFAULT_MODEL_ID


def embedding_device(explicit: Optional[str] = None) -> str:
    return (explicit or os.environ.get("PPGL_EMBEDDING_DEVICE", "cpu")).strip() or "cpu"


@lru_cache(maxsize=2)
def load_embedding_model(model_reference: str, device: str) -> SentenceTransformer:
    return SentenceTransformer(model_reference, device=device)


def encode_texts(
    texts: Sequence[str],
    *,
    model_reference: Optional[str] = None,
    device: Optional[str] = None,
    batch_size: int = 8,
    show_progress_bar: bool = False,
) -> np.ndarray:
    if not texts:
        return np.empty((0, 0), dtype=np.float32)
    resolved_model = embedding_model_reference(model_reference)
    resolved_device = embedding_device(device)
    model = load_embedding_model(resolved_model, resolved_device)
    return model.encode(
        list(texts),
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=show_progress_bar,
        convert_to_numpy=True,
    ).astype(np.float32, copy=False)


def chunk_embedding_text(chunk: dict) -> str:
    return (
        f"Title: {chunk.get('title', '')}\n"
        f"Section: {chunk.get('section', '')}\n"
        f"Content: {chunk.get('content', '')}"
    )
