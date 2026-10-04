"""Quest walkthroughs from the Witcher Fandom wiki (CC BY-SA 3.0), fetched on demand.

Only the "Walkthrough" and "Notes" sections are fetched, through the wiki's
MediaWiki API, reduced to plain text markup (no images, scripts or styles)
and cached gzip-compressed. The cache is capped in size and entries expire,
so it never grows without bound.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from html import escape
from html.parser import HTMLParser
from pathlib import Path

WIKI = "https://witcher.fandom.com"
API = f"{WIKI}/api.php"
LICENSE = "CC BY-SA 3.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/3.0/"
USER_AGENT = "w3-quest-tracker/0.1 (personal desktop app; on-demand walkthrough lookup)"
SECTIONS = ("Walkthrough", "Notes")

MAX_CACHE_BYTES = 5 * 1024 * 1024     # hard cap for the whole cache
MAX_AGE = 30 * 24 * 3600              # refetch after 30 days (stale copy used offline)
TIMEOUT = 15


def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "w3-quest-tracker" / "wiki"


@dataclass
class Walkthrough:
    title: str          # resolved wiki page title
    url: str
    html: str           # sanitized markup; "" if the page has no walkthrough
    fetched: float

    @property
    def found(self) -> bool:
        return bool(self.html)


class WikiError(Exception):
    pass


# ---------------------------------------------------------------- sanitizing

ALLOWED = {"p", "ul", "ol", "li", "b", "strong", "i", "em", "br", "h2", "h3", "h4", "a",
           "table", "tr", "td", "th", "dl", "dt", "dd", "blockquote"}
VOID = {"br", "img", "input", "hr", "wbr", "meta", "link", "source"}
DROP_WITH_CONTENT = {"script", "style", "figure", "figcaption", "noscript", "sup"}
DROP_CLASSES = ("toc", "mw-editsection", "gallery", "thumb", "navbox", "reference", "noprint",
                "portable-infobox", "mw-empty-elt")


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip_depth = 0
        self.stack: list[tuple[str, bool]] = []  # (tag, skipping started here)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        starts_skip = tag in DROP_WITH_CONTENT or any(c in cls.split() for c in DROP_CLASSES) \
            or a.get("id") == "toc"
        if tag in VOID:  # no end tag follows
            if tag == "br" and not self.skip_depth:
                self.out.append("<br>")
            return
        self.stack.append((tag, starts_skip))
        if starts_skip:
            self.skip_depth += 1
            return
        if self.skip_depth or tag not in ALLOWED:
            return
        if tag == "a":
            href = a.get("href") or ""
            if href.startswith("/wiki/"):
                href = WIKI + href
            if href.startswith("http"):
                self.out.append(f'<a href="{escape(href, quote=True)}">')
            else:
                self.out.append("<a>")
            return
        self.out.append(f"<{tag}>")

    def handle_startendtag(self, tag, attrs):
        # <x/>: never push it on the stack, or the next end tag pops too far
        if tag == "br" and not self.skip_depth:
            self.out.append("<br>")

    def handle_endtag(self, tag):
        if tag in VOID or not any(t == tag for t, _ in self.stack):
            return
        # pop to the matching start tag
        while self.stack:
            t, started_skip = self.stack.pop()
            if started_skip:
                self.skip_depth -= 1
            elif not self.skip_depth and t in ALLOWED:
                self.out.append(f"</{t}>")
            if t == tag:
                break

    def handle_data(self, data):
        if not self.skip_depth:
            self.out.append(escape(data))


def sanitize(html_text: str) -> str:
    s = _Sanitizer()
    s.feed(html_text)
    s.close()
    out = "".join(s.out)
    out = re.sub(r"<a>(.*?)</a>", r"\1", out, flags=re.S)        # links without target
    out = re.sub(r"<a [^>]*>\s*</a>", "", out)                    # icon-only links
    out = re.sub(r"<p>\s*</p>", "", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


# ---------------------------------------------------------------- fetching

def _api(params: dict) -> dict:
    query = urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"})
    req = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError) as e:
        raise WikiError(f"Witcher Wiki not reachable: {e}") from e
    if "error" in data:
        raise WikiError(data["error"].get("info", "wiki error"))
    return data


def page_url(title: str) -> str:
    return f"{WIKI}/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"


def search_url(name: str) -> str:
    return f"{WIKI}/wiki/Special:Search?query={urllib.parse.quote(name)}"


def fetch(page_title: str) -> Walkthrough:
    """Download and sanitize the walkthrough sections of one page."""
    try:
        meta = _api({"action": "parse", "page": page_title, "prop": "sections", "redirects": 1})
    except WikiError as e:
        if "doesn't exist" in str(e) or "missing" in str(e).lower():
            return Walkthrough(page_title, search_url(page_title), "", time.time())
        raise
    title = meta["parse"]["title"]
    wanted = [s for s in meta["parse"]["sections"]
              if str(s.get("level")) == "2" and s["line"] in SECTIONS]
    parts = []
    for sec in wanted:
        data = _api({"action": "parse", "page": title, "prop": "text", "section": sec["index"],
                     "redirects": 1, "disableeditsection": 1, "disablelimitreport": 1})
        text = data["parse"]["text"]
        parts.append(sanitize(text["*"] if isinstance(text, dict) else text))
    return Walkthrough(title, page_url(title), "\n".join(p for p in parts if p), time.time())


# ---------------------------------------------------------------- cache

def _cache_file(quest_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", quest_id)
    return cache_dir() / f"{safe}.json.gz"


def load_cached(quest_id: str) -> Walkthrough | None:
    f = _cache_file(quest_id)
    try:
        data = json.loads(gzip.decompress(f.read_bytes()))
        return Walkthrough(**data)
    except (OSError, ValueError, TypeError):
        return None


def store(quest_id: str, wt: Walkthrough) -> None:
    d = cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = _cache_file(quest_id).with_suffix(".tmp")
    tmp.write_bytes(gzip.compress(json.dumps(asdict(wt)).encode("utf-8")))
    tmp.replace(_cache_file(quest_id))
    prune()


def prune(max_bytes: int = MAX_CACHE_BYTES) -> None:
    """Delete the least recently fetched entries until the cache fits."""
    files = sorted(cache_dir().glob("*.json.gz"), key=lambda p: p.stat().st_mtime)
    total = sum(f.stat().st_size for f in files)
    while files and total > max_bytes:
        f = files.pop(0)
        total -= f.stat().st_size
        f.unlink(missing_ok=True)


def cache_size() -> int:
    return sum(f.stat().st_size for f in cache_dir().glob("*.json.gz")) if cache_dir().is_dir() else 0


def clear_cache() -> None:
    d = cache_dir()
    if d.is_dir():
        for f in d.glob("*"):
            f.unlink(missing_ok=True)
        d.rmdir()


def get(quest_id: str, page_title: str, force: bool = False) -> tuple[Walkthrough, bool]:
    """Cached walkthrough, refetched when missing, expired or forced.

    Returns (walkthrough, from_cache). If the wiki is unreachable, a stale
    cached copy is returned; otherwise WikiError is raised.
    """
    cached = load_cached(quest_id)
    if cached and not force and time.time() - cached.fetched < MAX_AGE:
        return cached, True
    try:
        wt = fetch(page_title)
    except WikiError:
        if cached:
            return cached, True
        raise
    store(quest_id, wt)
    return wt, False
