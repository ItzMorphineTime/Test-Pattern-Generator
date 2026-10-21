"""Output path and export controls that run a job on a background thread."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Callable

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.encoder import FormatPreset
from .render_worker import CANCELLED, ExportJob, RenderWorker


class ExportBar(QWidget):
    """Output path field, progress bar, and Export / Cancel buttons.

    The owner supplies ``get_preset()`` for the current format, ``validate()``
    returning a list of problems, ``make_job()`` returning an export job over a
    config snapshot, and optionally ``describe_result(path)`` for the message
    shown when the export completes.
    """

    path_edited = Signal(str)

    def __init__(self, path: str, *, get_preset: Callable[[], FormatPreset],
                 validate: Callable[[], list[str]],
                 make_job: Callable[[], ExportJob],
                 describe_result: Callable[[str], str] | None = None,
                 parent=None):
        super().__init__(parent)
        self._get_preset = get_preset
        self._validate = validate
        self._make_job = make_job
        self._describe = describe_result or (lambda p: f"Saved to:\n{p}")
        self._worker: RenderWorker | None = None
        self._thread: QThread | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(path)
        self.path_edit.textChanged.connect(self.path_edited)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse)
        path_row.addWidget(QLabel("Output"))
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        layout.addLayout(path_row)

        action_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.export_btn = QPushButton("Export Video")
        self.export_btn.setObjectName("primary")
        self.export_btn.clicked.connect(self._start)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.hide()
        action_row.addWidget(self.progress, 1)
        action_row.addWidget(self.cancel_btn)
        action_row.addWidget(self.export_btn)
        layout.addLayout(action_row)

    # -- public ----------------------------------------------------------
    def set_path(self, text: str) -> None:
        self.path_edit.setText(text)

    @property
    def busy(self) -> bool:
        return self._thread is not None

    def shutdown(self) -> None:
        """Cancel any running export and wait for its thread to finish."""
        if self._worker is not None:
            self._worker.cancel()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None

    # -- internals -------------------------------------------------------
    def _status(self, message: str, timeout: int = 0) -> None:
        window = self.window()
        if isinstance(window, QMainWindow):
            window.statusBar().showMessage(message, timeout)

    def _browse(self) -> None:
        preset = self._get_preset()
        if preset.is_sequence:
            path = QFileDialog.getExistingDirectory(self, "Choose output folder")
            if path:
                self.path_edit.setText(os.path.join(path, "frame"))
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Export as", self.path_edit.text(),
                f"Video (*{preset.extension})")
            if path:
                self.path_edit.setText(path)

    def _start(self) -> None:
        problems = self._validate()
        if problems:
            QMessageBox.warning(self, "Cannot export", "\n".join(problems))
            return

        self._worker = RenderWorker(self._make_job())
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        self.export_btn.setEnabled(False)
        self.cancel_btn.show()
        self.progress.setValue(0)
        self._status("Exporting...")
        self._thread.start()

    def _cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._status("Cancelling...")

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(done)

    def _on_finished(self, path: str) -> None:
        self._teardown()
        self._status(f"Exported {path}", 8000)
        result = QMessageBox.information(
            self, "Export complete", self._describe(path),
            QMessageBox.Open | QMessageBox.Ok)
        if result == QMessageBox.Open:
            self._open_in_explorer(path)

    def _on_failed(self, message: str) -> None:
        self._teardown()
        self.progress.setValue(0)
        self._status(message, 6000)
        if message != CANCELLED:
            QMessageBox.critical(self, "Export failed", message)

    def _teardown(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None
        self.export_btn.setEnabled(True)
        self.cancel_btn.hide()

    @staticmethod
    def _open_in_explorer(path: str) -> None:
        target = path if os.path.isdir(path) else (os.path.dirname(path) or ".")
        try:
            if sys.platform == "win32":
                os.startfile(target)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.run(["open", target], check=False)
            else:
                subprocess.run(["xdg-open", target], check=False)
        except OSError:
            pass
