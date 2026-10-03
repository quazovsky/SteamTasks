# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['worthlesstask/__main__.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='worthlesstask',
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
    # The Task Manager / taskbar entry is read from the PE resources, so the app
    # icon has to be embedded here -- `--icon` on the command line is ignored when
    # a .spec is used (it is a makespec option, not a build one).
    icon='assets/worthlesstask.ico',
)
