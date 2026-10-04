"""Find the Witcher 3 installation and its save folder under Steam/Proton."""

from __future__ import annotations

import re
from pathlib import Path

APP_ID = "292030"
STEAM_ROOTS = [
    Path.home() / ".local/share/Steam",
    Path.home() / ".steam/steam",
    Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
]
SAVE_SUBPATH = Path(
    f"steamapps/compatdata/{APP_ID}/pfx/drive_c/users/steamuser/Documents/The Witcher 3/gamesaves"
)


def steam_libraries() -> list[Path]:
    libs: list[Path] = []
    for root in STEAM_ROOTS:
        if not root.is_dir():
            continue
        libs.append(root)
        vdf = root / "steamapps/libraryfolders.vdf"
        if vdf.is_file():
            for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(errors="replace")):
                libs.append(Path(m.group(1)))
    seen, out = set(), []
    for lib in libs:
        key = lib.resolve()
        if key not in seen:
            seen.add(key)
            out.append(lib)
    return out


def find_game_dir() -> Path | None:
    for lib in steam_libraries():
        d = lib / "steamapps/common/The Witcher 3"
        if (d / "content/content0/bundles").is_dir():
            return d
    return None


def find_save_dirs() -> list[Path]:
    return [lib / SAVE_SUBPATH for lib in steam_libraries() if (lib / SAVE_SUBPATH).is_dir()]
