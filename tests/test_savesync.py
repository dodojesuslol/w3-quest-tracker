import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from w3qt import savesync  # noqa: E402
from w3qt.profiles import Profile  # noqa: E402

from support import CHECKPOINT, FIXTURES, MANUAL, needs_game, needs_saves, quest_db  # noqa: E402


def copy_save(stem: str, dest: Path, mtime: float) -> Path:
    for ext in (".sav", ".png", ".json"):
        src = FIXTURES / f"{stem}{ext}"
        if src.exists():
            shutil.copy(src, dest / src.name)
            os.utime(dest / src.name, (mtime, mtime))
    return dest / f"{stem}.sav"


@needs_saves
class TestNewestSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_picks_newest_by_mtime(self):
        now = time.time()
        copy_save(MANUAL, self.dir, now - 100)
        copy_save(CHECKPOINT, self.dir, now - 50)
        snap = savesync.newest_snapshot(self.dir, check_stable=False)
        self.assertEqual(snap.path.name, f"{CHECKPOINT}.sav")
        self.assertEqual(snap.meta["player_level"], 37)
        self.assertIsNotNone(snap.thumbnail)
        self.assertEqual(snap.warnings, [])

    def test_truncated_newest_is_not_ready(self):
        copy_save(MANUAL, self.dir, time.time() - 100)
        partial = self.dir / "AutoSave_new.sav"
        partial.write_bytes((FIXTURES / f"{MANUAL}.sav").read_bytes()[:100_000])
        with self.assertRaises(savesync.NotReady):
            savesync.newest_snapshot(self.dir, check_stable=False)

    def test_empty_folder(self):
        self.assertIsNone(savesync.newest_snapshot(self.dir, check_stable=False))

    def test_opens_read_only(self):
        p = copy_save(MANUAL, self.dir, time.time())
        p.chmod(0o444)
        before = p.read_bytes()
        savesync.newest_snapshot(self.dir, check_stable=False)
        self.assertEqual(p.read_bytes(), before)


@needs_game
@needs_saves
class TestApply(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = quest_db()
        cls.snap = savesync.load_snapshot(FIXTURES / f"{MANUAL}.sav")

    def test_apply_binds_playthrough(self):
        p = Profile("x")
        res = savesync.apply_snapshot(p, self.db, self.snap)
        self.assertTrue(res.applied)
        self.assertEqual(p.playthrough_id, "693a950b0000132e")
        self.assertEqual(p.save_status["q001yennsearch"], "completed")
        self.assertEqual(p.last_save["level"], 38)

    def test_other_playthrough_not_applied(self):
        p = Profile("x", playthrough_id="something-else")
        res = savesync.apply_snapshot(p, self.db, self.snap)
        self.assertFalse(res.applied)
        self.assertEqual(p.save_status, {})

    def test_manual_priority_still_wins(self):
        p = Profile("x", priority="manual")
        p.set_manual("q001yennsearch", "failed")
        savesync.apply_snapshot(p, self.db, self.snap)
        self.assertEqual(p.status("q001yennsearch"), "failed")

    def test_undecodable_journal_falls_back(self):
        snap = savesync.SaveSnapshot(self.snap.path, 0, None, self.snap.meta, None, ["broken"])
        p = Profile("x")
        res = savesync.apply_snapshot(p, self.db, snap)
        self.assertFalse(res.applied)

    def test_unknown_log_dedup(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "unknown.log"
            unknown = [{"guid": "ab" * 16, "resource": "x.journal", "status": "active"}]
            self.assertEqual(savesync.log_unknown(log, self.snap, unknown), 1)
            self.assertEqual(savesync.log_unknown(log, self.snap, unknown), 0)
            self.assertEqual(len(log.read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
