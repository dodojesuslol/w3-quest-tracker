"""Pure filtering, sorting and progress logic used by the UI."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .profiles import Profile

CATEGORY_LABELS = {
    "main": "Main",
    "secondary": "Secondary",
    "contract": "Witcher Contract",
    "treasure_hunt": "Treasure Hunt",
    "gwent": "Gwent",
}
EXPANSION_LABELS = {
    "base": "Base game",
    "hearts_of_stone": "Hearts of Stone",
    "blood_and_wine": "Blood and Wine",
}
STATUS_LABELS = {
    "not_started": "Not started",
    "in_progress": "In progress",
    "completed": "Completed",
    "failed": "Failed / Missed",
}
DONE = ("completed", "failed")


@dataclass
class Criteria:
    text: str = ""
    categories: set[str] = field(default_factory=set)   # empty = all
    regions: set[str] = field(default_factory=set)
    expansions: set[str] = field(default_factory=set)
    statuses: set[str] = field(default_factory=set)
    level_min: int | None = None
    level_max: int | None = None
    missable_only: bool = False
    name_lang: str = "en"


def display_name(q: dict, lang: str) -> str:
    return (q.get("name_de") if lang == "de" else None) or q["name"]


def region_of(q: dict) -> str:
    return q.get("region") or "Unknown"


def matches(q: dict, status: str, c: Criteria) -> bool:
    if c.text:
        needle = c.text.casefold()
        if needle not in q["name"].casefold() and needle not in (q.get("name_de") or "").casefold():
            return False
    if c.categories and q["category"] not in c.categories:
        return False
    if c.regions and region_of(q) not in c.regions:
        return False
    if c.expansions and q["expansion"] not in c.expansions:
        return False
    if c.statuses and status not in c.statuses:
        return False
    lvl = q.get("suggested_level")
    if c.level_min is not None and (lvl is None or lvl < c.level_min):
        return False
    if c.level_max is not None and (lvl is None or lvl > c.level_max):
        return False
    if c.missable_only and not q.get("missable"):
        return False
    return True


def filter_quests(quests: list[dict], profile: Profile, c: Criteria) -> list[dict]:
    return [q for q in quests if matches(q, profile.status(q["id"]), c)]


def sort_key(field_name: str, lang: str = "en"):
    if field_name == "level":
        return lambda q: (q.get("suggested_level") is None, q.get("suggested_level") or 0, q["name"])
    if field_name == "region":
        return lambda q: (region_of(q), display_name(q, lang).casefold())
    return lambda q: display_name(q, lang).casefold()


@dataclass
class Progress:
    done: int
    total: int

    @property
    def fraction(self) -> float:
        return self.done / self.total if self.total else 0.0


def progress(quests: list[dict], profile: Profile, key=None) -> dict[str, Progress] | Progress:
    """Completed quests out of all. With key, returns progress per group."""
    if key is None:
        done = sum(profile.status(q["id"]) == "completed" for q in quests)
        return Progress(done, len(quests))
    totals, dones = Counter(), Counter()
    for q in quests:
        k = key(q)
        totals[k] += 1
        dones[k] += profile.status(q["id"]) == "completed"
    return {k: Progress(dones[k], totals[k]) for k in totals}


def open_missables(db, profile: Profile, ponr_quest_id: str) -> list[dict]:
    return [q for q in db.missables_for(ponr_quest_id) if profile.status(q["id"]) not in DONE]
