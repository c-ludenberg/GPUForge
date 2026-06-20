from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QPushButton, QFrame, QStackedWidget, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon

from gettext import gettext as _

from gpuforge.backend.gpu_base import GPUBackend
from gpuforge.backend.monitor import MonitorController
from gpuforge.ui.monitor_widget import MonitorWidget
from gpuforge.ui.curve_editor import CurveEditorWidget
from gpuforge.ui.presets import PresetsWidget
from gpuforge.ui.stress_test import StressTestWidget
from gpuforge.ui.game_detector import GameDetectorWidget


class MainWindow(QMainWindow):
    def __init__(self, backend: GPUBackend, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._monitor = MonitorController(backend)
        self._gpu_count = max(backend.get_gpu_count(), 1)
        self._current_gpu = 0

        self.setWindowTitle(_("GPUForge"))
        self.setMinimumSize(1100, 720)
        self.resize(1280, 800)

        self._gpu_info = None
        if self._gpu_count > 0:
            try:
                self._gpu_info = backend.get_gpu_info(0)
            except Exception:
                pass

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

        self._monitor.start(500)

    def _setup_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = self._build_header()
        layout.addWidget(header)

        body = QWidget()
        body.setObjectName("bodyWidget")
        bl = QHBoxLayout(body)
        bl.setContentsMargins(16, 12, 16, 12)
        bl.setSpacing(14)

        sidebar = self._build_sidebar()
        bl.addWidget(sidebar)

        self._stack = QStackedWidget()
        self._stack.setObjectName("contentStack")
        bl.addWidget(self._stack, 1)

        layout.addWidget(body, 1)

        status = QLabel(f"GPUForge v0.1.0 — {_('Ready')}")
        status.setObjectName("statusLabel")
        status.setStyleSheet("color: #8b949e; font-size: 11px; padding: 4px 16px; background: transparent;")
        layout.addWidget(status)

    def _build_header(self):
        h = QWidget()
        h.setObjectName("headerBar")

        hl = QHBoxLayout(h)
        hl.setContentsMargins(20, 0, 20, 0)
        hl.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title_col.setContentsMargins(0, 0, 0, 0)

        title = QLabel("GPUForge")
        title.setObjectName("appTitle")
        title_col.addWidget(title)

        subtitle = QLabel(_("GPU Undervolt & Overclocking Tool"))
        subtitle.setObjectName("appSubtitle")
        title_col.addWidget(subtitle)

        hl.addLayout(title_col)
        hl.addStretch()

        if self._gpu_info:
            gpu_name = self._gpu_info.name
            badge = QLabel(f"  {gpu_name}  ")
            badge.setObjectName("gpuBadge")
            hl.addWidget(badge)

        self._gpu_selector = QLabel()
        self._gpu_selector.setStyleSheet("color: #8b949e; font-size: 12px; background: transparent;")
        if self._gpu_count > 1:
            self._gpu_selector.setText(f"GPU 1 / {self._gpu_count}")
        hl.addWidget(self._gpu_selector)

        return h

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(6, 6, 6, 6)
        sl.setSpacing(2)

        items = [
            ("monitor", "◉", _("Monitor")),
            ("curve", "⊞", _("Curve Editor")),
            ("presets", "⚡", _("Presets")),
            ("stress", "⟳", _("Stress Test")),
            ("games", "▷", _("Game Detection")),
        ]

        self._nav_buttons = {}
        for name, icon, label in items:
            btn = QPushButton(f"  {icon}  {label}")
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, n=name: self._navigate(n))
            sl.addWidget(btn)
            self._nav_buttons[name] = btn

        sl.addStretch()

        reset_btn = QPushButton(f"  ↺  {_('Reset GPU')}")
        reset_btn.setObjectName("dangerButton")
        reset_btn.clicked.connect(self._reset_gpu)
        sl.addWidget(reset_btn)

        self._nav_buttons["monitor"].setChecked(True)

        return sidebar

    def _apply_style(self):
        import os
        style_path = os.path.join(os.path.dirname(__file__), "..", "resources", "style.qss")
        try:
            with open(style_path) as f:
                self.setStyleSheet(f.read())
        except FileNotFoundError:
            pass

    def _connect_signals(self):
        self._monitor.sensors_updated.connect(self._on_sensors)

    def _on_sensors(self, index, sensors):
        if index == self._current_gpu:
            self._monitor_widget.update_sensors(sensors)

    def _navigate(self, name):
        mapping = {
            "monitor": 0,
            "curve": 1,
            "presets": 2,
            "stress": 3,
            "games": 4,
        }
        idx = mapping.get(name, 0)
        self._stack.setCurrentIndex(idx)
        for n, btn in self._nav_buttons.items():
            btn.setChecked(n == name)

    def _reset_gpu(self):
        try:
            self._backend.reset_to_defaults(self._current_gpu)
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, _("Error"), _("Reset failed: {}").format(e))

    def closeEvent(self, event):
        self._monitor.stop()
        super().closeEvent(event)
