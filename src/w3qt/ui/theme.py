"""Dark gray/silver theme with dark red accents."""

from PySide6.QtGui import QColor, QPalette

BG = "#1a1b1d"
PANEL = "#222326"
PANEL_2 = "#2a2c30"
BORDER = "#36383d"
TEXT = "#cfd1d5"
MUTED = "#8b8f96"
ACCENT = "#8e1c1c"
ACCENT_HI = "#b02a2a"
SELECTION = "#4a1616"

STATUS_COLORS = {
    "not_started": "#7b7f86",
    "in_progress": "#a9b4c2",
    "completed": "#8fa67c",
    "failed": "#c04040",
}


def palette() -> QPalette:
    p = QPalette()
    roles = {
        QPalette.Window: BG, QPalette.WindowText: TEXT, QPalette.Base: PANEL,
        QPalette.AlternateBase: PANEL_2, QPalette.Text: TEXT, QPalette.Button: PANEL_2,
        QPalette.ButtonText: TEXT, QPalette.Highlight: SELECTION, QPalette.HighlightedText: "#ffffff",
        QPalette.ToolTipBase: PANEL_2, QPalette.ToolTipText: TEXT, QPalette.PlaceholderText: MUTED,
        QPalette.Link: ACCENT_HI,
    }
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(MUTED))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(MUTED))
    return p


STYLESHEET = f"""
QWidget {{ font-size: 10pt; }}
QMainWindow, QDialog {{ background: {BG}; }}
QToolTip {{ background: {PANEL_2}; color: {TEXT}; border: 1px solid {BORDER}; }}
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextBrowser, QListWidget {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 3px; padding: 3px 5px;
    selection-background-color: {SELECTION};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {PANEL}; border: 1px solid {BORDER}; selection-background-color: {SELECTION}; }}
QPushButton {{
    background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 3px; padding: 4px 10px;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {SELECTION}; }}
QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT_HI}; color: #f0e6e6; }}
QPushButton#primary:hover {{ background: {ACCENT_HI}; }}
QTableView {{
    background: {PANEL}; alternate-background-color: {PANEL_2}; border: 1px solid {BORDER};
    gridline-color: transparent; selection-background-color: {SELECTION};
}}
QHeaderView::section {{
    background: {BG}; color: {MUTED}; border: none; border-bottom: 1px solid {ACCENT};
    padding: 4px 6px; font-weight: 600;
}}
QTabWidget::pane {{ border: 1px solid {BORDER}; top: -1px; }}
QTabBar::tab {{
    background: {BG}; color: {MUTED}; padding: 6px 16px; border: 1px solid transparent;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT_HI}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QProgressBar {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 3px; text-align: center;
    color: {TEXT}; min-height: 16px;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}
QGroupBox {{
    border: 1px solid {BORDER}; border-radius: 4px; margin-top: 14px; padding: 8px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; color: {MUTED}; }}
QFrame#warning {{
    background: #2a1414; border: 1px solid {ACCENT}; border-left: 4px solid {ACCENT_HI}; border-radius: 3px;
}}
QFrame#saveBar {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 4px; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#title {{ font-size: 15pt; font-weight: 600; color: #e6e7ea; }}
QLabel#sectionTitle {{ color: {MUTED}; font-weight: 600; text-transform: uppercase; }}
QSplitter::handle {{ background: {BORDER}; }}
QScrollArea {{ border: none; background: transparent; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {BORDER}; background: {PANEL}; border-radius: 2px; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT_HI}; }}
QStatusBar {{ color: {MUTED}; }}
"""
