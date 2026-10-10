"""Shared test data. Neither the sample saves nor quests.json are in the
repository (personal saves, game text), so tests that need them skip."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from w3qt import questdata  # noqa: E402
from w3qt.build_quests import build  # noqa: E402
from w3qt.gamefiles.locate import find_game_dir  # noqa: E402

# Put a few of your own version-66/67 saves here to run the save tests; the
# folder is git-ignored. Expected names match the original playthrough.
FIXTURES = Path(__file__).parent / "fixtures" / "saves"
MANUAL = "ManualSave_11b6cd_7ea48c00_411cb11"
CHECKPOINT = "CheckPoint_11b6cd_7ea48c00_3cd014e"
HAVE_SAVES = (FIXTURES / f"{MANUAL}.sav").is_file() and (FIXTURES / f"{CHECKPOINT}.sav").is_file()
GAME = find_game_dir()

needs_saves = unittest.skipUnless(HAVE_SAVES, "sample saves not present in tests/fixtures/saves")
needs_game = unittest.skipUnless(GAME, "Witcher 3 installation not found")

_tmp: tempfile.TemporaryDirectory | None = None


def quests_path() -> Path:
    """quests.json built once per test run from the installed game."""
    global _tmp
    if _tmp is None:
        _tmp = tempfile.TemporaryDirectory()
        build(GAME, Path(_tmp.name) / "quests.json")
    return Path(_tmp.name) / "quests.json"


def quest_db() -> questdata.QuestDB:
    return questdata.load(quests_path())
