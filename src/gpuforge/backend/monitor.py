import traceback
from collections import deque
from dataclasses import dataclass, field
from PySide6.QtCore import QObject, QThread, Signal, QMutex, QMutexLocker
import time
import logging

from gpuforge.backend.gpu_base import GPUBackend, GPUSensors

log = logging.getLogger(__name__)


@dataclass
class SensorHistory:
    times: deque = field(default_factory=lambda: deque(maxlen=300))
    temps: deque = field(default_factory=lambda: deque(maxlen=300))
    clocks: deque = field(default_factory=lambda: deque(maxlen=300))
    voltages: deque = field(default_factory=lambda: deque(maxlen=300))
    powers: deque = field(default_factory=lambda: deque(maxlen=300))
    fans: deque = field(default_factory=lambda: deque(maxlen=300))
    utilizations: deque = field(default_factory=lambda: deque(maxlen=300))


class MonitorWorker(QObject):
    sensors_updated = Signal(int, GPUSensors)
    gpu_count_changed = Signal(int)
    error_occurred = Signal(str)

    def __init__(self, backend: GPUBackend, interval_ms: int = 500):
        super().__init__()
        self._backend = backend
        self._interval = interval_ms / 1000.0
        self._running = False
        self._gpu_count = 0

    def run(self):
        self._running = True
        while self._running:
            try:
                count = self._backend.get_gpu_count()
                if count != self._gpu_count:
                    self._gpu_count = count
                    self.gpu_count_changed.emit(count)
                for i in range(count):
                    sensors = self._backend.get_sensors(i)
                    self.sensors_updated.emit(i, sensors)
            except Exception as e:
                self.error_occurred.emit(f"Monitor error: {e}")
                log.warning("Monitor poll failed: %s", traceback.format_exc())
            time.sleep(self._interval)

    def stop(self):
        self._running = False


class MonitorController(QObject):
    sensors_updated = Signal(int, GPUSensors)

    def __init__(self, backend: GPUBackend, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._thread: QThread = None
        self._worker: MonitorWorker = None
        self._history: dict[int, SensorHistory] = {}
        self._start_time = time.time()

    def start(self, interval_ms: int = 500):
        if self._thread is not None:
            return
        self._thread = QThread()
        self._worker = MonitorWorker(self._backend, interval_ms)
        self._worker.moveToThread(self._thread)
        self._worker.sensors_updated.connect(self._on_sensors)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def stop(self):
        if self._worker:
            self._worker.stop()
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
        self._thread = None
        self._worker = None

    def _on_sensors(self, index: int, sensors: GPUSensors):
        if index not in self._history:
            self._history[index] = SensorHistory()
        h = self._history[index]
        t = time.time() - self._start_time
        h.times.append(t)
        h.temps.append(sensors.temp_core)
        h.clocks.append(sensors.gpu_clock)
        h.voltages.append(sensors.voltage)
        h.powers.append(sensors.power_watts)
        h.fans.append(sensors.fan_speed_pct)
        h.utilizations.append(sensors.utilization_pct)
        self.sensors_updated.emit(index, sensors)

    def get_history(self, index: int) -> SensorHistory:
        if index not in self._history:
            self._history[index] = SensorHistory()
        return self._history[index]
