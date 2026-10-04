"""App configuration (~/.config/w3-quest-tracker/config.json)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from . import paths


@dataclass
class Config:
    active_profile: str | None = None
    name_lang: str = "de"
    save_dir: str | None = None

    @classmethod
    def path(cls) -> Path:
        return paths.config_dir() / "config.json"

    @classmethod
    def load(cls) -> Config:
        try:
            raw = json.loads(cls.path().read_text())
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def save(self) -> None:
        p = self.path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), indent=2))
