"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtGui import QGuiApplication
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

    db = questdata.load()
    win = MainWindow(db, ProfileStore(profiles_dir()), Config.load())
    win.show()
    return app.exec()
