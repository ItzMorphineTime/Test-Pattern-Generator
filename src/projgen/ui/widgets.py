"""Small reusable widgets and layout helpers for the control panel."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..core.config import OutputConfig
from ..core.encoder import FORMAT_PRESETS


class ColorButton(QPushButton):
    """A button whose face shows the current colour; click to pick a new one."""

    changed = Signal(tuple)  # (r, g, b) floats in [0, 1]

    def __init__(self, rgb=(1.0, 1.0, 1.0), parent=None):
        super().__init__(parent)
        self._rgb = tuple(rgb)
        self.setFixedSize(48, 24)
        self.clicked.connect(self._pick)
        self._refresh()

    def rgb(self) -> tuple[float, float, float]:
        return self._rgb

    def set_rgb(self, rgb) -> None:
        self._rgb = tuple(rgb)
        self._refresh()

    def _pick(self) -> None:
        initial = QColor.fromRgbF(*self._rgb)
        chosen = QColorDialog.getColor(initial, self, "Select colour")
        if chosen.isValid():
            self._rgb = (chosen.redF(), chosen.greenF(), chosen.blueF())
            self._refresh()
            self.changed.emit(self._rgb)

    def _refresh(self) -> None:
        r, g, b = (int(round(c * 255)) for c in self._rgb)
        self.setStyleSheet(
            f"background-color: rgb({r},{g},{b}); border: 1px solid #555; border-radius: 4px;"
        )


def int_spin(minimum: int, maximum: int, value: int, step: int = 1,
             suffix: str = "") -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(minimum, maximum)
    spin.setSingleStep(step)
    spin.setValue(value)
    if suffix:
        spin.setSuffix(suffix)
    return spin


def float_spin(minimum: float, maximum: float, value: float, step: float = 0.05,
               decimals: int = 2, suffix: str = "") -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setSingleStep(step)
    spin.setDecimals(decimals)
    spin.setValue(value)
    if suffix:
        spin.setSuffix(suffix)
    return spin


def row(*widgets) -> QWidget:
    """Lay widgets (or label strings) out side by side, flush with the form."""
    wrap = QWidget()
    layout = QHBoxLayout(wrap)
    layout.setContentsMargins(0, 0, 0, 0)
    for item in widgets:
        layout.addWidget(QLabel(item) if isinstance(item, str) else item)
    return wrap


class OutputGroup(QGroupBox):
    """Resolution, frame rate, duration and format controls for an OutputConfig.

    Emits ``changed(attr, value)`` for the owner to apply. ``frames_label`` is a
    summary line the owner keeps current, and ``form`` takes extra rows.
    """

    changed = Signal(str, object)

    def __init__(self, output: OutputConfig, title: str = "Output", parent=None):
        super().__init__(title, parent)
        self.form = QFormLayout(self)

        width = int_spin(2, 65536, output.width, 2, " px")
        height = int_spin(2, 65536, output.height, 2, " px")
        fps = float_spin(1.0, 240.0, output.fps, 1.0, 3, " fps")
        duration = float_spin(0.1, 3600.0, output.duration, 0.5, 2, " s")
        self.preset = QComboBox()
        for key, preset in sorted(FORMAT_PRESETS.items()):
            self.preset.addItem(preset.label, key)
        self.preset.setCurrentIndex(self.preset.findData(output.preset))

        width.valueChanged.connect(lambda v: self.changed.emit("width", v))
        height.valueChanged.connect(lambda v: self.changed.emit("height", v))
        fps.valueChanged.connect(lambda v: self.changed.emit("fps", v))
        duration.valueChanged.connect(lambda v: self.changed.emit("duration", v))
        self.preset.currentIndexChanged.connect(
            lambda _i: self.changed.emit("preset", self.preset.currentData()))

        self.frames_label = QLabel()
        # Wrapping stops a long summary from widening the panel past the sidebar.
        self.frames_label.setWordWrap(True)
        self.form.addRow("Resolution", row(width, "x", height))
        self.form.addRow("Frame rate", fps)
        self.form.addRow("Duration", duration)
        self.form.addRow("Format", self.preset)
        self.form.addRow("Frames", self.frames_label)


def control_panel() -> tuple[QWidget, QVBoxLayout]:
    """An empty settings panel and the layout to stack groups into."""
    panel = QWidget()
    panel.setObjectName("controlPanel")
    layout = QVBoxLayout(panel)
    # Extra right margin keeps fields clear of the vertical scrollbar.
    layout.setContentsMargins(12, 12, 18, 12)
    layout.setSpacing(12)
    return panel, layout


def split_page(controls: QWidget, preview: QWidget,
               footer: QWidget) -> tuple[QSplitter, QScrollArea]:
    """Scrollable controls on the left; the preview over a footer on the right."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(controls)
    scroll.setMinimumWidth(420)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    right = QWidget()
    right.setMinimumWidth(420)
    layout = QVBoxLayout(right)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(preview, 1)
    layout.addWidget(footer)

    splitter = QSplitter()
    splitter.addWidget(scroll)
    splitter.addWidget(right)
    splitter.setStretchFactor(0, 0)
    splitter.setStretchFactor(1, 1)
    splitter.setCollapsible(0, False)
    splitter.setChildrenCollapsible(False)
    splitter.setSizes([660, 800])
    return splitter, scroll
