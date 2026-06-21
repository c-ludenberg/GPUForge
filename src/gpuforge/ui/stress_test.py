import logging
import multiprocessing
import queue
import io
import sys
import time

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSpinBox, QTextEdit,
)
from PySide6.QtCore import Qt, QTimer, Signal

from gettext import gettext as _

from gpuforge.backend.gpu_base import GPUBackend

log = logging.getLogger(__name__)

# Module-level worker function for multiprocessing (required for PyInstaller compat)
def _stress_worker(duration: int, matrix_size: int, q):
    import sys as _sys
    from gpu_stress import GPUStress

    old_out = _sys.stdout
    _sys.stdout = io.StringIO()

    try:
        app = GPUStress(["-t", f"{duration}s", "-s", str(matrix_size)])
        app.run()
    except SystemExit:
        pass
    except Exception as e:
        print(f"FATAL: {e}", file=old_out)

    output = _sys.stdout.getvalue()
    _sys.stdout = old_out
    q.put(output)
    q.put(None)  # sentinel


class StressTestWidget(QWidget):
    closed = Signal()

    def __init__(self, backend: GPUBackend, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._process = None
        self._running = False
        self._queue = None
        self._gpu_name = ""

        try:
            info = self._backend.get_gpu_info(0)
            self._gpu_name = info.name
        except Exception:
            pass

        self._ctx = multiprocessing.get_context("spawn")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        title = QLabel(_("Stress Test"))
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f0f6fc;")
        layout.addWidget(title)

        desc = QLabel(_(
            "Runs a GPU compute stress test using gpu-stress (PyTorch).\n"
            "Matrix multiplication loop — maxes out GPU compute."
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

        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel(_("Duration (seconds):")))
        self._duration = QSpinBox()
        self._duration.setRange(10, 3600)
        self._duration.setValue(60)
        self._duration.setSuffix(" s")
        dur_row.addWidget(self._duration)
        dur_row.addStretch()
        cl.addLayout(dur_row)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel(_("Matrix size:")))
        self._matrix_size = QSpinBox()
        self._matrix_size.setRange(1000, 50000)
        self._matrix_size.setValue(10000)
        self._matrix_size.setSingleStep(1000)
        size_row.addWidget(self._matrix_size)
        size_row.addStretch()
        cl.addLayout(size_row)

        self._gpu_label = QLabel(_("GPU: {}").format(self._gpu_name or _("Unknown")))
        self._gpu_label.setStyleSheet("color: #8b949e; font-size: 12px; background: transparent;")
        cl.addWidget(self._gpu_label)

        layout.addWidget(config_frame)

        btn_row = QHBoxLayout()
        self._start_btn = QPushButton(f"\u25b6  {_('Start Stress Test')}")
        self._start_btn.setObjectName("primaryButton")
        self._start_btn.setStyleSheet("""
            QPushButton { background-color: #1a7f37; border: 1px solid #2ea043;
                          color: white; border-radius: 8px; padding: 10px 20px;
                          font-size: 14px; font-weight: 600; }
            QPushButton:hover { background-color: #238636; }
            QPushButton:disabled { background-color: #2d333b; border-color: #444c56; color: #6e7681; }
        """)
        self._start_btn.clicked.connect(self._toggle)
        btn_row.addWidget(self._start_btn)

        self._stop_btn = QPushButton(f"\u25a0  {_('Stop')}")
        self._stop_btn.setObjectName("dangerButton")
        self._stop_btn.setStyleSheet("""
            QPushButton { background-color: #da3633; border: 1px solid #f85149;
                          color: white; border-radius: 8px; padding: 10px 20px;
                          font-size: 14px; font-weight: 600; }
            QPushButton:hover { background-color: #b62324; }
            QPushButton:disabled { background-color: #2d333b; border-color: #444c56; color: #6e7681; }
        """)
        self._stop_btn.clicked.connect(self._stop)
        self._stop_btn.setEnabled(False)
        btn_row.addWidget(self._stop_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._status = QLabel(_("Ready"))
        self._status.setStyleSheet("font-weight: 600; font-size: 14px; color: #8b949e;")
        layout.addWidget(self._status)

        self._stats = QLabel()
        self._stats.setStyleSheet("color: #58a6ff; font-size: 13px;")
        layout.addWidget(self._stats)

        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setStyleSheet("""
            QTextEdit { background-color: #0d1117; color: #c9d1d9;
                        border: 1px solid #21262d; border-radius: 6px;
                        font-family: 'Consolas', 'Courier New', monospace;
                        font-size: 11px; padding: 8px; }
        """)
        self._output.setMaximumHeight(200)
        layout.addWidget(self._output)

        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll_stats)
        self._poll_timer.start(1000)

        self._output_timer = QTimer()
        self._output_timer.timeout.connect(self._poll_queue)
        self._output_timer.start(200)

        layout.addStretch()

    def _toggle(self):
        if self._running:
            self._stop()
        else:
            self._start()

    def _start(self):
        duration = self._duration.value()
        matrix_size = self._matrix_size.value()

        self._output.clear()
        self._output.append(_("Starting GPU stress test..."))
        self._output.append(_("Duration: {}s  |  Matrix size: {}x{}").format(duration, matrix_size, matrix_size))

        self._queue = multiprocessing.Queue()
        self._process = self._ctx.Process(
            target=_stress_worker,
            args=(duration, matrix_size, self._queue),
        )
        self._process.start()

        self._running = True
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._status.setText(_("Stress test running..."))
        self._status.setStyleSheet("font-weight: 600; font-size: 14px; color: #d29922;")

    def _poll_queue(self):
        if not self._running or self._queue is None:
            return
        try:
            while True:
                msg = self._queue.get_nowait()
                if msg is None:
                    self._on_finished()
                    return
                if isinstance(msg, str) and msg.strip():
                    for line in msg.strip().splitlines():
                        self._output.append(line)
        except queue.Empty:
            pass

    def _on_finished(self):
        self._running = False
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        exit_code = self._process.exitcode if self._process else 0
        if exit_code == 0:
            self._status.setText(_("Stress test completed"))
            self._status.setStyleSheet("font-weight: 600; font-size: 14px; color: #3fb950;")
        else:
            self._status.setText(_("Stress test failed (code {})").format(exit_code or 0))
            self._status.setStyleSheet("font-weight: 600; font-size: 14px; color: #f85149;")
        self._process = None
        self._queue = None

    def _stop(self):
        if self._process and self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=5)
            self._output.append(_("Stress test stopped by user"))
        self._running = False
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._status.setText(_("Stopped"))
        self._status.setStyleSheet("font-weight: 600; font-size: 14px; color: #8b949e;")
        self._process = None
        self._queue = None

    def _poll_stats(self):
        if not self._running:
            return
        try:
            s = self._backend.get_sensors(0)
            extra = ""
            if s.temp_hotspot > 0:
                extra += f"  {_('Hotspot')}: {s.temp_hotspot:.0f}C"
            if s.temp_mem > 0:
                extra += f"  {_('VRAM')}: {s.temp_mem:.0f}C"
            text = _("Temp: {:.0f}C{}  |  Load: {:.0f}%  |  Power: {:.1f}W").format(
                s.temp_core, extra, s.utilization_pct, s.power_watts
            )
            self._stats.setText(text)
        except Exception:
            pass
