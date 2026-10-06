"""Application entry point."""

from __future__ import annotations

import sys

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from .. import questdata
from ..build_quests import build, is_game_dir
from ..gamefiles.locate import find_game_dir
from ..config import Config
from ..profiles import ProfileStore
from . import theme
from .main_window import MainWindow, profiles_dir

APP_ID = "w3-quest-tracker"


def load_or_build_db() -> questdata.QuestDB | None:
    """Load quests.json; build it from the installed game if missing or broken.

    The file holds game text, so it is generated locally instead of shipped.
    """
    try:
        return questdata.load()
    except (OSError, ValueError, KeyError, TypeError):
        pass
    game = find_game_dir()
    while True:
        if game is not None and is_game_dir(game):
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                build(game, questdata.default_path())
                return questdata.load()
            except Exception as e:  # unexpected game file layout
                error = f"Reading the game files in {game} failed:\n{e}"
            finally:
                QApplication.restoreOverrideCursor()
        else:
            error = ("The Witcher 3 installation was not found. The quest list is built from "
                     "your installed game on first start.")
        answer = QMessageBox.question(
            None, "Quest database", error + "\n\nChoose the game folder (the one containing \"content\")?",
            QMessageBox.Open | QMessageBox.Cancel)
        if answer != QMessageBox.Open:
            return None
        chosen = QFileDialog.getExistingDirectory(None, "Choose The Witcher 3 game folder")
        if not chosen:
            return None
        game = Path(chosen)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    QGuiApplication.setDesktopFileName(APP_ID)  # Wayland app_id / X11 WM_CLASS
    app = QApplication(argv)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName("Witcher 3 Quest Tracker")
    app.setStyle("Fusion")
    theme.load_fonts()
    app.setFont(theme.body_font())
    app.setPalette(theme.palette())
    app.setStyleSheet(theme.STYLESHEET)
    bundled_icon = Path(__file__).resolve().parent.parent / "data" / "w3-quest-tracker.svg"
    app.setWindowIcon(QIcon.fromTheme(APP_ID, QIcon(str(bundled_icon))))

    db = load_or_build_db()
    if db is None:
        return 1
    win = MainWindow(db, ProfileStore(profiles_dir()), Config.load())
    win.show()
    return app.exec()
