"""FastMCP server exposing sewing-machine repair knowledge as MCP tools.

Loads a compiled SQLite+FTS5 index (built by build_index.py) once at startup
and answers queries against it. Runs over stdio, the transport Claude Desktop
and Claude Code expect for a locally-spawned MCP server.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from mcp_server import index_store


def default_db_path() -> Path:
    # server.py -> mcp_server/ -> src/ -> mcp-server/ -> repo root
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "index" / "knowledge.db"


def resolve_db_path() -> Path:
    env = os.environ.get("KNOWLEDGE_DB_PATH")
    return Path(env) if env else default_db_path()


mcp = FastMCP("sewing-machine-knowledge")

_conn: sqlite3.Connection | None = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = index_store.open_index(resolve_db_path())
    return _conn


@mcp.tool()
def list_machines() -> list[dict]:
    """List every sewing machine this knowledge base has data for."""
    return index_store.list_machines(get_conn())


@mcp.tool()
def get_machine_info(slug: str) -> dict:
    """Get metadata and full technical specifications for a machine.

    `slug` can be the machine's slug (e.g. 'pfaff-quilt-expression-720'), its
    brand, model name, or a known alias.
    """
    result = index_store.get_machine_info(get_conn(), slug)
    if result is None:
        known = [m["slug"] for m in index_store.list_machines(get_conn())]
        return {"error": f"no machine matching {slug!r}", "known_machines": known}
    return result


@mcp.tool()
def get_setting(slug: str, number: int) -> dict:
    """Get one numbered service/calibration setting for a machine (spec, tolerance,
    adjustment procedure, and any related settings resolved with their titles)."""
    result = index_store.get_setting(get_conn(), slug, number)
    if result is None:
        return {"error": f"no setting {number} found for machine {slug!r}"}
    return result


@mcp.tool()
def search(query: str, machine: str | None = None, source_type: str | None = None, limit: int = 10) -> list[dict]:
    """Full-text search across all machines' settings, fault-finding entries,
    disassembly procedures, and service-menu touch areas.

    `source_type` optionally filters to one of: setting, fault_finding,
    disassembly, touch_area. Use the returned source_type/source_id with the
    matching getter tool (get_setting, get_fault_finding, get_disassembly_procedure)
    for full detail.
    """
    return index_store.search(get_conn(), query, machine=machine, source_type=source_type, limit=limit)


@mcp.tool()
def get_fault_finding(slug: str, symptom_query: str | None = None) -> list[dict]:
    """Get fault-finding (troubleshooting) entries for a machine.

    Without `symptom_query`, returns every symptom -> checks -> fix entry for the
    machine. With it, returns entries whose symptom/checks match the query.
    """
    return index_store.get_fault_finding(get_conn(), slug, symptom_query)


@mcp.tool()
def get_disassembly_procedure(slug: str, component_query: str) -> list[dict]:
    """Get disassembly/reassembly procedure(s) for a machine component (e.g.
    'hook cover', 'presser bar bushing', 'main pc-board'). Returns dismantle
    steps, mount steps, tools needed, and which numbered settings must be
    rechecked afterward (resolved with their titles and specs)."""
    return index_store.get_disassembly_procedure(get_conn(), slug, component_query)


@mcp.tool()
def get_service_menu(slug: str, menu: str | None = None, submenu: str | None = None) -> object:
    """Get the machine's diagnostic service-program menu tree.

    Without args, returns the full 3-level tree (menu -> lettered submenu ->
    touch areas). Pass `menu` (a number like "1" or a name like "Set menu") to
    drill into one menu; add `submenu` (a letter like "A" or its name) to get
    just that submenu's touch areas.
    """
    result = index_store.get_service_menu(get_conn(), slug, menu=menu, submenu=submenu)
    if result is None:
        return {"error": f"no matching machine/menu/submenu for slug={slug!r} menu={menu!r} submenu={submenu!r}"}
    return result


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
