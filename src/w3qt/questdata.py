"""Quest database (data/quests.json) and mapping of save journal entries onto it."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "quests.json"

# save journal status -> tracker status
STATUS_FROM_SAVE = {
    "active": "in_progress",
    "inactive": "in_progress",  # discovered but currently not active
    "success": "completed",
    "failed": "failed",
}


@dataclass
class QuestDB:
    quests: list[dict]
    by_resource: dict[str, dict] = field(init=False)
    by_guid: dict[str, dict] = field(init=False)

    def __post_init__(self):
        self.by_resource = {q["save_ids"]["journal_resource"].lower(): q for q in self.quests}
        self.by_guid = {q["save_ids"]["guid"]: q for q in self.quests}

    def lookup(self, resource: str | None, guid: str | None) -> dict | None:
        if guid and guid in self.by_guid:
            return self.by_guid[guid]
        if resource:
            return self.by_resource.get(resource.lower())
        return None


def load(path: Path | str = DEFAULT_PATH) -> QuestDB:
    doc = json.loads(Path(path).read_text())
    return QuestDB(doc["quests"])


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
            statuses[entry["id"]] = STATUS_FROM_SAVE.get(q["status"], "in_progress")
    return MappingResult(statuses, unknown)
