from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import config as cfg
from app.core.db import init_db, set_meta


def test_llm_config_choice_overrides_provider(monkeypatch):
    monkeypatch.setattr(cfg, "JATEVO_BASE_URL", "https://jatevo.example")
    monkeypatch.setattr(cfg, "JATEVO_API_KEY", "jk")
    key, base, model = cfg.llm_config("jatevo:llama-3.3-70b")
    assert (key, base, model) == ("jk", "https://jatevo.example", "llama-3.3-70b")


def test_llm_config_choice_without_model_uses_env_default(monkeypatch):
    key, base, model = cfg.llm_config("deepseek")
    assert base == cfg.DEEPSEEK_BASE_URL
    assert model  # falls back to DEEPSEEK_MODEL env default


def _client(tmp_path, monkeypatch):
    import app.core.db as dbmod
    from app.web.admin_routes import router

    db = str(tmp_path / "m.db")
    monkeypatch.setattr(dbmod, "DB_PATH", db)
    init_db(db).close()
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_admin_llm_get_set_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "LLM_CHOICES", ["deepseek", "jatevo"])
    client = _client(tmp_path, monkeypatch)

    r = client.get("/admin/llm")
    assert r.status_code == 200
    assert r.json() == {"choices": ["deepseek", "jatevo"], "active": "deepseek"}

    assert client.post("/admin/llm", json={"choice": "jatevo"}).status_code == 200
    assert client.get("/admin/llm").json()["active"] == "jatevo"

    assert client.post("/admin/llm", json={"choice": "gpt-99"}).status_code == 422


def test_generator_uses_meta_choice(tmp_path, monkeypatch):
    import app.core.db as dbmod
    from app.rag import generator

    db = str(tmp_path / "g.db")
    monkeypatch.setattr(dbmod, "DB_PATH", db)
    conn = init_db(db)
    set_meta(conn, "llm_choice", "deepseek:custom-model")
    conn.close()
    monkeypatch.setattr(cfg, "DEEPSEEK_API_KEY", "dk")

    with patch("app.rag.generator.OpenAI"):
        _, model = generator._client_and_model()
    assert model == "custom-model"
