"""Watch the save folder and load the newest save in a background thread.

Uses watchdog (inotify) when installed, otherwise Qt's QFileSystemWatcher,
which is inotify-backed on Linux as well. A slow poll runs in both cases as
a safety net.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from .savesync import NotReady, SaveSnapshot, list_saves, newest_snapshot

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:  # optional dependency
    Observer = None
    FileSystemEventHandler = object

DEBOUNCE_MS = 1500
RETRY_MS = 2000
MAX_RETRIES = 8
POLL_MS = 30_000
RELEVANT = (".sav", ".png", ".json")


class _Job(QRunnable):
    def __init__(self, watcher: "SaveWatcher", directory: Path, generation: int):
        super().__init__()
        self.watcher, self.directory, self.generation = watcher, directory, generation

    def run(self):
        try:
            snap = newest_snapshot(self.directory)
        except NotReady as e:
            self.watcher._not_ready.emit(self.generation, str(e))
            return
        except Exception as e:  # never let a worker crash the app
            self.watcher._error.emit(self.generation, f"Could not read saves: {e}")
            return
        self.watcher._done.emit(self.generation, snap)


# Only events that mean "a file changed". Opening and closing without writing
# must be ignored: our own reads produce them and would loop forever.
CHANGE_EVENTS = {"created", "modified", "moved", "deleted", "closed"}


class _Handler(FileSystemEventHandler):
    def __init__(self, watcher: "SaveWatcher"):
        self.watcher = watcher

    def on_any_event(self, event):
        if event.is_directory or event.event_type not in CHANGE_EVENTS:
            return
        path = getattr(event, "dest_path", "") or event.src_path
        if str(path).lower().endswith(RELEVANT):
            self.watcher._fs_event.emit()


class SaveWatcher(QObject):
    snapshot_ready = Signal(object)   # SaveSnapshot
    failed = Signal(str)
    busy = Signal(str)                # human-readable progress text

    _fs_event = Signal()
    _done = Signal(int, object)
    _not_ready = Signal(int, str)
    _error = Signal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.directory: Path | None = None
        self.backend = "watchdog" if Observer else "qt"
        self._observer = None
        self._qt_watcher = None
        self._running = False
        self._pending = False
        self._generation = 0  # bumped on stop(); results of older jobs are dropped
        self._retries = 0
        self._last_seen: tuple[str, float, int] | None = None
        self._force = False
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)

        self._debounce = QTimer(self, singleShot=True, interval=DEBOUNCE_MS)
        self._debounce.timeout.connect(self.sync_now)
        self._retry = QTimer(self, singleShot=True, interval=RETRY_MS)
        self._retry.timeout.connect(self.sync_now)
        self._poll = QTimer(self, interval=POLL_MS)
        self._poll.timeout.connect(self._poll_check)

        self._fs_event.connect(self._debounce.start)
        self._done.connect(self._on_done)
        self._not_ready.connect(self._on_not_ready)
        self._error.connect(self._on_error)

    def set_directory(self, directory: Path | None) -> None:
        self.stop()
        self.directory = directory
        if directory is None or not directory.is_dir():
            return
        if Observer is not None:
            self._observer = Observer()
            self._observer.schedule(_Handler(self), str(directory), recursive=False)
            self._observer.daemon = True
            self._observer.start()
        else:
            from PySide6.QtCore import QFileSystemWatcher
            self._qt_watcher = QFileSystemWatcher([str(directory)], self)
            self._qt_watcher.directoryChanged.connect(self._debounce.start)
        self._poll.start()
        self.sync_now()

    def stop(self) -> None:
        self._generation += 1
        self._last_seen = None
        self._running = False
        self._pending = False
        self._retries = 0
        self._poll.stop()
        self._debounce.stop()
        self._retry.stop()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None
        if self._qt_watcher is not None:
            self._qt_watcher.deleteLater()
            self._qt_watcher = None

    @Slot()
    def force_sync(self) -> None:
        """Reload and re-emit even if the newest save has not changed."""
        self._force = True
        self.sync_now()

    @Slot()
    def sync_now(self) -> None:
        if self.directory is None:
            return
        if self._running:
            self._pending = True
            return
        self._running = True
        self.busy.emit("Reading newest save…")
        self._pool.start(_Job(self, self.directory, self._generation))

    def _finish(self) -> None:
        self._running = False
        if self._pending:
            self._pending = False
            self.sync_now()

    def _on_done(self, generation: int, snap: SaveSnapshot | None) -> None:
        if generation != self._generation:
            return
        self._retries = 0
        self._finish()
        if snap is None:
            self.failed.emit("No usable save found in the save folder.")
            return
        try:
            key = (snap.path.name, snap.mtime, snap.path.stat().st_size)
        except OSError:
            key = (snap.path.name, snap.mtime, -1)
        force, self._force = self._force, False
        if key == self._last_seen and not force:
            self.busy.emit("")
            return  # nothing new; do not refresh the UI
        self._last_seen = key
        self.snapshot_ready.emit(snap)

    def _on_error(self, generation: int, msg: str) -> None:
        if generation != self._generation:
            return
        self._finish()
        self.failed.emit(msg)

    def _on_not_ready(self, generation: int, msg: str) -> None:
        if generation != self._generation:
            return
        self._finish()
        self._retries += 1
        if self._retries > MAX_RETRIES:
            self._retries = 0
            self.failed.emit(f"Newest save could not be read: {msg}")
            return
        self.busy.emit("Game is still writing the save, retrying…")
        self._retry.start()

    def _poll_check(self) -> None:
        if self.directory is None or self._running:
            return
        saves = list_saves(self.directory)
        if saves:
            st = saves[0].stat()
            if (saves[0].name, st.st_mtime, st.st_size) != self._last_seen:
                self.sync_now()
