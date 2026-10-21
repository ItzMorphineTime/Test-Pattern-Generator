"""The Black & Burst tab: a sync test video with frame and second counters."""

from __future__ import annotations

import copy

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..core import burst, encoder
from ..core.config import BurstConfig
from .export_bar import ExportBar
from .preview import PREVIEW_MAX, PreviewWidget
from .render_worker import ExportJob
from .widgets import OutputGroup, control_panel, float_spin, split_page


class BurstPage(QWidget):
    """Settings, live preview, and export for the black & burst sync test."""

    def __init__(self, config: BurstConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self._job_config: BurstConfig | None = None

        self.preview = PreviewWidget()
        self.export_bar = ExportBar(
            config.output.output_path,
            get_preset=lambda: encoder.get_preset(self.config),
            validate=lambda: burst.validate(self.config),
            make_job=self._make_job,
            describe_result=self._describe_result,
        )
        self.export_bar.path_edited.connect(
            lambda text: self._set("output.output_path", text, refresh=False))

        splitter, self._scroll = split_page(self._build_controls(), self.preview,
                                            self.export_bar)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._rebuild_preview)
        self._rebuild_preview()

    def set_config(self, config: BurstConfig) -> None:
        """Show a different config (e.g. from a loaded preset)."""
        self.config = config
        self._scroll.setWidget(self._build_controls())
        self.export_bar.set_path(config.output.output_path)
        self._rebuild_preview()

    # -- controls --------------------------------------------------------
    def _build_controls(self) -> QWidget:
        panel, layout = control_panel()

        intro = QLabel(
            "A sync test: the background flips between black and white every "
            "second, the red, green and blue regions each show for a third of the "
            "second, and every frame shows its frame and second number.")
        intro.setWordWrap(True)
        intro.setObjectName("hint")
        layout.addWidget(intro)

        self._output_group = OutputGroup(self.config.output)
        self._output_group.changed.connect(
            lambda attr, value: self._set(f"output.{attr}", value))
        self._png = QCheckBox("Also export every frame as a PNG")
        self._png.setChecked(self.config.export_png)
        self._png.toggled.connect(lambda on: self._set("export_png", on, refresh=False))
        self._output_group.form.addRow("", self._png)
        layout.addWidget(self._output_group)

        layout.addWidget(self._build_pattern_group())
        layout.addStretch(1)
        return panel

    def _build_pattern_group(self) -> QGroupBox:
        box = QGroupBox("Pattern")
        form = QFormLayout(box)
        c = self.config

        region_height = float_spin(5.0, 60.0, c.region_height * 100.0, 1.0, 1, " %")
        region_height.setToolTip(
            "Height of the red/green/blue regions, as a percentage of the canvas height.")
        region_gap = float_spin(0.0, 20.0, c.region_gap * 100.0, 0.5, 1, " %")
        region_gap.setToolTip(
            "Space around and between the regions, as a percentage of the canvas width.")
        text_size = float_spin(2.0, 40.0, c.text_size * 100.0, 1.0, 1, " %")
        text_size.setToolTip(
            "Counter text height as a percentage of the canvas height; it shrinks "
            "automatically if it would not fit.")
        numbering = QComboBox()
        numbering.addItem("From 0 (timecode style)", 0)
        numbering.addItem("From 1", 1)
        numbering.setCurrentIndex(max(0, numbering.findData(c.start_number)))
        numbering.setToolTip(
            "The number shown on the first frame and the first second. "
            "PNG file names follow the same numbering.")

        region_height.valueChanged.connect(lambda v: self._set("region_height", v / 100.0))
        region_gap.valueChanged.connect(lambda v: self._set("region_gap", v / 100.0))
        text_size.valueChanged.connect(lambda v: self._set("text_size", v / 100.0))
        numbering.currentIndexChanged.connect(
            lambda: self._set("start_number", numbering.currentData()))

        form.addRow("Region height", region_height)
        form.addRow("Region spacing", region_gap)
        form.addRow("Counter size", text_size)
        form.addRow("Numbering", numbering)
        return box

    # -- state -----------------------------------------------------------
    def _set(self, dotted: str, value, refresh: bool = True) -> None:
        *parents, attr = dotted.split(".")
        target = self.config
        for name in parents:
            target = getattr(target, name)
        setattr(target, attr, value)
        self._update_summary()
        if refresh:
            self._refresh_timer.start(120)

    def _update_summary(self) -> None:
        cfg = self.config
        preset = encoder.get_preset(cfg)
        red, green, blue = burst.region_split(cfg.output.fps)
        text = (f"{cfg.total_frames():,} frames · {cfg.output.duration:g} s · "
                f"R/G/B shown {red}/{green}/{blue} frames each second")
        if preset.requires_even and (cfg.output.width % 2 or cfg.output.height % 2):
            text += "  ⚠ needs even size"
        self._output_group.frames_label.setText(text)

        if preset.is_sequence:
            self._png.setEnabled(False)
            self._png.setToolTip("This format already writes every frame as a PNG.")
        else:
            folder = encoder.resolve_output_path(cfg).stem + "_frames"
            self._png.setEnabled(True)
            self._png.setToolTip(f"Writes the frames to a '{folder}' folder next to "
                                 "the video, named by frame number.")

    def _rebuild_preview(self) -> None:
        self._update_summary()
        cfg = copy.deepcopy(self.config)
        w, h = cfg.output.width, cfg.output.height
        scale = min(1.0, PREVIEW_MAX / max(w, h))
        cfg.output.width = max(2, round(w * scale))
        cfg.output.height = max(2, round(h * scale))
        self.preview.set_renderer(burst.BurstRenderer(cfg), cfg.total_frames(),
                                  cfg.output.fps)

    # -- export ----------------------------------------------------------
    def _make_job(self) -> ExportJob:
        cfg = copy.deepcopy(self.config)
        self._job_config = cfg
        return lambda progress, cancel: burst.encode_burst(cfg, progress, cancel)

    def _describe_result(self, path: str) -> str:
        text = f"Saved to:\n{path}"
        png_dir = burst.png_frames_dir(self._job_config) if self._job_config else None
        if png_dir is not None:
            text += f"\n\nPNG frames:\n{png_dir}"
        return text
