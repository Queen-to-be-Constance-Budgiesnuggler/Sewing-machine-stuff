"""CLI: schema-validate manuals/**/knowledge.{yaml,json} files without building an index.

Usage:
    python -m mcp_server.validate --manuals-dir manuals/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mcp_server.build_index import validate_all


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manuals-dir", type=Path, default=Path("manuals"))
    args = parser.parse_args(argv)

    machines, errors = validate_all(args.manuals_dir)

    if errors:
        print(f"Found {len(errors)} invalid knowledge file(s):", file=sys.stderr)
        for e in errors:
            print(f"\n--- {e.path} ---\n{e.detail}", file=sys.stderr)
        return 1

    print(f"OK: {len(machines)} knowledge file(s) valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
