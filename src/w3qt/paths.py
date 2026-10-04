"""XDG locations."""

from __future__ import annotations

import os
from pathlib import Path

APP = "w3-quest-tracker"


def data_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    return base / APP


def config_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / APP
