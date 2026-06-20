from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
    QFrame, QSlider, QSpinBox, QGroupBox, QGridLayout, QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from gettext import gettext as _

from gpuforge.backend.gpu_base import GPUBackend, VoltagePoint


class CurveEditorWidget(QWidget):
    def __init__(self, backend: GPUBackend, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._points: list[VoltagePoint] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel(_("Voltage-Frequency Curve Editor"))
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        desc = QLabel(_("Drag points to adjust the voltage/frequency curve. Lower voltage at same clock = undervolt."))
        desc.setStyleSheet("color: #8b949e; font-size: 12px; padding-bottom: 8px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        controls = QGridLayout()
        controls.setSpacing(8)

        controls.addWidget(QLabel(_("Core Clock Offset:")), 0, 0)
        self._core_offset = QSpinBox()
        self._core_offset.setRange(-500, 500)
        self._core_offset.setSuffix(" MHz")
        self._core_offset.setValue(0)
        controls.addWidget(self._core_offset, 0, 1)

        controls.addWidget(QLabel(_("Memory Clock Offset:")), 1, 0)
        self._mem_offset = QSpinBox()
        self._mem_offset.setRange(-2000, 2000)
        self._mem_offset.setSuffix(" MHz")
        self._mem_offset.setValue(0)
        controls.addWidget(self._mem_offset, 1, 1)

        controls.addWidget(QLabel(_("Power Limit:")), 2, 0)
        self._power_limit = QSpinBox()
        self._power_limit.setRange(50, 600)
        self._power_limit.setSuffix(" W")
        self._power_limit.setValue(250)
        controls.addWidget(self._power_limit, 2, 1)

        self._apply_btn = QPushButton(_("Apply Offsets"))
        self._apply_btn.setObjectName("primaryButton")
        self._apply_btn.clicked.connect(self._apply)
        controls.addWidget(self._apply_btn, 3, 0, 1, 2)

        layout.addLayout(controls)

        info = QLabel("Note: Full voltage curve editor with interactive graph coming soon.\n"
                      "Clock offset controls are functional now.")
        info.setStyleSheet("color: #8b949e; font-size: 11px; padding: 12px; background: #161b22; border-radius: 6px;")
        layout.addWidget(info)

        layout.addStretch()

    def _apply(self):
        try:
            self._backend.set_clock_offsets(
                0,
                self._core_offset.value(),
                self._mem_offset.value(),
            )
            self._backend.set_power_limit(0, self._power_limit.value())
            QMessageBox.information(self, _("Applied"), _("Clock offsets and power limit applied."))
        except Exception as e:
            QMessageBox.warning(self, _("Error"), str(e))
