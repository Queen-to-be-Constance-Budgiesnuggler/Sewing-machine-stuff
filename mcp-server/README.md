# Sewing-machine knowledge MCP server

An MCP server that exposes structured, queryable sewing-machine service-manual
knowledge (settings/tolerances, the diagnostic service-program menu tree,
disassembly/reassembly procedures, and a fault-finding table) as tools an LLM
can call directly, instead of dumping a whole PDF into context.

The knowledge itself lives in `manuals/<machine-slug>/knowledge.yaml` at the
repo root, one file per machine. This server reads a compiled search index
(`index/knowledge.db`) built from those files by `build_index.py` (and kept
up to date automatically by the `.github/workflows/build-index.yml` CI job
whenever a knowledge file changes).

## Running it locally

From the repo root:

```bash
cd mcp-server
uv sync
uv run sewing-mcp-server
```

Or without `uv`:

```bash
cd mcp-server
pip install -e .
python -m mcp_server
```

The server needs a built index to exist at `index/knowledge.db` (repo root).
If you've just cloned the repo, it's already committed there by CI. To
rebuild it yourself after editing a `knowledge.yaml`:

```bash
cd mcp-server
uv run sewing-mcp-validate --manuals-dir ../manuals
uv run sewing-mcp-build-index --manuals-dir ../manuals --out ../index/knowledge.db
```

(Run from the repo root instead, the `--manuals-dir`/`--out` paths default to
`manuals/` and `index/knowledge.db` relative to your current directory.)

## Connecting to Claude Code (this repo)

A `.mcp.json` is already committed at the repo root, so opening this repo in
Claude Code should auto-discover the server:

```json
{
  "mcpServers": {
    "sewing-machine-knowledge": {
      "command": "uv",
      "args": ["--directory", "mcp-server", "run", "sewing-mcp-server"]
    }
  }
}
```

## Connecting to Claude Desktop

Claude Desktop's config is per-user, not part of this repo. Add an entry to
your own `claude_desktop_config.json` (Settings -> Developer -> Edit Config)
pointing at an absolute path to your clone:

```json
{
  "mcpServers": {
    "sewing-machine-knowledge": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/Sewing-machine-stuff/mcp-server", "run", "sewing-mcp-server"]
    }
  }
}
```

Without `uv`, after `pip install -e .` in `mcp-server/`:

```json
{
  "mcpServers": {
    "sewing-machine-knowledge": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/absolute/path/to/Sewing-machine-stuff/mcp-server/src"
    }
  }
}
```

Restart Claude Desktop after editing the config.

## Tools exposed

- `list_machines()` -- every machine this knowledge base covers.
- `get_machine_info(slug)` -- metadata + full technical specifications.
- `get_setting(slug, number)` -- one numbered service/calibration setting, tolerance, and related settings.
- `search(query, machine=None, source_type=None, limit=10)` -- ranked full-text search across everything.
- `get_fault_finding(slug, symptom_query=None)` -- troubleshooting symptom -> checks -> fix entries.
- `get_disassembly_procedure(slug, component_query)` -- teardown/rebuild steps for a component, with settings to recheck afterward.
- `get_service_menu(slug, menu=None, submenu=None)` -- the machine's diagnostic touchscreen menu tree.

`slug` accepts the machine's canonical slug, brand, model name, or a known alias.

## Adding another machine

1. Create `manuals/<brand-model-slug>/` with the source PDF and a `knowledge.yaml`
   authored against the schema in `src/mcp_server/models.py`.
2. Push it (or open a PR) -- CI validates the file and, once merged to `main`,
   rebuilds and commits `index/knowledge.db` automatically.

## Tests

```bash
cd mcp-server
uv run pytest tests/ -v
```
