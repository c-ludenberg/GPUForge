# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['src/gpuforge/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('src/gpuforge/resources/style.qss', 'gpuforge/resources'),
        ('src/gpuforge/locale/pl/LC_MESSAGES/gpuforge.mo', 'gpuforge/locale/pl/LC_MESSAGES'),
    ],
    hiddenimports=[
        'PySide6',
        'pyqtgraph',
        'pynvml',
        'psutil',
        'platformdirs',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    console=False,
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
