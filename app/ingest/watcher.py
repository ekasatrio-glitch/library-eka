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

from app.core.config import WATCH_FOLDERS
from app.core.db import init_db
from app.ingest.pipeline import file_hash, find_pdfs, ingest_pdf

log = logging.getLogger("watcher")


class _PdfHandler(FileSystemEventHandler):
    def __init__(self, q: "queue.Queue[Path]"):
        self.q = q

    def _maybe_enqueue(self, raw_path: str):
        p = Path(raw_path)
        if p.suffix.lower() == ".pdf":
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


def _worker(q: "queue.Queue[Optional[Path]]", stop_event: threading.Event, db_path: Optional[str] = None):
    conn = init_db(db_path)
    seen_in_flight: Set[str] = set()
    try:
        while not stop_event.is_set():
            try:
                item = q.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                break
            try:
                p = item.resolve()
                key = str(p)
                if key in seen_in_flight:
                    continue
                seen_in_flight.add(key)
                if not _wait_stable(p):
                    log.warning("not stable / missing: %s", p)
                    continue
                ok, msg = ingest_pdf(p, conn=conn)
                log.info("%s %s -> %s", "OK" if ok else "SKIP/ERR", p, msg)
            except Exception as e:
                log.exception("worker error on %s: %s", item, e)
            finally:
                try:
                    seen_in_flight.discard(key)
                except Exception:
                    pass
                q.task_done()
    finally:
        conn.close()


def startup_scan(roots: Iterable[str | Path], q: "queue.Queue[Path]") -> int:
    count = 0
    for pdf in find_pdfs(roots):
        q.put(pdf)
        count += 1
    return count


def run(roots: Optional[List[str]] = None, db_path: Optional[str] = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    folders = roots or WATCH_FOLDERS
    if not folders:
        print("No WATCH_FOLDERS configured.", file=sys.stderr)
        return 2

    valid = [f for f in folders if Path(f).is_dir()]
    if not valid:
        print(f"None of the WATCH_FOLDERS exist: {folders}", file=sys.stderr)
        return 2

    q: "queue.Queue[Path]" = queue.Queue()
    stop_event = threading.Event()
    worker_t = threading.Thread(target=_worker, args=(q, stop_event, db_path), daemon=True)
    worker_t.start()

    n = startup_scan(valid, q)
    log.info("startup scan enqueued %d files", n)

    handler = _PdfHandler(q)
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
