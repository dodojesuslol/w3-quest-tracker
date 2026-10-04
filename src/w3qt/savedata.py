"""Extract tracker-relevant data (journal, facts, metadata) from a parsed save."""

from __future__ import annotations

import struct
from dataclasses import asdict, dataclass

from .savefile import Node, SaveFile, SaveFormatError, decode_value, read_cstring

# Journal tree depth (number of path elements) for quest entries.
# Group (e.g. questact1.journal) -> quest -> phase -> objective -> sub-objective/map pin
DEPTH_NAMES = {1: "group", 2: "quest", 3: "phase", 4: "objective", 5: "subobjective"}

STATUS_MAP = {
    "JS_Inactive": "inactive",
    "JS_Active": "active",
    "JS_Success": "success",
    "JS_Failed": "failed",
}

# worldInfo.world path fragment -> region. Best effort; raw path is always reported too.
WORLD_REGIONS = [
    ("levels\\prolog_village_winter\\", "White Orchard (winter)"),
    ("levels\\prolog_village\\", "White Orchard"),
    ("levels\\novigrad\\", "Velen / Novigrad"),
    ("levels\\skellige\\", "Skellige"),
    ("levels\\kaer_morhen\\", "Kaer Morhen"),
    ("levels\\wyzima_castle\\", "Vizima"),
    ("levels\\island_of_mist\\", "Isle of Mist"),
    ("levels\\the_spiral\\", "The Spiral"),
    ("dlc\\bob\\", "Toussaint"),
]


@dataclass
class PathElement:
    guid: str
    resource: str  # .journal file that defines this element, "" if inline in parent
    flag: int      # meaning unverified; observed 1 on the last element only


@dataclass
class JournalEntry:
    path: list[PathElement]
    status: str     # inactive | active | success | failed | raw name if unknown
    unread: bool | None

    @property
    def guid(self) -> str:
        return self.path[-1].guid

    @property
    def depth(self) -> int:
        return len(self.path)

    @property
    def root_resource(self) -> str:
        return self.path[0].resource

    def resource_chain(self) -> str:
        """Nearest explicit resource walking up the path."""
        for el in reversed(self.path):
            if el.resource:
                return el.resource
        return ""


def journal_entries(save: SaveFile) -> list[JournalEntry]:
    jm = save.block("CJournalManager")
    if jm is None:
        raise SaveFormatError("CJournalManager block missing")
    active = jm.child("JActiveEntries")
    if active is None:
        raise SaveFormatError("JActiveEntries missing")
    out = []
    for e in active.find_all("SJournalEntryStatus"):
        path_node = e.child("path")
        status_node = e.child("status")
        if path_node is None or status_node is None:
            continue
        kids = path_node.children
        if len(kids) % 3:
            raise SaveFormatError(f"journal path at {path_node.offset} has {len(kids)} fields")
        path = [
            PathElement(
                guid=kids[i].raw[:16].hex(),
                resource=read_cstring(kids[i + 1].raw, 0)[0],
                flag=kids[i + 2].raw[0],
            )
            for i in range(0, len(kids), 3)
        ]
        raw_status = decode_value(save, status_node)
        unread_node = e.child("JEntryUnread")
        out.append(JournalEntry(
            path=path,
            status=STATUS_MAP.get(raw_status, str(raw_status)),
            unread=decode_value(save, unread_node) if unread_node else None,
        ))
    return out


def is_quest_entry(e: JournalEntry) -> bool:
    return "\\journal\\quests\\" in e.root_resource


def quest_tree(entries: list[JournalEntry]) -> list[dict]:
    """Group/quest view with per-quest phase/objective counts."""
    quests: dict[tuple[str, str], dict] = {}
    groups: dict[str, dict] = {}
    for e in entries:
        if not is_quest_entry(e):
            continue
        if e.depth == 1:
            groups[e.guid] = {"guid": e.guid, "resource": e.path[0].resource, "status": e.status}
        elif e.depth == 2:
            quests[(e.path[0].guid, e.guid)] = {
                "guid": e.guid,
                "group_guid": e.path[0].guid,
                "group_resource": e.path[0].resource,
                "resource": e.path[1].resource,
                "status": e.status,
                "unread": e.unread,
                "phases": {},
                "objectives": {},
            }
    for e in entries:
        if not is_quest_entry(e) or e.depth < 3:
            continue
        q = quests.get((e.path[0].guid, e.path[1].guid))
        if q is None:
            continue
        bucket = q["phases"] if e.depth == 3 else q["objectives"] if e.depth == 4 else None
        if bucket is not None:
            bucket[e.status] = bucket.get(e.status, 0) + 1
    for q in quests.values():
        # Some groups (e.g. livingworld.journal) have no entry of their own.
        groups.setdefault(q["group_guid"], {
            "guid": q["group_guid"], "resource": q["group_resource"], "status": None,
        })
    for g in groups.values():
        g["quests"] = [q for q in quests.values() if q["group_guid"] == g["guid"]]
    return list(groups.values())


