from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
from sentence_transformers import SentenceTransformer


AI_BACKEND_DIR = Path(__file__).resolve().parents[2]
LOCAL_MODEL_DIR = AI_BACKEND_DIR / "models" / "bge-m3"
DEFAULT_MODEL_ID = "BAAI/bge-m3"
DEFAULT_OLLAMA_MODEL = "bge-m3"


def embedding_model_reference(explicit: Optional[str] = None) -> str:
    configured = (explicit or os.environ.get("PPGL_EMBEDDING_MODEL", "")).strip()
    if configured:
        return configured
    if LOCAL_MODEL_DIR.exists():
        return str(LOCAL_MODEL_DIR.resolve())
    return DEFAULT_MODEL_ID


def embedding_device(explicit: Optional[str] = None) -> str:
    return (explicit or os.environ.get("PPGL_EMBEDDING_DEVICE", "cpu")).strip() or "cpu"


def embedding_provider() -> str:
    provider = os.environ.get("PPGL_EMBEDDING_PROVIDER", "sentence_transformers").strip().lower()
    if provider not in {"sentence_transformers", "ollama"}:
        raise ValueError("PPGL_EMBEDDING_PROVIDER must be sentence_transformers or ollama")
    return provider


def ollama_embedding_base_url() -> str:
    configured = os.environ.get("PPGL_EMBEDDING_OLLAMA_BASE_URL", "").strip()
    if configured:
        return configured.rstrip("/")

    chat_base_url = os.environ.get("CHAT_OPENAI_BASE_URL", "http://127.0.0.1:11434/v1").strip()
    return chat_base_url.removesuffix("/v1").rstrip("/")


def ollama_embedding_model(explicit: Optional[str] = None) -> str:
    return (
        explicit
        or os.environ.get("PPGL_EMBEDDING_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    ).strip()


@lru_cache(maxsize=2)
def load_embedding_model(model_reference: str, device: str) -> SentenceTransformer:
    return SentenceTransformer(model_reference, device=device)


def encode_texts_with_ollama(
    texts: Sequence[str],
    *,
    model: str,
    batch_size: int,
) -> np.ndarray:
    """Generate normalized embeddings through Ollama's local /api/embed endpoint."""
    timeout_seconds = float(os.environ.get("PPGL_EMBEDDING_OLLAMA_TIMEOUT_SECONDS", "120"))
    endpoint = f"{ollama_embedding_base_url()}/api/embed"
    batches: list[np.ndarray] = []

    for start in range(0, len(texts), max(1, batch_size)):
        batch = list(texts[start : start + max(1, batch_size)])
        payload = json.dumps({"model": model, "input": batch}).encode("utf-8")
        request = Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"Ollama embedding request failed ({exc.code}) for model '{model}': {detail}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(
                f"Cannot reach Ollama embedding endpoint {endpoint}: {exc.reason}"
            ) from exc

        embeddings = result.get("embeddings")
        vectors = np.asarray(embeddings, dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[0] != len(batch):
            raise RuntimeError(f"Unexpected Ollama embedding response for model '{model}'")
        batches.append(vectors)

    matrix = np.vstack(batches)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise RuntimeError(f"Ollama embedding model '{model}' returned a zero vector")
    return matrix / norms


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
    if embedding_provider() == "ollama":
        return encode_texts_with_ollama(
            texts,
            model=ollama_embedding_model(model_reference),
            batch_size=batch_size,
        )
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
