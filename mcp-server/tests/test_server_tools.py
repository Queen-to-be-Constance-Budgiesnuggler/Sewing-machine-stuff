from pathlib import Path

import pytest

import mcp_server.server as server
from mcp_server.build_index import validate_all
from mcp_server.index_store import build_index

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def test_index(tmp_path, monkeypatch):
    machines, errors = validate_all(FIXTURES / "good_manuals")
    assert errors == []
    db_path = tmp_path / "knowledge.db"
    build_index(machines, db_path)

    monkeypatch.setenv("KNOWLEDGE_DB_PATH", str(db_path))
    server._conn = None
    yield db_path
    if server._conn is not None:
        server._conn.close()
    server._conn = None


def test_list_machines(test_index):
    machines = server.list_machines()
    assert [m["slug"] for m in machines] == ["test-machine"]


def test_get_machine_info(test_index):
    info = server.get_machine_info("test-machine")
    assert info["brand"] == "TestBrand"
    assert any(s["label"] == "Needle system" for s in info["specifications"])


def test_get_machine_info_unknown_slug(test_index):
    info = server.get_machine_info("does-not-exist")
    assert "error" in info
    assert info["known_machines"] == ["test-machine"]


def test_get_setting_resolves_related(test_index):
    setting = server.get_setting("test-machine", 2)
    assert setting["title"] == "Needle centre position"
    assert setting["related_settings"] == [{"number": 1, "title": "Belt tension", "spec": "Firm tension"}]


def test_search_finds_tension(test_index):
    results = server.search("tension")
    assert any(r["source_type"] == "setting" for r in results)


def test_get_fault_finding_all(test_index):
    entries = server.get_fault_finding("test-machine")
    assert len(entries) == 1
    assert entries[0]["symptom"] == "The machine does not start."


def test_get_disassembly_procedure_resolves_recheck(test_index):
    procs = server.get_disassembly_procedure("test-machine", "top cover")
    assert len(procs) == 1
    assert procs[0]["settings_to_recheck"][0]["title"] == "Needle centre position"


def test_get_service_menu_full_tree(test_index):
    tree = server.get_service_menu("test-machine")
    assert tree[0]["name"] == "Set menu"
    assert tree[0]["submenus"][0]["touch_areas"][0]["label"] == "Centre"


def test_get_service_menu_drill_down(test_index):
    result = server.get_service_menu("test-machine", menu="1", submenu="A")
    assert result["submenu"]["name"] == "Needle menu"
