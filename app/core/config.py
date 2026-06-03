import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

DB_PATH = os.getenv("DB_PATH", str(ROOT / "data" / "library.db"))
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").lower()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
JATEVO_API_KEY = os.getenv("JATEVO_API_KEY", "")
JATEVO_BASE_URL = os.getenv("JATEVO_BASE_URL", "")

WATCH_FOLDERS = [
    p.strip() for p in os.getenv("WATCH_FOLDERS", "").split(",") if p.strip()
]


def llm_config() -> tuple[str, str, str]:
    if LLM_PROVIDER == "jatevo":
        if not JATEVO_BASE_URL:
            raise RuntimeError(
                "LLM_PROVIDER=jatevo but JATEVO_BASE_URL is empty — set it in .env "
                "(empty base_url silently falls back to api.openai.com)"
            )
        return JATEVO_API_KEY, JATEVO_BASE_URL, os.getenv("JATEVO_MODEL", "jatevo-default")
    return DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
