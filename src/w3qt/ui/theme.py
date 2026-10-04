"""Old-scroll theme: parchment, iron-gall ink, wax-seal red.

Fonts (bundled, SIL OFL): EB Garamond for text, IM Fell English SC for headings.
"""

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette

DATA = Path(__file__).resolve().parent.parent / "data"
TEXTURE = DATA / "parchment.jpg"
ARROW_DOWN = (DATA / "arrow-down.svg").as_posix()
ARROW_UP = (DATA / "arrow-up.svg").as_posix()

BODY_FONT = "EB Garamond"
TITLE_FONT = "IM FELL English SC"

# Names kept from the earlier theme so other modules need no changes.
DESK = "#2a2017"          # table the scroll lies on
BG = "#e6d5ad"            # parchment (dialogs, popups)
PANEL = "rgba(255, 250, 235, 0.72)"
PANEL_SOLID = "#efe2c2"
PANEL_2 = "rgba(120, 88, 40, 0.07)"
BORDER = "#a88a5a"
TEXT = "#24160a"          # ink
MUTED = "#5a4528"
ACCENT = "#8a1f1a"        # wax seal
ACCENT_HI = "#a8302a"
SELECTION = "#d4b680"

STATUS_COLORS = {
    "not_started": "#5f4b30",
    "in_progress": "#1f3f66",   # blue-black ink
    "completed": "#2f5c1e",     # green ink
    "failed": "#8a1f1a",
}


def load_fonts() -> None:
    for f in sorted((DATA / "fonts").glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(f))


def body_font(size: float = 13.0) -> QFont:
    f = QFont(BODY_FONT)
    f.setPointSizeF(size)
    f.setWeight(QFont.Medium)  # Garamond's regular weight is thin on screen
    return f


def palette() -> QPalette:
    p = QPalette()
    roles = {
        QPalette.Window: BG, QPalette.WindowText: TEXT, QPalette.Base: PANEL_SOLID,
        QPalette.AlternateBase: "#e9dab6", QPalette.Text: TEXT, QPalette.Button: "#dcc79a",
        QPalette.ButtonText: TEXT, QPalette.Highlight: SELECTION, QPalette.HighlightedText: TEXT,
        QPalette.ToolTipBase: PANEL_SOLID, QPalette.ToolTipText: TEXT, QPalette.PlaceholderText: MUTED,
        QPalette.Link: ACCENT, QPalette.BrightText: ACCENT,
    }
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(MUTED))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(MUTED))
    return p


