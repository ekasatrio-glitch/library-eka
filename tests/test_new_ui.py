from fastapi.testclient import TestClient

from app.web.app import create_app


def _html():
    client = TestClient(create_app())
    r = client.get("/")
    assert r.status_code == 200
    return r.text


def test_root_renders_grid_shell():
    html = _html()
    assert "library-eka" in html
    assert '/static/new/main.js' in html


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


def test_draft_mindmap_shell_present():
    html = _html()
    for el in (
        'id="nav-draft"', 'id="nav-mindmap"',
        'id="view-draft"', 'id="view-mindmap"',
        'markmap-autoloader',
    ):
        assert el in html, f"missing {el}"


def test_legacy_served_at_tools():
    client = TestClient(create_app())
    r = client.get("/tools")
    assert r.status_code == 200
    assert 'id="tab-mindmap"' in r.text  # legacy markup lives at /tools now


def test_new_redirects_to_root():
    client = TestClient(create_app())
    r = client.get("/new", follow_redirects=False)
    assert r.status_code in (302, 307, 308)
    assert r.headers["location"] == "/"


def test_mindmap_side_present():
    html = _html()
    for el in ('id="mindmap-side"', 'id="mindmap-recent"'):
        assert el in html, f"missing {el}"
