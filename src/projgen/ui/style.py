"""Morph brand theme for the desktop app.

Colours follow the Morph Brand System V2 in dark mode, which the brand directs
for control surfaces: Morph Black surfaces and Studio White text, Signal Red
for motion (progress, focus, the active tab, the played part of the scrubber)
and Pivot Gold for the single decisive action on a page (Export). The brand
defines no UI-state colours, so hover, border and secondary-text tones are
tints of Studio White over Morph Black rather than new hues.
"""

from __future__ import annotations

from string import Template

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ..resources import resource_path

MORPH_BLACK = "#0A0A0A"  # color/logo/black
STUDIO_WHITE = "#FFFFFF"  # color/logo/studio-white
SIGNAL_RED = "#C51622"  # color/logo/signal-red
PIVOT_GOLD = "#F2B705"  # color/logo/pivot-gold
PIVOT_GOLD_HOVER = "#F4C22A"  # Pivot Gold with a 15% Studio White tint

FONT_FAMILY = "Montserrat"
FONT_FILES = ("Montserrat-Regular.ttf", "Montserrat-SemiBold.ttf")


def _white(alpha: float) -> str:
    return f"rgba(255, 255, 255, {alpha})"


def _ui_image(name: str) -> str:
    # Qt stylesheets can't draw triangles from borders, so arrows are images;
    # Qt picks up the @2x files automatically on high-DPI screens.
    return resource_path("ui", name).as_posix()


TOKENS = {
    "chevron_up": _ui_image("chevron-up.png"),
    "chevron_down": _ui_image("chevron-down.png"),
    "chevron_up_off": _ui_image("chevron-up-disabled.png"),
    "chevron_down_off": _ui_image("chevron-down-disabled.png"),
    "black": MORPH_BLACK,
    "white": STUDIO_WHITE,
    "red": SIGNAL_RED,
    "gold": PIVOT_GOLD,
    "gold_hover": PIVOT_GOLD_HOVER,
    "font": FONT_FAMILY,
    "text2": _white(0.72),  # secondary text
    "text3": _white(0.38),  # disabled text
    "line": _white(0.14),  # card edges and dividers
    "line2": _white(0.22),  # scrollbar and slider tracks
    "edge": _white(0.30),  # input and button outlines
    "edge_hover": _white(0.55),
    "fill": _white(0.05),  # input fill
    "fill2": _white(0.08),  # spin-box buttons
    "hover": _white(0.10),
    "press": _white(0.16),
}


def load_brand_fonts() -> bool:
    """Register the bundled Montserrat faces with Qt; True if any loaded."""
    loaded = False
    for name in FONT_FILES:
        path = resource_path("fonts", name)
        if path.exists() and QFontDatabase.addApplicationFont(str(path)) != -1:
            loaded = True
    return loaded


def svg_pixmap(path, width: int, device_pixel_ratio: float = 1.0) -> QPixmap:
    """Render an SVG logo at `width` logical pixels, crisp on high-DPI screens."""
    renderer = QSvgRenderer(str(path))
    size = renderer.defaultSize()
    height = round(width * size.height() / max(1, size.width()))
    pixmap = QPixmap(round(width * device_pixel_ratio), round(height * device_pixel_ratio))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(device_pixel_ratio)
    return pixmap


