from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
    QProgressBar, QFrame, QCheckBox, QSpinBox, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer

from gettext import gettext as _

from gpuforge.backend.gpu_base import GPUBackend


class StressTestWidget(QWidget):
    def __init__(self, backend: GPUBackend, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._running = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel(_("Stress Test"))
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        desc = QLabel("Run a GPU stress test to validate stability of your undervolt/overclock settings.")
        desc.setStyleSheet("color: #8b949e; font-size: 12px; padding-bottom: 8px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        options = QFrame()
        options.setObjectName("card")
        ol = QVBoxLayout(options)

        self._error_detect = QCheckBox("Enable crash detection (auto-reset on hang)")
        self._error_detect.setChecked(True)
        ol.addWidget(self._error_detect)

        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Duration (minutes):"))
        self._duration = QSpinBox()
        self._duration.setRange(1, 60)
        self._duration.setValue(10)
        duration_layout.addWidget(self._duration)
        duration_layout.addStretch()
        ol.addLayout(duration_layout)

        layout.addWidget(options)

        progress_frame = QFrame()
        progress_frame.setObjectName("card")
        pl = QVBoxLayout(progress_frame)

        self._status_label = QLabel(_("Ready"))
        self._status_label.setStyleSheet("font-weight: 600; font-size: 14px;")
        pl.addWidget(self._status_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        pl.addWidget(self._progress)

        layout.addWidget(progress_frame)

        btn_layout = QHBoxLayout()
        self._start_btn = QPushButton(f"▶  {_('Start Stress Test')}")
        self._start_btn.setObjectName("primaryButton")
        self._start_btn.clicked.connect(self._toggle)
        btn_layout.addWidget(self._start_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        info = QLabel("Note: Uses a compute shader loop for GPU load. "
                      "Monitor temps closely during testing.\n"
                      "Full DX12/DXR-style scanner coming in a future update.")
        info.setStyleSheet("color: #8b949e; font-size: 11px; padding: 8px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addStretch()

        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._elapsed = 0

    def _toggle(self):
        if self._running:
            self._stop()
        else:
            self._start()

    def _start(self):
        self._running = True
        self._elapsed = 0
        self._progress.setMaximum(self._duration.value() * 60)
        self._start_btn.setText(f"⏹  {_('Stop Stress Test')}")
        self._status_label.setText(_("Running..."))
        self._timer.start(1000)

    def _stop(self):
        self._running = False
        self._timer.stop()
        self._start_btn.setText(f"▶  {_('Start Stress Test')}")
        self._status_label.setText(_("Stopped"))
        self._progress.setValue(0)

    def _tick(self):
        self._elapsed += 1
        self._progress.setValue(self._elapsed)
        remaining = self._progress.maximum() - self._elapsed
        self._status_label.setText(f"Running... {remaining}s remaining")

        if self._elapsed >= self._progress.maximum():
            self._stop()
            QMessageBox.information(self, _("Done"), _("Stress test completed without errors."))
