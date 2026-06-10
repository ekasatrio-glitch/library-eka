from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.web.routes import router


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _fake_draft(topic, style="vancouver", top_k=10, filters=None):
    _fake_draft.captured = filters
    return {"paragraph": "p (1)", "references": ["r"], "citations": []}


def test_draft_passes_doc_ids():
    with patch("app.rag.drafting.draft_paragraph", side_effect=_fake_draft):
        r = _client().post("/draft", json={"topic": "stunting", "doc_ids": [3, 7]})
    assert r.status_code == 200, r.text
    assert _fake_draft.captured == {"doc_ids": [3, 7]}


def test_draft_without_doc_ids_keeps_filters_none():
    with patch("app.rag.drafting.draft_paragraph", side_effect=_fake_draft):
        r = _client().post("/draft", json={"topic": "stunting"})
    assert r.status_code == 200
    assert _fake_draft.captured is None
