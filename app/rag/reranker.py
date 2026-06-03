"""Cross-encoder reranking of a small candidate set.

Operates only on the top-N hybrid candidates (not the whole corpus), so even the
heavier `bge` model stays fast. Selected via the RERANKER env var:

  flashrank (default) — tiny ONNX cross-encoder, ms-level on CPU
  bge                 — bge-reranker-v2-m3 (multilingual ID/EN, higher accuracy)
  none                — passthrough (keep fusion order)

If the configured backend's dependency is missing or errors, we log and fall
back to passthrough so retrieval never hard-fails on a reranker problem.
"""

import logging
from typing import List

from app.core.config import BGE_RERANK_MODEL, RERANKER

log = logging.getLogger("reranker")

_flashrank_ranker = None
_bge_model = None


def _get_flashrank():
    global _flashrank_ranker
    if _flashrank_ranker is None:
        from flashrank import Ranker

        _flashrank_ranker = Ranker()  # default nano model
    return _flashrank_ranker


def _get_bge():
    global _bge_model
    if _bge_model is None:
        from sentence_transformers import CrossEncoder

        _bge_model = CrossEncoder(BGE_RERANK_MODEL)
    return _bge_model


def _rerank_flashrank(query: str, texts: List[str]) -> List[int]:
    from flashrank import RerankRequest

    ranker = _get_flashrank()
    passages = [{"id": i, "text": t} for i, t in enumerate(texts)]
    ranked = ranker.rerank(RerankRequest(query=query, passages=passages))
    return [r["id"] for r in ranked]


def _rerank_bge(query: str, texts: List[str]) -> List[int]:
    model = _get_bge()
    scores = model.predict([(query, t) for t in texts])
    return sorted(range(len(texts)), key=lambda i: scores[i], reverse=True)


def rerank(query: str, hits: list, top_k: int, backend: str = None) -> list:
    """Return the top_k hits reordered by cross-encoder relevance to `query`.

    `hits` is any list of objects exposing `.text`. Order-only; objects unchanged.
    """
    mode = (backend or RERANKER or "none").lower()
    if mode == "none" or not hits:
        return hits[:top_k]

    texts = [h.text for h in hits]
    try:
        if mode == "bge":
            order = _rerank_bge(query, texts)
        else:  # flashrank default
            order = _rerank_flashrank(query, texts)
    except Exception as e:  # missing dep / model load / runtime — degrade gracefully
        log.warning("reranker '%s' unavailable (%s); using fusion order", mode, e)
        return hits[:top_k]

    return [hits[i] for i in order[:top_k]]
