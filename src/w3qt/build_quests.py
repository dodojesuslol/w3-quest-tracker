"""Build quests.json from the installed game files (read-only).

Everything written comes from the game: journal resources (.journal, CR2W),
quest_levels.csv and the .w3strings localisation. Fields the game files do
not contain (quest giver, missable, prerequisites) are left null and listed
in "unverified_fields".

The app runs this on first start; the file is never distributed because it
contains game text.

Usage: w3-quest-tracker-build-quests [--game-dir DIR] [-o FILE]

Default output: ~/.local/share/w3-quest-tracker/quests.json
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

from . import paths
from .gamefiles import cr2w
from .gamefiles.bundle import Bundle
from .gamefiles.locate import find_game_dir
from .gamefiles.w3strings import W3Strings

BUNDLES = ["startup", "dlc0", "ep1", "bob"]

# From scripts/game/commonMapManager.ws, GetDeprecatedAreaName(int)
AREAS = {
    0: ("AN_Undefined", None),
    1: ("AN_NMLandNovigrad", "Velen / Novigrad"),
    2: ("AN_Skellige_ArdSkellig", "Skellige"),
    3: ("AN_Kaer_Morhen", "Kaer Morhen"),
    4: ("AN_Prologue_Village", "White Orchard"),
    5: ("AN_Wyzima", "Vizima"),
    6: ("AN_Island_of_Myst", "Isle of Mist"),
    7: ("AN_Spiral", "The Spiral"),
    8: ("AN_Prologue_Village_Winter", "White Orchard"),
    9: ("AN_Velen", "Velen"),
    10: ("AN_CombatTestLevel", None),
    11: ("AN_Bob", "Toussaint"),
}

# eQuestType; Story is the enum default and therefore not serialized.
QUEST_TYPES = {
    "Story": "main",
    "Chapter": "main",
    "Side": "secondary",
    "MonsterHunt": "contract",
    "TreasureHunt": "treasure_hunt",
}

CONTENT = {None: "base", "EJCT_Vanilla": "base", "EJCT_EP1": "hearts_of_stone", "EJCT_EP2": "blood_and_wine"}

# Developer content that ships in the bundles but is not part of the game.
EXCLUDED_GROUPS = ("Demo Quests", "[PL] Test Level", "Test Level")

DEV_MARKERS = re.compile(r"^\s*(?:\[(?:[A-Z]{2}|DEBUG|TODO|WIP|PH)\]\s*)+")

UNVERIFIED_FIELDS = ["quest_giver", "missable", "missable_reason", "prerequisites"]


def localized(e: cr2w.Export, name: str) -> int | None:
    v = cr2w.prop_u32(e, name)
    return v or None


def read_levels(bundles: dict[str, Bundle]) -> dict[str, int]:
    levels: dict[str, int] = {}
    for b in bundles.values():
        for path in b.entries:
            if path.endswith(".csv") and "\\globals\\" in path and "quest_levels" in path:
                text = b.read(path).decode("utf-8-sig", "replace")
                for row in csv.reader(io.StringIO(text), delimiter=";"):
                    if len(row) >= 2 and row[1].strip().isdigit():
                        levels.setdefault(row[0].strip().lower(), int(row[1]))
    return levels


def collect(bundles: dict[str, Bundle]) -> tuple[list[dict], dict[str, dict]]:
    quests: list[dict] = []
    groups: dict[str, dict] = {}
    for bname, b in bundles.items():
        for path in sorted(b.entries):
            if not (path.endswith(".journal") and "\\journal\\quests\\" in path):
                continue
            doc = cr2w.parse(b.read(path))
            for g in doc.by_class("CJournalQuestGroup"):
                groups[cr2w.prop_guid(g)] = {
                    "resource": path,
                    "base_name": cr2w.prop_string(g, "baseName"),
                    "title_id": localized(g, "title"),
                }
            for q in doc.by_class("CJournalQuest"):
                descs = sorted(
                    (cr2w.prop_u32(d, "order") or 0, localized(d, "description"), cr2w.prop_guid(d))
                    for d in doc.by_class("CJournalQuestDescriptionEntry")
                    if localized(d, "description")
                )
                # objectives in file order, which follows the journal tree
                objectives = [
                    (cr2w.prop_guid(o), localized(o, "title"))
                    for o in doc.by_class("CJournalQuestObjective")
                    if localized(o, "title")
                ]
                quests.append({
                    "resource": path,
                    "bundle": bname,
                    "guid": cr2w.prop_guid(q),
                    "group_guid": cr2w.prop_guid(q, "parentGuid"),
                    "base_name": cr2w.prop_string(q, "baseName"),
                    "title_id": localized(q, "title"),
                    "type": cr2w.prop_enum(doc, q, "type") or "Story",
                    "content": cr2w.prop_enum(doc, q, "contentType"),
                    "world": cr2w.prop_u32(q, "world"),
                    "description_id": descs[0][1] if descs else None,
                    "journal": [(guid, sid) for _, sid, guid in descs],
                    "objectives": objectives,
                })
    return quests, groups


def expansion_of(q: dict) -> str:
    if q["content"] in CONTENT and q["content"] is not None:
        return CONTENT[q["content"]]
    if q["resource"].startswith("dlc\\ep1\\"):
        return "hearts_of_stone"
    if q["resource"].startswith("dlc\\bob\\"):
        return "blood_and_wine"
    return "base"


def is_game_dir(game: Path) -> bool:
    return (game / "content" / "content0" / "bundles").is_dir()


def build(game: Path, output: Path) -> tuple[int, int]:
    """Write quests.json for the installation in `game`; returns (quests, skipped)."""
    content = game / "content" / "content0"
    bundles = {n: Bundle(content / "bundles" / f"{n}.bundle") for n in BUNDLES}
    quests, groups = collect(bundles)
    levels = read_levels(bundles)

    known_ids = {q["title_id"] for q in quests if q["title_id"]}
    strings = {}
    for lang in ("en", "de"):
        s = W3Strings(content / f"{lang}.w3strings")
        s.set_key(s.find_lang_key(known_ids))
        strings[lang] = s

    def text(lang: str, sid: int | None) -> str | None:
        t = strings[lang].get(sid) if sid else None
        # developer markers such as "[EN] [DEBUG]" in front of a few game texts
        return DEV_MARKERS.sub("", t) if t else t

    out = []
    skipped = []
    for q in quests:
        name_en = text("en", q["title_id"])
        group = groups.get(q["group_guid"])
        if not name_en or group is None:
            skipped.append({"resource": q["resource"], "base_name": q["base_name"],
                            "reason": "no title" if not name_en else "not in a quest group"})
            continue
        group_name = text("en", group["title_id"]) or group["base_name"]
        if group_name in EXCLUDED_GROUPS:
            skipped.append({"resource": q["resource"], "base_name": q["base_name"],
                            "reason": f"developer group {group_name!r}"})
            continue
        category = QUEST_TYPES[q["type"]]
        internal = (q["base_name"] or "").strip().lower()
        if internal.startswith(("cg", "card game")):
            category = "gwent"
        area_code, region = AREAS.get(q["world"] or 0, (None, None))
        stem = q["resource"].rsplit("\\", 1)[-1].removesuffix(".journal")
        out.append({
            "id": stem,
            "name": name_en,
            "name_de": text("de", q["title_id"]),
            "category": category,
            "quest_type": q["type"],
            "region": region,
            "area_code": area_code,
            "suggested_level": levels.get((q["base_name"] or "").lower()),
            "quest_giver": None,
            "missable": None,
            "missable_reason": None,
            "prerequisites": [],
            "expansion": expansion_of(q),
            "journal_group": group_name,
            "save_ids": {"journal_resource": q["resource"], "guid": q["guid"]},
            "internal_name": q["base_name"],
            "description": text("en", q["description_id"]),
            "description_de": text("de", q["description_id"]),
            # Journal texts and objectives, each with the GUID the save uses to
            # mark it as revealed/active/done.
            "journal": [{"guid": g, "text": text("en", sid), "text_de": text("de", sid)}
                        for g, sid in q["journal"]],
            "objectives": [{"guid": g, "name": text("en", sid), "name_de": text("de", sid)}
                           for g, sid in q["objectives"]],
        })
    out.sort(key=lambda r: (r["expansion"], r["category"], r["name"]))
    doc = {
        "schema": 1,
        "source": "Extracted from the installed game files by w3qt.build_quests",
        "unverified_fields": UNVERIFIED_FIELDS,
        "quest_count": len(out),
        "quests": out,
        "skipped": skipped,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(output)
    return len(out), len(skipped)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game-dir", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=paths.data_dir() / "quests.json")
    args = ap.parse_args()
    game = args.game_dir or find_game_dir()
    if game is None:
        print("error: Witcher 3 installation not found; pass --game-dir", file=sys.stderr)
        return 1
    n, skipped = build(game, args.output)
    print(f"wrote {n} quests ({skipped} skipped) to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
