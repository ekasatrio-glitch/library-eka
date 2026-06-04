"""Vector-index health: detect when the index dimension no longer matches the
configured embedding model (e.g. after switching nomic 768 -> bge-m3 1024 but
before reembedding)."""

import re
import sqlite3
from typing import Optional

from app.core import config


def vec_dim(conn: sqlite3.Connection) -> Optional[int]:
    """Declared dimension of the vec_chunks table, or None if absent/unparseable."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'vec_chunks'"
    ).fetchone()
    if not row or not row[0]:
        return None
    m = re.search(r"FLOAT\[(\d+)\]", row[0])
    return int(m.group(1)) if m else None


def check_query_dim(conn: sqlite3.Connection) -> Optional[str]:
    """Return a human message if the index dim != config.EMBED_DIM, else None."""
    d = vec_dim(conn)
    if d is not None and d != config.EMBED_DIM:
        return (
            f"Indeks vektor {d}-d tapi model embedding {config.EMBED_DIM}-d "
            f"({config.EMBED_MODEL}). Jalankan reembed dulu (panel di /tools) "
            f"atau samakan EMBED_DIM."
        )
    return None
