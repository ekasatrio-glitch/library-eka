import tempfile
from pathlib import Path

from app.core import config
from app.core.db import init_db
from app.rag.index_health import vec_dim, check_query_dim


def test_vec_dim_reads_declared_dimension():
    with tempfile.TemporaryDirectory() as td:
        conn = init_db(str(Path(td) / "t.db"))
        assert vec_dim(conn) == config.EMBED_DIM
        conn.close()


def test_check_query_dim_ok_when_matching():
    with tempfile.TemporaryDirectory() as td:
        conn = init_db(str(Path(td) / "t.db"))
        assert check_query_dim(conn) is None
        conn.close()


def test_check_query_dim_message_on_mismatch():
    with tempfile.TemporaryDirectory() as td:
        conn = init_db(str(Path(td) / "t.db"))
        # Force the vec table to a different dimension than config.EMBED_DIM.
        conn.execute("DROP TABLE vec_chunks")
        conn.execute(
            "CREATE VIRTUAL TABLE vec_chunks USING vec0(chunk_id INTEGER PRIMARY KEY, embedding FLOAT[8])"
        )
        conn.commit()
        assert vec_dim(conn) == 8
        msg = check_query_dim(conn)
        assert msg is not None
        assert "8" in msg and str(config.EMBED_DIM) in msg
        conn.close()
