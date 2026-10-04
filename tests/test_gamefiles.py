"""Tests against the installed game; skipped when it is not found."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from w3qt.gamefiles import cr2w  # noqa: E402
from w3qt.gamefiles.bundle import Bundle  # noqa: E402
from w3qt.gamefiles.locate import find_game_dir  # noqa: E402
from w3qt.gamefiles.w3strings import W3Strings  # noqa: E402

GAME = find_game_dir()
CONTENT = GAME / "content" / "content0" if GAME else None
Q001 = "gameplay\\journal\\quests\\q001yennsearch.journal"


@unittest.skipUnless(GAME, "Witcher 3 installation not found")
class TestGameFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.startup = Bundle(CONTENT / "bundles" / "startup.bundle")

    def test_journal_cr2w(self):
        doc = cr2w.parse(self.startup.read(Q001))
        (quest,) = doc.by_class("CJournalQuest")
        self.assertEqual(cr2w.prop_guid(quest), "7c198a768adc3046b34b5a730b5b53c9")
        self.assertEqual(cr2w.prop_string(quest, "baseName"), "Q001 Find Yennefer")
        self.assertEqual(cr2w.prop_u32(quest, "title"), 0x8559A)

    def test_w3strings_en(self):
        s = W3Strings(CONTENT / "en.w3strings")
        s.set_key(0x79321793)
        self.assertEqual(s.get(0x8559A), "Lilac and Gooseberries")
        self.assertEqual(s.get(0x297A5), "Go to the tavern in White Orchard.")

    def test_w3strings_key_recovery(self):
        ids = set()
        for path in self.startup.entries:
            if path.startswith("gameplay\\journal\\quests\\") and len(ids) < 300:
                doc = cr2w.parse(self.startup.read(path))
                ids |= {cr2w.prop_u32(e, "title") for e in doc.exports if "title" in e.props}
        s = W3Strings(CONTENT / "en.w3strings")
        self.assertEqual(s.find_lang_key(ids), 0x79321793)


if __name__ == "__main__":
    unittest.main()
