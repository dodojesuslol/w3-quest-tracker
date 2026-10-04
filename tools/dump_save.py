#!/usr/bin/env python3
"""Dump quest/journal data from a Witcher 3 .sav file to JSON (read-only).

Usage:
    tools/dump_save.py SAVE.sav [-o out.json] [--facts] [--all-journal] [--tree]
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from w3qt.savedata import (  # noqa: E402
    entry_to_dict,
    facts,
    journal_entries,
    metadata,
    quest_tree,
    summarize_tree,
)
from w3qt.savefile import SaveFormatError, open_save  # noqa: E402


def build_dump(path: Path, with_facts: bool, all_journal: bool, tree: bool) -> dict:
    save = open_save(path)
    entries = journal_entries(save)
    sidecar = path.with_suffix(".json")
    out = {
        "file": str(path),
        "metadata": metadata(save),
        "sidecar_json": json.loads(sidecar.read_text()) if sidecar.exists() else None,
        "journal_stats": {
            "entries": len(entries),
            "by_status": dict(collections.Counter(e.status for e in entries)),
            "by_root_folder": dict(collections.Counter(
                e.root_resource.rsplit("\\", 1)[0] for e in entries)),
        },
        "quest_groups": quest_tree(entries),
    }
    if all_journal:
        out["journal"] = [entry_to_dict(e) for e in entries]
    if with_facts:
        out["facts"] = facts(save)
    else:
        out["facts_count"] = len(facts(save))
    if tree:
        out["tree"] = summarize_tree(save.root)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("save", type=Path)
    ap.add_argument("-o", "--output", type=Path, help="write JSON here instead of stdout")
    ap.add_argument("--facts", action="store_true", help="include the full facts DB (large)")
    ap.add_argument("--all-journal", action="store_true", help="include every journal entry (bestiary, characters, ...)")
    ap.add_argument("--tree", action="store_true", help="include top-level block overview")
    args = ap.parse_args()
    try:
        dump = build_dump(args.save, args.facts, args.all_journal, args.tree)
    except (OSError, SaveFormatError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    text = json.dumps(dump, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
