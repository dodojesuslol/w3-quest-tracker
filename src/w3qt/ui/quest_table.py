"""Table model for the quest list."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QTableView

from .. import filtering
from ..profiles import Profile
from . import theme

COLUMNS = ["Status", "Quest", "Category", "Region", "Lvl", "Content", "⚠"]
SHORT_CATEGORY = {**filtering.CATEGORY_LABELS, "contract": "Contract"}
SHORT_EXPANSION = {"base": "Base", "hearts_of_stone": "HoS", "blood_and_wine": "B&W"}
COL_STATUS, COL_NAME, COL_CATEGORY, COL_REGION, COL_LEVEL, COL_EXPANSION, COL_MISSABLE = range(7)
QUEST_ROLE = Qt.UserRole + 1


class QuestTableModel(QAbstractTableModel):
    def __init__(self, profile: Profile, lang: str):
        super().__init__()
        self.rows: list[dict] = []
        self.profile = profile
        self.lang = lang
        self._sort_col = COL_NAME
        self._sort_order = Qt.AscendingOrder
        self._bold = QFont()
        self._bold.setBold(True)

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self.rows = rows
        self._apply_sort()
        self.endResetModel()

    def set_profile(self, profile: Profile, lang: str) -> None:
        self.profile, self.lang = profile, lang
        self.refresh()

    def refresh(self) -> None:
        if self.rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.rows) - 1, len(COLUMNS) - 1))

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section]
        return None

    def quest_at(self, row: int) -> dict | None:
        return self.rows[row] if 0 <= row < len(self.rows) else None

    def row_of(self, quest_id: str) -> int:
        for i, q in enumerate(self.rows):
            if q["id"] == quest_id:
                return i
        return -1

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        q = self.rows[index.row()]
        col = index.column()
        status = self.profile.status(q["id"])
        open_missable = bool(q.get("missable")) and status not in filtering.DONE
        if role == QUEST_ROLE:
            return q
        if role == Qt.DisplayRole:
            if col == COL_STATUS:
                return filtering.STATUS_LABELS[status]
            if col == COL_NAME:
                return filtering.display_name(q, self.lang)
            if col == COL_CATEGORY:
                return SHORT_CATEGORY[q["category"]]
            if col == COL_REGION:
                return filtering.region_of(q)
            if col == COL_LEVEL:
                return "" if q.get("suggested_level") is None else str(q["suggested_level"])
            if col == COL_EXPANSION:
                return SHORT_EXPANSION[q["expansion"]]
            if col == COL_MISSABLE:
                return "⚠" if q.get("missable") else ""
        if role == Qt.ForegroundRole:
            if col == COL_STATUS:
                return QBrush(QColor(theme.STATUS_COLORS[status]))
            if col == COL_MISSABLE or (col == COL_NAME and open_missable):
                return QBrush(QColor(theme.ACCENT_HI if open_missable else theme.MUTED))
            if status in filtering.DONE:
                return QBrush(QColor(theme.MUTED))
        if role == Qt.FontRole and col == COL_NAME and q["category"] == "main":
            return self._bold
        if role == Qt.TextAlignmentRole and col == COL_LEVEL:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ToolTipRole:
            if col == COL_EXPANSION:
                return filtering.EXPANSION_LABELS[q["expansion"]]
            if q.get("missable"):
                return f"Missable: {q.get('missable_reason')}"
            if col == COL_NAME:
                return filtering.display_name(q, self.lang)
        return None

    # sorting -----------------------------------------------------------

    def sort(self, column, order=Qt.AscendingOrder):
        self.layoutAboutToBeChanged.emit()
        self._sort_col, self._sort_order = column, order
        self._apply_sort()
        self.layoutChanged.emit()

    def _apply_sort(self):
        col = self._sort_col
        name = filtering.sort_key("name", self.lang)
        keys = {
            COL_STATUS: lambda q: (list(filtering.STATUS_LABELS).index(self.profile.status(q["id"])), name(q)),
            COL_NAME: name,
            COL_CATEGORY: lambda q: (list(filtering.CATEGORY_LABELS).index(q["category"]), name(q)),
            COL_REGION: filtering.sort_key("region", self.lang),
            COL_LEVEL: filtering.sort_key("level", self.lang),
            COL_EXPANSION: lambda q: (list(filtering.EXPANSION_LABELS).index(q["expansion"]), name(q)),
            COL_MISSABLE: lambda q: (not q.get("missable"), name(q)),
        }
        self.rows.sort(key=keys[col], reverse=self._sort_order == Qt.DescendingOrder)


class QuestTableView(QTableView):
    """Gives the name column all spare width, but never less than NAME_MIN_WIDTH.

    Longer names wrap onto a second line; below the minimum a horizontal
    scrollbar appears instead of squeezing the names.
    """

    NAME_MIN_WIDTH = 240

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_name_column()

    def fit_name_column(self):
        hh = self.horizontalHeader()
        others = sum(hh.sectionSize(c) for c in range(len(COLUMNS)) if c != COL_NAME)
        avail = self.viewport().width() - others
        hh.resizeSection(COL_NAME, max(avail, self.NAME_MIN_WIDTH))
        self.resizeRowsToContents()
