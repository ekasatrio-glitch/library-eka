from unittest.mock import MagicMock, patch

from app.core import config
from app.ingest.embedder import embed_one


def test_embed_one_uses_configured_model():
    """Query embedding must go out with the configured EMBED_MODEL, so the
    query vector matches the index (e.g. both bge-m3)."""
    captured = {}

    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"embedding": [0.0] * config.EMBED_DIM}

    class FakeClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, json=None):
            captured["model"] = json["model"]
            captured["url"] = url
            return FakeResp()

    with patch("app.ingest.embedder.httpx.Client", FakeClient):
        vec = embed_one("apa itu sedasi?")

    assert captured["model"] == config.EMBED_MODEL
    assert captured["url"].endswith("/api/embeddings")
    assert len(vec) == config.EMBED_DIM


def test_embed_one_respects_explicit_model_override():
    """An explicit model arg still wins (used by the reembed migration)."""
    captured = {}

    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"embedding": [0.0] * 4}

    class FakeClient:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, json=None):
            captured["model"] = json["model"]
            return FakeResp()

    with patch("app.ingest.embedder.httpx.Client", FakeClient):
        embed_one("q", model="some-other-model")

    assert captured["model"] == "some-other-model"
