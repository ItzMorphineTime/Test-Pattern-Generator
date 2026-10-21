"""Main application window: one tab per generator, sharing presets and theme."""

from __future__ import annotations

import copy
import sys
from enum import Enum

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from ..core import encoder
from ..core.config import (
    Axis,
    ImageEffect,
    LabelMode,
    LineGroupConfig,
    LineStyle,
    ProjectConfig,
)
from ..core.render import FrameRenderer
from ..resources import icon_path, resource_path
from .burst_page import BurstPage
from .export_bar import ExportBar
from .preview import PREVIEW_MAX, PreviewWidget
from .render_worker import ExportJob
from .style import BRAND_QSS, FONT_FAMILY, load_brand_fonts, svg_pixmap
from .widgets import (
    ColorButton,
    OutputGroup,
    control_panel,
    float_spin,
    int_spin,
    row,
    split_page,
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Projection Test-Pattern Generator")
        if icon_path():
            self.setWindowIcon(QIcon(icon_path()))
        self.resize(1460, 860)
        self.config = ProjectConfig()

        self.preview = PreviewWidget()
        self.export_bar = ExportBar(
            self.config.output.output_path,
            get_preset=lambda: encoder.get_preset(self.config),
            validate=lambda: encoder.validate(self.config),
            make_job=self._make_job,
        )
        self.export_bar.path_edited.connect(
            lambda text: self._set("output.output_path", text, False))
        loop_page, self._scroll = split_page(self._build_controls(), self.preview,
                                             self.export_bar)
        self.burst_page = BurstPage(self.config.burst)

        self.pages = QStackedWidget()
        self.pages.addWidget(loop_page)
        self.pages.addWidget(self.burst_page)
        central = QWidget()
        column = QVBoxLayout(central)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_header())
        column.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Ready")

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._rebuild_preview)

        self._sync_enabled_states()
        self._rebuild_preview()

    # ------------------------------------------------------------------
    # Control panel construction
    # ------------------------------------------------------------------
    def _build_controls(self) -> QWidget:
        panel, layout = control_panel()
        self.output_group = OutputGroup(self.config.output)
        self.output_group.changed.connect(self._on_output_changed)
        layout.addWidget(self.output_group)
        layout.addWidget(self._build_color_group())
        layout.addWidget(self._build_line_group("Horizontal Lines", self.config.h_lines, "h"))
        layout.addWidget(self._build_line_group("Vertical Lines", self.config.v_lines, "v"))
        layout.addWidget(self._build_grid_group())
        layout.addWidget(self._build_image_group())
        layout.addStretch(1)
        return panel

    def _build_color_group(self) -> QGroupBox:
        box = QGroupBox("Colour Loop")
        box.setCheckable(True)
        box.setChecked(self.config.color_loop.enabled)
        box.toggled.connect(lambda on: self._set("color_loop.enabled", on))
        form = QFormLayout(box)
        c = self.config.color_loop

        self.w_sat = float_spin(0.0, 1.0, c.saturation, 0.02)
        self.w_val = float_spin(0.0, 1.0, c.value, 0.02)
        self.w_cycles = float_spin(0.1, 20.0, c.hue_cycles, 0.5, 1)
        self.w_axis = QComboBox()
        self.w_axis.addItem("Horizontal (X)", Axis.X)
        self.w_axis.addItem("Vertical (Y)", Axis.Y)
        self.w_axis.setCurrentIndex(self.w_axis.findData(c.axis))
        self.w_cdir = QComboBox()
        self.w_cdir.addItem("Forward", 1)
        self.w_cdir.addItem("Reverse", -1)
        self.w_cdir.setCurrentIndex(self.w_cdir.findData(c.direction))

        self.w_sat.valueChanged.connect(lambda v: self._set("color_loop.saturation", v))
        self.w_val.valueChanged.connect(lambda v: self._set("color_loop.value", v))
        self.w_cycles.valueChanged.connect(lambda v: self._set("color_loop.hue_cycles", v))
        self.w_axis.currentIndexChanged.connect(
            lambda: self._set("color_loop.axis", self.w_axis.currentData()))
        self.w_cdir.currentIndexChanged.connect(
            lambda: self._set("color_loop.direction", self.w_cdir.currentData()))

        form.addRow("Saturation", self.w_sat)
        form.addRow("Value", self.w_val)
        form.addRow("Hue cycles", self.w_cycles)
        form.addRow("Axis", self.w_axis)
        form.addRow("Direction", self.w_cdir)
        self._color_group = box
        return box

    def _build_line_group(self, title: str, cfg: LineGroupConfig, tag: str) -> QGroupBox:
        box = QGroupBox(title)
        box.setCheckable(True)
        box.setChecked(cfg.enabled)
        box.toggled.connect(lambda on, t=tag: self._set(f"{t}_lines.enabled", on))
        form = QFormLayout(box)

        count = int_spin(1, 200, cfg.count)
        thickness = int_spin(1, 400, cfg.thickness, 1, " px")
        speed = float_spin(0.0, 200.0, cfg.speed, 0.5, 2)
        speed.setToolTip(
            "Sweeps per loop. Each sweep moves the lines across and back to the "
            "start (there and back).")
        seamless = QCheckBox("Loop seamlessly (whole sweeps)")
        seamless.setChecked(cfg.seamless)
        seamless.setToolTip(
            "On: the sweep count is rounded to a whole number so the lines return "
            "to their start position at the loop point.\n"
            "Off: uses the exact speed (free motion that need not return).")
        opacity = float_spin(0.0, 1.0, cfg.opacity, 0.05)
        style = QComboBox()
        style.addItem("Solid", LineStyle.SOLID)
        style.addItem("Soft", LineStyle.SOFT)
        style.setCurrentIndex(style.findData(cfg.style))
        direction = QComboBox()
        direction.addItem("Forward", 1)
        direction.addItem("Reverse", -1)
        direction.setCurrentIndex(direction.findData(cfg.direction))
        color = ColorButton(cfg.color)

        key = f"{tag}_lines"
        count.valueChanged.connect(lambda v, k=key: self._set(f"{k}.count", v))
        thickness.valueChanged.connect(lambda v, k=key: self._set(f"{k}.thickness", v))
        speed.valueChanged.connect(lambda v, k=key: self._set(f"{k}.speed", v))
        seamless.toggled.connect(lambda on, k=key: self._set(f"{k}.seamless", on))
        opacity.valueChanged.connect(lambda v, k=key: self._set(f"{k}.opacity", v))
        style.currentIndexChanged.connect(
            lambda _i, w=style, k=key: self._set(f"{k}.style", w.currentData()))
        direction.currentIndexChanged.connect(
            lambda _i, w=direction, k=key: self._set(f"{k}.direction", w.currentData()))
        color.changed.connect(lambda rgb, k=key: self._set(f"{k}.color", rgb))

        form.addRow("Count", count)
        form.addRow("Thickness", thickness)
        form.addRow("Speed (sweeps/loop)", speed)
        form.addRow("", seamless)
        form.addRow("Opacity", opacity)
        form.addRow("Style", style)
        form.addRow("Direction", direction)
        form.addRow("Colour", color)
        return box

    def _build_grid_group(self) -> QGroupBox:
        box = QGroupBox("Number Grid")
        box.setCheckable(True)
        box.setChecked(self.config.grid.enabled)
        box.toggled.connect(lambda on: self._set("grid.enabled", on))
        form = QFormLayout(box)
        g = self.config.grid

        rows = int_spin(1, 200, g.rows)
        cols = int_spin(1, 200, g.cols)
        labels = QComboBox()
        for mode, text in ((LabelMode.ALPHA_NUM, "Alpha-numeric (A1)"),
                           (LabelMode.SEQUENTIAL, "Sequential (0,1,2)"),
                           (LabelMode.ROW_COL, "Row/Col (R1C1)"),
                           (LabelMode.COORDS, "Pixel coords")):
            labels.addItem(text, mode)
        labels.setCurrentIndex(labels.findData(g.label_mode))
        font_size = int_spin(0, 400, g.font_size, 1, " px")
        font_size.setSpecialValueText("Auto")
        font_color = ColorButton(g.font_color)
        line_color = ColorButton(g.line_color)
        line_thickness = int_spin(1, 40, g.line_thickness, 1, " px")
        line_opacity = float_spin(0.0, 1.0, g.line_opacity, 0.05)
        show_lines = QComboBox()
        show_lines.addItem("Show grid lines", True)
        show_lines.addItem("Labels only", False)
        show_lines.setCurrentIndex(0 if g.show_lines else 1)
        cell_bg = QComboBox()
        cell_bg.addItem("Transparent labels", False)
        cell_bg.addItem("Dark pad behind labels", True)
        cell_bg.setCurrentIndex(1 if g.cell_background else 0)

        rows.valueChanged.connect(lambda v: self._set("grid.rows", v))
        cols.valueChanged.connect(lambda v: self._set("grid.cols", v))
        labels.currentIndexChanged.connect(
            lambda: self._set("grid.label_mode", labels.currentData()))
        font_size.valueChanged.connect(lambda v: self._set("grid.font_size", v))
        font_color.changed.connect(lambda rgb: self._set("grid.font_color", rgb))
        line_color.changed.connect(lambda rgb: self._set("grid.line_color", rgb))
        line_thickness.valueChanged.connect(lambda v: self._set("grid.line_thickness", v))
        line_opacity.valueChanged.connect(lambda v: self._set("grid.line_opacity", v))
        show_lines.currentIndexChanged.connect(
            lambda: self._set("grid.show_lines", show_lines.currentData()))
        cell_bg.currentIndexChanged.connect(
            lambda: self._set("grid.cell_background", cell_bg.currentData()))

        grid_size = QHBoxLayout()
        grid_size.setContentsMargins(0, 0, 0, 0)
        grid_size.addWidget(rows)
        grid_size.addWidget(QLabel("rows x"))
        grid_size.addWidget(cols)
        grid_size.addWidget(QLabel("cols"))
        gs_wrap = QWidget()
        gs_wrap.setLayout(grid_size)

        form.addRow("Grid", gs_wrap)
        form.addRow("Labels", labels)
        form.addRow("Font size", font_size)
        form.addRow("Font colour", font_color)
        form.addRow("Line colour", line_color)
        form.addRow("Line thickness", line_thickness)
        form.addRow("Line opacity", line_opacity)
        form.addRow("Grid lines", show_lines)
        form.addRow("Label background", cell_bg)
        return box

    def _build_image_group(self) -> QGroupBox:
        box = QGroupBox("Image / Logo")
        box.setCheckable(True)
        box.setChecked(self.config.image.enabled)
        box.toggled.connect(lambda on: self._set("image.enabled", on))
        form = QFormLayout(box)
        img = self.config.image

        self.w_image_path = QLineEdit(img.path)
        self.w_image_path.setPlaceholderText("Choose an image file...")
        self.w_image_path.textChanged.connect(lambda t: self._set("image.path", t))
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_image)
        path_row = QHBoxLayout()
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.addWidget(self.w_image_path, 1)
        path_row.addWidget(browse)
        path_wrap = QWidget()
        path_wrap.setLayout(path_row)

        pos_x = float_spin(0.0, 100.0, img.pos_x * 100.0, 1.0, 1, " %")
        pos_y = float_spin(0.0, 100.0, img.pos_y * 100.0, 1.0, 1, " %")
        scale = float_spin(1.0, 400.0, img.scale * 100.0, 1.0, 1, " %")
        scale.setToolTip("Rendered image width as a percentage of the canvas width.")
        opacity = float_spin(0.0, 1.0, img.opacity, 0.05)
        effect = QComboBox()
        for eff, text in ((ImageEffect.NONE, "None (static)"),
                          (ImageEffect.PULSE, "Grow && Shrink"),
                          (ImageEffect.FADE, "Fade"),
                          (ImageEffect.SPIN, "Spin"),
                          (ImageEffect.BOUNCE, "Bounce (screensaver)")):
            effect.addItem(text, eff)
        effect.setCurrentIndex(effect.findData(img.effect))
        layer = QComboBox()
        layer.addItem("Behind grid", False)
        layer.addItem("On top of grid", True)
        layer.setCurrentIndex(1 if img.above_grid else 0)
        cycles = int_spin(1, 100, img.effect_cycles)
        cycles.setToolTip("Whole effect cycles per loop, so the final frame "
                          "returns to the start.")
        amount = float_spin(0.0, 1.0, img.effect_amount, 0.05)
        amount.setToolTip("Effect strength (size change, fade depth); "
                          "not used by Bounce.")

        pos_x.valueChanged.connect(lambda v: self._set("image.pos_x", v / 100.0))
        pos_y.valueChanged.connect(lambda v: self._set("image.pos_y", v / 100.0))
        scale.valueChanged.connect(lambda v: self._set("image.scale", v / 100.0))
        opacity.valueChanged.connect(lambda v: self._set("image.opacity", v))
        effect.currentIndexChanged.connect(
            lambda: self._set("image.effect", effect.currentData()))
        layer.currentIndexChanged.connect(
            lambda: self._set("image.above_grid", layer.currentData()))
        cycles.valueChanged.connect(lambda v: self._set("image.effect_cycles", v))
        amount.valueChanged.connect(lambda v: self._set("image.effect_amount", v))

        pos_row = QHBoxLayout()
        pos_row.setContentsMargins(0, 0, 0, 0)
        pos_row.addWidget(pos_x)
        pos_row.addWidget(QLabel("x"))
        pos_row.addWidget(pos_y)
        pos_wrap = QWidget()
        pos_wrap.setLayout(pos_row)

        form.addRow("File", path_wrap)
        form.addRow("Position", pos_wrap)
        form.addRow("Scale", scale)
        form.addRow("Opacity", opacity)
        form.addRow("Layer", layer)
        form.addRow("Effect", effect)
        form.addRow("Effect cycles", cycles)
        form.addRow("Effect amount", amount)
        return box

    def _browse_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All files (*)")
        if path:
            self.w_image_path.setText(path)

    def _build_header(self) -> QWidget:
        """The Morph wordmark, the tool tabs, and the preset buttons."""
        header = QWidget()
        header.setObjectName("header")
        # The wordmark is 36 px tall; 84 px leaves the brand's 24 px clear space.
        header.setFixedHeight(84)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(0)

        wordmark = QLabel()
        wordmark.setPixmap(svg_pixmap(resource_path("brand", "morph-wordmark-dark.svg"),
                                      124, self.devicePixelRatioF()))
        wordmark.setAccessibleName("Morph")
        layout.addWidget(wordmark, 0, Qt.AlignVCenter)
        layout.addSpacing(40)

        self.tabs = QTabBar()
        self.tabs.setObjectName("mainTabs")
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        self.tabs.addTab("Colour Loop")
        self.tabs.addTab("Black && Burst")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs, 0, Qt.AlignVCenter)
        layout.addStretch(1)
        layout.addWidget(self._build_preset_buttons(), 0, Qt.AlignVCenter)
        return header

    def _build_preset_buttons(self) -> QWidget:
        load = QPushButton("Load Preset...")
        save = QPushButton("Save Preset...")
        load.setToolTip("Load the settings for every tab from a preset file.")
        save.setToolTip("Save the settings of every tab to a preset file.")
        load.clicked.connect(self._load_preset)
        save.clicked.connect(self._save_preset)
        return row(load, save)

    # ------------------------------------------------------------------
    # State plumbing
    # ------------------------------------------------------------------
    def _set(self, dotted: str, value, refresh: bool = True) -> None:
        section, attr = dotted.split(".")
        target = getattr(self.config, section)
        current = getattr(target, attr)
        # Qt's QVariant flattens str-mixin enum members to plain strings on the
        # way through a combo box; restore the enum type so the render core's
        # comparisons keep working.
        if isinstance(current, Enum) and not isinstance(value, Enum):
            value = type(current)(value)
        setattr(target, attr, value)
        if dotted in ("color_loop.enabled", "h_lines.enabled",
                      "v_lines.enabled", "grid.enabled"):
            self._sync_enabled_states()
        if refresh:
            self._refresh_timer.start(120)

    def _sync_enabled_states(self) -> None:
        # Checkable group boxes grey out their children automatically; nothing
        # extra needed, but keep the hook for future dependent-field logic.
        pass

    def _on_output_changed(self, attr: str, value) -> None:
        self._set(f"output.{attr}", value)
        if attr == "preset":
            self.statusBar().showMessage(
                f"Format: {encoder.get_preset(self.config).label}", 4000)

    def _update_frames_label(self) -> None:
        n = self.config.total_frames()
        preset = encoder.get_preset(self.config)
        warn = ""
        if preset.requires_even and (self.config.output.width % 2
                                     or self.config.output.height % 2):
            warn = "  ⚠ needs even size"
        self.output_group.frames_label.setText(f"{n:,} frames · one seamless loop{warn}")

    def _rebuild_preview(self) -> None:
        self._update_frames_label()
        preview_cfg = self._preview_config()
        renderer = FrameRenderer(preview_cfg)
        self.preview.set_renderer(renderer, self.config.total_frames(),
                                  self.config.output.fps)

    def _preview_config(self) -> ProjectConfig:
        cfg = copy.deepcopy(self.config)
        w, h = cfg.output.width, cfg.output.height
        scale = min(1.0, PREVIEW_MAX / max(w, h))
        cfg.output.width = max(2, int(round(w * scale)) // 2 * 2)
        cfg.output.height = max(2, int(round(h * scale)) // 2 * 2)
        if scale < 1.0:
            # Scale pixel-based sizes with the canvas so the preview is a
            # faithful miniature of the final render.
            if cfg.grid.font_size:
                cfg.grid.font_size = max(1, round(cfg.grid.font_size * scale))
            cfg.grid.line_thickness = max(1, round(cfg.grid.line_thickness * scale))
            for group in (cfg.h_lines, cfg.v_lines):
                group.thickness = max(1, round(group.thickness * scale))
        return cfg

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------
    def _save_preset(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save preset", "preset.json", "JSON (*.json)")
        if path:
            self.config.save(path)
            self.statusBar().showMessage(f"Saved preset to {path}", 4000)

    def _load_preset(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load preset", "", "JSON (*.json)")
        if not path:
            return
        try:
            self.config = ProjectConfig.load(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Load failed", str(exc))
            return
        self._reload_widgets_from_config()
        self.statusBar().showMessage(f"Loaded preset {path}", 4000)

    def _reload_widgets_from_config(self) -> None:
        # Simplest robust approach: rebuild the whole control panel.
        self._scroll.setWidget(self._build_controls())
        self.export_bar.set_path(self.config.output.output_path)
        self.burst_page.set_config(self.config.burst)
        self._sync_enabled_states()
        self._rebuild_preview()

    # ------------------------------------------------------------------
    # Export and window lifecycle
    # ------------------------------------------------------------------
    def _make_job(self) -> ExportJob:
        cfg = copy.deepcopy(self.config)
        return lambda progress, cancel: encoder.encode(cfg, progress=progress,
                                                       cancel=cancel)

    def _on_tab_changed(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        # Only the visible tab's preview should spend time rendering.
        self.preview.pause()
        self.burst_page.preview.pause()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        bars = (self.export_bar, self.burst_page.export_bar)
        if any(bar.busy for bar in bars):
            answer = QMessageBox.question(
                self, "Export running",
                "An export is still running. Cancel it and quit?")
            if answer != QMessageBox.Yes:
                event.ignore()
                return
        for bar in bars:
            bar.shutdown()
        super().closeEvent(event)


def apply_theme(app: QApplication) -> None:
    """Load the brand fonts and stylesheet into `app`."""
    if load_brand_fonts():
        app.setFont(QFont(FONT_FAMILY, 10))
    app.setStyleSheet(BRAND_QSS)


def run() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)
    if icon_path():
        app.setWindowIcon(QIcon(icon_path()))
    window = MainWindow()
    window.show()
    return app.exec()
