"""Main window: quest list, progress overview and point-of-no-return view."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableView,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import filtering, paths
from ..config import Config
from ..filtering import CATEGORY_LABELS, EXPANSION_LABELS, STATUS_LABELS, Criteria
from ..profiles import STATUSES, Profile, ProfileStore
from ..questdata import QuestDB
from . import theme
from .quest_table import COL_LEVEL, COL_NAME, COL_STATUS, QuestTableModel

ALL = "__all__"


def _muted(text: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("muted")
    lbl.setWordWrap(True)
    return lbl


def _section(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("sectionTitle")
    return lbl


def _bar(done: int, total: int) -> QProgressBar:
    bar = QProgressBar()
    bar.setRange(0, max(total, 1))
    bar.setValue(done)
    pct = round(100 * done / total) if total else 0
    bar.setFormat(f"{done} / {total}  ({pct}%)")
    return bar


class MainWindow(QMainWindow):
    def __init__(self, db: QuestDB, store: ProfileStore, config: Config):
        super().__init__()
        self.db = db
        self.store = store
        self.config = config
        names = store.names()
        if config.active_profile in names:
            self.profile = store.load(config.active_profile)
        else:
            self.profile = store.ensure_default()
        self._current_id: str | None = None
        self._loading_detail = False

        self.setWindowTitle("Witcher 3 Quest Tracker")
        self.resize(1400, 860)

        self._note_timer = QTimer(self, singleShot=True, interval=600)
        self._note_timer.timeout.connect(self._save_note)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(8)
        root.addLayout(self._build_header())
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_quests_tab(), "Quests")
        self.progress_tab = QScrollArea(widgetResizable=True)
        self.tabs.addTab(self.progress_tab, "Progress")
        self.ponr_tab = QScrollArea(widgetResizable=True)
        self.tabs.addTab(self.ponr_tab, "Point of no return")
        root.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Manual tracking: live save sync arrives in phase 4.")

        self._build_menu()
        self._reload_profiles()
        self.refresh_all()

    # ------------------------------------------------------------ layout

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        title = QLabel("Quest Tracker")
        title.setObjectName("title")
        row.addWidget(title)
        row.addSpacing(16)

        self.overall = QProgressBar()
        self.overall.setMinimumWidth(320)
        row.addWidget(self.overall, 1)
        row.addSpacing(16)

        row.addWidget(_muted("Profile"))
        self.profile_combo = QComboBox(minimumWidth=160)
        self.profile_combo.activated.connect(self._switch_profile)
        row.addWidget(self.profile_combo)

        row.addWidget(_muted("Priority"))
        self.priority_combo = QComboBox()
        self.priority_combo.addItem("Save file wins", "save")
        self.priority_combo.addItem("Manual edits win", "manual")
        self.priority_combo.setToolTip("Which status is shown when the save and a manual edit disagree.")
        self.priority_combo.activated.connect(self._change_priority)
        row.addWidget(self.priority_combo)

        row.addWidget(_muted("Names"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Deutsch", "de")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.setCurrentIndex(0 if self.config.name_lang == "de" else 1)
        self.lang_combo.activated.connect(self._change_lang)
        row.addWidget(self.lang_combo)
        return row

    def _build_menu(self) -> None:
        m = self.menuBar().addMenu("&Profile")
        for text, slot, key in (
            ("&New profile…", self._new_profile, QKeySequence.New),
            ("&Rename profile…", self._rename_profile, None),
            ("&Delete profile…", self._delete_profile, None),
            (None, None, None),
            ("&Export profile…", self._export_profile, QKeySequence("Ctrl+E")),
            ("&Import profile…", self._import_profile, QKeySequence("Ctrl+I")),
            (None, None, None),
            ("&Quit", self.close, QKeySequence.Quit),
        ):
            if text is None:
                m.addSeparator()
                continue
            act = QAction(text, self)
            if key:
                act.setShortcut(key)
            act.triggered.connect(slot)
            m.addAction(act)
        find = QAction(self, shortcut=QKeySequence.Find)
        find.triggered.connect(lambda: (self.tabs.setCurrentIndex(0), self.search.setFocus(), self.search.selectAll()))
        self.addAction(find)

    def _build_quests_tab(self) -> QWidget:
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_filters())

        self.model = QuestTableModel(self.profile, self.config.name_lang)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(26)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        hh.setHighlightSections(False)
        self.table.sortByColumn(COL_NAME, Qt.AscendingOrder)
        self.table.selectionModel().currentRowChanged.connect(self._on_row_changed)
        splitter.addWidget(self.table)

        splitter.addWidget(self._build_detail())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([250, 750, 400])
        return splitter

    def _build_filters(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(220)
        w.setMaximumWidth(300)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 8, 4)

        self.search = QLineEdit(placeholderText="Search quest name…", clearButtonEnabled=True)
        self.search.textChanged.connect(self.apply_filters)
        lay.addWidget(self.search)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)

        def combo(items: dict[str, str]) -> QComboBox:
            c = QComboBox()
            c.addItem("All", ALL)
            for key, label in items.items():
                c.addItem(label, key)
            c.currentIndexChanged.connect(self.apply_filters)
            return c

        self.f_category = combo(CATEGORY_LABELS)
        regions = sorted({filtering.region_of(q) for q in self.db.quests})
        self.f_region = combo({r: r for r in regions})
        self.f_expansion = combo(EXPANSION_LABELS)
        self.f_status = combo(STATUS_LABELS)
        form.addRow("Category", self.f_category)
        form.addRow("Region", self.f_region)
        form.addRow("Content", self.f_expansion)
        form.addRow("Status", self.f_status)

        lvl = QHBoxLayout()
        self.f_lmin = QSpinBox(minimum=0, maximum=100, specialValueText="any")
        self.f_lmax = QSpinBox(minimum=0, maximum=100, specialValueText="any")
        for s in (self.f_lmin, self.f_lmax):
            s.valueChanged.connect(self.apply_filters)
        lvl.addWidget(self.f_lmin)
        lvl.addWidget(_muted("to"))
        lvl.addWidget(self.f_lmax)
        form.addRow("Level", lvl)

        self.f_sort = QComboBox()
        for label, col in (("Name", COL_NAME), ("Level", COL_LEVEL), ("Region", 3), ("Status", COL_STATUS)):
            self.f_sort.addItem(label, col)
        self.f_sort.activated.connect(lambda: self.table.sortByColumn(self.f_sort.currentData(), Qt.AscendingOrder))
        form.addRow("Sort by", self.f_sort)
        lay.addLayout(form)

        self.f_missable = QCheckBox("Missable quests only")
        self.f_missable.toggled.connect(self.apply_filters)
        lay.addWidget(self.f_missable)

        reset = QPushButton("Reset filters")
        reset.clicked.connect(self._reset_filters)
        lay.addWidget(reset)

        self.result_count = _muted()
        lay.addWidget(self.result_count)
        lay.addStretch(1)
        return w

    def _build_detail(self) -> QWidget:
        outer = QScrollArea(widgetResizable=True)
        outer.setMinimumWidth(340)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 4, 4, 4)
        lay.setSpacing(8)

        self.d_title = QLabel(objectName="title", wordWrap=True)
        self.d_alt = _muted()
        self.d_meta = _muted()
        lay.addWidget(self.d_title)
        lay.addWidget(self.d_alt)
        lay.addWidget(self.d_meta)

        self.d_warning = QFrame(objectName="warning")
        wl = QVBoxLayout(self.d_warning)
        self.d_warning_text = QLabel(wordWrap=True)
        self.d_warning_text.setTextFormat(Qt.RichText)
        wl.addWidget(self.d_warning_text)
        lay.addWidget(self.d_warning)

        st = QHBoxLayout()
        st.addWidget(_section("Status"))
        self.d_status = QComboBox()
        self.d_status.addItem("— not set manually —", None)
        for s in STATUSES:
            self.d_status.addItem(STATUS_LABELS[s], s)
        self.d_status.activated.connect(self._on_manual_status)
        st.addWidget(self.d_status, 1)
        lay.addLayout(st)
        self.d_effective = _muted()
        lay.addWidget(self.d_effective)

        lay.addWidget(_section("Description"))
        self.d_desc = QTextBrowser()
        self.d_desc.setMinimumHeight(140)
        lay.addWidget(self.d_desc, 2)

        lay.addWidget(_section("Notes"))
        self.d_notes = QPlainTextEdit(placeholderText="Your notes for this playthrough…")
        self.d_notes.setMinimumHeight(110)
        self.d_notes.textChanged.connect(self._on_notes_changed)
        lay.addWidget(self.d_notes, 1)

        self.d_ids = _muted()
        self.d_ids.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.d_ids)

        self.d_empty = _muted("Select a quest.")
        lay.addWidget(self.d_empty)
        outer.setWidget(w)
        self._detail_widgets = [self.d_title, self.d_alt, self.d_meta, self.d_status, self.d_effective,
                                self.d_desc, self.d_notes, self.d_ids]
        self._show_detail(None)
        return outer

    # ------------------------------------------------------------ refresh

    def criteria(self) -> Criteria:
        def sel(c: QComboBox) -> set[str]:
            return set() if c.currentData() == ALL else {c.currentData()}
        return Criteria(
            text=self.search.text().strip(),
            categories=sel(self.f_category),
            regions=sel(self.f_region),
            expansions=sel(self.f_expansion),
            statuses=sel(self.f_status),
            level_min=self.f_lmin.value() or None,
            level_max=self.f_lmax.value() or None,
            missable_only=self.f_missable.isChecked(),
            name_lang=self.config.name_lang,
        )

    def apply_filters(self) -> None:
        rows = filtering.filter_quests(self.db.quests, self.profile, self.criteria())
        self.model.set_rows(rows)
        self.result_count.setText(f"{len(rows)} of {len(self.db.quests)} quests shown")
        self._reselect()

    def refresh_all(self) -> None:
        self.model.set_profile(self.profile, self.config.name_lang)
        self.apply_filters()
        self._refresh_overall()
        self._build_progress_view()
        self._build_ponr_view()
        self._show_detail(self.db.by_id.get(self._current_id) if self._current_id else None)

    def _refresh_overall(self) -> None:
        p = filtering.progress(self.db.quests, self.profile)
        failed = sum(self.profile.status(q["id"]) == "failed" for q in self.db.quests)
        self.overall.setRange(0, p.total)
        self.overall.setValue(p.done)
        self.overall.setFormat(f"{p.done} / {p.total} completed ({round(100 * p.fraction)}%)"
                               + (f" · {failed} failed" if failed else ""))

    def _reselect(self) -> None:
        if not self._current_id:
            return
        row = self.model.row_of(self._current_id)
        if row >= 0:
            idx = self.model.index(row, 0)
            self.table.selectionModel().setCurrentIndex(
                idx, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)

    def _build_progress_view(self) -> None:
        w = QWidget()
        grid = QGridLayout(w)
        grid.setContentsMargins(16, 16, 16, 16)
        grid.setHorizontalSpacing(24)
        groups = (
            ("By category", lambda q: CATEGORY_LABELS[q["category"]], list(CATEGORY_LABELS.values())),
            ("By content", lambda q: EXPANSION_LABELS[q["expansion"]], list(EXPANSION_LABELS.values())),
            ("By region", filtering.region_of, None),
        )
        for col, (title, key, order) in enumerate(groups):
            box = QGroupBox(title)
            form = QFormLayout(box)
            stats = filtering.progress(self.db.quests, self.profile, key=key)
            for name in order or sorted(stats):
                if name in stats:
                    form.addRow(name, _bar(stats[name].done, stats[name].total))
            grid.addWidget(box, 0, col, Qt.AlignTop)
        grid.setRowStretch(1, 1)
        self.progress_tab.setWidget(w)

    def _build_ponr_view(self) -> None:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)
        lay.addWidget(_muted(
            "Story points after which some quests can no longer be completed. "
            "This data is hand-curated and UNVERIFIED — check before relying on it."))
        lang = self.config.name_lang
        for p in self.db.points_of_no_return:
            q = self.db.by_id[p["quest_id"]]
            status = self.profile.status(q["id"])
            box = QGroupBox(f"{filtering.display_name(q, lang)}  —  {STATUS_LABELS[status]}")
            bl = QVBoxLayout(box)
            bl.addWidget(QLabel(p["effect"], wordWrap=True))
            missables = self.db.missables_for(q["id"])
            open_ = [m for m in missables if self.profile.status(m["id"]) not in filtering.DONE]
            if open_ and status not in filtering.DONE:
                warn = QFrame(objectName="warning")
                QVBoxLayout(warn).addWidget(QLabel(
                    f"<b>{len(open_)} missable quest(s) still open.</b> Finish them before completing this quest.",
                    wordWrap=True))
                bl.addWidget(warn)
            for m in missables:
                ms = self.profile.status(m["id"])
                color = theme.ACCENT_HI if ms not in filtering.DONE else theme.MUTED
                icon = {"completed": "✓", "failed": "✗"}.get(ms, "⚠")
                link = QLabel(
                    f'<a href="{m["id"]}" style="color:{color}; text-decoration:none">'
                    f'{icon} {filtering.display_name(m, lang)}</a>'
                    f'  <span style="color:{theme.MUTED}">({STATUS_LABELS[ms]}) — {m.get("missable_reason") or ""}</span>')
                link.setWordWrap(True)
                link.linkActivated.connect(self.select_quest)
                bl.addWidget(link)
            lay.addWidget(box)
        lay.addStretch(1)
        self.ponr_tab.setWidget(w)

    # ------------------------------------------------------------ detail

    def select_quest(self, quest_id: str) -> None:
        self.tabs.setCurrentIndex(0)
        if self.model.row_of(quest_id) < 0:
            self._reset_filters()
        self._current_id = quest_id
        self._reselect()
        self.table.scrollTo(self.model.index(self.model.row_of(quest_id), 0))

    def _on_row_changed(self, current, _previous) -> None:
        q = self.model.quest_at(current.row()) if current.isValid() else None
        if q is not None:
            self._flush_note()
            self._current_id = q["id"]
        self._show_detail(q)

    def _show_detail(self, q: dict | None) -> None:
        self._loading_detail = True
        try:
            for wdg in self._detail_widgets:
                wdg.setVisible(q is not None)
            self.d_empty.setVisible(q is None)
            self.d_warning.setVisible(bool(q and q.get("missable")))
            if q is None:
                return
            lang = self.config.name_lang
            self.d_title.setText(filtering.display_name(q, lang))
            alt = q["name"] if lang == "de" else q.get("name_de")
            self.d_alt.setText(alt if alt and alt != self.d_title.text() else "")
            level = q.get("suggested_level")
            self.d_meta.setText(" · ".join(filter(None, [
                CATEGORY_LABELS[q["category"]], filtering.region_of(q),
                f"Level {level}" if level is not None else "Level unknown",
                EXPANSION_LABELS[q["expansion"]],
            ])))
            if q.get("missable"):
                ponr = self.db.by_id.get(q.get("point_of_no_return") or "")
                text = f"<b>⚠ Missable.</b> {q.get('missable_reason') or ''}"
                if ponr:
                    text += f"<br>Do it before: <b>{filtering.display_name(ponr, lang)}</b>"
                if not q.get("verified"):
                    text += f'<br><span style="color:{theme.MUTED}">Unverified ({q.get("source")}).</span>'
                self.d_warning_text.setText(text)
            manual = self.profile.manual_status.get(q["id"])
            self.d_status.setCurrentIndex(self.d_status.findData(manual) if manual else 0)
            saved = self.profile.save_status.get(q["id"])
            eff = self.profile.status(q["id"])
            self.d_effective.setText(
                f"Shown: {STATUS_LABELS[eff]} · From save: {STATUS_LABELS[saved] if saved else '—'}")
            desc = q.get("description_de") if lang == "de" else q.get("description")
            # Game texts contain simple markup such as <br>.
            self.d_desc.setHtml(desc or q.get("description") or "<i>No description in the game files.</i>")
            self.d_notes.setPlainText(self.profile.notes.get(q["id"], ""))
            self.d_ids.setText(f"{q['id']} · {q['save_ids']['guid']}")
        finally:
            self._loading_detail = False

    def _on_manual_status(self) -> None:
        if not self._current_id:
            return
        self.profile.set_manual(self._current_id, self.d_status.currentData())
        self._persist()
        self.refresh_all()

    def _on_notes_changed(self) -> None:
        if not self._loading_detail:
            self._note_timer.start()

    def _flush_note(self) -> None:
        if self._note_timer.isActive():
            self._note_timer.stop()
            self._save_note()

    def _save_note(self) -> None:
        if self._current_id:
            self.profile.set_note(self._current_id, self.d_notes.toPlainText())
            self._persist()

    # ------------------------------------------------------------ profile actions

    def _persist(self) -> None:
        self.store.save(self.profile)

    def _reload_profiles(self) -> None:
        self.profile_combo.clear()
        for n in self.store.names():
            self.profile_combo.addItem(n)
        self.profile_combo.setCurrentText(self.profile.name)
        self.priority_combo.setCurrentIndex(self.priority_combo.findData(self.profile.priority))
        self.config.active_profile = self.profile.name
        self.config.save()

    def _set_profile(self, profile: Profile) -> None:
        self._flush_note()
        self.profile = profile
        self._reload_profiles()
        self.refresh_all()

    def _switch_profile(self) -> None:
        name = self.profile_combo.currentText()
        if name and name != self.profile.name:
            self._set_profile(self.store.load(name))

    def _change_priority(self) -> None:
        self.profile.priority = self.priority_combo.currentData()
        self._persist()
        self.refresh_all()

    def _change_lang(self) -> None:
        self.config.name_lang = self.lang_combo.currentData()
        self.config.save()
        self.refresh_all()

    def _new_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "New profile", "Name of the playthrough:")
        if ok and name.strip():
            if name.strip() in self.store.names():
                QMessageBox.warning(self, "New profile", "A profile with this name already exists.")
                return
            p = Profile(name.strip())
            self.store.save(p)
            self._set_profile(p)

    def _rename_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "Rename profile", "New name:", text=self.profile.name)
        name = name.strip()
        if ok and name and name != self.profile.name:
            if name in self.store.names():
                QMessageBox.warning(self, "Rename profile", "A profile with this name already exists.")
                return
            old = self.profile.name
            self.profile.name = name
            self.store.save(self.profile)
            self.store.delete(old)
            self._reload_profiles()

    def _delete_profile(self) -> None:
        if len(self.store.names()) <= 1:
            QMessageBox.information(self, "Delete profile", "The last profile cannot be deleted.")
            return
        if QMessageBox.question(
            self, "Delete profile",
            f"Delete profile “{self.profile.name}” with all statuses and notes? This cannot be undone.",
        ) != QMessageBox.Yes:
            return
        self.store.delete(self.profile.name)
        self._set_profile(self.store.load(self.store.names()[0]))

    def _export_profile(self) -> None:
        self._flush_note()
        default = str(Path.home() / f"{self.profile.name}.w3qt.json")
        path, _ = QFileDialog.getSaveFileName(self, "Export profile", default, "JSON (*.json)")
        if path:
            self.store.export(self.profile, Path(path))
            self.statusBar().showMessage(f"Exported to {path}", 5000)

    def _import_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import profile", str(Path.home()), "JSON (*.json)")
        if not path:
            return
        try:
            p = self.store.import_file(Path(path))
        except (OSError, ValueError, KeyError) as e:
            QMessageBox.warning(self, "Import profile", f"Could not import: {e}")
            return
        self._set_profile(p)
        self.statusBar().showMessage(f"Imported profile “{p.name}”", 5000)

    def _reset_filters(self) -> None:
        widgets = (self.search, self.f_category, self.f_region, self.f_expansion, self.f_status,
                   self.f_lmin, self.f_lmax, self.f_missable)
        for wdg in widgets:
            wdg.blockSignals(True)
        self.search.clear()
        for c in (self.f_category, self.f_region, self.f_expansion, self.f_status):
            c.setCurrentIndex(0)
        self.f_lmin.setValue(0)
        self.f_lmax.setValue(0)
        self.f_missable.setChecked(False)
        for wdg in widgets:
            wdg.blockSignals(False)
        self.apply_filters()

    def closeEvent(self, event) -> None:
        self._flush_note()
        self._persist()
        super().closeEvent(event)


def profiles_dir() -> Path:
    return paths.data_dir() / "profiles"
