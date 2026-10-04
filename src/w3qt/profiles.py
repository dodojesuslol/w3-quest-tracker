"""Playthrough profiles: manual statuses, notes, save-derived statuses."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

STATUSES = ("not_started", "in_progress", "completed", "failed")
PRIORITIES = ("save", "manual")


@dataclass
class Profile:
    name: str
    priority: str = "save"                     # which source wins when both exist
    manual_status: dict[str, str] = field(default_factory=dict)
    save_status: dict[str, str] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)
    playthrough_id: str | None = None          # save playthrough this profile follows
    last_save: dict | None = None              # info about the last synced save
    created: float = field(default_factory=time.time)

    def status(self, quest_id: str) -> str:
        manual = self.manual_status.get(quest_id)
        saved = self.save_status.get(quest_id)
        if self.priority == "manual":
            return manual or saved or "not_started"
        return saved or manual or "not_started"

    def set_manual(self, quest_id: str, status: str | None) -> None:
        if status is None:
            self.manual_status.pop(quest_id, None)
        elif status not in STATUSES:
            raise ValueError(status)
        else:
            self.manual_status[quest_id] = status

    def set_note(self, quest_id: str, text: str) -> None:
        if text.strip():
            self.notes[quest_id] = text
        else:
            self.notes.pop(quest_id, None)

    def to_dict(self) -> dict:
        return {"format": "w3-quest-tracker-profile", "version": 1, **asdict(self)}

    @classmethod
    def from_dict(cls, d: dict) -> Profile:
        if d.get("format") != "w3-quest-tracker-profile":
            raise ValueError("not a w3-quest-tracker profile")
        p = cls(name=str(d["name"]))
        p.priority = d.get("priority", "save") if d.get("priority") in PRIORITIES else "save"
        p.manual_status = {k: v for k, v in d.get("manual_status", {}).items() if v in STATUSES}
        p.save_status = {k: v for k, v in d.get("save_status", {}).items() if v in STATUSES}
        p.notes = {k: str(v) for k, v in d.get("notes", {}).items()}
        p.playthrough_id = d.get("playthrough_id")
        p.last_save = d.get("last_save")
        p.created = float(d.get("created", time.time()))
        return p


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "profile"


class ProfileStore:
    def __init__(self, directory: Path):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, name: str) -> Path:
        return self.dir / f"{_slug(name)}.json"

    def names(self) -> list[str]:
        out = []
        for f in sorted(self.dir.glob("*.json")):
            try:
                out.append(json.loads(f.read_text())["name"])
            except (OSError, ValueError, KeyError):
                continue
        return out

    def load(self, name: str) -> Profile:
        return Profile.from_dict(json.loads(self.path_for(name).read_text()))

    def save(self, profile: Profile) -> None:
        path = self.path_for(profile.name)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False))
        tmp.replace(path)

    def delete(self, name: str) -> None:
        self.path_for(name).unlink(missing_ok=True)

    def ensure_default(self) -> Profile:
        names = self.names()
        if names:
            return self.load(names[0])
        p = Profile("Default")
        self.save(p)
        return p

    def export(self, profile: Profile, dest: Path) -> None:
        dest.write_text(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False))

    def import_file(self, src: Path) -> Profile:
        p = Profile.from_dict(json.loads(src.read_text()))
        base, n = p.name, 2
        while p.name in self.names():
            p.name = f"{base} ({n})"
            n += 1
        self.save(p)
        return p
