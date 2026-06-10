import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

DB_PATH = os.getenv("DB_PATH", str(ROOT / "data" / "library.db"))
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")
# PDF extraction backend: docling (reading order, tables, OCR) | pymupdf (fast)
EXTRACTOR = os.getenv("EXTRACTOR", "docling").lower()
OCR = os.getenv("OCR", "false").lower() in ("1", "true", "yes")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").lower()

# Generation-model choices selectable at runtime from the admin mini-menu.
# Each entry is "provider" or "provider:model"; the active one is persisted in
# the meta table (key "llm_choice"). Add models here, no code change needed.
LLM_CHOICES = [c.strip() for c in os.getenv("LLM_CHOICES", "deepseek,jatevo").split(",") if c.strip()]
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
JATEVO_API_KEY = os.getenv("JATEVO_API_KEY", "")
JATEVO_BASE_URL = os.getenv("JATEVO_BASE_URL", "")

WATCH_FOLDERS = [
    p.strip() for p in os.getenv("WATCH_FOLDERS", "").split(",") if p.strip()
]

# Base dir for per-project folders. Each project gets a subfolder "<id>-<slug>";
# PDFs dropped there are auto-ingested and linked to that project (watcher).
PROJECTS_DIR = os.getenv("PROJECTS_DIR", str(Path.home() / "Documents" / "library-eka"))

# Reranker for final precision: flashrank (fast, ONNX) | bge (bge-reranker-v2-m3) | none
RERANKER = os.getenv("RERANKER", "flashrank").lower()
BGE_RERANK_MODEL = os.getenv("BGE_RERANK_MODEL", "BAAI/bge-reranker-v2-m3")
RERANK_POOL = int(os.getenv("RERANK_POOL", "40"))  # candidates fed to the reranker

# Title-based PDF rename (Phase 14). Pattern fields: {authors} {year} {title}
RENAME_PATTERN = os.getenv("RENAME_PATTERN", "{authors} ({year}) - {title}")
CROSSREF_ENABLED = os.getenv("CROSSREF_ENABLED", "true").lower() in ("1", "true", "yes")


def llm_config(choice: Optional[str] = None) -> tuple[str, str, str]:
    """Resolve (api_key, base_url, model). choice = "provider[:model]" overrides
    the LLM_PROVIDER env; without a model suffix the provider's env default is used."""
    provider, _, model = (choice or LLM_PROVIDER).partition(":")
    provider = provider.strip().lower()
    if provider == "jatevo":
        if not JATEVO_BASE_URL:
            raise RuntimeError(
                "LLM_PROVIDER=jatevo but JATEVO_BASE_URL is empty — set it in .env "
                "(empty base_url silently falls back to api.openai.com)"
            )
        return JATEVO_API_KEY, JATEVO_BASE_URL, model or os.getenv("JATEVO_MODEL", "jatevo-default")
    return DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
