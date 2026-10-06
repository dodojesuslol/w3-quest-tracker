"""Quest database (quests.json, built from the game) and mapping of save journal entries onto it."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

DATA_DIR = Path(__file__).resolve().parent / "data"
MISSABLE_PATH = DATA_DIR / "missable.json"


def default_path() -> Path:
    """Built from the installed game on first start (see build_quests)."""
    return paths.data_dir() / "quests.json"


OVERLAY_FIELDS = ("missable", "missable_reason", "point_of_no_return", "sources", "verified", "note")

# save journal status -> tracker status
# JS_Inactive entries exist in the journal but are not shown to the player,
# so they carry no status; manual tracking applies for them.
STATUS_FROM_SAVE = {
    "active": "in_progress",
    "success": "completed",
    "failed": "failed",
}


@dataclass
class QuestDB:
    quests: list[dict]
    points_of_no_return: list[dict] = field(default_factory=list)
    by_id: dict[str, dict] = field(init=False)
    by_resource: dict[str, dict] = field(init=False)
    by_guid: dict[str, dict] = field(init=False)

    def __post_init__(self):
        self.by_id = {q["id"]: q for q in self.quests}
        self.by_resource = {q["save_ids"]["journal_resource"].lower(): q for q in self.quests}
        self.by_guid = {q["save_ids"]["guid"]: q for q in self.quests}

    def missables_for(self, ponr_quest_id: str) -> list[dict]:
        return [q for q in self.quests if q.get("point_of_no_return") == ponr_quest_id]

    def lookup(self, resource: str | None, guid: str | None) -> dict | None:
        if guid and guid in self.by_guid:
            return self.by_guid[guid]
        if resource:
            return self.by_resource.get(resource.lower())
        return None


def load(path: Path | str | None = None, missable_path: Path | str | None = MISSABLE_PATH) -> QuestDB:
    """Raises OSError, ValueError, KeyError or TypeError for a missing or broken file."""
    doc = json.loads(Path(path or default_path()).read_text())
    quests = doc["quests"]
    ponr: list[dict] = []
    if missable_path and Path(missable_path).is_file():
        overlay = json.loads(Path(missable_path).read_text())
        by_id = {q["id"]: q for q in quests}
        for qid, extra in overlay.get("quests", {}).items():
            if qid in by_id:
                by_id[qid].update({k: extra[k] for k in OVERLAY_FIELDS if k in extra})
        ponr = [p for p in overlay.get("points_of_no_return", []) if p["quest_id"] in by_id]
    return QuestDB(quests, ponr)


@dataclass
class MappingResult:
    statuses: dict[str, str]          # quest id -> tracker status
    unknown: list[dict]               # save quests not found in quests.json


def map_save_quests(db: QuestDB, quest_groups: list[dict]) -> MappingResult:
    """quest_groups is the output of savedata.quest_tree()."""
    statuses: dict[str, str] = {}
    unknown: list[dict] = []
    for g in quest_groups:
        for q in g["quests"]:
            entry = db.lookup(q["resource"], q["guid"])
            if entry is None:
                unknown.append({"guid": q["guid"], "resource": q["resource"], "status": q["status"]})
                continue
            status = STATUS_FROM_SAVE.get(q["status"])
            if status:
                statuses[entry["id"]] = status
    return MappingResult(statuses, unknown)
