"""Background export worker so the UI never blocks during encoding."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal, Slot

from ..core.encoder import CancelFn, ProgressFn

ExportJob = Callable[[ProgressFn, CancelFn], Path]
CANCELLED = "Export cancelled."


class RenderWorker(QObject):
    """Runs an export job on a worker thread.

    The job is called as ``job(progress, cancel)`` and returns the written path;
    it should work from its own config snapshot so later UI edits can't leak in.
    Emits ``progress(done, total)`` per frame, then ``finished(path)`` or
    ``failed(message)``.  ``cancel()`` requests an early, cooperative stop.
    """

    progress = Signal(int, int)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, job: ExportJob):
        super().__init__()
        self._job = job
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        try:
            path = self._job(
                lambda done, total: self.progress.emit(done, total),
                lambda: self._cancelled,
            )
        except Exception as exc:  # noqa: BLE001 - report any failure to the UI
            self.failed.emit(str(exc))
            return
        if self._cancelled:
            self.failed.emit(CANCELLED)
        else:
            self.finished.emit(str(path))
