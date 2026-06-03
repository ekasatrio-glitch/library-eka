import argparse
import logging
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Iterable, List, Optional, Set

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.core.config import PROJECTS_DIR, WATCH_FOLDERS
from app.core.db import document_exists, init_db
from app.core.projects import add_papers, project_for_path
from app.ingest.pipeline import file_hash, find_pdfs, ingest_pdf

log = logging.getLogger("watcher")


class _InFlight:
    """Thread-safe set of resolved paths queued or being processed.

    Collapses duplicate watchdog events (on_created + on_modified bursts) for
    the same file while one copy is still pending.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._keys: Set[str] = set()

    def add(self, key: str) -> bool:
        """Return True if newly added, False if already in flight."""
        with self._lock:
            if key in self._keys:
                return False
            self._keys.add(key)
            return True

    def discard(self, key: str) -> None:
        with self._lock:
            self._keys.discard(key)


class _PdfHandler(FileSystemEventHandler):
    def __init__(self, q: "queue.Queue[Path]", inflight: _InFlight):
        self.q = q
        self.inflight = inflight

    def _maybe_enqueue(self, raw_path: str):
        p = Path(raw_path)
        if p.suffix.lower() != ".pdf":
            return
        key = str(p.resolve())
        if self.inflight.add(key):
            self.q.put(p)

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory:
            self._maybe_enqueue(event.src_path)

    def on_moved(self, event: FileSystemEvent):
        if not event.is_directory:
            self._maybe_enqueue(event.dest_path)

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory:
            self._maybe_enqueue(event.src_path)


def _wait_stable(path: Path, settle_seconds: float = 2.0, max_wait: float = 60.0) -> bool:
    """Wait until size stable for `settle_seconds`. Returns True if stable, False if timeout/missing."""
    deadline = time.time() + max_wait
    last_size = -1
    last_change = time.time()
    while time.time() < deadline:
        if not path.exists():
            return False
        try:
            size = path.stat().st_size
        except OSError:
            return False
        now = time.time()
        if size != last_size:
            last_size = size
            last_change = now
        elif now - last_change >= settle_seconds:
            return True
        time.sleep(0.5)
    return False


def _worker(
    q: "queue.Queue[Optional[Path]]",
    stop_event: threading.Event,
    inflight: _InFlight,
    db_path: Optional[str] = None,
):
    conn = init_db(db_path)
    try:
        while not stop_event.is_set():
            try:
                item = q.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                q.task_done()
                break
            key = str(item.resolve())
            try:
                p = item.resolve()
                if not _wait_stable(p):
                    log.warning("not stable / missing: %s", p)
                    continue
                ok, msg = ingest_pdf(p, conn=conn)
                log.info("%s %s -> %s", "OK" if ok else "SKIP/ERR", p, msg)
                # If the file sits inside a project's folder, link it (add-only).
                pid = project_for_path(conn, str(p))
                if pid is not None:
                    doc_id = document_exists(conn, file_hash(p))
                    if doc_id is not None and add_papers(conn, pid, [doc_id]):
                        log.info("linked %s -> project %d", p, pid)
            except Exception as e:
                log.exception("worker error on %s: %s", item, e)
            finally:
                inflight.discard(key)
                q.task_done()
    finally:
        conn.close()


def startup_scan(roots: Iterable[str | Path], q: "queue.Queue[Path]", inflight: _InFlight) -> int:
    count = 0
    for pdf in find_pdfs(roots):
        if inflight.add(str(pdf.resolve())):
            q.put(pdf)
            count += 1
    return count


def run(roots: Optional[List[str]] = None, db_path: Optional[str] = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    folders = list(roots or WATCH_FOLDERS)
    # Always watch the per-project base dir (created if missing) so dropping a PDF
    # into a project subfolder auto-ingests + links — even with no WATCH_FOLDERS.
    Path(PROJECTS_DIR).mkdir(parents=True, exist_ok=True)
    folders.append(PROJECTS_DIR)

    # Keep existing dirs, deduped by resolved path (avoid double-watching overlaps).
    seen: Set[str] = set()
    valid: List[str] = []
    for f in folders:
        if Path(f).is_dir():
            key = str(Path(f).resolve())
            if key not in seen:
                seen.add(key)
                valid.append(f)
    if not valid:
        print(f"No watchable folders: {folders}", file=sys.stderr)
        return 2

    q: "queue.Queue[Path]" = queue.Queue()
    stop_event = threading.Event()
    inflight = _InFlight()
    worker_t = threading.Thread(target=_worker, args=(q, stop_event, inflight, db_path), daemon=True)
    worker_t.start()

    n = startup_scan(valid, q, inflight)
    log.info("startup scan enqueued %d files", n)

    handler = _PdfHandler(q, inflight)
    observer = Observer()
    for f in valid:
        observer.schedule(handler, f, recursive=True)
    observer.start()
    log.info("watching: %s", valid)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("stopping...")
    finally:
        observer.stop()
        observer.join()
        stop_event.set()
        q.put(None)  # type: ignore[arg-type]
        worker_t.join(timeout=5)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description="Watch folders + auto-ingest PDFs")
    p.add_argument("folders", nargs="*", help="Override WATCH_FOLDERS")
    args = p.parse_args(argv)
    return run(args.folders or None)


if __name__ == "__main__":
    raise SystemExit(main())
