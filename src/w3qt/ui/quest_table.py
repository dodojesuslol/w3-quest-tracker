"""Table model for the quest list."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, QRect, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics
from PySide6.QtWidgets import QTableView

from .. import filtering
from ..profiles import Profile
from . import theme

COLUMNS = ["Status", "Quest", "Category", "Region", "Lvl", "Content", "⚠", ""]
SHORT_CATEGORY = {**filtering.CATEGORY_LABELS, "contract": "Contract"}
SHORT_EXPANSION = {"base": "Base", "hearts_of_stone": "HoS", "blood_and_wine": "B&W"}
COL_STATUS, COL_NAME, COL_CATEGORY, COL_REGION, COL_LEVEL, COL_EXPANSION, COL_MISSABLE, COL_OPEN = range(8)
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
            if col == COL_OPEN:
                return "Details ›"
        if role == Qt.ForegroundRole:
            if col == COL_OPEN:
                return QBrush(QColor(theme.ACCENT))
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
        if role == Qt.TextAlignmentRole and col in (COL_OPEN, COL_MISSABLE):
            return int(Qt.AlignCenter)
        if role == Qt.ToolTipRole:
            if col == COL_OPEN:
                return "Open the quest page (or double-click the row / press Enter)"
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
            COL_OPEN: name,
        }
        self.rows.sort(key=keys[col], reverse=self._sort_order == Qt.DescendingOrder)


class QuestTableView(QTableView):
    """Fixed column widths and row heights computed from font metrics.

    The name column gets all spare width, but never less than NAME_MIN_WIDTH;
    longer names wrap onto a second line. Sizes are computed directly instead
    of via Qt's ResizeToContents/resizeRowsToContents, which query every cell
    in every role and made filtering and resizing slow.
    """

    NAME_MIN_WIDTH = 210
    CELL_PAD = 20          # item padding (2 × 4 px from the stylesheet) + focus margins + air
    HEAD_PAD = 16          # header section padding
    SORT_ARROW = 16        # extra room for the sort indicator
    ROW_PAD = 12           # vertical padding per row

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fit_timer = QTimer(self, singleShot=True, interval=40)
        self._fit_timer.timeout.connect(self.fit)
        self._col_widths: dict[int, int] = {}
        self.setMouseTracking(True)


    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_timer.start()  # coalesce the many events of a window drag

    def viewportEvent(self, event):
        # also fires when the vertical scrollbar appears or disappears
        if event.type() == QEvent.Resize:
            self._fit_timer.start()
        return super().viewportEvent(event)

    def mouseMoveEvent(self, event):
        over_link = self.indexAt(event.position().toPoint()).column() == COL_OPEN
        self.viewport().setCursor(Qt.PointingHandCursor if over_link else Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def _metrics(self):
        self.ensurePolished()
        body = QFont(self.font())
        bold = QFont(body)
        bold.setBold(True)
        head = QFont(theme.TITLE_FONT)
        head.setPointSizeF(13)
        return QFontMetrics(body), QFontMetrics(bold), QFontMetrics(head)

    def fit(self, recompute_columns: bool = True):
        model = self.model()
        if model is None:
            return
        fm, fm_bold, fm_head = self._metrics()
        hh = self.horizontalHeader()
        if recompute_columns or not self._col_widths:
            widths = {}
            for c in range(len(COLUMNS)):
                if c == COL_NAME:
                    continue
                w = fm_head.horizontalAdvance(COLUMNS[c]) + self.HEAD_PAD
                if hh.sortIndicatorSection() == c:
                    w += self.SORT_ARROW
                for r in range(model.rowCount()):
                    text = model.data(model.index(r, c), Qt.DisplayRole) or ""
                    w = max(w, fm.horizontalAdvance(text) + self.CELL_PAD)
                widths[c] = w
            self._col_widths = widths
        hh.setMinimumSectionSize(16)  # Qt's default minimum would widen the narrow columns
        for c, w in self._col_widths.items():
            hh.resizeSection(c, w)
        others = sum(hh.sectionSize(c) for c in self._col_widths)  # actual sizes
        name_w = max(self.viewport().width() - others - 2, self.NAME_MIN_WIDTH)
        hh.resizeSection(COL_NAME, name_w)

        base = fm.height() + self.ROW_PAD
        self.verticalHeader().setDefaultSectionSize(base)
        text_w = name_w - 12  # what the delegate really has for text
        for r in range(model.rowCount()):
            q = model.quest_at(r)
            text = model.data(model.index(r, COL_NAME), Qt.DisplayRole) or ""
            m = fm_bold if q and q["category"] == "main" else fm
            h = m.boundingRect(QRect(0, 0, text_w, 10_000), Qt.TextWordWrap, text).height() + self.ROW_PAD
            if h > base:
                self.setRowHeight(r, h)
            elif self.rowHeight(r) != base:
                self.setRowHeight(r, base)

    def fit_name_column(self):  # kept for callers; widths change only with content
        self.fit(recompute_columns=True)
