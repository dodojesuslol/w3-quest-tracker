import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from w3qt import questdata  # noqa: E402
from w3qt.savedata import journal_entries, quest_tree  # noqa: E402
from w3qt.savefile import open_save  # noqa: E402

from support import FIXTURES, MANUAL, needs_game, needs_saves, quest_db  # noqa: E402

SAVE = FIXTURES / f"{MANUAL}.sav"

REQUIRED = {"id", "name", "category", "region", "suggested_level", "quest_giver", "missable",
            "missable_reason", "prerequisites", "expansion", "save_ids", "description"}
CATEGORIES = {"main", "secondary", "contract", "treasure_hunt", "gwent"}
EXPANSIONS = {"base", "hearts_of_stone", "blood_and_wine"}


@needs_game
class TestQuestsJson(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = quest_db()

    def test_schema(self):
        self.assertGreater(len(self.db.quests), 350)
        for q in self.db.quests:
            with self.subTest(q.get("id")):
                self.assertLessEqual(REQUIRED, q.keys())
                self.assertIn(q["category"], CATEGORIES)
                self.assertIn(q["expansion"], EXPANSIONS)
                self.assertTrue(q["name"])

    def test_unique_keys(self):
        ids = [q["id"] for q in self.db.quests]
        guids = [q["save_ids"]["guid"] for q in self.db.quests]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(guids), len(set(guids)))

    def test_known_entries(self):
        q = self.db.by_resource["gameplay\\journal\\quests\\q001yennsearch.journal"]
        self.assertEqual((q["name"], q["name_de"]), ("Lilac and Gooseberries", "Flieder und Stachelbeeren"))
        self.assertEqual((q["category"], q["region"], q["suggested_level"]), ("main", "White Orchard", 1))
        self.assertEqual(self.db.by_resource["gameplay\\journal\\quests\\mq0003freshwater.journal"]["category"],
                         "contract")

    def test_unverified_fields_left_empty(self):
        for q in self.db.quests:
            self.assertIsNone(q["quest_giver"])
            if q["missable"] is not None:  # only from the hand-curated overlay
                self.assertTrue(q["sources"], q["id"])
                self.assertTrue(all(u.startswith("https://") for u in q["sources"]))


class TestDefaultPath(unittest.TestCase):
    def test_missing_or_broken_raises(self):
        import os
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"XDG_DATA_HOME": d}):
            with self.assertRaises(OSError):
                questdata.load()
            questdata.default_path().parent.mkdir()
            questdata.default_path().write_text('{"quests": [')
            with self.assertRaises(ValueError):
                questdata.load()


class TestMapping(unittest.TestCase):
    @needs_game
    @needs_saves
    def test_save_maps_completely(self):
        db = quest_db()
        groups = quest_tree(journal_entries(open_save(SAVE)))
        res = questdata.map_save_quests(db, groups)
        self.assertEqual(res.unknown, [])
        self.assertEqual(res.statuses["q001yennsearch"], "completed")
        self.assertGreater(len(res.statuses), 150)

    def test_unknown_reported(self):
        db = questdata.QuestDB([])
        groups = [{"quests": [{"guid": "00" * 16, "resource": "x.journal", "status": "active"}]}]
        res = questdata.map_save_quests(db, groups)
        self.assertEqual(len(res.unknown), 1)
        self.assertEqual(res.statuses, {})


if __name__ == "__main__":
    unittest.main()
