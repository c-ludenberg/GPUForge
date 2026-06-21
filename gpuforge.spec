# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['src/gpuforge/main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src/gpuforge/resources/style.qss', 'gpuforge/resources'),
        ('src/gpuforge/locale/pl/LC_MESSAGES/gpuforge.mo', 'gpuforge/locale/pl/LC_MESSAGES'),
    ],
    hiddenimports=[
        'gpuforge',
        'gpuforge.main',
        'gpuforge.backend.gpu_base',
        'gpuforge.backend.nvidia_backend',
        'gpuforge.backend.amd_backend',
        'gpuforge.ui.main_window',
        'gpuforge.ui.monitor_widget',
        'gpuforge.ui.curve_editor',
        'gpuforge.ui.presets',
        'gpuforge.ui.stress_test',
        'gpuforge.ui.game_detector',
        'gpu_stress',
        'cmdkit',
        'torch',
        'numpy',
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'pyqtgraph',
        'pynvml',
        'psutil',
        'platformdirs',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'tkinter', 'OpenGL', 'OpenGL_accelerate', 'trimesh', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='GPUForge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

app = BUNDLE(
    exe,
    name='GPUForge.app',
    icon=None,
    bundle_identifier='com.antergosnext.gpuforge',
)
