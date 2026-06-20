from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
    QFrame, QListWidget, QListWidgetItem, QMessageBox,
)
from PySide6.QtCore import Qt

from gettext import gettext as _

from gpuforge.backend.gpu_base import GPUBackend, UndervoltPreset, PRESETS_LIBRARY


class PresetsWidget(QWidget):
    def __init__(self, backend: GPUBackend, parent=None):
        super().__init__(parent)
        self._backend = backend

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel(_("Undervolt Presets"))
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        desc = QLabel(_("Select a preset to apply. Each preset adjusts clock offsets, power limits, and voltage targets."))
        desc.setStyleSheet("color: #8b949e; font-size: 12px; padding-bottom: 8px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self._preset_list = QListWidget()
        self._preset_list.setMinimumHeight(200)

        presets = [
            ("Eco", "Max efficiency, lower temps", "#3fb950"),
            ("Balanced", "Good perf with reduced power", "#d29922"),
            ("Performance", "Sustained high clocks", "#58a6ff"),
            ("Max", "Peak overclock + undervolt", "#da3633"),
        ]

        for name, description, color in presets:
            item = QListWidgetItem(f"  {name}")
            item.setData(Qt.UserRole, name.lower())
            item.setToolTip(description)
            item.setSizeHint(50, 50)
            self._preset_list.addItem(item)

        self._preset_list.setStyleSheet("""
            QListWidget::item {
                padding: 12px;
                font-size: 15px;
                font-weight: 600;
            }
        """)
        layout.addWidget(self._preset_list)

        btn_layout = QHBoxLayout()
        self._apply_btn = QPushButton(_("Apply Preset"))
        self._apply_btn.setObjectName("primaryButton")
        self._apply_btn.clicked.connect(self._apply)
        btn_layout.addWidget(self._apply_btn)

        self._reset_btn = QPushButton(_("Reset to Defaults"))
        self._reset_btn.setObjectName("dangerButton")
        self._reset_btn.clicked.connect(self._reset)
        btn_layout.addWidget(self._reset_btn)

        layout.addLayout(btn_layout)

        layout.addStretch()

    def _apply(self):
        selected = self._preset_list.currentItem()
        if not selected:
            QMessageBox.warning(self, _("No Selection"), _("Select a preset first."))
            return
        preset_name = selected.data(Qt.UserRole)
        preset = PRESETS_LIBRARY.get(preset_name)
        if not preset:
            return
        try:
            self._backend.apply_preset(0, preset)
            QMessageBox.information(self, "Applied",
                                    f"Preset '{preset.name}' applied.\n"
                                    f"Core offset: {preset.core_clock_offset:+d} MHz\n"
                                    f"Mem offset: {preset.mem_clock_offset:+d} MHz")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def _reset(self):
        try:
            self._backend.reset_to_defaults(0)
            QMessageBox.information(self, _("Reset"), _("GPU returned to default settings."))
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
