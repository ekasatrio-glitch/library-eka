from fastapi.testclient import TestClient

from app.web.app import create_app


def _html():
    client = TestClient(create_app())
    r = client.get("/new")
    assert r.status_code == 200
    return r.text


def test_new_route_renders():
    html = _html()
    assert "library-eka" in html


def test_shell_core_elements_present():
    html = _html()
    for el in (
        'id="sidebar"', 'id="nav-chat"', 'id="nav-projects"',
        'id="view-chat"', 'id="view-projects"',
        'id="recent-list"', 'id="projects-list"',
        'id="splash"', 'id="splash-close"', 'id="splash-enter"',
    ):
        assert el in html, f"missing {el}"


def test_loads_main_module():
    html = _html()
    assert 'type="module"' in html
    assert '/static/new/main.js' in html


def test_old_index_untouched():
    client = TestClient(create_app())
    assert client.get("/").status_code == 200  # legacy UI still served


def test_draft_mindmap_shell_present():
    html = _html()
    for el in (
        'id="nav-draft"', 'id="nav-mindmap"',
        'id="view-draft"', 'id="view-mindmap"',
        'markmap-autoloader',
    ):
        assert el in html, f"missing {el}"
