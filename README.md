# Witcher 3 Quest Tracker

A Linux desktop app that lists every quest in The Witcher 3: Wild Hunt
(Complete Edition, including Hearts of Stone and Blood and Wine). It updates
your progress live from your newest save file.

- 401 quests, with English and German names, category, region, suggested
  level and expansion. All of this is extracted from your installed game, not
  typed in by hand.
- Live sync: the app watches the save folder and reads the newest save. It
  opens saves read-only and retries while the game is still writing.
- Filters, search, progress per category, content and region, and a
  point-of-no-return view.
- Notes per quest, several profiles (one per playthrough), and JSON
  export/import.
- Works on Wayland and X11.

Only the current game version is supported: next-gen/REDkit build 5.0, save
version 66. The app skips older saves.

## Install (Arch Linux)

```sh
cd packaging/arch
makepkg -si
```

This builds a package from the **committed** state of this git checkout and
installs it, together with `pyside6` and `python-watchdog`. After that:

- start "Witcher 3 Quest Tracker" from your application menu, or
- run `w3-quest-tracker` in a terminal.

`makepkg` runs the test suite in `check()`. To skip it, use `makepkg -si --nocheck`.

## Run from source

With the system packages:

```sh
sudo pacman -S pyside6 python-watchdog   # python-lz4 optional (faster)
./w3-quest-tracker
```

With uv, in a project-local venv (`.venv/`, downloads PySide6 from PyPI, ~250 MB):

```sh
uv sync                    # add --extra fast for python-lz4
uv run w3-quest-tracker
uv run w3-quest-tracker-build-quests   # rebuild src/w3qt/data/quests.json
QT_QPA_PLATFORM=offscreen uv run python -m unittest discover -s tests
```

`watchdog` is optional. Without it, the app falls back to Qt's own file
watcher, which is also inotify-based. The save bar shows which watcher is
active while no save is loaded.

## Save folder

The app detects the Proton save folder automatically:

```
<steam>/steamapps/compatdata/292030/pfx/drive_c/users/steamuser/Documents/The Witcher 3/gamesaves/
```

It searches these `<steam>` locations: `~/.local/share/Steam`,
`~/.steam/steam`, Flatpak Steam (`~/.var/app/com.valvesoftware.Steam/...`)
and every library listed in `libraryfolders.vdf`.

For GOG (Heroic or Lutris) or any other location, pick the folder via
**Save → Choose save folder…**.

## How tracking works

- **Statuses:** Not started, In progress, Completed and Failed/Missed. The
  save's journal supplies the status of every quest you have discovered.
  Quests that never appeared in your journal count as "Not started".
- **Manual edits:** You can always set a status by hand in the detail panel.
  Each profile has a **priority** setting that decides which source wins when
  the save and a manual edit disagree.
- **Profiles:** A profile binds itself to the playthrough of the first save
  it syncs. After that, it ignores saves from other playthroughs. To release
  the binding, use **Save → Unlink profile from playthrough**.
- **Unknown quests:** If a save contains quests that are not in the database,
  the app logs them to `~/.local/share/w3-quest-tracker/unknown_quests.log`.
- **Fallback:** If part of a save cannot be decoded, the app keeps your
  manual statuses and shows a warning in the save bar.

## Missable quests

The game files do not say which quests can be missed. A small hand-curated
list lives in `src/w3qt/data/missable.json`. It covers the White Orchard side
quests, Vesemir's Gwent card and the three main points of no return.

Every entry is marked `"verified": false`, and the app labels these warnings
as unverified. Edit the file to correct or extend the list. Rebuilding
`quests.json` does not touch it.

## Data locations

| What | Where |
|---|---|
| Profiles (statuses, notes) | `~/.local/share/w3-quest-tracker/profiles/` |
| Unknown quests log | `~/.local/share/w3-quest-tracker/unknown_quests.log` |
| Settings | `~/.config/w3-quest-tracker/config.json` |
| Rebuilt quest database (optional) | `~/.local/share/w3-quest-tracker/quests.json` |

## Rebuilding the quest database

`quests.json` is generated from your game installation. Rebuild it after a
game update:

```sh
tools/build_quests.py               # source checkout: writes src/w3qt/data/quests.json
w3-quest-tracker-build-quests       # installed: writes ~/.local/share/w3-quest-tracker/quests.json
```

The file contains text from the game, such as quest names and journal
descriptions. That is fine for personal use. If you publish this project,
generate the file at install time instead of distributing it.

## Development

```sh
python -m unittest discover -s tests      # QT_QPA_PLATFORM=offscreen for headless
tools/dump_save.py SAVE.sav --tree        # inspect a save as JSON
```

- **Fixtures:** The sample saves in `tests/fixtures/saves/` come from a real
  playthrough.
- **Game file tests:** Tests that read the installed game skip themselves
  when the game is not found.

```
src/w3qt/
  savefile.py, savedata.py   save container, record tree, journal/facts/metadata
  savesync.py, watcher.py    newest-save loading, folder watching
  gamefiles/                 bundle, CR2W and w3strings readers, install detection
  build_quests.py            quest database builder
  questdata.py, profiles.py, filtering.py
  ui/                        PySide6 interface
docs/save-format.md          save format notes
docs/game-files.md           game file formats and mapping decisions
```

The app uses original styling only: it ships no game logos or official
artwork.
