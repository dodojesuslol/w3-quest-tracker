import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    QApplication = None

FIXTURES = Path(__file__).parent / "fixtures" / "saves"


@unittest.skipUnless(QApplication, "PySide6 not installed")
class TestSaveWatcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_for(self, signal, timeout_ms=15000):
        loop, got = QEventLoop(), []
        signal.connect(lambda *a: (got.append(a), loop.quit()))
        QTimer.singleShot(timeout_ms, loop.quit)
        loop.exec()
        return got[0] if got else None

    def test_initial_and_new_save(self):
        from w3qt.watcher import SaveWatcher
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            shutil.copy(FIXTURES / "CheckPoint_11b6cd_7ea48c00_3cd014e.sav", d)
            w = SaveWatcher()
            w.set_directory(d)
            (snap,) = self.wait_for(w.snapshot_ready)
            self.assertEqual(snap.meta["player_level"], 37)
            # the game writes a new save -> watcher picks it up
            shutil.copy(FIXTURES / "ManualSave_11b6cd_7ea48c00_411cb11.sav", d)
            (snap,) = self.wait_for(w.snapshot_ready)
            self.assertEqual(snap.path.name, "ManualSave_11b6cd_7ea48c00_411cb11.sav")
            w.stop()


if __name__ == "__main__":
    unittest.main()
