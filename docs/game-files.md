# Game file formats used by the quest database builder

`quests.json` (in `~/.local/share/w3-quest-tracker/`) is built only from the installed game (Steam, build 5.0).
Nothing in it is typed in by hand. The app builds it on first start; rebuild it with `tools/build_quests.py` (source checkout) or `w3-quest-tracker-build-quests` (installed).

## Bundles (`content/content0/bundles/*.bundle`)

The header is `POTATO70`, and the TOC size sits at offset 16. TOC entries are
0x130 bytes each:

- `char[0x100]` path
- `u8[16]` hash
- `u32` offset
- `u32` unknown
- `u32` size
- `u32` compressed size
- `u32` crc
- `u32` compressed flag
- padding

Every compressed journal and CSV entry is zlib (`78 da`).

Quest journals live in `startup` (base game and free DLC), `dlc0` (free
DLC), `ep1` (Hearts of Stone) and `bob` (Blood and Wine).

## CR2W journal resources

The parser reads these tables: the string buffer, the names, and the
exports. Properties are stored as `u16 name, u16 type, u32 size, value`.

From each `CJournalQuest`, the builder uses:

- `guid`: the same GUID the save stores in its journal path.
- `baseName`: the internal name. It is the key into `quest_levels.csv`.
- `title`: a LocalizedString, stored as a u32 string id.
- `type`: an enum, `eQuestType`. A missing value means `Story`, the enum
  default.
- `contentType`: `EJCT_EP1` or `EJCT_EP2`. A missing value means the base
  game.
- `world`: an int. Its mapping comes from `GetDeprecatedAreaName()` in
  `scripts/game/commonMapManager.ws`.

The description is the first `CJournalQuestDescriptionEntry`, which is the
journal's opening text.

## quest_levels.csv

The file `gameplay\globals\quest_levels.csv` and its DLC copies use the
format `Quest Name;Level`. The key is the quest's `baseName`. For 11 quests,
no row exists.

## .w3strings (next-gen)

See the module docstring in `src/w3qt/gamefiles/w3strings.py`. In short:

- String ids are XORed with a per-language key, which is not stored in the
  file. For `en` it is `0x79321793`, for `de` `0x42791159`. The builder
  recovers the key from the journal title ids.
- Text is UTF-8. Each byte is XORed with
  `((len + 1) * hi8(rotl16(C, i % 16))) & 0xFF`, where
  `C = byteswap16((key >> 8) & 0xFFFF)`.
- Verification: all 96,863 `en` strings decode as valid UTF-8.

## Mapping decisions

- **Category.** `Story` and `Chapter` map to `main`. `Side` maps to
  `secondary`, `MonsterHunt` to `contract` and `TreasureHunt` to
  `treasure_hunt`.
- **Gwent.** A quest whose internal name starts with `CG` or `Card Game`
  becomes `gwent`. "High Stakes" (`SQ306`) stays `secondary`, as the game
  types it.
- **Excluded.** The journal groups "Demo Quests" (E3 demos) and
  "[PL] Test Level" are left out, as are quests without a title.
- **Missing from the game files.** Quest giver, missable and prerequisites
  stay null or empty. They are listed in `unverified_fields`.
