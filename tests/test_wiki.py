import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from w3qt import wiki  # noqa: E402

SAMPLE = """<div class="mw-parser-output"><div id="toc" class="toc"><input type="checkbox" id="t" />
<div class="toctitle"><h2>Contents</h2></div><ul><li>1 Walkthrough</li></ul></div>
<h2><span class="mw-headline">Walkthrough</span><span class="mw-editsection">[edit]</span></h2>
<p>Talk to <a href="/wiki/Vesemir" title="Vesemir">Vesemir</a> (250<span typeof="mw:File"><a href="/wiki/XP"><img src="https://x/icon.png" /></a></span>)<br/>then go.</p>
<figure><img src="a.png"/><figcaption>Spoiler image</figcaption></figure>
<script>alert(1)</script><p style="color:red">Last <a href="#anchor">step</a>.</p></div>"""


class TestSanitize(unittest.TestCase):
    def setUp(self):
        self.out = wiki.sanitize(SAMPLE)

    def test_removes_toc_scripts_images_editlinks(self):
        for bad in ("Contents", "alert", "<img", "Spoiler image", "[edit]", "<script", "style="):
            self.assertNotIn(bad, self.out)

    def test_keeps_text_and_rewrites_links(self):
        self.assertIn('<a href="https://witcher.fandom.com/wiki/Vesemir">Vesemir</a>', self.out)
        self.assertIn("(250)", self.out)          # icon-only link dropped, text kept
        self.assertIn("<br>then go.", self.out)
        self.assertIn("Last step.", self.out)     # anchor-only link unwrapped
        self.assertIn("<h2>Walkthrough</h2>", self.out)


class TestCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"XDG_CACHE_HOME": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def wt(self, html="<p>x</p>", age=0.0):
        return wiki.Walkthrough("T", "https://witcher.fandom.com/wiki/T", html, time.time() - age)

    def test_store_load_clear(self):
        wiki.store("q1", self.wt())
        self.assertEqual(wiki.load_cached("q1").html, "<p>x</p>")
        self.assertGreater(wiki.cache_size(), 0)
        wiki.clear_cache()
        self.assertEqual(wiki.cache_size(), 0)
        self.assertFalse(wiki.cache_dir().exists())

    def test_prune_keeps_cache_under_cap(self):
        big = "<p>" + os.urandom(20000).hex() + "</p>"   # incompressible
        for i in range(6):
            wiki.store(f"q{i}", self.wt(big))
            os.utime(wiki._cache_file(f"q{i}"), (time.time() + i, time.time() + i))
        wiki.prune(max_bytes=100_000)
        self.assertLessEqual(wiki.cache_size(), 100_000)
        self.assertIsNotNone(wiki.load_cached("q5"))   # newest survives
        self.assertIsNone(wiki.load_cached("q0"))      # oldest evicted

    def test_get_uses_fresh_cache_without_network(self):
        wiki.store("q1", self.wt())
        with mock.patch.object(wiki, "fetch", side_effect=AssertionError("network used")):
            wt, cached = wiki.get("q1", "T")
        self.assertTrue(cached)

    def test_get_falls_back_to_stale_copy_offline(self):
        wiki.store("q1", self.wt(age=wiki.MAX_AGE + 10))
        with mock.patch.object(wiki, "fetch", side_effect=wiki.WikiError("offline")):
            wt, cached = wiki.get("q1", "T")
        self.assertTrue(cached)
        self.assertEqual(wt.html, "<p>x</p>")

    def test_get_raises_offline_without_cache(self):
        with mock.patch.object(wiki, "fetch", side_effect=wiki.WikiError("offline")):
            with self.assertRaises(wiki.WikiError):
                wiki.get("q1", "T")


if __name__ == "__main__":
    unittest.main()
