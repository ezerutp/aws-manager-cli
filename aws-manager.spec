# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for aws-manager CLI (Linux)
# Generated: 2026-03-09

block_cipher = None


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.example.json', '.'),
        ('config-environment.example.json', '.'),
    ],
    hiddenimports=[
        'requests',
        'json',
        'subprocess',
        'pathlib',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'test',
        'unittest',
        'distutils',
        'setuptools',
    ],
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
    name='aws-manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
