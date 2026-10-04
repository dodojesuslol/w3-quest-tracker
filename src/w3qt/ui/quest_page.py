"""Full-page quest view with journal entries and objectives from the save."""

from __future__ import annotations

import html
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import filtering
from ..filtering import CATEGORY_LABELS, EXPANSION_LABELS, STATUS_LABELS
from ..profiles import STATUSES
from . import theme

STATUS_SHORT = {"not_started": "Not started", "in_progress": "In progress",
                "completed": "Completed", "failed": "Failed / Missed"}
OBJ_ICON = {"success": ("✓", theme.STATUS_COLORS["completed"]),
            "active": ("▸", theme.STATUS_COLORS["in_progress"]),
            "failed": ("✗", theme.STATUS_COLORS["failed"]),
            "inactive": ("○", theme.MUTED)}


def _label(text: str = "", name: str | None = None, wrap: bool = True) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


def sources_html(entry: dict) -> str:
    links = [f'<a href="{u}" style="color:{theme.MUTED}">{urlparse(u).netloc.removeprefix("www.")}</a>'
             for u in entry.get("sources", [])]
    return f'<span style="color:{theme.MUTED}">Sources: {", ".join(links) or "none"}</span>'


class QuestPage(QWidget):
    back = Signal()
    status_changed = Signal(str, object)   # quest id, status or None (use save)
    note_changed = Signal(str, str)
    open_quest = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.quest: dict | None = None
        self._loading = False
        self._note_timer = QTimer(self, singleShot=True, interval=600)
        self._note_timer.timeout.connect(self._emit_note)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)

        top = QHBoxLayout()
        back = QPushButton("‹  Back to quests")
        back.setToolTip("Back to the quest list (Esc)")
        back.clicked.connect(self.go_back)
        top.addWidget(back)
        top.addStretch(1)
        root.addLayout(top)

        self.title = _label(name="pageTitle")
        self.alt = _label(name="muted")
        self.meta = _label(name="muted")
        for w in (self.title, self.alt, self.meta):
            root.addWidget(w)

        cols = QHBoxLayout()
        cols.setSpacing(18)
        root.addLayout(cols, 1)

        # left: journal + objectives
        left = QVBoxLayout()
        head = QHBoxLayout()
        head.addWidget(_label("Journal & objectives", "sectionTitle", wrap=False))
        head.addStretch(1)
        self.spoilers = QCheckBox("Show unrevealed entries (spoilers)")
        self.spoilers.toggled.connect(self._render_journal)
        head.addWidget(self.spoilers)
        left.addLayout(head)
        self.journal = QTextBrowser()
        self.journal.setOpenLinks(False)
        left.addWidget(self.journal, 1)
        cols.addLayout(left, 3)

        # right: status, warnings, notes, info
        right_area = QScrollArea(widgetResizable=True)
        right_area.setMinimumWidth(340)
        right_area.setMaximumWidth(420)
        right_w = QWidget()
        right = QVBoxLayout(right_w)
        right.setContentsMargins(0, 0, 6, 0)
        right.setSpacing(8)

        right.addWidget(_label("Status", "sectionTitle"))
        grid = QGridLayout()
        grid.setSpacing(4)
        self.status_group = QButtonGroup(self)
        self.status_buttons: dict[str, QPushButton] = {}
        for i, st in enumerate(STATUSES):
            b = QPushButton(STATUS_SHORT[st], objectName="statusButton", checkable=True)
            b.clicked.connect(lambda _=False, v=st: self._set_status(v))
            self.status_group.addButton(b)
            self.status_buttons[st] = b
            grid.addWidget(b, i // 2, i % 2)
        right.addLayout(grid)
        eff = QHBoxLayout()
        self.effective = _label(name="muted")
        eff.addWidget(self.effective, 1)
        self.reset = QPushButton("use save status", objectName="linkButton")
        self.reset.setCursor(Qt.PointingHandCursor)
        self.reset.clicked.connect(lambda: self._set_status(None))
        eff.addWidget(self.reset)
        right.addLayout(eff)

        self.warning = QFrame(objectName="warning")
        self.warning_text = _label()
        self.warning_text.setTextFormat(Qt.RichText)
        self.warning_text.linkActivated.connect(self._on_link)
        QVBoxLayout(self.warning).addWidget(self.warning_text)
        right.addWidget(self.warning)

        self.ponr = QFrame(objectName="warning")
        self.ponr_text = _label()
        self.ponr_text.setTextFormat(Qt.RichText)
        self.ponr_text.linkActivated.connect(self._on_link)
        QVBoxLayout(self.ponr).addWidget(self.ponr_text)
        right.addWidget(self.ponr)

        right.addWidget(_label("Notes", "sectionTitle"))
        self.notes = QPlainTextEdit(placeholderText="Your notes for this playthrough…")
        self.notes.setMinimumHeight(130)
        self.notes.textChanged.connect(self._on_notes)
        right.addWidget(self.notes)

        right.addWidget(_label("Details", "sectionTitle"))
        self.info = QFormLayout()
        self.info.setLabelAlignment(Qt.AlignLeft)
        self.info.setVerticalSpacing(3)
        right.addLayout(self.info)
        right.addStretch(1)
        right_area.setWidget(right_w)
        cols.addWidget(right_area, 2)

        self._db = None
        self._profile = None
        self._lang = "de"
        self._entries: dict[str, str] | None = None

    # ------------------------------------------------------------ public

    def show_quest(self, quest: dict, db, profile, lang: str, entry_status: dict[str, str] | None) -> None:
        if self.quest is not None and self.quest["id"] != quest["id"]:
            self.flush()
            self.spoilers.setChecked(False)
        self.quest, self._db, self._profile, self._lang = quest, db, profile, lang
        self._entries = entry_status
        self.refresh()

    def refresh(self) -> None:
        q = self.quest
        if q is None:
            return
        self._loading = True
        try:
            lang, profile = self._lang, self._profile
            self.title.setText(filtering.display_name(q, lang))
            alt = q["name"] if lang == "de" else q.get("name_de")
            self.alt.setText(alt if alt and alt != self.title.text() else "")
            self.alt.setVisible(bool(self.alt.text()))
            level = q.get("suggested_level")
            self.meta.setText(" · ".join([
                CATEGORY_LABELS[q["category"]], filtering.region_of(q),
                f"Level {level}" if level is not None else "Level unknown",
                EXPANSION_LABELS[q["expansion"]]]))

            manual = profile.manual_status.get(q["id"])
            saved = profile.save_status.get(q["id"])
            self.status_buttons[profile.status(q["id"])].setChecked(True)
            src = f"From save: {STATUS_LABELS[saved] if saved else '—'}"
            if manual:
                src += f" · set by hand: {STATUS_LABELS[manual]}"
            self.effective.setText(src)
            self.reset.setVisible(manual is not None)

            self._render_warning()
            self._render_ponr()
            self.notes.setPlainText(profile.notes.get(q["id"], ""))
            self._render_info()
            self._render_journal()
        finally:
            self._loading = False

    def flush(self) -> None:
        if self._note_timer.isActive():
            self._note_timer.stop()
            self._emit_note()

    def go_back(self) -> None:
        self.flush()
        self.back.emit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Escape, Qt.Key_Backspace) and not self.notes.hasFocus():
            self.go_back()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------ rendering

    def _quest_link(self, qid: str) -> str:
        other = self._db.by_id.get(qid)
        if other is None:
            return html.escape(qid)
        st = self._profile.status(qid)
        return (f'<a href="quest:{qid}" style="color:{theme.ACCENT}">'
                f'{html.escape(filtering.display_name(other, self._lang))}</a>'
                f' <span style="color:{theme.MUTED}">({STATUS_LABELS[st]})</span>')

    def _render_warning(self) -> None:
        q = self.quest
        self.warning.setVisible(bool(q.get("missable")))
        if not q.get("missable"):
            return
        text = f"<b>⚠ Missable.</b> {html.escape(q.get('missable_reason') or '')}"
        if q.get("point_of_no_return"):
            text += f"<br>Do it before: {self._quest_link(q['point_of_no_return'])}"
        if q.get("note"):
            text += f'<br><span style="color:{theme.MUTED}">{html.escape(q["note"])}</span>'
        text += "<br>" + sources_html(q)
        self.warning_text.setText(text)

    def _render_ponr(self) -> None:
        q = self.quest
        ponr = next((p for p in self._db.points_of_no_return if p["quest_id"] == q["id"]), None)
        self.ponr.setVisible(ponr is not None)
        if ponr is None:
            return
        when = "Starting" if ponr.get("trigger") == "start" else "Completing"
        rows = "".join(f"<br>• {self._quest_link(m['id'])}" for m in self._db.missables_for(q["id"]))
        self.ponr_text.setText(
            f"<b>Point of no return.</b> {when} this quest locks other content. "
            f"{html.escape(ponr['effect'])}{rows}<br>{sources_html(ponr)}")

    def _render_info(self) -> None:
        q = self.quest
        while self.info.rowCount():
            self.info.removeRow(0)
        rows = [
            ("Journal group", q.get("journal_group") or "—"),
            ("Internal name", q.get("internal_name") or "—"),
            ("Journal file", q["save_ids"]["journal_resource"].rsplit("\\", 1)[-1]),
            ("GUID", q["save_ids"]["guid"]),
        ]
        for k, v in rows:
            val = _label(v, "muted")
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.info.addRow(_label(k, wrap=False), val)

    def _render_journal(self) -> None:
        q = self.quest
        if q is None:
            return
        lang = self._lang
        entries = self._entries
        show_all = self.spoilers.isChecked() or entries is None
        discovered = entries is not None and q["save_ids"]["guid"] in entries
        ink, muted = theme.TEXT, theme.MUTED
        parts = [f'<div style="color:{ink}; font-size:13.5pt">']

        if entries is None:
            parts.append(f'<p style="color:{muted}"><i>No save loaded — showing every entry.</i></p>')
        elif not discovered and not show_all:
            parts.append(f'<p style="color:{muted}">This quest has not appeared in your journal yet. '
                         'Tick “Show unrevealed entries” to read ahead.</p></div>')
            self.journal.setHtml("".join(parts))
            return

        def visible(guid: str) -> bool:
            return show_all or (entries is not None and guid in entries)

        texts = [j for j in q.get("journal", []) if visible(j["guid"])]
        hidden_texts = len(q.get("journal", [])) - len(texts)
        parts.append(f'<h3 style="font-family:\'{theme.TITLE_FONT}\'; color:{theme.ACCENT}">Journal</h3>')
        if texts:
            for j in texts:
                body = (j.get("text_de") if lang == "de" else None) or j.get("text") or ""
                parts.append(f"<p>{body}</p>")  # game text uses simple markup like <br>
        else:
            parts.append(f'<p style="color:{muted}">No journal entry yet.</p>')
        if hidden_texts and not show_all:
            parts.append(f'<p style="color:{muted}">{hidden_texts} more entr{"y" if hidden_texts == 1 else "ies"} '
                         'not revealed yet.</p>')

        objs = q.get("objectives", [])
        shown = [o for o in objs if visible(o["guid"])]
        parts.append(f'<h3 style="font-family:\'{theme.TITLE_FONT}\'; color:{theme.ACCENT}">Objectives</h3>')
        if shown:
            parts.append('<table cellspacing="0" cellpadding="3">')
            for o in shown:
                st = entries.get(o["guid"]) if entries else None
                icon, color = OBJ_ICON.get(st, ("·", muted))
                name = html.escape((o.get("name_de") if lang == "de" else None) or o.get("name") or "")
                style = f"color:{muted}; text-decoration:line-through" if st == "success" else f"color:{ink}"
                if st == "failed":
                    style = f"color:{theme.STATUS_COLORS['failed']}"
                parts.append(f'<tr><td style="color:{color}; font-weight:700; padding-right:8px">{icon}</td>'
                             f'<td style="{style}">{name}</td></tr>')
            parts.append("</table>")
        else:
            parts.append(f'<p style="color:{muted}">No objectives revealed yet.</p>')
        hidden = len(objs) - len(shown)
        if hidden and not show_all:
            parts.append(f'<p style="color:{muted}">{hidden} objective{"s" if hidden != 1 else ""} '
                         'not revealed yet.</p>')
        parts.append(f'<p style="color:{muted}; font-size:11pt">✓ done · ▸ active · ✗ failed · ○ inactive</p>')
        parts.append("</div>")
        self.journal.setHtml("".join(parts))

    # ------------------------------------------------------------ events

    def _on_link(self, href: str) -> None:
        if href.startswith("quest:"):
            self.open_quest.emit(href.removeprefix("quest:"))
        else:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(href))

    def _set_status(self, status: str | None) -> None:
        if self.quest:
            self.status_changed.emit(self.quest["id"], status)

    def _on_notes(self) -> None:
        if not self._loading:
            self._note_timer.start()

    def _emit_note(self) -> None:
        if self.quest:
            self.note_changed.emit(self.quest["id"], self.notes.toPlainText())
