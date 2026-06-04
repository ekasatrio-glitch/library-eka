import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import fitz

from app.core import config
from app.core import projects as proj
from app.core.db import init_db
from app.ingest.pipeline import ingest_pdf
from app.rag import matrix


def _mk(path: Path, text: str, pages: int = 2):
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text} Page {i + 1}", fontsize=10)
    doc.save(str(path))
    doc.close()


def _embed_stub(texts, model=None, base_url=None):
    return [[0.01] * config.EMBED_DIM for _ in texts]


class _FakeHit:
    def __init__(self, doc_id, title, ps=1, pe=1):
        self.doc_id, self.title, self.page_start, self.page_end = doc_id, title, ps, pe


def test_detect_schema():
    assert matrix.detect_schema("A meta-analysis of X", "pooled random-effects I²=40%") == "meta-analisis"
    assert matrix.detect_schema("A systematic review", "PRISMA flow") == "review"
    assert matrix.detect_schema("An RCT of drug Y", "we randomized patients") == "empiris"
    assert matrix.detect_schema("anything", "anything", override="review") == "review"


def test_extract_empirical_grounding_and_weakness_split():
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "t.db")
        conn = init_db(db)
        a = Path(td) / "rct.pdf"
        _mk(a, "randomized controlled trial of drug effect on blood pressure")
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
            ingest_pdf(a, conn=conn)
        doc_id = conn.execute("SELECT id FROM documents").fetchone()[0]

        # LLM returns some fields; omits 'mekanisme' (should become GAP); gives a
        # bare suggestion (should get the marker prefix).
        def fake_chat(system, user):
            return json.dumps({
                "main_finding": "Drug lowers BP by 10mmHg",
                "definisi_operasional": "BP measured by sphygmomanometer",
                "kontroversi": "tidak disebutkan dalam paper",
                "kelemahan_penulis": "Small sample size acknowledged",
                "kelemahan_saran": "tambahkan kontrol plasebo",
                "tag": "hipertensi",
                "notes": "(draft) hasil menjanjikan",
            })

        def fake_search(q, top_k=6, conn=None):
            return [_FakeHit(doc_id, "self"), _FakeHit(999, "Other Paper", 3, 4)]

        row = matrix.extract_paper(conn, doc_id, fake_chat, fake_search)
        assert row["schema"] == "empiris"
        f = row["fields"]
        assert f["mekanisme"] == matrix.GAP  # omitted -> explicit gap
        assert f["kelemahan_penulis"].startswith("Small sample")
        assert f["kelemahan_saran"].startswith("saran — perlu verifikasi:")
        # Supporting paper from corpus only, excludes self.
        assert "Other Paper" in f["paper_pendukung"] and "self" not in f["paper_pendukung"]
        assert row["refs"]["paper_pendukung"][0]["doc_id"] == 999
        # Grounded ref present for a stated field, absent for the gap field.
        assert "main_finding" in row["refs"] and "mekanisme" not in row["refs"]
        conn.close()


def test_meta_unreported_flows_to_weakness():
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "t.db")
        conn = init_db(db)
        a = Path(td) / "ma.pdf"
        _mk(a, "meta-analysis pooled random-effects I2 of statin trials")
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
            ingest_pdf(a, conn=conn)
        doc_id = conn.execute("SELECT id FROM documents").fetchone()[0]

        def fake_chat(system, user):
            # Report pooled estimate but leave bias_publikasi unreported.
            return json.dumps({"pooled_estimate": "OR 0.8 (95% CI 0.7-0.9)"})

        def fake_search(q, top_k=6, conn=None):
            return []

        row = matrix.extract_paper(conn, doc_id, fake_chat, fake_search)
        assert row["schema"] == "meta-analisis"
        f = row["fields"]
        assert f["pooled_estimate"].startswith("OR 0.8")
        assert f["bias_publikasi"] == matrix.GAP_META  # unreported
        assert "kelemahan_tidak_dilaporkan" in f
        assert "bias_publikasi" in f["kelemahan_tidak_dilaporkan"]
        conn.close()


def test_build_matrix_persists_and_views():
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "t.db")
        conn = init_db(db)
        a, b = Path(td) / "old.pdf", Path(td) / "new.pdf"
        _mk(a, "empirical study one")
        _mk(b, "empirical study two")
        with patch("app.ingest.pipeline.embed_texts", side_effect=_embed_stub):
            ingest_pdf(a, conn=conn)
            ingest_pdf(b, conn=conn)
        ids = [r[0] for r in conn.execute("SELECT id FROM documents ORDER BY id").fetchall()]
        conn.execute("UPDATE documents SET year=2010 WHERE id=?", (ids[0],))
        conn.execute("UPDATE documents SET year=2020 WHERE id=?", (ids[1],))
        conn.commit()
        pid = proj.create_project(conn, "P")
        proj.add_papers(conn, pid, ids)

        def fake_chat(system, user):
            return json.dumps({"main_finding": "x", "tag": "topikA", "notes": "(draft)"})

        def fake_search(q, top_k=6, conn=None):
            return []

        rows = matrix.build_matrix(conn, pid, fake_chat, fake_search)
        assert len(rows) == 2
        # Persisted.
        assert conn.execute("SELECT COUNT(*) FROM project_matrix WHERE project_id=?", (pid,)).fetchone()[0] == 2
        loaded = matrix.load_matrix(conn, pid)
        assert len(loaded) == 2

        timeline = matrix.shape_view(loaded, "linimasa")
        assert [r["year"] for r in timeline["rows"]] == [2010, 2020]
        assert "main_finding" in timeline["columns"]

        # Re-build is idempotent on row count (upsert, not append).
        matrix.build_matrix(conn, pid, fake_chat, fake_search)
        assert conn.execute("SELECT COUNT(*) FROM project_matrix WHERE project_id=?", (pid,)).fetchone()[0] == 2
        conn.close()
