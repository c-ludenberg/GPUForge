import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
    QFrame, QComboBox, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer

from gettext import gettext as _

from gpuforge.backend.gpu_base import GPUBackend
from gpuforge.ui.gl_stress import GLStressWindow, RESOLUTIONS, QUALITY_CONFIGS, MODEL_GENERATORS

log = logging.getLogger(__name__)


class StressTestWidget(QWidget):
    def __init__(self, backend: GPUBackend, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._stress_window = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        title = QLabel(_("Stress Test"))
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f0f6fc;")
        layout.addWidget(title)

        desc = QLabel(_(
            "Launch a fullscreen FurMark-style GPU stress test.\n"
            "Renders a furry 3D torus with configurable shader complexity.\n"
            "Monitor temps and FPS in the overlay during the test."
        ))
        desc.setStyleSheet("color: #8b949e; font-size: 12px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        config_frame = QFrame()
        config_frame.setObjectName("card")
        config_frame.setStyleSheet("""
            QFrame#card { background-color: #11161e; border: 1px solid #1e2a3a;
                          border-radius: 10px; padding: 14px; }
            QLabel { background: transparent; }
        """)
        cl = QVBoxLayout(config_frame)
        cl.setSpacing(10)

        res_row = QHBoxLayout()
        res_row.addWidget(QLabel(_("Resolution:")))
        self._res_combo = QComboBox()
        self._res_combo.addItems(RESOLUTIONS)
        self._res_combo.setCurrentText("1920x1080")
        res_row.addWidget(self._res_combo)
        res_row.addStretch()
        cl.addLayout(res_row)

        qual_row = QHBoxLayout()
        qual_row.addWidget(QLabel(_("Quality:")))
        self._qual_combo = QComboBox()
        for k in ["low", "medium", "high", "ultra"]:
            cfg = QUALITY_CONFIGS[k]
            label = f"{k.capitalize()}  ({cfg['shells']} shells, {cfg['major']}×{cfg['minor']} segments)"
            self._qual_combo.addItem(label, k)
        self._qual_combo.setCurrentIndex(1)
        qual_row.addWidget(self._qual_combo)
        qual_row.addStretch()
        cl.addLayout(qual_row)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel(_("Model:")))
        self._model_combo = QComboBox()
        model_names = {"torus": "Torus (furry donut)", "donut": "Donut", "toilet": "🚽 Toilet"}
        for m, label in model_names.items():
            self._model_combo.addItem(label, m)
        self._model_combo.setCurrentIndex(0)
        model_row.addWidget(self._model_combo)
        model_row.addStretch()
        cl.addLayout(model_row)

        warn = QLabel(_(
            "⚠ This will run fullscreen. Press ESC to exit. "
            "Monitor your GPU temperatures closely."
        ))
        warn.setStyleSheet("color: #d29922; font-size: 11px; background: transparent;")
        warn.setWordWrap(True)
        cl.addWidget(warn)

        layout.addWidget(config_frame)

        self._btn = QPushButton(f"▶  {_('Launch Stress Test')}")
        self._btn.setObjectName("primaryButton")
        self._btn.setStyleSheet("""
            QPushButton { background-color: #1a7f37; border: 1px solid #2ea043;
                          color: white; border-radius: 8px; padding: 10px 20px;
                          font-size: 14px; font-weight: 600; }
            QPushButton:hover { background-color: #238636; }
        """)
        self._btn.clicked.connect(self._launch)
        layout.addWidget(self._btn)

        self._status = QLabel(_("Ready"))
        self._status.setStyleSheet("font-weight: 600; font-size: 14px; color: #8b949e;")
        layout.addWidget(self._status)

        self._stats = QLabel()
        self._stats.setStyleSheet("color: #8b949e; font-size: 12px;")
        self._stats.setWordWrap(True)
        layout.addWidget(self._stats)

        layout.addStretch()

    def _launch(self):
        if self._stress_window is not None:
            return

        res_text = self._res_combo.currentText()
        res_w, res_h = map(int, res_text.split("x"))
        quality = self._qual_combo.currentData()
        model = self._model_combo.currentData()

        try:
            gpu_info = self._backend.get_gpu_info(0)
            gpu_name = gpu_info.name
        except Exception:
            gpu_name = ""

        log.info("Launching GL stress test: %s %s %s", quality, res_text, model)
        self._stress_window = GLStressWindow(quality, res_w, res_h, self._backend, gpu_name, model)
        self._stress_window.closed.connect(self._on_closed)

        self._btn.setEnabled(False)
        self._btn.setText(_("Running..."))
        self._status.setText(_("Stress test running — press ESC to exit"))

        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll_stats)
        self._poll_timer.start(1000)

    def _poll_stats(self):
        if self._stress_window is None:
            return
        fps = self._stress_window.fps
        try:
            s = self._backend.get_sensors(0)
            extra = ""
            if s.temp_hotspot > 0:
                extra += f"  {_('Hotspot')}: {s.temp_hotspot:.0f}°C"
            if s.temp_mem > 0:
                extra += f"  {_('VRAM')}: {s.temp_mem:.0f}°C"
            text = _("FPS: {:.0f}  |  Temp: {:.0f}°C{}  |  Load: {:.0f}%").format(
                fps, s.temp_core, extra, s.utilization_pct
            )
            self._stats.setText(text)
        except Exception:
            self._stats.setText(_("FPS: {:.0f}").format(fps))

    def _on_closed(self):
        self._stress_window = None
        self._btn.setEnabled(True)
        self._btn.setText(f"▶  {_('Launch Stress Test')}")
        self._status.setText(_("Ready"))
        self._stats.setText("")
        if hasattr(self, "_poll_timer"):
            self._poll_timer.stop()