_QSS = Template("""
* { font-family: "$font"; font-size: 13px; }
QWidget { background-color: $black; color: $white; }
QMainWindow, QScrollArea, QStackedWidget, #controlPanel { background-color: $black; }
QLabel { background: transparent; }
QLabel#hint { color: $text2; padding: 0 2px; }
QToolTip { background-color: $black; color: $white; border: 1px solid $edge; padding: 6px; }

/* Header: wordmark, tool tabs, presets. */
#header { background-color: $black; border-bottom: 1px solid $line; }
QTabBar#mainTabs { background: transparent; }
QTabBar#mainTabs::tab {
    background: transparent;
    color: $text2;
    font-size: 14px;
    font-weight: 600;
    padding: 8px 2px 7px 2px;
    margin-right: 28px;
    border: 0;
    border-bottom: 3px solid transparent;
}
QTabBar#mainTabs::tab:selected { color: $white; border-bottom: 3px solid $red; }
QTabBar#mainTabs::tab:hover:!selected { color: $white; }

/* Settings cards. */
QGroupBox {
    border: 1px solid $line;
    border-radius: 10px;
    margin-top: 16px;
    padding: 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: $white;
}
QGroupBox::indicator { width: 16px; height: 16px; }
QCheckBox::indicator:unchecked, QGroupBox::indicator:unchecked {
    border: 1px solid $edge_hover;
    border-radius: 3px;
    background: $fill;
}
QCheckBox:disabled { color: $text3; }

/* Fields. */
QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit {
    background-color: $fill;
    border: 1px solid $edge;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 24px;
    selection-background-color: $red;
    selection-color: $white;
}
QSpinBox, QDoubleSpinBox { padding-right: 22px; }
QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover, QLineEdit:hover { border-color: $edge_hover; }
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QLineEdit:focus { border: 1px solid $red; }
QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled, QLineEdit:disabled {
    color: $text3;
    border-color: $line;
}
QComboBox::drop-down { border: 0; width: 24px; }
QComboBox::down-arrow { image: url("$chevron_down"); width: 8px; height: 5px; margin-right: 8px; }
QComboBox::down-arrow:disabled { image: url("$chevron_down_off"); }
QComboBox QAbstractItemView {
    background-color: $black;
    border: 1px solid $edge;
    selection-background-color: $red;
    selection-color: $white;
    outline: 0;
}

/* Explicit step-button geometry keeps them flush, clickable, and clear of the text. */
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    border-left: 1px solid $edge;
    border-top-right-radius: 6px;
    background-color: $fill2;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    border-left: 1px solid $edge;
    border-bottom-right-radius: 6px;
    background-color: $fill2;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background-color: $press; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url("$chevron_up"); width: 8px; height: 5px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url("$chevron_down"); width: 8px; height: 5px; }
QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled,
QSpinBox::up-arrow:off, QDoubleSpinBox::up-arrow:off { image: url("$chevron_up_off"); }
QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled,
QSpinBox::down-arrow:off, QDoubleSpinBox::down-arrow:off { image: url("$chevron_down_off"); }

/* Buttons: outlined by default; Pivot Gold marks the one decisive action. */
QPushButton {
    background-color: transparent;
    color: $white;
    border: 1px solid $edge;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 600;
}
QPushButton:hover { background-color: $hover; border-color: $edge_hover; }
QPushButton:pressed { background-color: $press; }
QPushButton:disabled { color: $text3; border-color: $line; }
QPushButton#primary {
    background-color: $gold;
    color: $black;
    border: 0;
    padding: 9px 22px;
}
QPushButton#primary:hover { background-color: $gold_hover; }
QPushButton#primary:disabled { background-color: rgba(242, 183, 5, 0.35); color: rgba(10, 10, 10, 0.7); }

/* Preview, progress and scrubbing carry motion, so they use Signal Red. */
#previewCanvas { background-color: $black; border: 1px solid $line; border-radius: 10px; }
QProgressBar {
    background-color: $fill;
    border: 1px solid $line;
    border-radius: 6px;
    text-align: center;
    color: $white;
    min-height: 20px;
}
QProgressBar::chunk { background-color: $red; border-radius: 5px; }
QSlider::groove:horizontal { height: 4px; background: $line2; border-radius: 2px; }
QSlider::sub-page:horizontal { background: $red; border-radius: 2px; }
QSlider::handle:horizontal {
    background: $white;
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
}

QScrollBar:vertical { background: $black; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: $line2; border-radius: 6px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: $edge; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QSplitter::handle { background: transparent; }
QSplitter::handle:hover { background: $line; }

QStatusBar { background: $black; color: $text2; border-top: 1px solid $line; }
""")

BRAND_QSS = _QSS.substitute(TOKENS)
