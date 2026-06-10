from typing import List, Optional

from openai import OpenAI

from app.core.config import llm_config
from app.core.db import connect, get_meta


def _active_choice() -> Optional[str]:
    """meta.llm_choice set from the admin mini-menu; None = env default."""
    try:
        conn = connect()
        try:
            return get_meta(conn, "llm_choice")
        finally:
            conn.close()
    except Exception:
        return None


def _client_and_model() -> tuple[OpenAI, str]:
    api_key, base_url, model = llm_config(_active_choice())
    if not api_key:
        raise RuntimeError("LLM API key missing — set DEEPSEEK_API_KEY or JATEVO_API_KEY in .env")
    client = OpenAI(api_key=api_key, base_url=base_url or None)
    return client, model


def chat(
    system: str,
    user: str,
    temperature: float = 0.2,
    max_tokens: int = 1500,
    model: Optional[str] = None,
) -> str:
    client, default_model = _client_and_model()
    resp = client.chat.completions.create(
        model=model or default_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""
