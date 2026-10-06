import struct
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from w3qt import lz4block, savefile  # noqa: E402
from w3qt.savedata import facts, journal_entries, metadata, quest_tree  # noqa: E402
from w3qt.savefile import SaveFormatError, open_save, parse_bytes, read_cstring  # noqa: E402

from support import FIXTURES, needs_saves  # noqa: E402

NEXTGEN = FIXTURES / "ManualSave_11b6cd_7ea48c00_411cb11.sav"   # Toussaint, level 38
CHECKPOINT = FIXTURES / "CheckPoint_11b6cd_7ea48c00_3cd014e.sav"  # same run, level 37


def all_saves():
    return sorted(FIXTURES.glob("*.sav"))


class TestLz4(unittest.TestCase):
    def test_literals_and_overlapping_match(self):
        # token: 1 literal + match len 4+4; literal 'a'; offset 1 -> 'a' * 9
        block = bytes([0x14]) + b"a" + struct.pack("<H", 1) + bytes([0x10]) + b"b"
        self.assertEqual(lz4block._decompress_py(block, 10), b"a" * 9 + b"b")

    def test_size_mismatch_raises(self):
        with self.assertRaises(ValueError):
            lz4block._decompress_py(bytes([0x10]) + b"x", 5)


class TestCString(unittest.TestCase):
    def test_narrow_short(self):
        self.assertEqual(read_cstring(b"\x83abcX", 0), ("abc", 4))

    def test_narrow_long(self):
        s = b"x" * 100  # 100 = 0x24 | (1 << 6)
        self.assertEqual(read_cstring(bytes([0x80 | 0x40 | 0x24, 1]) + s, 0), ("x" * 100, 102))

    def test_wide(self):
        self.assertEqual(read_cstring(b"\x02h\x00i\x00", 0), ("hi", 5))


@needs_saves
class TestContainer(unittest.TestCase):
    def test_all_fixtures_parse(self):
        saves = all_saves()
        self.assertTrue(saves, "no fixtures")
        for p in saves:
            with self.subTest(p.name):
                s = open_save(p)
                self.assertEqual(s.save_version, 66)
                self.assertIsNotNone(s.block("CJournalManager"))

    def test_rejects_non_save(self):
        with self.assertRaises(SaveFormatError):
            parse_bytes(b"not a save at all")

    def test_truncated_file_raises_format_error(self):
        raw = NEXTGEN.read_bytes()
        with self.assertRaises(SaveFormatError):
            parse_bytes(raw[: len(raw) // 2])

    def test_versions(self):
        s = open_save(NEXTGEN)
        self.assertEqual((s.save_version, s.game_version), (66, 29))

    def test_rejects_unsupported_version(self):
        with mock.patch.object(savefile, "SUPPORTED_SAVE_VERSIONS", (64,)):
            with self.assertRaises(SaveFormatError):
                open_save(NEXTGEN)


@needs_saves
class TestMetadata(unittest.TestCase):
    def test_nextgen(self):
        m = metadata(open_save(NEXTGEN))
        self.assertEqual(m["region"], "Toussaint")
        self.assertEqual(m["player_level"], 38)
        self.assertTrue(m["initial_build_id"].startswith("5.0"))

    def test_checkpoint(self):
        m = metadata(open_save(CHECKPOINT))
        self.assertEqual((m["region"], m["player_level"]), ("Toussaint", 37))


@needs_saves
class TestJournal(unittest.TestCase):
    def test_statuses_known(self):
        for p in all_saves():
            with self.subTest(p.name):
                for e in journal_entries(open_save(p)):
                    self.assertIn(e.status, {"inactive", "active", "success", "failed"})

    def test_path_flag_marks_last_element(self):
        for e in journal_entries(open_save(NEXTGEN)):
            self.assertEqual([el.flag for el in e.path], [0] * (e.depth - 1) + [1])

    def test_known_quests_present(self):
        groups = quest_tree(journal_entries(open_save(NEXTGEN)))
        by_res = {q["resource"].rsplit("\\", 1)[-1]: q for g in groups for q in g["quests"]}
        self.assertEqual(by_res["q001yennsearch.journal"]["status"], "success")
        self.assertEqual(by_res["mq0003freshwater.journal"]["status"], "success")
        self.assertIn("mh102arachas.journal", by_res)

    def test_every_quest_has_resource(self):
        for p in all_saves():
            with self.subTest(p.name):
                for g in quest_tree(journal_entries(open_save(p))):
                    for q in g["quests"]:
                        self.assertTrue(q["resource"].endswith(".journal"))

    def test_progress_grows(self):
        def count(p):
            return sum(len(g["quests"]) for g in quest_tree(journal_entries(open_save(p))))
        self.assertEqual(count(CHECKPOINT), count(NEXTGEN))
        self.assertLess(len(facts(open_save(CHECKPOINT))), len(facts(open_save(NEXTGEN))))


@needs_saves
class TestFacts(unittest.TestCase):
    def test_parse_consumes_stream(self):
        for p in all_saves():
            with self.subTest(p.name):
                f = facts(open_save(p))
                self.assertGreater(len(f), 100)

    def test_known_fact(self):
        f = facts(open_save(NEXTGEN))
        self.assertEqual(f["q402_roche_helps_context_dialogue"][0]["value"], 1)
        self.assertEqual(f["q402_roche_helps_context_dialogue"][0]["expiry"], -1.0)


if __name__ == "__main__":
    unittest.main()
