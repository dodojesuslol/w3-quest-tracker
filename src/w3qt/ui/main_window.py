"""Main window: quest list, progress overview and point-of-no-return view."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QEvent, QItemSelectionModel, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QKeySequence, QPixmap
from PySide6.QtCore import QDir, QUrl
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
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
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QMenu,
    QTreeView,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import filtering, paths, savesync, wiki
from ..gamefiles.locate import find_save_dirs
from ..savesync import SaveSnapshot
from ..watcher import SaveWatcher
from ..config import Config
from ..filtering import CATEGORY_LABELS, EXPANSION_LABELS, STATUS_LABELS, Criteria
from ..profiles import STATUSES, Profile, ProfileStore
from ..questdata import QuestDB
from . import theme
from .quest_page import QuestPage
from .scroll import ScrollFrame
from .quest_table import COL_LEVEL, COL_NAME, COL_STATUS, QuestTableModel, QuestTableView

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

        self.watcher = SaveWatcher(self)
        central = ScrollFrame()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        # header + save bar: shown on the list views, hidden on the quest page
        self.top_area = QWidget()
        top = QVBoxLayout(self.top_area)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        top.addLayout(self._build_header())
        top.addWidget(self._build_save_bar())
        root.addWidget(self.top_area)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_quests_tab(), "Quests")
        self.progress_tab = QScrollArea(widgetResizable=True)
        self.tabs.addTab(self.progress_tab, "Progress")
        self.ponr_tab = QScrollArea(widgetResizable=True)
        self.tabs.addTab(self.ponr_tab, "Point of no return")
        self.page = QuestPage()
        self.page.back.connect(self.close_page)
        self.page.status_changed.connect(self._on_page_status)
        self.page.note_changed.connect(self._on_page_note)
        self.page.open_quest.connect(self.open_page)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.tabs)
        self.stack.addWidget(self.page)
        root.addWidget(self.stack, 1)
        self.tabs.currentChanged.connect(lambda _i: (setattr(self, "_views_dirty", True),
                                                     self._refresh_visible_tab()))
        self.setCentralWidget(central)
        self._snapshot: SaveSnapshot | None = None
        self._snapshot_applied = False
        self._sync_note = ""
        self.watcher.snapshot_ready.connect(self._on_snapshot)
        self.watcher.failed.connect(self._on_sync_failed)
        self.watcher.busy.connect(lambda msg: self.statusBar().showMessage(msg))

        self._build_shortcuts()
        QApplication.instance().installEventFilter(self)  # mouse back button
        self._reload_profiles()
        self.refresh_all()
        self._start_watching()

    # ------------------------------------------------------------ layout

    def _build_header(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(4)
        row = QHBoxLayout()
        title = QLabel("Quest Chronicle")
        title.setObjectName("title")
        row.addWidget(title)
        row.addStretch(1)

        self.profile_btn = QToolButton(popupMode=QToolButton.InstantPopup)
        self.profile_btn.setToolTip("Switch, create, rename, export or import profiles")
        self.profile_menu = QMenu(self)
        self.profile_menu.aboutToShow.connect(self._fill_profile_menu)
        self.profile_btn.setMenu(self.profile_menu)
        row.addWidget(self.profile_btn)

        self.settings_btn = QToolButton(popupMode=QToolButton.InstantPopup, objectName="icon", text="⚙")
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setMenu(self._build_settings_menu())
        row.addWidget(self.settings_btn)

        sync = QToolButton(objectName="icon", text="⟳")
        sync.setToolTip("Read the newest save now (F5)")
        sync.clicked.connect(self.watcher_sync)
        row.addWidget(sync)
        col.addLayout(row)

        self.overall = QProgressBar()
        col.addWidget(self.overall)
        return col

    def _build_settings_menu(self) -> QMenu:
        m = QMenu(self)
        m.addSection("When save and manual edit disagree")
        self.priority_group = QActionGroup(self)
        self.priority_actions = {}
        for value, text in (("save", "Save file wins"), ("manual", "Manual edits win")):
            act = QAction(text, self, checkable=True)
            act.triggered.connect(lambda _=False, v=value: self._change_priority(v))
            self.priority_group.addAction(act)
            self.priority_actions[value] = act
            m.addAction(act)
        m.addSection("Quest names")
        lang_group = QActionGroup(self)
        for value, text in (("de", "Deutsch"), ("en", "English")):
            act = QAction(text, self, checkable=True, checked=self.config.name_lang == value)
            act.triggered.connect(lambda _=False, v=value: self._change_lang(v))
            lang_group.addAction(act)
            m.addAction(act)
        m.addSeparator()
        self.wiki_cache_action = m.addAction("Clear wiki cache", self._clear_wiki_cache)
        m.aboutToShow.connect(self._update_wiki_cache_action)
        m.addAction("Show unknown quests log", self._show_unknown_log)
        m.addAction("Quit", QKeySequence.Quit, self.close)
        return m

    def _update_wiki_cache_action(self) -> None:
        size = wiki.cache_size()
        self.wiki_cache_action.setText(f"Clear wiki cache ({size / 1024:.0f} KB)")
        self.wiki_cache_action.setEnabled(size > 0)

    def _clear_wiki_cache(self) -> None:
        wiki.clear_cache()
        self.statusBar().showMessage("Wiki cache cleared.", 4000)

    def _fill_profile_menu(self) -> None:
        m = self.profile_menu
        m.clear()
        m.addSection("Playthroughs")
        group = QActionGroup(m)
        for name in self.store.names():
            act = QAction(name, m, checkable=True, checked=name == self.profile.name)
            act.triggered.connect(lambda _=False, n=name: self._switch_profile(n))
            group.addAction(act)
            m.addAction(act)
        m.addSeparator()
        m.addAction("New profile…", self._new_profile)
        m.addAction("Rename profile…", self._rename_profile)
        m.addAction("Delete profile…", self._delete_profile)
        m.addSeparator()
        m.addAction("Export profile…", self._export_profile)
        m.addAction("Import profile…", self._import_profile)
        m.addSeparator()
        m.addAction("Unlink from playthrough", self._unlink_playthrough)

    def _build_shortcuts(self) -> None:
        for key, slot in (
            (QKeySequence.New, self._new_profile),
            (QKeySequence("Ctrl+E"), self._export_profile),
            (QKeySequence("Ctrl+I"), self._import_profile),
            (QKeySequence.Quit, self.close),
            (QKeySequence.Refresh, self.watcher_sync),
            (QKeySequence.Find, lambda: (self.tabs.setCurrentIndex(0), self.search.setFocus(),
                                         self.search.selectAll())),
        ):
            act = QAction(self, shortcut=key)
            act.triggered.connect(slot)
            self.addAction(act)

    def _build_quests_tab(self) -> QWidget:
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_filters())

        self.model = QuestTableModel(self.profile, self.config.name_lang)
        self.table = QuestTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(26)
        hh = self.table.horizontalHeader()
        # The name column takes the spare width; long names wrap onto a second
        # line instead of being cut off.
        hh.setSectionResizeMode(QHeaderView.Fixed)  # sizes come from QuestTableView.fit()
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.ElideNone)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        hh.setHighlightSections(False)
        self.table.sortByColumn(COL_NAME, Qt.AscendingOrder)
        hh.sortIndicatorChanged.connect(lambda *_: self.table.fit())
        self.table.selectionModel().currentRowChanged.connect(self._on_row_changed)
        self.table.activated.connect(lambda idx: self.open_page(self.model.quest_at(idx.row())["id"]))
        self.table.doubleClicked.connect(lambda idx: self.open_page(self.model.quest_at(idx.row())["id"]))
        splitter.addWidget(self.table)

        splitter.addWidget(self._build_detail())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([238, 862, 300])
        return splitter

    def _build_filters(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(232)
        w.setMaximumWidth(260)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 8, 4)

        head = QHBoxLayout()
        head.addWidget(_section("Filters"))
        head.addStretch(1)
        self.clear_filters = QPushButton(objectName="ghost")
        self.clear_filters.setCursor(Qt.PointingHandCursor)
        self.clear_filters.setToolTip("Show all quests again")
        self.clear_filters.clicked.connect(self._reset_filters)
        head.addWidget(self.clear_filters)
        lay.addLayout(head)

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

        self.result_count = _muted()
        lay.addWidget(self.result_count)
        lay.addStretch(1)
        return w

    def _build_detail(self) -> QWidget:
        outer = QScrollArea(widgetResizable=True)
        outer.setMinimumWidth(280)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 4, 4, 4)
        lay.setSpacing(8)

        self.d_title = QLabel(objectName="questTitle", wordWrap=True)
        self.d_alt = _muted()
        self.d_meta = _muted()
        lay.addWidget(self.d_title)
        lay.addWidget(self.d_alt)
        lay.addWidget(self.d_meta)
        self.d_more = QPushButton("More details  ›", objectName="primary")
        self.d_more.setToolTip("Open the full quest page (double-click or Enter in the list)")
        self.d_more.clicked.connect(lambda: self._current_id and self.open_page(self._current_id))
        lay.addWidget(self.d_more)

        self.d_warning = QFrame(objectName="warning")
        wl = QVBoxLayout(self.d_warning)
        self.d_warning_text = QLabel(wordWrap=True)
        self.d_warning_text.setOpenExternalLinks(True)
        self.d_warning_text.setTextFormat(Qt.RichText)
        wl.addWidget(self.d_warning_text)
        lay.addWidget(self.d_warning)

        self.d_status_label = _section("Status")
        lay.addWidget(self.d_status_label)
        self.d_status = QWidget()
        grid = QGridLayout(self.d_status)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        self.status_group = QButtonGroup(self)
        self.status_buttons: dict[str, QPushButton] = {}
        short = {"not_started": "Not started", "in_progress": "In progress",
                 "completed": "Completed", "failed": "Failed / Missed"}
        for i, st in enumerate(STATUSES):
            b = QPushButton(short[st], objectName="statusButton", checkable=True)
            b.clicked.connect(lambda _=False, v=st: self._on_manual_status(v))
            self.status_group.addButton(b)
            self.status_buttons[st] = b
            grid.addWidget(b, i // 2, i % 2)
        lay.addWidget(self.d_status)
        eff = QHBoxLayout()
        self.d_effective = _muted()
        eff.addWidget(self.d_effective, 1)
        self.d_reset = QPushButton("use save status", objectName="linkButton")
        self.d_reset.setCursor(Qt.PointingHandCursor)
        self.d_reset.clicked.connect(lambda: self._on_manual_status(None))
        eff.addWidget(self.d_reset)
        lay.addLayout(eff)

        self.d_desc_label = _section("Description")
        lay.addWidget(self.d_desc_label)
        self.d_desc = QTextBrowser()
        self.d_desc.setMinimumHeight(140)
        lay.addWidget(self.d_desc, 2)

        self.d_notes_label = _section("Notes")
        lay.addWidget(self.d_notes_label)
        self.d_notes = QPlainTextEdit(objectName="notes", placeholderText="Write your notes here…")
        self.d_notes.setMinimumHeight(110)
        self.d_notes.textChanged.connect(self._on_notes_changed)
        lay.addWidget(self.d_notes, 1)

        self.d_ids = _muted()
        self.d_ids.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.d_ids)

        self.d_empty = _muted("Select a quest.")
        lay.addWidget(self.d_empty)
        outer.setWidget(w)
        self._detail_widgets = [self.d_title, self.d_alt, self.d_meta, self.d_more, self.d_status, self.d_effective,
                                self.d_desc, self.d_notes, self.d_ids, self.d_status_label, self.d_reset,
                                self.d_desc_label, self.d_notes_label]
        self._show_detail(None)
        return outer

    # ------------------------------------------------------------ save sync

    def _build_save_bar(self) -> QFrame:
        bar = QFrame(objectName="saveBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 6, 8, 6)
        self.s_thumb = QLabel(objectName="thumb")
        self.s_thumb.setFixedSize(112, 63)
        self.s_thumb.setScaledContents(True)
        lay.addWidget(self.s_thumb)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.s_title = QLabel()
        self.s_title.setTextFormat(Qt.RichText)
        self.s_info = _muted()
        self.s_warn = QLabel(wordWrap=True)
        self.s_warn.setStyleSheet(f"color: {theme.ACCENT_HI};")
        for w in (self.s_title, self.s_info, self.s_warn):
            text.addWidget(w)
        lay.addLayout(text, 1)
        folder = QToolButton(popupMode=QToolButton.InstantPopup, text="Save folder ▾")
        fm = QMenu(self)
        fm.addAction("Choose save folder…", self._choose_save_dir)
        fm.addAction("Use auto-detected folder", self._auto_save_dir)
        fm.addAction("Open in file manager", self._open_save_dir)
        folder.setMenu(fm)
        lay.addWidget(folder, 0, Qt.AlignTop)
        self._synced_timer = QTimer(self, interval=15_000)
        self._synced_timer.timeout.connect(self._update_save_bar)
        self._synced_timer.start()
        return bar

    def watcher_sync(self) -> None:
        self.watcher.force_sync()

    def _resolve_save_dir(self) -> Path | None:
        if self.config.save_dir:
            p = Path(self.config.save_dir).expanduser()
            return p if p.is_dir() else None
        dirs = find_save_dirs()
        with_saves = [d for d in dirs if savesync.list_saves(d)]
        return (with_saves or dirs or [None])[0]

    def _start_watching(self) -> None:
        directory = self._resolve_save_dir()
        self._sync_note = "" if directory else "No save folder found. Choose one via “Save folder…”."
        self.watcher.set_directory(directory)
        self._update_save_bar()

    def _on_snapshot(self, snap: SaveSnapshot) -> None:
        self._snapshot = snap
        self._apply_snapshot(snap)
        self.refresh_all()
        self._update_save_bar()
        self.statusBar().showMessage(f"Synced {snap.path.name}", 5000)

    def _apply_snapshot(self, snap: SaveSnapshot) -> None:
        result = savesync.apply_snapshot(self.profile, self.db, snap)
        self._snapshot_applied = result.applied
        notes = list(snap.warnings)
        if not result.applied:
            notes.append(result.reason)
        else:
            self._persist()
            new = savesync.log_unknown(self.unknown_log_path(), snap, result.unknown)
            if result.unknown:
                notes.append(f"{len(result.unknown)} quest(s) in the save are not in quests.json"
                             f" ({new} newly logged).")
        if snap.skipped:
            notes.append(f"Skipped {len(snap.skipped)} newer save(s) from an unsupported game version.")
        self._sync_note = " ".join(notes)

    def _on_sync_failed(self, msg: str) -> None:
        self._sync_note = msg
        self._update_save_bar()
        self.statusBar().showMessage(msg, 8000)

    def _update_save_bar(self) -> None:
        snap = self._snapshot
        directory = self.watcher.directory
        if snap is None:
            self.s_thumb.clear()
            self.s_title.setText("<b>No save loaded</b>")
            where = str(directory) if directory else "—"
            self.s_info.setText(f"Folder: {where} · watcher: {self.watcher.backend}")
        else:
            self.s_thumb.setPixmap(QPixmap(str(snap.thumbnail)) if snap.thumbnail else QPixmap())
            stamp = time.strftime("%d.%m.%Y %H:%M", time.localtime(snap.mtime))
            self.s_title.setText(f"<b>{snap.path.name}</b> &nbsp; <span style='color:{theme.MUTED}'>{stamp}</span>")
            parts = []
            if snap.meta.get("player_level") is not None:
                parts.append(f"Level {snap.meta['player_level']}")
            if snap.meta.get("region"):
                parts.append(snap.meta["region"])
            last = self.profile.last_save or {}
            if last.get("file") == snap.path.name and last.get("synced"):
                ago = int(time.time() - last["synced"])
                parts.append("synced just now" if ago < 60 else
                             f"last synced {time.strftime('%H:%M:%S', time.localtime(last['synced']))}")
            parts.append(f"priority: {'save' if self.profile.priority == 'save' else 'manual edits'}")
            self.s_info.setText(" · ".join(parts))
        self.s_warn.setText(self._sync_note)
        self.s_warn.setVisible(bool(self._sync_note))

    def _choose_save_dir(self) -> None:
        # Qt's own dialog: it can show the .sav files inside folders (a plain
        # directory picker shows only subfolders, so gamesaves looks empty) and
        # hidden folders such as ~/.local and ~/.steam.
        dlg = QFileDialog(self, "Choose Witcher 3 save folder (gamesaves)")
        dlg.setFileMode(QFileDialog.Directory)
        dlg.setOption(QFileDialog.ShowDirsOnly, False)
        dlg.setOption(QFileDialog.DontUseNativeDialog, True)
        dlg.setFilter(QDir.AllDirs | QDir.Files | QDir.Hidden | QDir.NoDotAndDotDot)
        dlg.setNameFilter("Witcher 3 saves (*.sav)")
        start = self.watcher.directory or Path.home()
        dlg.setDirectory(str(start))
        detected = [QUrl.fromLocalFile(str(d)) for d in find_save_dirs()]
        dlg.setSidebarUrls([QUrl.fromLocalFile(str(Path.home()))] + detected)
        dlg.resize(1000, 600)
        dlg.setViewMode(QFileDialog.Detail)
        for view in dlg.findChildren(QTreeView):
            view.header().setSectionResizeMode(QHeaderView.ResizeToContents)
            view.header().setSectionResizeMode(0, QHeaderView.Stretch)
            view.header().setStretchLastSection(False)
        for splitter in dlg.findChildren(QSplitter):
            splitter.setSizes([220, 780])
        if not dlg.exec() or not dlg.selectedFiles():
            return
        path = dlg.selectedFiles()[0]
        if Path(path).is_file():  # a .sav was picked: use its folder
            path = str(Path(path).parent)
        if path:
            self.config.save_dir = path
            self.config.save()
            self._snapshot = None
            self._start_watching()

    def _open_save_dir(self) -> None:
        if self.watcher.directory:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.watcher.directory)))
        else:
            QMessageBox.information(self, "Save folder", "No save folder is set.")

    def _auto_save_dir(self) -> None:
        self.config.save_dir = None
        self.config.save()
        self._snapshot = None
        self._start_watching()

    def _unlink_playthrough(self) -> None:
        self.profile.playthrough_id = None
        self.profile.save_status = {}
        self._persist()
        self.statusBar().showMessage("Profile unlinked; it will follow the next synced save.", 5000)
        self.watcher.sync_now()
        self.refresh_all()

    @staticmethod
    def unknown_log_path() -> Path:
        return paths.data_dir() / "unknown_quests.log"

    def _show_unknown_log(self) -> None:
        path = self.unknown_log_path()
        if not path.is_file():
            QMessageBox.information(self, "Unknown quests", "No unknown quests have been logged.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

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
        self.table.fit_name_column()
        self.result_count.setText(f"{len(rows)} of {len(self.db.quests)} shown")
        c = self.criteria()
        active = sum(bool(x) for x in (c.text, c.categories, c.regions, c.expansions, c.statuses,
                                         c.missable_only)) + (c.level_min is not None or c.level_max is not None)
        self.clear_filters.setText(f"✕ Clear ({active})")
        self.clear_filters.setVisible(active > 0)
        self._reselect()

    def refresh_all(self) -> None:
        self.model.set_profile(self.profile, self.config.name_lang)
        self.apply_filters()
        self._refresh_overall()
        # the overview tabs are rebuilt lazily, when they are actually shown
        self._views_dirty = True
        self._refresh_visible_tab()
        self._show_detail(self.db.by_id.get(self._current_id) if self._current_id else None)
        if self.stack.currentWidget() is self.page and self.page.quest:
            self.page.show_quest(self.db.by_id[self.page.quest["id"]], self.db, self.profile,
                                 self.config.name_lang, self._entry_status())

    def _refresh_visible_tab(self) -> None:
        if not getattr(self, "_views_dirty", True):
            return
        current = self.tabs.currentWidget()
        if current is self.progress_tab:
            self._build_progress_view()
        elif current is self.ponr_tab:
            self._build_ponr_view()
        else:
            return
        self._views_dirty = False

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
            "Each entry is backed by the linked web sources; none of it is read from the game files."))
        lang = self.config.name_lang
        for p in self.db.points_of_no_return:
            q = self.db.by_id[p["quest_id"]]
            status = self.profile.status(q["id"])
            box = QGroupBox(f"{filtering.display_name(q, lang)}  —  {STATUS_LABELS[status]}")
            bl = QVBoxLayout(box)
            when = "starting" if p.get("trigger") == "start" else "completing"
            effect = QLabel(f"<b>Triggered by {when} this quest.</b> {p['effect']}<br>{self._sources_html(p)}",
                            wordWrap=True)
            effect.setOpenExternalLinks(True)
            bl.addWidget(effect)
            missables = self.db.missables_for(q["id"])
            open_ = [m for m in missables if self.profile.status(m["id"]) not in filtering.DONE]
            passed = filtering.ponr_passed(self.profile, p)
            if open_ and not passed:
                warn = QFrame(objectName="warning")
                QVBoxLayout(warn).addWidget(QLabel(
                    f"<b>{len(open_)} missable quest(s) still open.</b> Finish them before {when} this quest.",
                    wordWrap=True))
                bl.addWidget(warn)
            missed = [m for m in open_ if passed]
            if missed:
                bl.addWidget(QLabel(
                    f"<span style='color:{theme.ACCENT_HI}'>Point passed: {len(missed)} quest(s) below were "
                    "probably missed.</span>", wordWrap=True))
            for m in missables:
                ms = self.profile.status(m["id"])
                color = theme.ACCENT_HI if ms not in filtering.DONE else theme.MUTED
                icon = {"completed": "✓", "failed": "✗"}.get(ms, "✗" if passed else "⚠")
                link = QLabel(
                    f'<a href="{m["id"]}" style="color:{color}; text-decoration:none">'
                    f'{icon} {filtering.display_name(m, lang)}</a>'
                    f'  <span style="color:{theme.MUTED}">({STATUS_LABELS[ms]}{", probably missed" if passed and ms not in filtering.DONE else ""})'
                    f' — {m.get("missable_reason") or ""}</span>')
                link.setWordWrap(True)
                link.linkActivated.connect(self.select_quest)
                bl.addWidget(link)
            lay.addWidget(box)
        lay.addStretch(1)
        self.ponr_tab.setWidget(w)

    @staticmethod
    def _sources_html(entry: dict) -> str:
        from urllib.parse import urlparse
        links = [f'<a href="{u}" style="color:{theme.MUTED}">{urlparse(u).netloc.removeprefix("www.")}</a>'
                 for u in entry.get("sources", [])]
        return f'<span style="color:{theme.MUTED}">Sources: {", ".join(links) or "none"}</span>'

    # ------------------------------------------------------------ quest page

    def _entry_status(self) -> dict[str, str] | None:
        """Journal entry states of the synced save, if it belongs to this profile."""
        if self._snapshot is not None and self._snapshot_applied:
            return self._snapshot.entry_status
        return None

    def open_page(self, quest_id: str) -> None:
        q = self.db.by_id.get(quest_id)
        if q is None:
            return
        self._flush_note()
        self._current_id = quest_id
        self.page.show_quest(q, self.db, self.profile, self.config.name_lang, self._entry_status())
        self.top_area.hide()
        self.stack.setCurrentWidget(self.page)
        self.page.setFocus()

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.MouseButtonPress and event.button() == Qt.BackButton
                and self.stack.currentWidget() is self.page):
            self.page.go_back()
            return True
        return super().eventFilter(obj, event)

    def close_page(self) -> None:
        self.top_area.show()
        self.stack.setCurrentWidget(self.tabs)
        self.refresh_all()
        self._reselect()
        self.table.setFocus()

    def _on_page_status(self, quest_id: str, status: str | None) -> None:
        self.profile.set_manual(quest_id, status)
        self._persist()
        self.refresh_all()

    def _on_page_note(self, quest_id: str, text: str) -> None:
        self.profile.set_note(quest_id, text)
        self._persist()

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
                if q.get("note"):
                    text += f'<br><span style="color:{theme.MUTED}">{q["note"]}</span>'
                text += "<br>" + self._sources_html(q)
                self.d_warning_text.setText(text)
            manual = self.profile.manual_status.get(q["id"])
            saved = self.profile.save_status.get(q["id"])
            eff = self.profile.status(q["id"])
            self.status_buttons[eff].setChecked(True)
            src = f"From save: {STATUS_LABELS[saved] if saved else '—'}"
            if manual:
                src += f" · set by hand: {STATUS_LABELS[manual]}"
            self.d_effective.setText(src)
            self.d_reset.setVisible(manual is not None)
            desc = q.get("description_de") if lang == "de" else q.get("description")
            # Game texts contain simple markup such as <br>.
            self.d_desc.setHtml(desc or q.get("description") or "<i>No description in the game files.</i>")
            self.d_notes.setPlainText(self.profile.notes.get(q["id"], ""))
            self.d_ids.setText(f"{q['id']} · {q['save_ids']['guid']}")
        finally:
            self._loading_detail = False

    def _on_manual_status(self, status: str | None) -> None:
        if not self._current_id:
            return
        self.profile.set_manual(self._current_id, status)
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
        self.profile_btn.setText(f"{self.profile.name} ▾")
        self.priority_actions[self.profile.priority].setChecked(True)
        self.config.active_profile = self.profile.name
        self.config.save()

    def _set_profile(self, profile: Profile) -> None:
        self._flush_note()
        self.profile = profile
        self._reload_profiles()
        if self._snapshot is not None:
            self._apply_snapshot(self._snapshot)
        self.refresh_all()
        self._update_save_bar()

    def _switch_profile(self, name: str) -> None:
        if name and name != self.profile.name:
            self._set_profile(self.store.load(name))

    def _change_priority(self, value: str) -> None:
        self.profile.priority = value
        self._persist()
        self.refresh_all()

    def _change_lang(self, value: str) -> None:
        self.config.name_lang = value
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
        QApplication.instance().removeEventFilter(self)
        self.watcher.shutdown()
        self._flush_note()
        self._persist()
        super().closeEvent(event)


def profiles_dir() -> Path:
    return paths.data_dir() / "profiles"
