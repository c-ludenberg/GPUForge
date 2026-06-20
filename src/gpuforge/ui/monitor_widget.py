import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QGridLayout,
    QLabel, QProgressBar, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from gettext import gettext as _

from gpuforge.backend.gpu_base import GPUBackend, GPUSensors
from gpuforge.backend.monitor import MonitorController

pg.setConfigOption("background", "#0d1117")
pg.setConfigOption("foreground", "#e1e4e8")
pg.setConfigOption("antialias", True)


class SensorCard(QFrame):
    def __init__(self, title: str, unit: str, color: str = "#58a6ff", parent=None):
        super().__init__(parent)
        self.setObjectName("sensorCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("cardTitle")
        self._title_label.setStyleSheet(f"color: {color};")
        header.addWidget(self._title_label)

        header.addStretch()

        self._bar = QProgressBar()
        self._bar.setMaximumWidth(48)
        self._bar.setMaximumHeight(4)
        self._bar.setObjectName("utilBar")
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        header.addWidget(self._bar)

        layout.addLayout(header)

        val_layout = QHBoxLayout()
        val_layout.setSpacing(4)

        self._value_label = QLabel("--")
        self._value_label.setObjectName("cardValue")
        self._value_label.setStyleSheet(f"color: {color};")
        val_layout.addWidget(self._value_label)

        self._unit_label = QLabel(unit)
        self._unit_label.setObjectName("cardUnit")
        val_layout.addWidget(self._unit_label)

        val_layout.addStretch()
        layout.addLayout(val_layout)

    def set_value(self, value: float, bar_pct: float = 0):
        if abs(value) < 0.01 and value != 0:
            self._value_label.setText(f"{value:.1f}")
        elif value >= 1000:
            self._value_label.setText(f"{value:.0f}")
        elif value >= 10:
            self._value_label.setText(f"{value:.1f}")
        elif value > 0:
            self._value_label.setText(f"{value:.2f}")
        else:
            self._value_label.setText("0")
        self._bar.setValue(int(bar_pct))


class MiniGraph(QFrame):
    def __init__(self, title: str, color: str = "#58a6ff", parent=None):
        super().__init__(parent)
        self.setObjectName("graphCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 2)
        layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {color};")
        layout.addWidget(title_label)

        self._plot = pg.PlotWidget()
        self._plot.setMinimumHeight(70)
        self._plot.setMaximumHeight(110)
        self._plot.showGrid(True, True, alpha=0.08)
        self._plot.getAxis("left").setStyle(showValues=False)
        self._plot.getAxis("bottom").setStyle(showValues=False)
        self._plot.setMenuEnabled(False)

        fill_brush = pg.mkBrush(color + "33")
        pen = pg.mkPen(color=color, width=2)
        self._curve = self._plot.plot([], [], pen=pen, fillLevel=0, brush=fill_brush)

        layout.addWidget(self._plot)

    def update_data(self, data: list):
        self._curve.setData(data)


class MonitorWidget(QWidget):
    def __init__(self, backend: GPUBackend, monitor: MonitorController, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._monitor = monitor
        self._current_sensors = GPUSensors()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        title = QLabel(_("Real-Time Monitor"))
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        tiles_grid = QGridLayout()
        tiles_grid.setSpacing(8)

        self._temp_tile = SensorCard(_("GPU Temp"), "°C", "#f85149")
        tiles_grid.addWidget(self._temp_tile, 0, 0)

        self._clock_tile = SensorCard(_("GPU Clock"), "MHz", "#58a6ff")
        tiles_grid.addWidget(self._clock_tile, 0, 1)

        self._mem_tile = SensorCard(_("Memory Clock"), "MHz", "#d2a8ff")
        tiles_grid.addWidget(self._mem_tile, 0, 2)

        self._power_tile = SensorCard(_("Power Draw"), "W", "#d29922")
        tiles_grid.addWidget(self._power_tile, 0, 3)

        self._fan_tile = SensorCard(_("Fan Speed"), "%", "#79c0ff")
        tiles_grid.addWidget(self._fan_tile, 0, 4)

        self._util_tile = SensorCard(_("Utilization"), "%", "#3fb950")
        tiles_grid.addWidget(self._util_tile, 0, 5)

        layout.addLayout(tiles_grid)

        graphs_layout = QHBoxLayout()
        graphs_layout.setSpacing(8)

        self._temp_graph = MiniGraph(_("Temperature"), "#f85149")
        graphs_layout.addWidget(self._temp_graph)

        self._clock_graph = MiniGraph(_("GPU Clock"), "#58a6ff")
        graphs_layout.addWidget(self._clock_graph)

        self._power_graph = MiniGraph(_("Power"), "#d29922")
        graphs_layout.addWidget(self._power_graph)

        layout.addLayout(graphs_layout, 1)

        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._update_graphs)
        self._update_timer.start(1000)

    def update_sensors(self, sensors: GPUSensors):
        self._current_sensors = sensors
        self._temp_tile.set_value(sensors.temp_core)
        self._clock_tile.set_value(sensors.gpu_clock)
        self._mem_tile.set_value(sensors.mem_clock)
        self._power_tile.set_value(sensors.power_watts,
                                   bar_pct=(sensors.power_watts / max(sensors.power_max_watts, 1)) * 100)
        self._fan_tile.set_value(sensors.fan_speed_pct)
        self._util_tile.set_value(sensors.utilization_pct, bar_pct=sensors.utilization_pct)

    def _update_graphs(self):
        history = self._monitor.get_history(0)
        if len(history.times) < 2:
            return
        self._temp_graph.update_data(list(history.temps))
        self._clock_graph.update_data(list(history.clocks))
        self._power_graph.update_data(list(history.powers))
