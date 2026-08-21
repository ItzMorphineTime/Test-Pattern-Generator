"""Background export worker so the UI never blocks during encoding."""

from __future__ import annotations

import copy

from PySide6.QtCore import QObject, Signal, Slot

from ..core import encoder
from ..core.config import ProjectConfig


class RenderWorker(QObject):
    """Runs :func:`encoder.encode` on a worker thread.

    Emits ``progress(done, total)`` per frame, then ``finished(path)`` or
    ``failed(message)``.  ``cancel()`` requests an early, cooperative stop.
    """

    progress = Signal(int, int)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, config: ProjectConfig):
        super().__init__()
        self._config = copy.deepcopy(config)
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        try:
            path = encoder.encode(
                self._config,
                progress=lambda done, total: self.progress.emit(done, total),
                cancel=lambda: self._cancelled,
            )
        except Exception as exc:  # noqa: BLE001 - report any failure to the UI
            self.failed.emit(str(exc))
            return
        if self._cancelled:
            self.failed.emit("Export cancelled.")
        else:
            self.finished.emit(str(path))
