from fastapi.testclient import TestClient

from app.web.app import create_app


def _html():
    client = TestClient(create_app())
    r = client.get("/tools")
    assert r.status_code == 200
    return r.text


def test_projects_home_and_workspace_present():
    html = _html()
    assert 'id="proj-home"' in html
    assert 'id="proj-grid"' in html
    assert 'id="proj-workspace"' in html
    assert 'id="proj-back"' in html
    assert 'id="proj-count"' in html


def test_project_subnav_and_panels_present():
    html = _html()
    for sub in ("paper", "chat", "matrix"):
        assert f'data-subtab="{sub}"' in html
        assert f'data-panel="{sub}"' in html


def test_chat_threads_present():
    html = _html()
    assert 'id="proj-chat-thread"' in html
    assert 'id="ask-chat-thread"' in html


def test_preserved_handler_ids_still_present():
    html = _html()
    for el in (
        "proj-create-form", "proj-title", "proj-folder", "proj-upload-form",
        "proj-import-toggle", "proj-import-panel", "proj-import-search",
        "proj-import-list", "proj-import-apply", "proj-papers", "proj-ask-form",
        "proj-expand", "proj-matrix-btn", "proj-delete-btn", "matrix-view",
        "matrix-xlsx", "matrix-csv", "matrix-output", "codebook-form", "codebook-info",
        "proj-addpaper-toggle", "proj-add-panel",
    ):
        assert f'id="{el}"' in html, f"missing {el}"
