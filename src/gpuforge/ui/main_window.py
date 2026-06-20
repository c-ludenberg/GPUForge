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

        self._setup_ui()
        self._apply_style()
        self._connect_signals()

        self._monitor.start(500)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        header = self._build_header()
        layout.addWidget(header)

        content = QHBoxLayout()
        content.setSpacing(12)
        layout.addLayout(content, 1)

        sidebar = self._build_sidebar()
        content.addWidget(sidebar)

        self._stack = QStackedWidget()
        content.addWidget(self._stack, 1)

        self._monitor_widget = MonitorWidget(self._backend, self._monitor, self)
        self._curve_widget = CurveEditorWidget(self._backend, self)
        self._presets_widget = PresetsWidget(self._backend, self)
        self._stress_widget = StressTestWidget(self._backend, self)
        self._game_widget = GameDetectorWidget(self._backend, self)

        self._stack.addWidget(self._monitor_widget)
        self._stack.addWidget(self._curve_widget)
        self._stack.addWidget(self._presets_widget)
        self._stack.addWidget(self._stress_widget)
        self._stack.addWidget(self._game_widget)

        status = QLabel(f"GPUForge v0.1.0 — {_('Ready')}")
        status.setObjectName("statusLabel")
        status.setStyleSheet("color: #8b949e; font-size: 11px; padding: 2px 0;")
        layout.addWidget(status)

        self._sidebar_buttons = []

    def _build_header(self):
        h = QWidget()
        h.setObjectName("header")
        h.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(h)
        hl.setContentsMargins(0, 0, 0, 0)

        title = QLabel("GPUForge")
        title.setObjectName("titleLabel")
        hl.addWidget(title)

        hl.addStretch()

        self._gpu_selector = QLabel()
        self._gpu_selector.setStyleSheet("color: #8b949e; font-size: 12px;")
        if self._gpu_count > 1:
            self._gpu_selector.setText(f"GPU 1 of {self._gpu_count}")
        else:
            self._gpu_selector.setText("")
        hl.addWidget(self._gpu_selector)

        return h

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("card")
        sidebar.setFixedWidth(180)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(8, 8, 8, 8)
        sl.setSpacing(4)

        items = [
            ("monitor", f"📊  {_('Monitor')}"),
            ("curve", f"📈  {_('Curve Editor')}"),
            ("presets", f"⚡  {_('Presets')}"),
            ("stress", f"🧪  {_('Stress Test')}"),
            ("games", f"🎮  {_('Game Detection')}"),
        ]

        self._nav_buttons = {}
        for name, label in items:
            btn = QPushButton(label)
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 10px 14px;
                    border-radius: 6px;
                    border: none;
                    background: transparent;
                    color: #8b949e;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #21262d;
                    color: #c9d1d9;
                }
                QPushButton:checked {
                    background-color: #1f6feb22;
                    color: #58a6ff;
                    font-weight: 600;
                }
            """)
            btn.clicked.connect(lambda checked, n=name: self._navigate(n))
            sl.addWidget(btn)
            self._nav_buttons[name] = btn

        sl.addStretch()

        reset_btn = QPushButton(f"🔄  {_('Reset GPU')}")
        reset_btn.setObjectName("dangerButton")
        reset_btn.clicked.connect(self._reset_gpu)
        sl.addWidget(reset_btn)

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
