# Project NOVA — Voice-Controlled Assistive Desktop Companion

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011%20x64-blue.svg)](https://microsoft.com)
[![Privacy](https://img.shields.io/badge/Privacy-100%25%20Offline%20%7C%20Zero%20Cloud-emerald.svg)]()
[![Python](https://img.shields.io/badge/Python-3.10%2B-informational.svg)](https://python.org)
[![Accessibility](https://img.shields.io/badge/Accessibility-WCAG%202.2%20AAA-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-Proprietary%20%2F%20Custom-orange.svg)]()

**NOVA** is a lightweight, 100% offline assistive desktop companion designed for Windows 10 and 11 (64-bit). It enables complete hands-free navigation, precise target snapping, hybrid mouse emulation, and voice dictation for individuals with severe motor impairments—paired with a friendly, animated Chibi robot mascot ("Nova") that provides continuous, glanceable visual feedback of system states.

---

## Key Features

- **100% Local & Privacy-Preserving**: Runs completely offline using an embedded Kaldi Vosk acoustic model. Zero network egress, zero cloud dependencies, zero audio telemetry, and zero user accounts.
- **Ambient Desktop Companion HUD**: An unobtrusive, frameless 256×256 floating Chibi robot ("Nova") positioned at the bottom-right of your screen. Provides instant visual feedback for active listening, waking, sleeping, dictating, executing, tracking, and hardware error states.
- **Real-Time Target Snapping HUD**: Say `"Tag"` or `"Scan"` to instantly project high-contrast, solid obsidian numbered badges (`1` through `9`) directly over clickable controls across active applications. Simply speak the digit to snap and click.
- **Dual-Axis Crosshair Laser Scanner**: For legacy applications, video players, or canvas games without exposed accessibility elements, say `"Crosshair"` to sweep precision dual-axis laser lines across the display. Say `"Lock"` to freeze coordinates, and `"Hit"` to execute a primary click.
- **Continuous Voice Dictation**: Say `"Type"` to enter direct text-injection mode, streaming speech directly into the active input focus with real-time feedback.
- **Emergency Safety Net**: Instant emergency stop via spoken `"Halt"`, `"Escape"`, or the physical `Escape` / `Ctrl+Shift+Q` global hotkeys to dismiss all overlays and abort active cursor motion.
- **Hardware-Efficient & Non-Intrusive**: Native Win32 integration (`WS_EX_LAYERED`, `WS_EX_TRANSPARENT`, `WS_EX_NOACTIVATE`) ensures overlay graphics never steal focus or disrupt underlying desktop workflows. Operates at `<35 MB` RAM usage.

---

## System Requirements

- **Operating System**: Windows 10 (Build 19041 or higher) or Windows 11 (64-bit).
- **Processor**: 64-bit x86 multi-core processor (Intel Core i3 / AMD Ryzen 3 or higher).
- **RAM**: 4 GB minimum (App consumes <35 MB RAM).
- **Audio Input**: Standard USB microphone or integrated microphone array.
- **Disk Space**: ~120 MB (including local Vosk acoustic model).

---

## Quick Start & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/RavishkaB2003/Nova-Desktop-Companion.git
cd Nova-Desktop-Companion
```

### 2. Set Up Python Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Download the Offline Acoustic Model
Run the built-in helper to automatically download and unpack the offline English acoustic model into `models/`:
```bash
python scripts/download_model.py
```

### 5. Launch Project NOVA
```bash
python -m nova
```

---

## Voice Command Reference

| Spoken Command | Trigger Function | Visual Feedback |
|---|---|---|
| **"Hey Nova" / "Wake up"** | Wakes companion into active listening mode | Mascot opens eyes wide with neon cyan antenna glow |
| **"Tag" / "Scan"** | Scans focused window and overlays numbered badges (`1`–`9`) | Solid obsidian pill badges appear over clickable controls |
| **"[1 to 9]"** | Snaps cursor to corresponding target and executes click | Target badge flashes emerald; mascot executes nod |
| **"Next" / "Back"** | Navigates overflow target badge pages | Updates pagination indicator pill (`Page X/Y`) |
| **"Crosshair"** | Initiates continuous dual-axis laser scanning | Emerald horizontal line sweeps top-to-bottom at 400 px/s |
| **"Lock"** | Locks horizontal coordinate and initiates vertical sweep | Horizontal line freezes; vertical line sweeps across |
| **"Hit"** | Snaps cursor to intersection reticle and clicks | Reticle flashes emerald; click executes; overlay clears |
| **"Type [text]"** | Enters free-text dictation into active input field | Mascot displays chest notepad with blinking cursor |
| **"Sleep" / "Standby"** | Places companion into low-power passive standby | Mascot closes eyes into relaxed lavender curves |
| **"Halt" / "Escape"** | Emergency stop — immediately aborts motion and clears HUD | Instant dismissal of all overlays and audio cues |

---

## Project Structure

```
Nova-Desktop-Companion/
├── assets/                  # Production visual assets
│   ├── hud/                 # Target badges, reticles, pagination pills
│   └── mascot/              # 256x256 SVG vectors for all 7 mascot companion states
├── models/                  # Offline Vosk acoustic model storage (downloaded)
│   └── .gitkeep
├── scripts/                 # Operational and setup automation scripts
│   └── download_model.py    # Offline model downloader
├── requirements.txt         # Pinned production Python dependencies
└── README.md                # Client and end-user documentation
```

---

## Packaging as Standalone Windows Executable

To compile Project NOVA into a single, self-contained Windows `.exe` bundle with zero external Python requirements:

```powershell
pip install pyinstaller
pyinstaller --noconfirm --onedir --windowed --name "Nova" `
  --add-data "assets;assets" `
  --add-data "models;models" `
  --icon "assets/hud/target_badge_default.svg" `
  nova/__main__.py
```
The compiled standalone package will be generated in `dist/Nova/Nova.exe`.

---

## Accessibility & Contrast Standards

Project NOVA is engineered in accordance with **WCAG 2.2 Level AAA** contrast standards:
- **Target Badges**: Solid obsidian `#0A0E17` background with 2px neon cyan `#00F0FF` borders and pure white `#FFFFFF` bold digits, achieving an **18.5:1** contrast ratio against all application backgrounds.
- **Glanceable Mascot**: Non-flashing, color-independent state cues (distinct facial geometries, eye shapes, and chest meter modes) complement high-contrast color indicators.
- **Per-Monitor DPI V2**: Full Per-Monitor-V2 DPI awareness prevents scaling distortion and coordinate drift across multi-monitor setups.

---

## License & Intellectual Property

Proprietary and confidential. Developed specifically for client delivery. All rights reserved.