STYLESHEET = f"""
* {{ font-family: "{BODY_FONT}"; font-size: 13pt; font-weight: 500; color: {TEXT}; }}
QMainWindow {{ background: {DESK}; }}
QDialog, QMessageBox, QFileDialog {{ background: {BG}; }}
QToolTip {{ background: {PANEL_SOLID}; border: 1px solid {BORDER}; padding: 4px; }}

QTextBrowser {{ background: transparent; border: none; selection-background-color: {SELECTION}; }}
QPlainTextEdit#notes {{
    background: rgba(255, 248, 226, 0.22); border: none; border-left: 3px solid {ACCENT};
    border-radius: 0; padding: 4px 10px; font-style: italic;
}}
QPlainTextEdit#notes:focus {{ background: rgba(255, 248, 226, 0.4); }}
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 2px; padding: 2px 6px;
    selection-background-color: {SELECTION}; selection-color: {TEXT};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{ image: url({ARROW_DOWN}); width: 12px; height: 10px; }}
QSpinBox::up-arrow {{ image: url({ARROW_UP}); width: 9px; height: 7px; }}
QSpinBox::down-arrow {{ image: url({ARROW_DOWN}); width: 9px; height: 7px; }}
QComboBox QAbstractItemView, QListView, QTreeView {{
    background: {PANEL_SOLID}; border: 1px solid {BORDER};
    selection-background-color: {SELECTION}; selection-color: {TEXT};
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 14px; border: none; }}

QPushButton, QToolButton {{
    background: rgba(214, 190, 140, 0.55); border: 1px solid {BORDER}; border-radius: 3px;
    padding: 3px 12px;
}}
QPushButton:hover, QToolButton:hover {{ border-color: {ACCENT}; background: rgba(214, 190, 140, 0.85); }}
QPushButton:pressed, QToolButton:pressed {{ background: {SELECTION}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton#icon {{ font-size: 15pt; padding: 0px 8px; }}

QPushButton#statusButton {{ padding: 4px 6px; }}
QPushButton#statusButton:checked {{
    background: {ACCENT}; border-color: #5e1210; color: #f6ead0; font-weight: 600;
}}
QPushButton#primary {{
    background: {ACCENT}; border: 1px solid #5e1210; color: #f6ead0; font-weight: 600; padding: 4px 14px;
}}
QPushButton#primary:hover {{ background: {ACCENT_HI}; }}
QPushButton#ghost {{
    background: transparent; border: none; border-bottom: 1px solid transparent; border-radius: 0;
    color: {ACCENT}; padding: 2px 4px; font-weight: 600;
}}
QPushButton#ghost:hover {{ border-bottom: 1px solid {ACCENT}; background: rgba(138, 31, 26, 0.07); }}
QPushButton#ghost:pressed {{ background: rgba(138, 31, 26, 0.15); }}
QPushButton#linkButton {{
    background: transparent; border: none; color: {ACCENT}; text-decoration: underline; padding: 0;
}}

QTableView {{
    background: transparent; alternate-background-color: {PANEL_2}; border: none;
    gridline-color: transparent; selection-background-color: {SELECTION}; selection-color: {TEXT};
}}
QTableView::item {{ border-bottom: 1px solid rgba(120, 90, 50, 0.18); padding: 0 4px; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: transparent; color: {MUTED}; border: none; border-bottom: 2px solid {ACCENT};
    padding: 4px 6px; font-family: "{TITLE_FONT}"; font-size: 13pt; color: {TEXT};
}}
QTableCornerButton::section {{ background: transparent; border: none; }}

QTabWidget::pane {{ border: none; border-top: 1px solid {BORDER}; }}
QTabBar::tab {{
    background: transparent; color: {MUTED}; padding: 4px 18px 6px 18px; margin-right: 4px;
    font-family: "{TITLE_FONT}"; font-size: 14pt; border-bottom: 3px solid transparent;
}}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 3px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

QProgressBar {{
    background: rgba(255, 248, 226, 0.5); border: 1px solid {BORDER}; border-radius: 3px;
    text-align: center; min-height: 20px; font-weight: 600;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #a8302a, stop:1 #6e1713);
    border-radius: 2px;
}}

QGroupBox {{
    border: 1px solid {BORDER}; border-radius: 3px; margin-top: 18px; padding: 10px 8px 8px 8px;
    background: rgba(255, 248, 226, 0.25);
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 10px; padding: 0 6px; color: {TEXT};
    font-family: "{TITLE_FONT}"; font-size: 14pt;
}}

QFrame#warning {{
    background: rgba(138, 31, 26, 0.08); border: 1px solid rgba(138, 31, 26, 0.5);
    border-left: 4px solid {ACCENT}; border-radius: 2px;
}}
QFrame#saveBar {{
    background: rgba(255, 248, 226, 0.3); border: 1px solid {BORDER}; border-radius: 3px;
}}
QLabel#thumb {{ border: 2px solid #6b4f2a; background: #3a2c1c; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#title {{ font-family: "{TITLE_FONT}"; font-size: 26pt; color: {TEXT}; }}
QLabel#pageTitle {{ font-family: "{TITLE_FONT}"; font-size: 28pt; color: {TEXT}; }}
QLabel#questTitle {{ font-family: "{TITLE_FONT}"; font-size: 19pt; color: {TEXT}; }}
QLabel#sectionTitle {{ font-family: "{TITLE_FONT}"; font-size: 14pt; color: {ACCENT}; }}

QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ border-left: 1px solid rgba(120, 90, 50, 0.35); margin: 8px 3px; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: rgba(107, 79, 42, 0.45); border-radius: 4px; min-height: 30px; min-width: 30px; }}
QScrollBar::handle:hover {{ background: rgba(107, 79, 42, 0.7); }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; width: 0; height: 0; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {BORDER}; background: {PANEL}; border-radius: 2px; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: #5e1210; }}
QMenu {{ background: {PANEL_SOLID}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 4px 22px 4px 18px; }}
QMenu::item:selected {{ background: {SELECTION}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}
QStatusBar {{ background: transparent; color: #d9c79f; }}
QStatusBar QLabel {{ color: #d9c79f; }}
"""
