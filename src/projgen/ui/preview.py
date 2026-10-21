"""Live preview widget: a scrubber + play control over rendered frames."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

PREVIEW_MAX = 720  # longest preview edge in px, for responsiveness


def numpy_to_qimage(frame: np.ndarray) -> QImage:
    """Wrap a contiguous ``(H, W, 3)`` uint8 array as an RGB888 QImage (owned copy)."""
    frame = np.ascontiguousarray(frame)
    h, w = frame.shape[:2]
    return QImage(frame.data, w, h, 3 * w, QImage.Format_RGB888).copy()


class PreviewWidget(QWidget):
    """Shows one rendered frame, with a scrub slider and a play/pause toggle."""

    frameChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._renderer = None  # anything with render(index) -> (H, W, 3) uint8
        self._total = 1
        self._index = 0
        self._playing = False

        self._image = QLabel("Preview", alignment=Qt.AlignCenter)
        self._image.setMinimumSize(360, 240)
        self._image.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._image.setObjectName("previewCanvas")

        self._play_btn = QPushButton("Play")
        self._play_btn.setFixedWidth(72)
        self._play_btn.clicked.connect(self.toggle_play)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.valueChanged.connect(self._on_slider)

        self._counter = QLabel("0 / 0")
        self._counter.setFixedWidth(90)
        self._counter.setAlignment(Qt.AlignCenter)

        controls = QHBoxLayout()
        controls.addWidget(self._play_btn)
        controls.addWidget(self._slider, 1)
        controls.addWidget(self._counter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._image, 1)
        layout.addLayout(controls)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)

    # -- public API ------------------------------------------------------
    def set_renderer(self, renderer, total: int, fps: float = 25.0) -> None:
        self._renderer = renderer
        self._total = max(1, total)
        self._fps = max(1.0, min(60.0, fps))
        self._index = min(self._index, self._total - 1)
        blocked = self._slider.blockSignals(True)
        self._slider.setRange(0, self._total - 1)
        self._slider.setValue(self._index)
        self._slider.blockSignals(blocked)
        if self._playing:
            self._timer.start(int(1000 / self._fps))
        self._render_current()

    def toggle_play(self) -> None:
        self._playing = not self._playing
        self._play_btn.setText("Pause" if self._playing else "Play")
        if self._playing and self._renderer is not None:
            self._timer.start(int(1000 / getattr(self, "_fps", 25.0)))
        else:
            self._timer.stop()

    def pause(self) -> None:
        if self._playing:
            self.toggle_play()

    # -- internals -------------------------------------------------------
    def _advance(self) -> None:
        if self._total <= 1:
            return
        self._slider.setValue((self._index + 1) % self._total)

    def _on_slider(self, value: int) -> None:
        self._index = value
        self._render_current()
        self.frameChanged.emit(value)

    def _render_current(self) -> None:
        if self._renderer is None:
            return
        frame = self._renderer.render(self._index)
        pixmap = QPixmap.fromImage(numpy_to_qimage(frame))
        self._image.setPixmap(
            pixmap.scaled(self._image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        self._counter.setText(f"{self._index + 1} / {self._total}")

    def resizeEvent(self, event):  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._render_current()
