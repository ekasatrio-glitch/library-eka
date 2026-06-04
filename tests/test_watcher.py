import queue
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import fitz

from app.core import config
from app.core.db import init_db
from app.ingest.watcher import _InFlight, _wait_stable, _worker, startup_scan


def make_pdf(path: Path, n_pages: int = 1):
    doc = fitz.open()
    for i in range(n_pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"content page {i+1} " + "lorem " * 200, fontsize=10)
    doc.save(str(path))
    doc.close()


def test_inflight_dedup():
    f = _InFlight()
    assert f.add("/x/a.pdf") is True
    assert f.add("/x/a.pdf") is False  # already in flight -> not re-enqueued
    f.discard("/x/a.pdf")
    assert f.add("/x/a.pdf") is True   # re-addable after completion


def test_wait_stable_quick():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "a.bin"
        p.write_bytes(b"x" * 1024)
        assert _wait_stable(p, settle_seconds=0.5, max_wait=5)


def test_startup_scan_enqueues():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        make_pdf(root / "a.pdf")
        make_pdf(root / "b.pdf")
        q: "queue.Queue[Path]" = queue.Queue()
        n = startup_scan([root], q, _InFlight())
        assert n == 2
        assert q.qsize() == 2


def test_worker_processes_queue():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pdf = root / "doc.pdf"
        make_pdf(pdf, n_pages=2)
        db = str(root / "t.db")

        q: "queue.Queue" = queue.Queue()
        stop = threading.Event()

        def fake_embed(texts, model=None, base_url=None):
            return [[0.01] * config.EMBED_DIM for _ in texts]

        with patch("app.ingest.pipeline.embed_texts", side_effect=fake_embed), \
             patch("app.ingest.watcher._wait_stable", return_value=True):
            t = threading.Thread(target=_worker, args=(q, stop, _InFlight(), db), daemon=True)
            t.start()
            q.put(pdf)
            q.join()
            stop.set()
            q.put(None)
            t.join(timeout=5)

        conn = init_db(db)
        n = conn.execute("SELECT COUNT(*) FROM documents WHERE status='done'").fetchone()[0]
        conn.close()
        assert n == 1
