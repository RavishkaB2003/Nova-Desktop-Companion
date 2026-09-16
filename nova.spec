# -*- mode: python ; coding: utf-8 -*-
"""
Project NOVA - PyInstaller Specification
Builds a standalone, portable Windows x64 distribution bundle containing
all runtime dependencies, offline Kaldi speech models, and SVG vector assets.
"""

import os
import sys

import importlib.util
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Project paths
project_root = os.path.abspath(os.getcwd())

datas = [
    (os.path.join(project_root, 'assets'), 'assets'),
    (os.path.join(project_root, 'models', 'vosk-model-small-en-us-0.15'), os.path.join('models', 'vosk-model-small-en-us-0.15')),
]

# Explicitly collect Vosk package, DLLs, and transcriber modules
vosk_datas, vosk_binaries, vosk_hiddenimports = collect_all('vosk')
datas += vosk_datas

# Ensure site-packages/vosk is bundled into 'vosk'
vosk_spec = importlib.util.find_spec('vosk')
if vosk_spec and vosk_spec.origin:
    vosk_site_dir = os.path.dirname(vosk_spec.origin)
    datas.append((vosk_site_dir, 'vosk'))

binaries = list(vosk_binaries)

hiddenimports = [
    'pystray',
    'pystray._win32',
    'comtypes',
    'comtypes.stream',
    'sounddevice',
    'scipy',
    'scipy.signal',
    'scipy.signal._sosfilt',
    'scipy.special',
    'vosk',
    'PIL',
    'PIL.Image',
    'PIL.ImageTk',
    'fitz',
    'pymupdf',
    'cv2',
    'uiautomation',
    'win32gui',
    'win32con',
    'win32api',
    'win32process',
    'ctypes',
    'ctypes.wintypes',
    'tkinter',
    'tkinter.ttk',
] + vosk_hiddenimports

# Exclude unnecessary heavy scientific, AI, and notebook libraries present in dev environment
# NOTE: Do NOT exclude 'unittest' because numpy.testing and scipy internally reference it.
excludes = [
    'torch',
    'torchvision',
    'torchaudio',
    'matplotlib',
    'pandas',
    'IPython',
    'ipykernel',
    'jupyter',
    'notebook',
    'openai',
    'gradio',
    'seaborn',
    'sklearn',
    'tensorboard',
    'pytest',
]

a = Analysis(
    [os.path.join('nova', '__main__.py')],
    pathex=[project_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='nova',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='nova',
)
