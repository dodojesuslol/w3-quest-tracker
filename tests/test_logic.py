import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from w3qt import filtering  # noqa: E402
from w3qt.filtering import Criteria  # noqa: E402
from w3qt.profiles import Profile, ProfileStore  # noqa: E402

from support import needs_game, quest_db  # noqa: E402


class TestProfile(unittest.TestCase):
    def test_priority(self):
        p = Profile("x")
        p.save_status["a"] = "completed"
        p.set_manual("a", "failed")
        self.assertEqual(p.status("a"), "completed")
        p.priority = "manual"
        self.assertEqual(p.status("a"), "failed")
        self.assertEqual(p.status("zzz"), "not_started")

    def test_falls_back_to_other_source(self):
        p = Profile("x", priority="save")
        p.set_manual("b", "in_progress")
        self.assertEqual(p.status("b"), "in_progress")

    def test_invalid_status(self):
        with self.assertRaises(ValueError):
            Profile("x").set_manual("a", "done")

    def test_store_roundtrip_and_import_rename(self):
        with tempfile.TemporaryDirectory() as d:
            store = ProfileStore(Path(d) / "profiles")
            p = Profile("Run 1")
            p.set_manual("q1", "completed")
            p.set_note("q1", "kept the sword")
            store.save(p)
            self.assertEqual(store.load("Run 1").notes["q1"], "kept the sword")
            exp = Path(d) / "export.json"
            store.export(p, exp)
            imported = store.import_file(exp)
            self.assertEqual(imported.name, "Run 1 (2)")
            self.assertEqual(imported.manual_status, {"q1": "completed"})
            self.assertEqual(sorted(store.names()), ["Run 1", "Run 1 (2)"])

    def test_import_rejects_garbage(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.json"
            f.write_text(json.dumps({"name": "x"}))
            with self.assertRaises(ValueError):
                ProfileStore(Path(d) / "p").import_file(f)


@needs_game
class TestFiltering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = quest_db()

    def test_overlay_merged(self):
        q = self.db.by_id["sq202yen"]
        self.assertTrue(q["missable"])
        self.assertEqual(q["point_of_no_return"], "q401_konsylium")
        self.assertTrue(q["sources"])
        self.assertEqual(len(self.db.points_of_no_return), 15)

    def test_search_both_languages(self):
        p = Profile("x")
        en = filtering.filter_quests(self.db.quests, p, Criteria(text="gooseberries"))
        de = filtering.filter_quests(self.db.quests, p, Criteria(text="stachelbeeren"))
        self.assertEqual([q["id"] for q in en], ["q001yennsearch"])
        self.assertEqual(en, de)

    def test_combined_filters(self):
        p = Profile("x")
        c = Criteria(categories={"contract"}, expansions={"base"}, level_min=10, level_max=20)
        res = filtering.filter_quests(self.db.quests, p, c)
        self.assertTrue(res)
        for q in res:
            self.assertEqual(q["category"], "contract")
            self.assertTrue(10 <= q["suggested_level"] <= 20)

    def test_status_and_missable_filter(self):
        p = Profile("x")
        p.set_manual("mq0003freshwater", "completed")
        res = filtering.filter_quests(self.db.quests, p, Criteria(missable_only=True, statuses={"not_started"}))
        ids = {q["id"] for q in res}
        self.assertNotIn("mq0003freshwater", ids)
        self.assertIn("sq202yen", ids)

    def test_sorting(self):
        qs = sorted(self.db.quests, key=filtering.sort_key("level"))
        levels = [q["suggested_level"] for q in qs if q["suggested_level"] is not None]
        self.assertEqual(levels, sorted(levels))
        self.assertIsNone(qs[-1]["suggested_level"])

    def test_progress(self):
        p = Profile("x")
        p.set_manual("q001yennsearch", "completed")
        p.set_manual("mq0003freshwater", "failed")
        total = filtering.progress(self.db.quests, p)
        self.assertEqual((total.done, total.total), (1, len(self.db.quests)))
        by_cat = filtering.progress(self.db.quests, p, key=lambda q: q["category"])
        self.assertEqual(by_cat["main"].done, 1)
        self.assertEqual(by_cat["contract"].done, 0)

    def test_open_missables(self):
        p = Profile("x")
        before = filtering.open_missables(self.db, p, "q001yennsearch")
        p.set_manual("mq0003freshwater", "completed")
        after = filtering.open_missables(self.db, p, "q001yennsearch")
        self.assertEqual(len(before) - 1, len(after))

    def test_ponr_trigger(self):
        p = Profile("x")
        start = {"quest_id": "q402ciri", "trigger": "start"}
        complete = {"quest_id": "q402ciri", "trigger": "complete"}
        p.set_manual("q402ciri", "in_progress")
        self.assertTrue(filtering.ponr_passed(p, start))
        self.assertFalse(filtering.ponr_passed(p, complete))


if __name__ == "__main__":
    unittest.main()
