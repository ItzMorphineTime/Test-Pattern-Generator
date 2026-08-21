"""Small reusable widgets and layout helpers for the control panel."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QDoubleSpinBox,
    QPushButton,
    QSpinBox,
)


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
