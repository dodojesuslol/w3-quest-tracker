# Witcher 3 save format (as used by this project)

Reverse-engineered from real PC saves. Implemented in `src/w3qt/savefile.py`
and `src/w3qt/savedata.py`. Fields marked **unverified** are parsed but their
meaning is not confirmed.

## Scope

Only the current next-gen/REDkit format is supported: save_version 66,
game_version 29, build 5.0. The parser rejects other versions
(`SUPPORTED_SAVE_VERSIONS`). The original release and older next-gen saves
are out of scope.

Fixtures: `CheckPoint_11b6cd_…` (level 37) and `ManualSave_11b6cd_…`
(level 38), both from the same Toussaint playthrough.

## Container

```
"SNFHFZLC"
u32 chunk_count
u32 header_size                      (3084 in every fixture)
chunk_count × { u32 compressed, u32 decompressed, u32 end_offset }
```

Chunks start at `header_size` and are stored back to back. Each chunk is an
LZ4 *block* (no frame) and decompresses to at most 1 MiB. In the last chunk,
`end_offset` is 0. The parser therefore sums the compressed sizes and does
not trust `end_offset`.

## Decompressed stream

```
"SAV3" u32 save_version u32 game_version u32 unknown(163/164)
… record tree …
"MANU" u32 count u32 unknown(0) count × name    ← string table
u32 0 "ENOD" u32 u32
"SC" u32 count count × { u32 offset, u32 size } ← variable table
u32 string_table_offset u32 unknown u32 variable_table_offset "SE"
```

Every offset stored in the stream counts from the start of the on-disk file.
To get a stream offset, subtract `header_size`.

Each string-table name has a length prefix. The low 6 bits hold the length.
If bit `0x40` is set, the next byte adds `<< 6`.

### Records

- `BS <u16 name>`: block. Its extent comes from the variable table.
- `VL <u16 name> <u16 type> <value>`: typed value. Name and type are
  **1-based** string-table indices.
- `SS <u32 size> <payload>`: opaque stream. The facts DB lives here.
- `OP`: seen but not decoded.

The variable table lists `(offset, size)` for every record. It also has
entries that point into opaque payloads. The tree is built from that table
by nesting on offset ranges.

Value encodings that were checked: Bool/Uint8 use 1 byte. Uint32/Int32 use
4 bytes, little-endian. CGUID uses 16 bytes. `String` uses the length prefix
above, where `0x80` means 8-bit chars and no flag means UTF-16LE.
`StringAnsi` has a u8 length that includes a trailing NUL. Enums and CName
are stored as u16 string-table indices.

## Journal (quest status) — reliable

The status lives in `CJournalManager / JActiveEntries`, which is a list of
`SJournalEntryStatus` records:

- `path`: a list of triples `guid: CGUID`, `resource: String`, and
  `flags: Uint8`. The flag is 1 on the last element only (**unverified**
  meaning).
- `status: EJournalStatus`: one of `JS_Inactive`, `JS_Active`,
  `JS_Success` or `JS_Failed`.
- `JEntryUnread: Bool`.

The path depth gives the entry type. Depth 1 is a quest group, for example
`questact1.journal` or `minorquests.journal`. Depth 2 is a quest, depth 3 a
phase, depth 4 an objective and depth 5 a sub-objective. This hierarchy
is confirmed against the fixtures: each depth-2 entry is a quest .journal
file, and its children are its phases and objectives.

Every quest seen so far has its own `.journal` file, for example
`gameplay\journal\quests\q001yennsearch.journal`. The file name is a stable,
readable identifier. Combined with the GUID, it is the key for mapping to
`data/quests.json`.

Quests that were never discovered have no entry. The tracker cannot tell
"not started" apart from "not yet visible in the journal".

The save does **not** contain quest display names. They live in the game
files, in `.journal` resources plus `.w3strings`.

The journal also has other root folders that the tracker does not need:
bestiary, characters, glossary, storybook and tutorial.

## Facts DB — reliable layout, partly unverified fields

The `facts` block holds one `SS` stream with this layout:

```
"SXAP" u32 save_version u32 game_version u32 unknown
"SBDF" u32 count
count × { name, u16 unknown, u16 n, n × { i16 value, f32 time, f32 expiry } }
"EBDF"
```

On every fixture, the parser consumes the stream exactly up to `EBDF`. The
`u16 unknown` is 0 for over 99 % of facts (**unverified**). It may be the
high half of the value, and in that case the value would really be an i32.
`time` is in-game time in seconds. An `expiry` of -1 means the fact never
expires.

Fact names such as `q402_roche_helps_context_dialogue` reveal quest choices.
They could help detect missed quests, but this is not mapped yet.

## Metadata

- Region: `worldInfo / world`, a `.w2w` path mapped to a region name.
- Player level: the parser searches the player's `PORP` property stream
  for `levelManager: handle:W3LevelManager`, then reads `level: Int32`
  inside it. Confirmed against the in-game level (38).
- Build ID: `InitialBuildIDBlock`.
- Playthrough ID: `saveInfo / playthroughId` (`String`).
- Total playtime: not decoded, and not needed.
- `.json` sidecar: build IDs, versions and the active mods list.
- `.png` next to the save: the thumbnail.

## Prior art

Atvaark's C# W3SavegameEditor on GitHub covers the same container and record
format. I did not consult it while writing this, so naming details may
differ.