def facts(save: SaveFile) -> dict[str, list[dict]]:
    """Facts DB: name -> list of {value, time, expiry}.

    Layout inside the 'facts' SS stream (verified to consume the stream exactly):
        "SXAP" u32 save_version u32 game_version u32 unknown
        "SBDF" u32 count
        count * (cstring name, u16 unknown, u16 n, n * (i16 value, f32 time, f32 expiry))
        "EBDF"
    The u16 before n is 0 for >99% of facts; its meaning is unverified (it may be
    the high half of the value). Time is game time in seconds; expiry -1 = never.
    """
    blk = save.block("facts")
    if blk is None or not blk.children or blk.children[0].tag != "SS":
        raise SaveFormatError("facts SS stream missing")
    ss = blk.children[0]
    d = save.data
    p = ss.offset + 6
    if d[p:p + 4] != b"SXAP":
        raise SaveFormatError("facts stream magic SXAP not found")
    p += 16
    if d[p:p + 4] != b"SBDF":
        raise SaveFormatError("facts DB magic SBDF not found")
    count = struct.unpack_from("<I", d, p + 4)[0]
    p += 8
    out: dict[str, list[dict]] = {}
    for _ in range(count):
        name, p = read_cstring(d, p)
        unk, n = struct.unpack_from("<HH", d, p)
        p += 4
        vals = []
        for _ in range(n):
            v, t, exp = struct.unpack_from("<hff", d, p)
            p += 10
            vals.append({"value": v, "time": round(t, 3), "expiry": exp})
        if unk:
            vals.append({"_unknown_u16": unk})
        out[name] = vals
    if d[p:p + 4] != b"EBDF":
        raise SaveFormatError(f"facts DB end marker EBDF not found at {p}")
    return out


def player_level(save: SaveFile) -> int | None:
    """W3LevelManager.level inside the player's PORP property stream."""
    try:
        lm = save.names.index("levelManager") + 1
        handle = save.names.index("handle:W3LevelManager") + 1
        level = save.names.index("level") + 1
        int32 = save.names.index("Int32") + 1
    except ValueError:
        return None
    d = save.data
    p = d.find(struct.pack("<HH", lm, handle))
    if p < 0:
        return None
    size = struct.unpack_from("<I", d, p + 4)[0]
    blob = d[p:p + 4 + size]
    q = blob.find(struct.pack("<HHI", level, int32, 8))
    if q < 0:
        return None
    return struct.unpack_from("<i", blob, q + 8)[0]


def metadata(save: SaveFile) -> dict:
    def val(block: str, name: str):
        b = save.block(block)
        n = b.child(name) if b else None
        return decode_value(save, n) if n else None

    world = val("worldInfo", "world")
    region = next((r for frag, r in WORLD_REGIONS if world and frag in world), None)
    build = val("InitialBuildIDBlock", "InitialBuildID")
    return {
        "save_version": save.save_version,
        "game_version": save.game_version,
        "initial_build_id": build.strip() if isinstance(build, str) else None,
        "playthrough_id": val("saveInfo", "playthroughId"),
        "world": world,
        "region": region,
        "player_level": player_level(save),
        "new_game_plus": val("NewGamePlus", "active"),
    }


def entry_to_dict(e: JournalEntry) -> dict:
    return {
        "depth": e.depth,
        "kind": DEPTH_NAMES.get(e.depth, "unknown"),
        "status": e.status,
        "unread": e.unread,
        "path": [asdict(p) for p in e.path],
    }


def summarize_tree(node: Node, depth: int = 0, max_depth: int = 1) -> list:
    """Debug helper: top-level block names with sizes."""
    return [
        {"tag": c.tag, "name": c.name, "size": c.end - c.offset,
         **({"children": summarize_tree(c, depth + 1, max_depth)} if depth < max_depth and c.children else {})}
        for c in node.children
    ]
