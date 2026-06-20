import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QGridLayout,
    QLabel, QProgressBar, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer

from gettext import gettext as _

from gpuforge.backend.gpu_base import GPUBackend, GPUSensors

pg.setConfigOption("background", "#0d1117")
pg.setConfigOption("foreground", "#e1e4e8")
pg.setConfigOption("antialias", True)


class SensorCard(QFrame):
    def __init__(self, title: str, unit: str, color: str = "#58a6ff", parent=None):
        super().__init__(parent)
        self.setObjectName("sensorCard")
        self.setStyleSheet(f"""
            QFrame#sensorCard {{
                background-color: #11161e;
                border: 1px solid #1e2a3a;
                border-radius: 10px;
                padding: 10px 14px;
            }}
            QFrame#sensorCard:hover {{
                border-color: #28303d;
            }}
            QLabel#cardTitle {{
                font-size: 11px; font-weight: 600; color: {color};
                text-transform: uppercase; letter-spacing: 0.5px;
                background: transparent;
            }}
            QLabel#cardValue {{
                font-size: 24px; font-weight: 700; color: {color};
                background: transparent;
            }}
            QLabel#cardUnit {{
                font-size: 11px; font-weight: 500; color: #8b949e;
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("cardTitle")
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

        self._value = QLabel("--")
        self._value.setObjectName("cardValue")
        val_layout.addWidget(self._value)

        unit_label = QLabel(unit)
        unit_label.setObjectName("cardUnit")
        val_layout.addWidget(unit_label)
        val_layout.addStretch()
        layout.addLayout(val_layout)

    def set_value(self, value: float, bar_pct: float = 0):
        if value >= 1000:
            self._value.setText(f"{value:.0f}")
        elif value >= 10:
            self._value.setText(f"{value:.1f}")
        elif value >= 0.01:
            self._value.setText(f"{value:.2f}")
        else:
            self._value.setText("0")
        self._bar.setValue(int(bar_pct))


class MiniGraph(QFrame):
    def __init__(self, title: str, color: str = "#58a6ff", parent=None):
        super().__init__(parent)
        self.setObjectName("graphCard")
        self.setStyleSheet(f"""
            QFrame#graphCard {{
                background-color: #11161e;
                border: 1px solid #1e2a3a;
                border-radius: 10px;
                padding: 8px 10px;
            }}
            QLabel {{
                font-size: 11px; font-weight: 600; color: {color};
                text-transform: uppercase; letter-spacing: 0.5px;
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 2)
        layout.setSpacing(2)

        title_label = QLabel(title)
        layout.addWidget(title_label)

        self._plot = pg.PlotWidget()
        self._plot.setMinimumHeight(70)
        self._plot.setMaximumHeight(110)
        self._plot.showGrid(True, True, alpha=0.08)
        self._plot.getAxis("left").setStyle(showValues=False)
        self._plot.getAxis("bottom").setStyle(showValues=False)
        self._plot.setMenuEnabled(False)

        fill = pg.mkBrush(color + "33") if color.startswith("#") else pg.mkBrush(0, 100, 200, 50)
        pen = pg.mkPen(color=color, width=2)
        self._curve = self._plot.plot([], [], pen=pen, fillLevel=0, brush=fill)
        layout.addWidget(self._plot)

    def update_data(self, data: list):
        self._curve.setData(data)


class MonitorWidget(QWidget):
    def __init__(self, backend: GPUBackend, parent=None):
        super().__init__(parent)
        self._backend = backend

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        title = QLabel(_("Real-Time Monitor"))
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #f0f6fc;")
        layout.addWidget(title)

        tiles = QGridLayout()
        tiles.setSpacing(8)

        self._temp = SensorCard(_("GPU Temp"), "°C", "#f85149")
        tiles.addWidget(self._temp, 0, 0)

        self._clock = SensorCard(_("GPU Clock"), "MHz", "#58a6ff")
        tiles.addWidget(self._clock, 0, 1)

        self._mem = SensorCard(_("Memory"), "MHz", "#d2a8ff")
        tiles.addWidget(self._mem, 0, 2)

        self._power = SensorCard(_("Power"), "W", "#d29922")
        tiles.addWidget(self._power, 0, 3)

        self._fan = SensorCard(_("Fan"), "%", "#79c0ff")
        tiles.addWidget(self._fan, 0, 4)

        self._util = SensorCard(_("Util"), "%", "#3fb950")
        tiles.addWidget(self._util, 0, 5)

        layout.addLayout(tiles)

        graphs = QHBoxLayout()
        graphs.setSpacing(8)

        self._temp_graph = MiniGraph(_("Temperature"), "#f85149")
        graphs.addWidget(self._temp_graph)

        self._clock_graph = MiniGraph(_("GPU Clock"), "#58a6ff")
        graphs.addWidget(self._clock_graph)

        self._power_graph = MiniGraph(_("Power"), "#d29922")
        graphs.addWidget(self._power_graph)

        layout.addLayout(graphs, 1)

        self._data = {"temps": [], "clocks": [], "powers": []}
        self._timer = QTimer()
        self._timer.timeout.connect(self._poll)
        self._timer.start(500)

    def _poll(self):
        try:
            sensors = self._backend.get_sensors(0)
        except Exception:
            return

        self._temp.set_value(sensors.temp_core)
        self._clock.set_value(sensors.gpu_clock)
        self._mem.set_value(sensors.mem_clock)
        self._power.set_value(sensors.power_watts,
                              bar_pct=(sensors.power_watts / max(sensors.power_max_watts, 1)) * 100)
        self._fan.set_value(sensors.fan_speed_pct)
        self._util.set_value(sensors.utilization_pct, bar_pct=sensors.utilization_pct)

        self._data["temps"].append(sensors.temp_core)
        self._data["clocks"].append(sensors.gpu_clock)
        self._data["powers"].append(sensors.power_watts)
        if len(self._data["temps"]) > 200:
            for k in self._data:
                self._data[k] = self._data[k][-200:]

        if len(self._data["temps"]) > 2:
            self._temp_graph.update_data(list(self._data["temps"]))
            self._clock_graph.update_data(list(self._data["clocks"]))
            self._power_graph.update_data(list(self._data["powers"]))
