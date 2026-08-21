"""A compact dark theme for the application."""

DARK_QSS = """
* { font-size: 13px; }
QWidget { background-color: #1e2127; color: #d7dae0; }
QMainWindow, QScrollArea, #controlPanel { background-color: #1e2127; }

QGroupBox {
    border: 1px solid #333842;
    border-radius: 8px;
    margin-top: 14px;
    padding: 8px 10px 10px 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #8ea0b6;
}
QGroupBox::indicator { width: 16px; height: 16px; }

QLabel { background: transparent; }

QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit {
    background-color: #262b33;
    border: 1px solid #3a4150;
    border-radius: 5px;
    padding: 3px 6px;
    min-height: 22px;
    selection-background-color: #4c8bf5;
}
/* Reserve room on the right so the text never slides under the step buttons. */
QSpinBox, QDoubleSpinBox { padding-right: 20px; }

QComboBox::drop-down { border: 0; width: 18px; }
QComboBox QAbstractItemView {
    background-color: #262b33;
    selection-background-color: #4c8bf5;
    border: 1px solid #3a4150;
}
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QLineEdit:focus {
    border: 1px solid #4c8bf5;
}

/* Explicit geometry for the up/down step buttons so they sit flush at the
   right edge, don't overlap the field, and stay clickable. */
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    border-left: 1px solid #3a4150;
    border-top-right-radius: 5px;
    background-color: #2d333d;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    border-left: 1px solid #3a4150;
    border-bottom-right-radius: 5px;
    background-color: #2d333d;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #3a4150;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid #9aa7b8;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #9aa7b8;
}

QPushButton {
    background-color: #2d333d;
    border: 1px solid #3a4150;
    border-radius: 6px;
    padding: 6px 12px;
}
QPushButton:hover { background-color: #353c47; }
QPushButton:pressed { background-color: #2a2f38; }

QPushButton#primary {
    background-color: #4c8bf5;
    border: 0;
    color: white;
    font-weight: 700;
    padding: 9px 16px;
}
QPushButton#primary:hover { background-color: #5c97f7; }
QPushButton#primary:disabled { background-color: #37506f; color: #9fb2cc; }

QPushButton#danger { background-color: #a13a3a; border: 0; color: white; }
QPushButton#danger:hover { background-color: #b84545; }

#previewCanvas {
    background-color: #101216;
    border: 1px solid #333842;
    border-radius: 8px;
}

QProgressBar {
    background-color: #262b33;
    border: 1px solid #3a4150;
    border-radius: 6px;
    text-align: center;
    height: 20px;
}
QProgressBar::chunk { background-color: #4c8bf5; border-radius: 5px; }

QSlider::groove:horizontal { height: 5px; background: #3a4150; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #4c8bf5; width: 14px; margin: -5px 0; border-radius: 7px;
}

QScrollBar:vertical { background: #1e2127; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #3a4150; border-radius: 6px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }

QStatusBar { background: #171a1f; color: #8ea0b6; }
"""
