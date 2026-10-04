"""Load the newest save and apply its quest statuses to a profile (no Qt)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import questdata
from .profiles import Profile
from .savedata import journal_entries, metadata, quest_tree
from .savefile import SaveFormatError, UnsupportedSaveVersion, open_save


@dataclass
class SaveSnapshot:
    path: Path
    mtime: float
    thumbnail: Path | None
    meta: dict
    quest_groups: list[dict] | None       # None if the journal could not be decoded
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # newer saves that were not usable


@dataclass
class SyncResult:
    applied: bool
    reason: str = ""
    quest_count: int = 0
    unknown: list[dict] = field(default_factory=list)


def list_saves(directory: Path) -> list[Path]:
    """*.sav files, newest modification time first."""
    try:
        saves = [p for p in directory.iterdir() if p.suffix.lower() == ".sav" and p.is_file()]
    except OSError:
        return []
    return sorted(saves, key=lambda p: p.stat().st_mtime, reverse=True)


def is_stable(path: Path, wait: float = 0.4) -> bool:
    """True if size and mtime do not change within `wait` seconds (game done writing)."""
    try:
        a = path.stat()
        time.sleep(wait)
        b = path.stat()
    except OSError:
        return False
    return (a.st_size, a.st_mtime_ns) == (b.st_size, b.st_mtime_ns) and a.st_size > 0


def load_snapshot(path: Path) -> SaveSnapshot:
    """Parse one save. Raises SaveFormatError if the file itself is unusable."""
    mtime = path.stat().st_mtime
    save = open_save(path)  # read-only
    warnings: list[str] = []
    try:
        meta = metadata(save)
    except Exception as e:  # metadata is best effort
        meta = {}
        warnings.append(f"Save metadata could not be decoded ({e}).")
    try:
        groups = quest_tree(journal_entries(save))
    except Exception as e:
        groups = None
        warnings.append(f"Quest journal could not be decoded ({e}); manual tracking only.")
    thumb = path.with_suffix(".png")
    return SaveSnapshot(path, mtime, thumb if thumb.is_file() else None, meta, groups, warnings)


class NotReady(Exception):
    """The newest save is still being written; try again shortly."""


def newest_snapshot(directory: Path, check_stable: bool = True) -> SaveSnapshot | None:
    """Load the newest usable save.

    Saves from unsupported game versions are skipped (noted in .skipped).
    If the newest save is incomplete, NotReady is raised so the caller retries.
    """
    skipped: list[str] = []
    for i, path in enumerate(list_saves(directory)):
        if check_stable and i == 0 and not is_stable(path):
            raise NotReady(path.name)
        try:
            snap = load_snapshot(path)
        except UnsupportedSaveVersion as e:
            skipped.append(f"{path.name}: {e}")
            continue
        except (SaveFormatError, OSError) as e:
            if i == 0:
                raise NotReady(f"{path.name}: {e}") from e
            skipped.append(f"{path.name}: {e}")
            continue
        snap.skipped = skipped
        return snap
    return None


def apply_snapshot(profile: Profile, db: questdata.QuestDB, snap: SaveSnapshot) -> SyncResult:
    """Copy save statuses into the profile, respecting its playthrough binding."""
    playthrough = snap.meta.get("playthrough_id")
    if profile.playthrough_id and playthrough and playthrough != profile.playthrough_id:
        return SyncResult(False, "This save belongs to a different playthrough than the active profile.")
    if snap.quest_groups is None:
        return SyncResult(False, "Quest journal could not be decoded; keeping manual statuses.")
    result = questdata.map_save_quests(db, snap.quest_groups)
    if profile.playthrough_id is None and playthrough:
        profile.playthrough_id = playthrough
    profile.save_status = result.statuses
    profile.last_save = {
        "file": snap.path.name,
        "mtime": snap.mtime,
        "synced": time.time(),
        "level": snap.meta.get("player_level"),
        "region": snap.meta.get("region"),
    }
    return SyncResult(True, "", len(result.statuses), result.unknown)


def log_unknown(log_path: Path, snap: SaveSnapshot, unknown: list[dict]) -> int:
    """Append unknown quest identifiers (deduplicated by GUID). Returns number of new entries."""
    if not unknown:
        return 0
    seen: set[str] = set()
    if log_path.is_file():
        for line in log_path.read_text().splitlines():
            try:
                seen.add(json.loads(line)["guid"])
            except (ValueError, KeyError):
                continue
    new = [u for u in unknown if u["guid"] not in seen]
    if new:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            for u in new:
                f.write(json.dumps({**u, "save": snap.path.name, "logged": time.strftime("%Y-%m-%d %H:%M:%S")}) + "\n")
    return len(new)
