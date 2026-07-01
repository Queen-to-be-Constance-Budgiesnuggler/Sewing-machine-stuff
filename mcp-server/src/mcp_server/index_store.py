"""SQLite + FTS5 index schema and query helpers.

The compiled index is a single SQLite file built from all manuals/*/knowledge.yaml
files. Normal tables hold structured, indexed lookups (get_setting, get_fault_finding,
etc.); a single unified FTS5 table backs the free-text `search` tool across all
machines and content types.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from mcp_server.models import MachineKnowledge

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE machines (
    slug TEXT PRIMARY KEY,
    brand TEXT NOT NULL,
    model TEXT NOT NULL,
    aliases_json TEXT NOT NULL,
    manual_pdf TEXT NOT NULL,
    manual_version TEXT,
    source_pages INTEGER,
    notes TEXT
);

CREATE TABLE specifications (
    id INTEGER PRIMARY KEY,
    machine_slug TEXT NOT NULL REFERENCES machines(slug),
    label TEXT NOT NULL,
    value TEXT NOT NULL,
    category TEXT
);

CREATE TABLE settings (
    id INTEGER PRIMARY KEY,
    machine_slug TEXT NOT NULL REFERENCES machines(slug),
    number INTEGER NOT NULL,
    title TEXT NOT NULL,
    page INTEGER,
    description TEXT NOT NULL,
    spec TEXT,
    service_menu_path TEXT,
    related_settings_json TEXT NOT NULL
);
CREATE INDEX idx_settings_machine_number ON settings(machine_slug, number);

CREATE TABLE menus (
    id INTEGER PRIMARY KEY,
    machine_slug TEXT NOT NULL REFERENCES machines(slug),
    menu_number INTEGER NOT NULL,
    menu_name TEXT NOT NULL
);

CREATE TABLE submenus (
    id INTEGER PRIMARY KEY,
    machine_slug TEXT NOT NULL REFERENCES machines(slug),
    menu_number INTEGER NOT NULL,
    letter TEXT NOT NULL,
    submenu_name TEXT NOT NULL
);

CREATE TABLE touch_areas (
    id INTEGER PRIMARY KEY,
    machine_slug TEXT NOT NULL REFERENCES machines(slug),
    menu_number INTEGER NOT NULL,
    letter TEXT NOT NULL,
    label TEXT NOT NULL,
    description TEXT NOT NULL,
    check_procedure TEXT
);

CREATE TABLE disassembly (
    id INTEGER PRIMARY KEY,
    machine_slug TEXT NOT NULL REFERENCES machines(slug),
    component TEXT NOT NULL,
    page INTEGER,
    tools_needed_json TEXT NOT NULL,
    dismantle_steps_json TEXT NOT NULL,
    mount_steps_json TEXT NOT NULL,
    settings_to_recheck_json TEXT NOT NULL
);

CREATE TABLE fault_finding (
    id INTEGER PRIMARY KEY,
    machine_slug TEXT NOT NULL REFERENCES machines(slug),
    symptom TEXT NOT NULL,
    checks_json TEXT NOT NULL,
    replace_order_json TEXT NOT NULL,
    notes TEXT
);

CREATE VIRTUAL TABLE search_fts USING fts5(
    machine_slug UNINDEXED,
    source_type UNINDEXED,
    source_id UNINDEXED,
    title,
    body
);

CREATE TABLE index_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def build_index(machines: list[MachineKnowledge], out_path: Path) -> dict:
    """Build a fresh SQLite+FTS5 index from validated MachineKnowledge objects.

    Always a full rebuild (out_path is deleted first if present) so the index
    exactly matches the given set of machines -- never incrementally patched.
    Returns a small summary dict for logging.
    """
    if out_path.exists():
        out_path.unlink()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(out_path)
    try:
        conn.executescript(DDL)

        summary = {"machines": 0, "settings": 0, "fault_finding": 0, "disassembly": 0, "touch_areas": 0}

        for mk in machines:
            m = mk.machine
            conn.execute(
                "INSERT INTO machines (slug, brand, model, aliases_json, manual_pdf, "
                "manual_version, source_pages, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (m.slug, m.brand, m.model, json.dumps(m.aliases), m.manual_pdf, m.manual_version, m.source_pages, m.notes),
            )
            summary["machines"] += 1

            for spec in mk.specifications:
                conn.execute(
                    "INSERT INTO specifications (machine_slug, label, value, category) VALUES (?, ?, ?, ?)",
                    (m.slug, spec.label, spec.value, spec.category),
                )

            for s in mk.settings:
                conn.execute(
                    "INSERT INTO settings (machine_slug, number, title, page, description, spec, "
                    "service_menu_path, related_settings_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        m.slug, s.number, s.title, s.page, s.description, s.spec,
                        s.service_menu_path, json.dumps(s.related_settings),
                    ),
                )
                summary["settings"] += 1
                body = f"{s.description}\n{s.spec or ''}".strip()
                conn.execute(
                    "INSERT INTO search_fts (machine_slug, source_type, source_id, title, body) "
                    "VALUES (?, 'setting', ?, ?, ?)",
                    (m.slug, str(s.number), s.title, body),
                )

            for menu in mk.service_program.menus:
                conn.execute(
                    "INSERT INTO menus (machine_slug, menu_number, menu_name) VALUES (?, ?, ?)",
                    (m.slug, menu.number, menu.name),
                )
                for sub in menu.submenus:
                    conn.execute(
                        "INSERT INTO submenus (machine_slug, menu_number, letter, submenu_name) VALUES (?, ?, ?, ?)",
                        (m.slug, menu.number, sub.letter, sub.name),
                    )
                    for ta in sub.touch_areas:
                        conn.execute(
                            "INSERT INTO touch_areas (machine_slug, menu_number, letter, label, description, "
                            "check_procedure) VALUES (?, ?, ?, ?, ?, ?)",
                            (m.slug, menu.number, sub.letter, ta.label, ta.description, ta.check_procedure),
                        )
                        summary["touch_areas"] += 1
                        touch_id = f"{menu.number}{sub.letter}:{ta.label}"
                        body = f"{ta.description}\n{ta.check_procedure or ''}".strip()
                        conn.execute(
                            "INSERT INTO search_fts (machine_slug, source_type, source_id, title, body) "
                            "VALUES (?, 'touch_area', ?, ?, ?)",
                            (m.slug, touch_id, f"{menu.name} - {sub.name} - {ta.label}", body),
                        )

            for i, d in enumerate(mk.disassembly):
                conn.execute(
                    "INSERT INTO disassembly (machine_slug, component, page, tools_needed_json, "
                    "dismantle_steps_json, mount_steps_json, settings_to_recheck_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        m.slug, d.component, d.page, json.dumps(d.tools_needed),
                        json.dumps(d.dismantle_steps), json.dumps(d.mount_steps),
                        json.dumps(d.settings_to_recheck),
                    ),
                )
                summary["disassembly"] += 1
                body = "\n".join(d.dismantle_steps + d.mount_steps)
                conn.execute(
                    "INSERT INTO search_fts (machine_slug, source_type, source_id, title, body) "
                    "VALUES (?, 'disassembly', ?, ?, ?)",
                    (m.slug, str(i), d.component, body),
                )

            for i, f in enumerate(mk.fault_finding):
                conn.execute(
                    "INSERT INTO fault_finding (machine_slug, symptom, checks_json, replace_order_json, notes) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (m.slug, f.symptom, json.dumps(f.checks), json.dumps(f.replace_order), f.notes),
                )
                summary["fault_finding"] += 1
                body = "\n".join(f.checks) + "\n" + (f.notes or "")
                conn.execute(
                    "INSERT INTO search_fts (machine_slug, source_type, source_id, title, body) "
                    "VALUES (?, 'fault_finding', ?, ?, ?)",
                    (m.slug, str(i), f.symptom, body),
                )

        conn.execute("INSERT INTO index_meta (key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
        conn.execute("INSERT INTO index_meta (key, value) VALUES ('machine_count', ?)", (str(summary["machines"]),))
        conn.commit()
        return summary
    finally:
        conn.close()


def list_machines(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT slug, brand, model, aliases_json, manual_version FROM machines ORDER BY slug"
    ).fetchall()
    return [
        {
            "slug": r["slug"],
            "brand": r["brand"],
            "model": r["model"],
            "aliases": json.loads(r["aliases_json"]),
            "manual_version": r["manual_version"],
        }
        for r in rows
    ]


def _resolve_slug(conn: sqlite3.Connection, slug_or_alias: str) -> str | None:
    """Resolve a slug or alias/brand+model string to a canonical machine slug."""
    row = conn.execute("SELECT slug FROM machines WHERE slug = ?", (slug_or_alias,)).fetchone()
    if row:
        return row["slug"]
    needle = slug_or_alias.strip().lower()
    for m in list_machines(conn):
        if needle == m["brand"].lower() or needle == m["model"].lower():
            return m["slug"]
        if any(needle == a.lower() for a in m["aliases"]):
            return m["slug"]
    return None


def get_machine_info(conn: sqlite3.Connection, slug: str) -> dict | None:
    resolved = _resolve_slug(conn, slug)
    if resolved is None:
        return None
    row = conn.execute("SELECT * FROM machines WHERE slug = ?", (resolved,)).fetchone()
    specs = conn.execute(
        "SELECT label, value, category FROM specifications WHERE machine_slug = ?", (resolved,)
    ).fetchall()
    return {
        "slug": row["slug"],
        "brand": row["brand"],
        "model": row["model"],
        "aliases": json.loads(row["aliases_json"]),
        "manual_pdf": row["manual_pdf"],
        "manual_version": row["manual_version"],
        "source_pages": row["source_pages"],
        "notes": row["notes"],
        "specifications": [dict(s) for s in specs],
    }


def get_setting(conn: sqlite3.Connection, slug: str, number: int) -> dict | None:
    resolved = _resolve_slug(conn, slug)
    if resolved is None:
        return None
    row = conn.execute(
        "SELECT * FROM settings WHERE machine_slug = ? AND number = ?", (resolved, number)
    ).fetchone()
    if row is None:
        return None
    related_numbers = json.loads(row["related_settings_json"])
    related = []
    for n in related_numbers:
        r = conn.execute(
            "SELECT number, title, spec FROM settings WHERE machine_slug = ? AND number = ?", (resolved, n)
        ).fetchone()
        if r:
            related.append({"number": r["number"], "title": r["title"], "spec": r["spec"]})
    return {
        "number": row["number"],
        "title": row["title"],
        "page": row["page"],
        "description": row["description"],
        "spec": row["spec"],
        "service_menu_path": row["service_menu_path"],
        "related_settings": related,
    }


def search(
    conn: sqlite3.Connection,
    query: str,
    machine: str | None = None,
    source_type: str | None = None,
    limit: int = 10,
) -> list[dict]:
    resolved_machine = _resolve_slug(conn, machine) if machine else None
    sql = (
        "SELECT machine_slug, source_type, source_id, title, "
        "snippet(search_fts, 4, '>>', '<<', '...', 12) AS snippet, bm25(search_fts) AS rank "
        "FROM search_fts WHERE search_fts MATCH ?"
    )
    params: list = [query]
    if resolved_machine:
        sql += " AND machine_slug = ?"
        params.append(resolved_machine)
    if source_type:
        sql += " AND source_type = ?"
        params.append(source_type)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [
        {
            "machine": r["machine_slug"],
            "source_type": r["source_type"],
            "source_id": r["source_id"],
            "title": r["title"],
            "snippet": r["snippet"],
        }
        for r in rows
    ]


def get_fault_finding(conn: sqlite3.Connection, slug: str, symptom_query: str | None = None) -> list[dict]:
    resolved = _resolve_slug(conn, slug)
    if resolved is None:
        return []
    if symptom_query:
        matches = search(conn, symptom_query, machine=resolved, source_type="fault_finding", limit=50)
        ids = [int(m["source_id"]) for m in matches]
    else:
        ids = None
    rows = conn.execute(
        "SELECT rowid, symptom, checks_json, replace_order_json, notes FROM fault_finding WHERE machine_slug = ? ORDER BY rowid",
        (resolved,),
    ).fetchall()
    all_entries = [
        {
            "symptom": r["symptom"],
            "checks": json.loads(r["checks_json"]),
            "replace_order": json.loads(r["replace_order_json"]),
            "notes": r["notes"],
        }
        for i, r in enumerate(rows)
    ]
    if ids is None:
        return all_entries
    # fault_finding rows were inserted in order starting at index 0 per machine,
    # so position in the ordered fetch corresponds to the source_id index.
    return [entry for i, entry in enumerate(all_entries) if i in set(ids)]


def get_disassembly_procedure(conn: sqlite3.Connection, slug: str, component_query: str) -> list[dict]:
    resolved = _resolve_slug(conn, slug)
    if resolved is None:
        return []
    needle = component_query.strip().lower()
    rows = conn.execute(
        "SELECT * FROM disassembly WHERE machine_slug = ? ORDER BY id", (resolved,)
    ).fetchall()
    matches = [r for r in rows if needle in r["component"].lower()]
    if not matches:
        # fall back to FTS search over component + step text
        hits = search(conn, component_query, machine=resolved, source_type="disassembly", limit=10)
        wanted_ids = {int(h["source_id"]) for h in hits}
        matches = [r for i, r in enumerate(rows) if i in wanted_ids]

    results = []
    for r in matches:
        recheck_numbers = json.loads(r["settings_to_recheck_json"])
        recheck = []
        for n in recheck_numbers:
            s = conn.execute(
                "SELECT number, title, spec FROM settings WHERE machine_slug = ? AND number = ?", (resolved, n)
            ).fetchone()
            if s:
                recheck.append({"number": s["number"], "title": s["title"], "spec": s["spec"]})
        results.append(
            {
                "component": r["component"],
                "page": r["page"],
                "tools_needed": json.loads(r["tools_needed_json"]),
                "dismantle_steps": json.loads(r["dismantle_steps_json"]),
                "mount_steps": json.loads(r["mount_steps_json"]),
                "settings_to_recheck": recheck,
            }
        )
    return results


def get_service_menu(
    conn: sqlite3.Connection, slug: str, menu: str | None = None, submenu: str | None = None
) -> dict | list[dict] | None:
    resolved = _resolve_slug(conn, slug)
    if resolved is None:
        return None

    menus = conn.execute(
        "SELECT menu_number, menu_name FROM menus WHERE machine_slug = ? ORDER BY menu_number", (resolved,)
    ).fetchall()

    def submenus_for(menu_number: int) -> list[dict]:
        subs = conn.execute(
            "SELECT letter, submenu_name FROM submenus WHERE machine_slug = ? AND menu_number = ? ORDER BY letter",
            (resolved, menu_number),
        ).fetchall()
        out = []
        for s in subs:
            tas = conn.execute(
                "SELECT label, description, check_procedure FROM touch_areas "
                "WHERE machine_slug = ? AND menu_number = ? AND letter = ? ORDER BY id",
                (resolved, menu_number, s["letter"]),
            ).fetchall()
            out.append(
                {
                    "letter": s["letter"],
                    "name": s["submenu_name"],
                    "touch_areas": [dict(t) for t in tas],
                }
            )
        return out

    def find_menu(m: str) -> dict | None:
        for row in menus:
            if m.strip().lower() in (str(row["menu_number"]), row["menu_name"].lower()):
                return row
        return None

    if menu is None:
        return [{"number": r["menu_number"], "name": r["menu_name"], "submenus": submenus_for(r["menu_number"])} for r in menus]

    m_row = find_menu(menu)
    if m_row is None:
        return None
    subs = submenus_for(m_row["menu_number"])

    if submenu is None:
        return {"number": m_row["menu_number"], "name": m_row["menu_name"], "submenus": subs}

    for s in subs:
        if submenu.strip().upper() == s["letter"] or submenu.strip().lower() == s["name"].lower():
            return {"number": m_row["menu_number"], "name": m_row["menu_name"], "submenu": s}
    return None


def open_index(db_path: Path) -> sqlite3.Connection:
    """Open a read-only connection to a compiled index, failing fast if it's missing or stale."""
    if not db_path.exists():
        raise FileNotFoundError(
            f"knowledge index not found at {db_path} -- run "
            "`python -m mcp_server.build_index` to build it first"
        )
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT value FROM index_meta WHERE key = 'schema_version'").fetchone()
    except sqlite3.OperationalError as e:
        raise RuntimeError(f"{db_path} does not look like a valid knowledge index: {e}") from e
    if row is None or int(row["value"]) != SCHEMA_VERSION:
        raise RuntimeError(
            f"{db_path} has schema_version {row['value'] if row else 'unknown'}, "
            f"expected {SCHEMA_VERSION} -- rebuild the index with build_index.py"
        )
    return conn
