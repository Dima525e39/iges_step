# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


datas = [
    ("version.txt", "."),
    ("settings/default_settings.json", "settings"),
]
binaries = []
hiddenimports = [
    "app_build",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPrintSupport",
    "PySide6.QtWidgets",
    "OCC.Core.Bnd",
    "OCC.Core.BRep",
    "OCC.Core.BRepAdaptor",
    "OCC.Core.BRepBndLib",
    "OCC.Core.BRepBuilderAPI",
    "OCC.Core.BRepGProp",
    "OCC.Core.BRepTools",
    "OCC.Core.GeomAbs",
    "OCC.Core.GProp",
    "OCC.Core.IFSelect",
    "OCC.Core.IGESControl",
    "OCC.Core.Interface",
    "OCC.Core.STEPControl",
    "OCC.Core.TopAbs",
    "OCC.Core.TopExp",
    "OCC.Core.TopTools",
    "OCC.Core.TopoDS",
    "OCC.Display.backend",
    "OCC.Display.qtDisplay",
]

for package_name in ("OCC",):
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

conda_library_bin = Path(sys.prefix) / "Library" / "bin"
if conda_library_bin.exists():
    for dll_path in conda_library_bin.glob("*.dll"):
        binaries.append((str(dll_path), "."))

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="TubeCutCalculator",
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
