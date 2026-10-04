"""Application entry point."""

from __future__ import annotations

import sys

from pathlib import Path

from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from .. import questdata
from ..config import Config
from ..profiles import ProfileStore
from . import theme
from .main_window import MainWindow, profiles_dir

APP_ID = "w3-quest-tracker"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    QGuiApplication.setDesktopFileName(APP_ID)  # Wayland app_id / X11 WM_CLASS
    app = QApplication(argv)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName("Witcher 3 Quest Tracker")
    app.setStyle("Fusion")
    app.setPalette(theme.palette())
    app.setStyleSheet(theme.STYLESHEET)
    bundled_icon = Path(__file__).resolve().parent.parent / "data" / "w3-quest-tracker.svg"
    app.setWindowIcon(QIcon.fromTheme(APP_ID, QIcon(str(bundled_icon))))

    db = questdata.load()
    win = MainWindow(db, ProfileStore(profiles_dir()), Config.load())
    win.show()
    return app.exec()
