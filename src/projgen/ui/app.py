"""Main application window."""

from __future__ import annotations

import copy
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..core import encoder
from ..core.config import Axis, LabelMode, LineGroupConfig, LineStyle, ProjectConfig
from ..core.render import FrameRenderer
from .preview import PreviewWidget
from .render_worker import RenderWorker
from .style import DARK_QSS
from .widgets import ColorButton, float_spin, int_spin

PREVIEW_MAX = 720  # longest preview edge in px, for responsiveness


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Projection Test-Pattern Generator")
        self.resize(1180, 760)
        self.config = ProjectConfig()
        self._worker: RenderWorker | None = None
        self._thread: QThread | None = None

        self.preview = PreviewWidget()

        controls = self._build_controls()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(controls)
        scroll.setFixedWidth(430)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.preview, 1)
        right_layout.addWidget(self._build_export_bar())

        splitter = QSplitter()
        splitter.addWidget(scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)
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
        panel = QWidget()
        panel.setObjectName("controlPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        layout.addWidget(self._build_output_group())
        layout.addWidget(self._build_color_group())
        layout.addWidget(self._build_line_group("Horizontal Lines", self.config.h_lines, "h"))
        layout.addWidget(self._build_line_group("Vertical Lines", self.config.v_lines, "v"))
        layout.addWidget(self._build_grid_group())
        layout.addWidget(self._build_preset_buttons())
        layout.addStretch(1)
        return panel

    def _build_output_group(self) -> QGroupBox:
        box = QGroupBox("Output")
        form = QFormLayout(box)
        o = self.config.output

        self.w_width = int_spin(2, 65536, o.width, 2, " px")
        self.w_height = int_spin(2, 65536, o.height, 2, " px")
        self.w_fps = float_spin(1.0, 240.0, o.fps, 1.0, 3, " fps")
        self.w_duration = float_spin(0.1, 3600.0, o.duration, 0.5, 2, " s")
        self.w_preset = QComboBox()
        for key, preset in sorted(encoder.FORMAT_PRESETS.items()):
            self.w_preset.addItem(preset.label, key)
        self.w_preset.setCurrentIndex(self.w_preset.findData(o.preset))

        self.w_width.valueChanged.connect(lambda v: self._set("output.width", v))
        self.w_height.valueChanged.connect(lambda v: self._set("output.height", v))
        self.w_fps.valueChanged.connect(lambda v: self._set("output.fps", v))
        self.w_duration.valueChanged.connect(lambda v: self._set("output.duration", v))
        self.w_preset.currentIndexChanged.connect(self._on_preset_changed)

        size_row = QHBoxLayout()
        size_row.addWidget(self.w_width)
        size_row.addWidget(QLabel("x"))
        size_row.addWidget(self.w_height)
        size_wrap = QWidget()
        size_wrap.setLayout(size_row)
        size_row.setContentsMargins(0, 0, 0, 0)

        form.addRow("Resolution", size_wrap)
        form.addRow("Frame rate", self.w_fps)
        form.addRow("Duration", self.w_duration)
        form.addRow("Format", self.w_preset)
        self.frames_label = QLabel()
        form.addRow("Frames", self.frames_label)
        return box

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
        speed = int_spin(0, 200, cfg.speed)
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
        opacity.valueChanged.connect(lambda v, k=key: self._set(f"{k}.opacity", v))
        style.currentIndexChanged.connect(
            lambda _i, w=style, k=key: self._set(f"{k}.style", w.currentData()))
        direction.currentIndexChanged.connect(
            lambda _i, w=direction, k=key: self._set(f"{k}.direction", w.currentData()))
        color.changed.connect(lambda rgb, k=key: self._set(f"{k}.color", rgb))

        form.addRow("Count", count)
        form.addRow("Thickness", thickness)
        form.addRow("Speed (sweeps/loop)", speed)
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

    def _build_preset_buttons(self) -> QWidget:
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        save = QPushButton("Save Preset...")
        load = QPushButton("Load Preset...")
        save.clicked.connect(self._save_preset)
        load.clicked.connect(self._load_preset)
        row.addWidget(load)
        row.addWidget(save)
        return wrap

    def _build_export_bar(self) -> QWidget:
        bar = QWidget()
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(8, 8, 8, 8)

        path_row = QHBoxLayout()
        self.w_path = QLineEdit(self.config.output.output_path)
        self.w_path.textChanged.connect(lambda t: self._set("output.output_path", t, False))
        browse = QPushButton("Browse...")
        browse.clicked.connect(self._browse_output)
        path_row.addWidget(QLabel("Output"))
        path_row.addWidget(self.w_path, 1)
        path_row.addWidget(browse)
        layout.addLayout(path_row)

        action_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.export_btn = QPushButton("Export Video")
        self.export_btn.setObjectName("primary")
        self.export_btn.clicked.connect(self._start_export)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.clicked.connect(self._cancel_export)
        self.cancel_btn.hide()
        action_row.addWidget(self.progress, 1)
        action_row.addWidget(self.cancel_btn)
        action_row.addWidget(self.export_btn)
        layout.addLayout(action_row)
        return bar

    # ------------------------------------------------------------------
    # State plumbing
    # ------------------------------------------------------------------
    def _set(self, dotted: str, value, refresh: bool = True) -> None:
        section, attr = dotted.split(".")
        setattr(getattr(self.config, section), attr, value)
        if dotted in ("color_loop.enabled", "h_lines.enabled",
                      "v_lines.enabled", "grid.enabled"):
            self._sync_enabled_states()
        if refresh:
            self._refresh_timer.start(120)

    def _sync_enabled_states(self) -> None:
        # Checkable group boxes grey out their children automatically; nothing
        # extra needed, but keep the hook for future dependent-field logic.
        pass

    def _on_preset_changed(self, _index: int) -> None:
        self.config.output.preset = self.w_preset.currentData()
        self.statusBar().showMessage(
            f"Format: {encoder.get_preset(self.config).label}", 4000)
        self._update_frames_label()

    def _update_frames_label(self) -> None:
        n = self.config.total_frames()
        preset = encoder.get_preset(self.config)
        warn = ""
        if preset.requires_even and (self.config.output.width % 2
                                     or self.config.output.height % 2):
            warn = "  ⚠ needs even size"
        self.frames_label.setText(f"{n:,} frames · one seamless loop{warn}")

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
        scroll = self.centralWidget().widget(0)
        scroll.setWidget(self._build_controls())
        self.w_path.setText(self.config.output.output_path)
        self._sync_enabled_states()
        self._rebuild_preview()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def _browse_output(self) -> None:
        preset = encoder.get_preset(self.config)
        if preset.is_sequence:
            path = QFileDialog.getExistingDirectory(self, "Choose output folder")
            if path:
                self.w_path.setText(os.path.join(path, "frame"))
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Export as", self.config.output.output_path,
                f"Video (*{preset.extension})")
            if path:
                self.w_path.setText(path)

    def _start_export(self) -> None:
        problems = encoder.validate(self.config)
        if problems:
            QMessageBox.warning(self, "Cannot export", "\n".join(problems))
            return

        self._worker = RenderWorker(self.config)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)

        self.export_btn.setEnabled(False)
        self.cancel_btn.show()
        self.progress.setValue(0)
        self.statusBar().showMessage("Exporting...")
        self._thread.start()

    def _cancel_export(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self.statusBar().showMessage("Cancelling...")

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(done)

    def _on_finished(self, path: str) -> None:
        self._teardown_thread()
        self.statusBar().showMessage(f"Exported {path}", 8000)
        result = QMessageBox.information(
            self, "Export complete", f"Saved to:\n{path}",
            QMessageBox.Open | QMessageBox.Ok)
        if result == QMessageBox.Open:
            self._open_in_explorer(path)

    def _on_failed(self, message: str) -> None:
        self._teardown_thread()
        self.progress.setValue(0)
        self.statusBar().showMessage(message, 6000)
        if message != "Export cancelled.":
            QMessageBox.critical(self, "Export failed", message)

    def _teardown_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None
        self.export_btn.setEnabled(True)
        self.cancel_btn.hide()

    @staticmethod
    def _open_in_explorer(path: str) -> None:
        target = os.path.dirname(path) or "."
        try:
            if sys.platform == "win32":
                os.startfile(target)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.run(["open", target], check=False)
            else:
                subprocess.run(["xdg-open", target], check=False)
        except OSError:
            pass


def run() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)
    window = MainWindow()
    window.show()
    return app.exec()
