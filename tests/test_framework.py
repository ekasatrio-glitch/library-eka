import json
import tempfile
from pathlib import Path

from app.rag import framework


def test_parse_title_extracts_variables():
    def fake_chat(system, user):
        return json.dumps({
            "bebas": ["Dosis norepinefrin", "Gula darah sewaktu"],
            "terikat": "Syndecan-1",
            "populasi": "pasien sepsis",
        })

    out = framework.parse_title(
        "Pengaruh dosis norepinefrin dan gula darah terhadap syndecan-1 pada pasien sepsis",
        chat_fn=fake_chat,
    )
    assert out["bebas"] == ["Dosis norepinefrin", "Gula darah sewaktu"]
    assert out["terikat"] == "Syndecan-1"
    assert out["populasi"] == "pasien sepsis"


def test_parse_title_malformed_json_is_fail_safe():
    def fake_chat(system, user):
        return "maaf saya tidak bisa"

    out = framework.parse_title("judul apa pun", chat_fn=fake_chat)
    assert out == {"bebas": [], "terikat": "", "populasi": ""}
