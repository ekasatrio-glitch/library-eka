from unittest.mock import patch

from app.rag import mindmap as mm


def _stub_chat(sys, user, **kw):
    # _expand_subtopics expects a JSON array; outline call returns markdown.
    if "subtopik" in sys.lower() and "JSON" in sys:
        return '["sub a", "sub b"]'
    return "# topik\n\n## sub a\n- poin"


class _Hit:
    def __init__(self, cid):
        self.chunk_id = cid
        self.doc_id = 7
        self.title = "Paper"
        self.page_start = 1
        self.page_end = 1
        self.text = "ctx"
        self.score = 1.0


def test_build_mindmap_passes_doc_ids_filter():
    calls = []

    def fake_search(q, top_k=6, conn=None, filters=None):
        calls.append(filters)
        return [_Hit(1)]

    with patch("app.rag.mindmap.search", side_effect=fake_search), \
         patch("app.rag.mindmap.chat", side_effect=_stub_chat), \
         patch("app.rag.mindmap.build_citations", return_value=[]), \
         patch("app.rag.mindmap.format_context", return_value="CTX"):
        mm.build_mindmap("sedasi", breadth=2, doc_ids=[7])

    assert calls, "search was never called"
    assert all(f == {"doc_ids": [7]} for f in calls), calls


def test_build_mindmap_no_doc_ids_means_no_filter():
    calls = []

    def fake_search(q, top_k=6, conn=None, filters=None):
        calls.append(filters)
        return [_Hit(1)]

    with patch("app.rag.mindmap.search", side_effect=fake_search), \
         patch("app.rag.mindmap.chat", side_effect=_stub_chat), \
         patch("app.rag.mindmap.build_citations", return_value=[]), \
         patch("app.rag.mindmap.format_context", return_value="CTX"):
        mm.build_mindmap("sedasi", breadth=2)

    assert calls and all(f is None for f in calls), calls
