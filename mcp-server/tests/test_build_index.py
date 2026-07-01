from pathlib import Path

from mcp_server.build_index import validate_all
from mcp_server.index_store import build_index, open_index

FIXTURES = Path(__file__).parent / "fixtures"


def test_validate_all_good_manuals_has_no_errors():
    machines, errors = validate_all(FIXTURES / "good_manuals")
    assert errors == []
    assert len(machines) == 1
    assert machines[0].machine.slug == "test-machine"


def test_validate_all_bad_manuals_reports_error():
    machines, errors = validate_all(FIXTURES / "bad_manuals")
    assert machines == []
    assert len(errors) == 1
    assert "duplicate setting numbers" in errors[0].detail


def test_build_index_creates_expected_rows(tmp_path):
    machines, errors = validate_all(FIXTURES / "good_manuals")
    assert errors == []

    db_path = tmp_path / "knowledge.db"
    summary = build_index(machines, db_path)
    assert summary["machines"] == 1
    assert summary["settings"] == 2
    assert summary["disassembly"] == 1
    assert summary["fault_finding"] == 1

    conn = open_index(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM settings WHERE machine_slug = 'test-machine'").fetchone()
        assert row["c"] == 2

        hits = conn.execute("SELECT COUNT(*) AS c FROM search_fts WHERE search_fts MATCH 'tension'").fetchone()
        assert hits["c"] > 0
    finally:
        conn.close()


def test_build_index_is_full_rebuild_not_incremental(tmp_path):
    machines, errors = validate_all(FIXTURES / "good_manuals")
    assert errors == []
    db_path = tmp_path / "knowledge.db"

    build_index(machines, db_path)
    build_index(machines, db_path)  # rebuilding again should not duplicate rows

    conn = open_index(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM machines").fetchone()
        assert row["c"] == 1
    finally:
        conn.close()
