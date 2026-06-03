import pytest

from app.core import config


@pytest.fixture(autouse=True)
def _fast_extractor(monkeypatch):
    """Use the pymupdf backend in tests so the suite stays fast and never triggers
    Docling model downloads. Docling itself is covered by its own opt-in test."""
    monkeypatch.setattr(config, "EXTRACTOR", "pymupdf")
