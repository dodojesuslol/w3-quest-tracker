#!/usr/bin/env python3
"""Rebuild ~/.local/share/w3-quest-tracker/quests.json from the installed game (see w3qt.build_quests)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from w3qt.build_quests import main  # noqa: E402

sys.exit(main())
