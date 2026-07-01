"""CLI: validate manuals/**/knowledge.{yaml,json} files and compile them into a
single SQLite+FTS5 index.

Usage:
    python -m mcp_server.build_index --manuals-dir manuals/ --out index/knowledge.db
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from mcp_server.index_store import build_index as _build_index
from mcp_server.models import MachineKnowledge


class KnowledgeFileError(Exception):
    def __init__(self, path: Path, detail: str):
        self.path = path
        self.detail = detail
        super().__init__(f"{path}: {detail}")


def find_knowledge_files(manuals_dir: Path) -> list[Path]:
    files = sorted(manuals_dir.glob("*/knowledge.yaml")) + sorted(manuals_dir.glob("*/knowledge.json"))
    return sorted(files)


def load_one(path: Path) -> MachineKnowledge:
    """Load and validate a single knowledge file. Raises KnowledgeFileError on any problem."""
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise KnowledgeFileError(path, f"invalid YAML/JSON: {e}") from e

    try:
        mk = MachineKnowledge.model_validate(raw)
    except ValidationError as e:
        raise KnowledgeFileError(path, f"schema validation failed:\n{e}") from e

    expected_folder = path.parent.name
    if mk.machine.slug != expected_folder:
        raise KnowledgeFileError(
            path,
            f"machine.slug {mk.machine.slug!r} does not match its folder name {expected_folder!r}",
        )
    return mk


def validate_all(manuals_dir: Path) -> tuple[list[MachineKnowledge], list[KnowledgeFileError]]:
    """Validate every knowledge file under manuals_dir.

    Returns (successfully-validated machines, errors) -- collects ALL errors
    rather than stopping at the first, so CI can report everything broken at once.
    """
    machines: list[MachineKnowledge] = []
    errors: list[KnowledgeFileError] = []
    for path in find_knowledge_files(manuals_dir):
        try:
            machines.append(load_one(path))
        except KnowledgeFileError as e:
            errors.append(e)

    slugs = [m.machine.slug for m in machines]
    if len(slugs) != len(set(slugs)):
        dupes = {s for s in slugs if slugs.count(s) > 1}
        errors.append(KnowledgeFileError(manuals_dir, f"duplicate machine slugs across files: {dupes}"))

    return machines, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manuals-dir", type=Path, default=Path("manuals"))
    parser.add_argument("--out", type=Path, default=Path("index/knowledge.db"))
    args = parser.parse_args(argv)

    machines, errors = validate_all(args.manuals_dir)

    if errors:
        print(f"Found {len(errors)} invalid knowledge file(s):", file=sys.stderr)
        for e in errors:
            print(f"\n--- {e.path} ---\n{e.detail}", file=sys.stderr)
        return 1

    if not machines:
        print(f"No knowledge files found under {args.manuals_dir} -- nothing to build.", file=sys.stderr)
        return 1

    summary = _build_index(machines, args.out)
    print(
        f"Built {args.out}: {summary['machines']} machine(s), {summary['settings']} setting(s), "
        f"{summary['disassembly']} disassembly procedure(s), {summary['fault_finding']} fault-finding "
        f"entr(y/ies), {summary['touch_areas']} service-menu touch area(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
