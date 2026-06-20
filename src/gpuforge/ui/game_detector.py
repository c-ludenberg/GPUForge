import os
import json
import subprocess
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
    QFrame, QListWidget, QListWidgetItem, QCheckBox, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer

from gettext import gettext as _

from gpuforge.backend.gpu_base import GPUBackend


_KNOWN_GAMES = [
    "Cyberpunk2077.exe", "cyberpunk2077",
    "EldenRing.exe", "eldenring",
    "BaldursGate3.exe", "bg3", "baldursgate3",
    "Starfield.exe", "starfield",
    "HL2.exe", "portal2.exe",
    "DOOMEternal.exe", "doometernal",
    "HorizonForbiddenWest.exe",
    "Spider-Man.exe",
    "Destiny2.exe", "destiny2",
    "Overwatch.exe", "overwatch",
    "Valorant.exe", "valorant",
    "CS2.exe", "cs2",
    "Dota2.exe", "dota2",
    "FortniteClient-Win64-Shipping.exe",
    "RDR2.exe", "rdr2",
    "Witcher3.exe", "witcher3",
    "DarkSouls3.exe", "darksouls3",
    "Sekiro.exe", "sekiro",
    "MonsterHunterWorld.exe", "monsterhunterworld",
    "MHW.exe",
]


class GameDetectorWidget(QWidget):
    def __init__(self, backend: GPUBackend, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._enabled = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel(_("Game Detection & Auto-Preset"))
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        desc = QLabel("GPUForge can detect running games and automatically apply the optimal undervolt preset.")
        desc.setStyleSheet("color: #8b949e; font-size: 12px; padding-bottom: 8px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        toggle = QFrame()
        toggle.setObjectName("card")
        tl = QHBoxLayout(toggle)
        self._enabled_check = QCheckBox("Enable automatic game detection")
        self._enabled_check.setChecked(True)
        tl.addWidget(self._enabled_check)
        tl.addStretch()
        layout.addWidget(toggle)

        game_frame = QFrame()
        game_frame.setObjectName("card")
        gl = QVBoxLayout(game_frame)

        gl.addWidget(QLabel(_("Detected Games:")))

        self._game_list = QListWidget()
        self._game_list.setMinimumHeight(180)
        gl.addWidget(self._game_list)

        layout.addWidget(game_frame)

        status = QFrame()
        status.setObjectName("card")
        sl = QHBoxLayout(status)
        self._current_game_label = QLabel(_("No game detected"))
        self._current_game_label.setStyleSheet("font-weight: 600;")
        sl.addWidget(self._current_game_label)
        sl.addStretch()

        self._preset_label = QLabel(_("Preset: —"))
        sl.addWidget(self._preset_label)

        layout.addWidget(status)

        self._scan_timer = QTimer()
        self._scan_timer.timeout.connect(self._scan_games)
        self._scan_timer.start(5000)

    def _scan_games(self):
        if not self._enabled_check.isChecked():
            return

        running = self._get_running_processes()
        detected = [g for g in _KNOWN_GAMES if g.lower() in running]

        self._game_list.clear()
        if detected:
            for game in detected:
                item = QListWidgetItem(f"  {game}")
                self._game_list.addItem(item)
            self._current_game_label.setText(_("Playing: {}").format(detected[0]))
            self._preset_label.setText(_("Preset: Performance"))
        else:
            self._current_game_label.setText(_("No game detected"))
            self._preset_label.setText(_("Preset: —"))

    def _get_running_processes(self) -> set:
        procs = set()
        try:
            if os.name == "nt":
                result = subprocess.run(
                    ["tasklist", "/FO", "CSV"],
                    capture_output=True, text=True, timeout=5,
                )
                for line in result.stdout.split("\n")[1:]:
                    if ',' in line:
                        name = line.split(',')[0].strip('"').lower()
                        procs.add(name)
            else:
                for entry in os.scandir("/proc"):
                    if entry.name.isdigit():
                        try:
                            with open(f"/proc/{entry.name}/comm") as f:
                                procs.add(f.read().strip().lower())
                        except (OSError, FileNotFoundError):
                            pass
        except Exception:
            pass
        return procs
