# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['TrackNote_Launcher.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config_template.json', '.'),
        ('VERSION', '.'),
        ('credentials', 'credentials'),
        ('app.py', '.'),
        ('ui.py', '.'),
        ('data_source.py', '.'),
        ('setup_wizard.py', '.'),
        ('loading_screen.py', '.'),
        ('parsing.py', '.'),
        ('sheets_cache.py', '.'),
        ('user_data.py', '.'),
        ('firebase_sync.py', '.'),
        ('firebase_setup.py', '.'),
        ('firebase_gui_dialog.py', '.'),
        ('license_manager.py', '.'),
        ('icon.icns', '.'),
        ('firebase_config.json', '.'),
    ],
    hiddenimports=[
        'pandas',
        'openpyxl',
        'gspread',
        'google.auth',
        'google.oauth2.service_account',
        'cryptography',
        'requests',
        'ttkbootstrap',
        'tkinter',
        'threading',
        'json',
        'pathlib',
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
    [],
    exclude_binaries=True,
    name='TrackNote',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='arm64',
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TrackNote',
)

app = BUNDLE(
    coll,
    name='TrackNote.app',
    icon='icon.icns',
    bundle_identifier='com.tracknote.app',
    info_plist={
        'NSHighResolutionCapable': 'True',
        'LSMinimumSystemVersion': '10.13.0',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'NSHumanReadableCopyright': 'TrackNote',
    },
)
