"""Offscreen smoke test of the main window."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    QApplication = None

from support import needs_game, quest_db  # noqa: E402


@unittest.skipUnless(QApplication, "PySide6 not installed")
@needs_game
class TestMainWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["XDG_DATA_HOME"] = str(Path(cls.tmp.name) / "data")
        os.environ["XDG_CONFIG_HOME"] = str(Path(cls.tmp.name) / "config")
        # point the watcher at an empty folder so the test never reads real saves
        saves = Path(cls.tmp.name) / "saves"
        saves.mkdir()
        cfg = Path(cls.tmp.name) / "config" / "w3-quest-tracker"
        cfg.mkdir(parents=True)
        (cfg / "config.json").write_text(json.dumps({"save_dir": str(saves)}))
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def make_window(self):
        from w3qt.config import Config
        from w3qt.profiles import ProfileStore
        from w3qt.ui.main_window import MainWindow, profiles_dir
        return MainWindow(quest_db(), ProfileStore(profiles_dir()), Config.load())

    def test_filter_select_and_set_status(self):
        w = self.make_window()
        self.assertEqual(w.model.rowCount(), len(w.db.quests))
        w.search.setText("gooseberries")
        self.assertEqual(w.model.rowCount(), 1)
        w.open_page("q001yennsearch")
        w.page.status_buttons["completed"].click()
        w.page.go_back()
        self.assertEqual(w.profile.status("q001yennsearch"), "completed")
        self.assertEqual(w.overall.value(), 1)
        w.close()
        # persisted
        w2 = self.make_window()
        self.assertEqual(w2.profile.status("q001yennsearch"), "completed")
        w2.close()

    def test_quest_page_open_status_back(self):
        w = self.make_window()
        w.open_page("q001yennsearch")
        self.assertIs(w.stack.currentWidget(), w.page)
        self.assertTrue(w.top_area.isHidden())
        self.assertIn("Lilac", w.page.alt.text() + w.page.title.text())
        # no save loaded in this test: every objective is listed
        self.assertIn("Vesemir", w.page.objectives.text())
        w.page.status_buttons["failed"].click()
        self.assertEqual(w.profile.status("q001yennsearch"), "failed")
        w.page.go_back()
        self.assertIs(w.stack.currentWidget(), w.tabs)
        self.assertFalse(w.top_area.isHidden())
        w.close()

    def test_missable_filter(self):
        w = self.make_window()
        w.f_missable.setChecked(True)
        rows = [w.model.quest_at(i) for i in range(w.model.rowCount())]
        self.assertTrue(rows)
        self.assertTrue(all(q["missable"] for q in rows))
        w.close()


if __name__ == "__main__":
    unittest.main()
