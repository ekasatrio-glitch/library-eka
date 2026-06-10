from fastapi.testclient import TestClient

from app.web.app import create_app


def _html():
    client = TestClient(create_app())
    r = client.get("/")
    assert r.status_code == 200
    return r.text


def test_root_renders_naskah_shell():
    html = _html()
    assert "library-eka" in html
    assert 'id="screen"' in html
    assert 'id="admin-gear"' in html
    assert 'type="module"' in html and "/static/new/main.js" in html


def test_old_tab_nav_is_gone():
    html = _html()
    for el in ('id="nav-chat"', 'id="nav-projects"', 'id="nav-draft"',
               'id="nav-mindmap"', 'id="sidebar"'):
        assert el not in html, f"legacy element still present: {el}"


def test_splash_kept():
    html = _html()
    for el in ('id="splash"', 'id="splash-close"', 'id="splash-enter"'):
        assert el in html


def test_semua_pdf_link_present():
    assert "/tools#tab-library" in _html()


def test_tools_still_serves_legacy_ui():
    client = TestClient(create_app())
    r = client.get("/tools")
    assert r.status_code == 200
    assert "/static/app.js" in r.text
