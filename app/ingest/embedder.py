from typing import List

import httpx

from app.core.config import EMBED_MODEL, OLLAMA_BASE_URL


class EmbeddingError(RuntimeError):
    pass


def embed_texts(texts: List[str], model: str | None = None, base_url: str | None = None) -> List[List[float]]:
    """Call Ollama /api/embeddings per text. Ollama embeddings endpoint is single-input."""
    mdl = model or EMBED_MODEL
    url = (base_url or OLLAMA_BASE_URL).rstrip("/") + "/api/embeddings"
    out: List[List[float]] = []
    with httpx.Client(timeout=60.0) as client:
        for t in texts:
            try:
                r = client.post(url, json={"model": mdl, "prompt": t})
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                raise EmbeddingError(f"Ollama embed failed: {e}") from e
            emb = data.get("embedding")
            if not emb:
                raise EmbeddingError(f"No embedding in response: {data}")
            out.append(emb)
    return out


def embed_one(text: str, model: str | None = None) -> List[float]:
    return embed_texts([text], model=model)[0]
