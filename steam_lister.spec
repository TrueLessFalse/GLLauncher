# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None
project_root = Path(SPECPATH).resolve()

a = Analysis(
    [str(project_root / "app.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "PIL.ImageTk", "PIL._tkinter_finder", "psutil",
        "requests", "bs4", "lxml", "lxml.etree",
        "steam_api", "download_list", "image_cache", "config",
        "applist_io", "greenluma", "greenluma_setup",
        "tutorial", "updater", "greenluma_version",
        "app_updater", "theme",
    ],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["playwright", "playwright_stealth", "matplotlib", "numpy", "pandas", "PyQt5", "PyQt6", "PySide2", "PySide6", "unittest", "pydoc", "doctest", "test"],
    win_no_prefer_redirects=False, win_private_assemblies=False,
    cipher=block_cipher, noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name="GLLauncher",
    debug=False, bootloader_ignore_signals=False, strip=False,
    upx=True, upx_exclude=[], runtime_tmpdir=None,
    console=False, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None,
    codesign_identity=None, entitlements_file=None,
)
