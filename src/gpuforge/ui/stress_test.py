import subprocess
import os
import shutil
import time
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
    QFrame, QProgressBar, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer

from gettext import gettext as _

from gpuforge.backend.gpu_base import GPUBackend

log = logging.getLogger(__name__)


class StressTestWidget(QWidget):
    def __init__(self, backend: GPUBackend, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._running = False
        self._process = None
        self._temp_history = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        title = QLabel(_("Stress Test"))
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f0f6fc;")
        layout.addWidget(title)

        desc = QLabel(_(
            "Runs glmark2 or glxgears to put real GPU load on the card.\n"
            "Temperatures are monitored during the test."
        ))
        desc.setStyleSheet("color: #8b949e; font-size: 12px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        status_frame = QFrame()
        status_frame.setObjectName("card")
        status_frame.setStyleSheet("""
            QFrame#card { background-color: #11161e; border: 1px solid #1e2a3a;
                          border-radius: 10px; padding: 14px; }
        """)
        sl = QVBoxLayout(status_frame)
        sl.setSpacing(8)

        self._status = QLabel(_("Ready"))
        self._status.setStyleSheet("font-weight: 600; font-size: 16px;")
        sl.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        sl.addWidget(self._progress)

        self._temp_label = QLabel(_("Current GPU temp: -- °C"))
        self._temp_label.setStyleSheet("color: #8b949e;")
        sl.addWidget(self._temp_label)

        self._peak_label = QLabel(_("Peak temp: -- °C"))
        self._peak_label.setStyleSheet("color: #f85149; font-weight: 600;")
        sl.addWidget(self._peak_label)

        layout.addWidget(status_frame)

        self._btn = QPushButton(f"▶  {_('Start Stress Test')}")
        self._btn.setObjectName("primaryButton")
        self._btn.setStyleSheet("""
            QPushButton { background-color: #1a7f37; border: 1px solid #2ea043;
                          color: white; border-radius: 8px; padding: 10px 20px;
                          font-size: 14px; font-weight: 600; }
            QPushButton:hover { background-color: #238636; }
            QPushButton#stopBtn { background-color: #b62324; border-color: #f85149; }
            QPushButton#stopBtn:hover { background-color: #da3633; }
        """)
        self._btn.clicked.connect(self._toggle)
        layout.addWidget(self._btn)

        layout.addStretch()

        self._monitor_timer = QTimer()
        self._monitor_timer.timeout.connect(self._monitor)
        self._elapsed = 0

    def _toggle(self):
        if self._running:
            self._stop()
        else:
            self._start()

    def _start(self):
        self._running = True
        self._elapsed = 0
        self._temp_history = []
        self._progress.setValue(0)
        self._btn.setText(f"⏹  {_('Stop Stress Test')}")
        self._btn.setObjectName("stopBtn")
        self._btn.setStyleSheet(self._btn.styleSheet())
        self._status.setText(_("Running..."))

        stressor = self._find_stressor()
        if not stressor:
            QMessageBox.warning(
                self, _("Error"),
                _("No GPU stress tool found.\nInstall glmark2 or mesa-utils (glxgears).")
            )
            self._stop()
            return

        log.info("Starting GPU stress test with: %s", stressor)
        try:
            env = os.environ.copy()
            env["DISPLAY"] = env.get("DISPLAY", ":0")
            env["__GL_SYNC_TO_VBLANK"] = "0"

            if "glmark2" in stressor:
                self._process = subprocess.Popen(
                    [stressor, "--run-forever", "--fullscreen"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    env=env,
                )
            else:
                self._process = subprocess.Popen(
                    [stressor],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    env=env,
                )
        except FileNotFoundError:
            QMessageBox.warning(self, _("Error"), _("Failed to launch stress tool."))
            self._stop()
            return

        self._monitor_timer.start(2000)

    def _stop(self):
        self._running = False
        self._monitor_timer.stop()

        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except Exception:
                self._process.kill()
        self._process = None

        self._btn.setText(f"▶  {_('Start Stress Test')}")
        self._btn.setObjectName("")
        self._status.setText(_("Stopped"))
        self._progress.setValue(0)
        self._elapsed = 0

        if self._temp_history:
            peak = max(self._temp_history)
            QMessageBox.information(
                self, _("Test Complete"),
                _("Peak GPU temperature during test: {:.0f} °C").format(peak)
            )

    def _monitor(self):
        self._elapsed += 2
        self._progress.setValue(min(self._elapsed, 120))

        try:
            sensors = self._backend.get_sensors(0)
            temp = sensors.temp_core
            self._temp_history.append(temp)

            self._temp_label.setText(_("Current GPU temp: {:.0f} °C").format(temp))
            peak = max(self._temp_history)
            self._peak_label.setText(_("Peak temp: {:.0f} °C").format(peak))
        except Exception:
            pass

        if self._elapsed >= 120:
            self._stop()
            QMessageBox.information(
                self, _("Done"),
                _("Stress test completed. GPU was loaded for 2 minutes.")
            )

    def _find_stressor(self):
        for tool in ["glmark2", "glmark2-es2", "glxgears"]:
            if shutil.which(tool):
                return tool
        return None
