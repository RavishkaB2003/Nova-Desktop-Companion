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
- **Continuous Cursor Glider**: Say `"Glide"` to enter continuous cursor movement mode with voice-directed steering (`"Left"`, `"Right"`, `"Up"`, `"Down"`). Ideal for drag-and-drop, painting, and precise positioning.
- **Fluid Mouse Wheel Scrolling**: Say `"Scroll down"` or `"Scroll up"` for continuous hands-free scrolling with voice speed control (`"Faster"`, `"Slower"`).
- **Continuous Voice Dictation**: Say `"Type"` to enter direct text-injection mode, streaming speech directly into the active input focus with real-time feedback.
- **Desktop App Launching & Window Management**: Voice-launch browsers, Paint, File Explorer, and YouTube searches. Switch windows, close windows, and show desktop—all hands-free.
- **Emergency Safety Net**: Instant emergency stop via spoken `"Halt"`, `"Cancel"`, or the physical `Escape` / `Ctrl+Shift+Q` global hotkeys to dismiss all overlays and abort active cursor motion.
- **Hardware-Efficient & Non-Intrusive**: Native Win32 integration (`WS_EX_LAYERED`, `WS_EX_TRANSPARENT`, `WS_EX_NOACTIVATE`) ensures overlay graphics never steal focus or disrupt underlying desktop workflows. Operates at `<35 MB` RAM usage.

---

## System Requirements

- **Operating System**: Windows 10 (Build 19041 or higher) or Windows 11 (64-bit).
- **Processor**: 64-bit x86 multi-core processor (Intel Core i3 / AMD Ryzen 3 or higher).
- **RAM**: 4 GB minimum (App consumes <35 MB RAM).
- **Audio Input**: Standard USB microphone or integrated microphone array.
- **Disk Space**: ~120 MB (including local Vosk acoustic model).

---

## Download Pre-Built Release

If you just want to run NOVA without setting up Python:

1. Go to the [**Releases**](https://github.com/RavishkaB2003/Nova-Desktop-Companion/releases) page.
2. Download the latest `NOVA-Desktop-Companion-v1.0.0-win64.zip`.
3. Extract the zip to any folder.
4. Run `nova\nova.exe`.
5. NOVA starts silently in the **system tray** — right-click the tray icon to activate the mascot.

> **No Python, no installation, no internet required.** The zip includes the offline speech model, all assets, and all dependencies.

Verify download integrity with the included `SHA256SUMS.txt`.

---

## Quick Start (From Source)

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

NOVA starts silently in the **system tray**. Right-click the tray icon and select **"Activate Mascot"** to bring Nova on screen, then say **"Hey Nova"** or **"Wake up"** to begin.

### CLI Flags

```bash
python -m nova                     # Normal launch
python -m nova --debug             # Verbose debug logging
python -m nova --reduced-motion    # Disable ambient animations (WCAG 2.2 AA)
python -m nova --model-path PATH   # Custom Vosk model directory
python -m nova --device NAME       # Specific microphone device ID or name
python -m nova --check             # Subsystem self-check (model, assets, audio) and exit
```

---

## Voice Command Reference

### Wake & Sleep

| Spoken Command | Function |
|---|---|
| **"Hey Nova"** / **"Wake up"** / **"Wake up Nova"** | Wake companion into active listening mode |
| **"Sleep"** / **"Go to sleep"** | Enter low-power standby mode |
| **"Activate"** | Show mascot from system tray background |
| **"Deactivate"** | Hide mascot back to system tray background |

### Tag & Snap (Target Snapping)

| Spoken Command | Function |
|---|---|
| **"Tag"** / **"Scan"** | Scan focused window and overlay numbered badges (1–9) |
| **"One"** through **"Nine"** | Aim cursor at the corresponding target badge |
| **"Click"** | Confirm click on aimed target (or in-place click if no target) |
| **"Double click"** / **"Right click"** / **"Middle click"** / **"Triple click"** | Modified click on aimed target |
| **"Double [digit]"** / **"Right [digit]"** | Instant compound snap-and-modified-click |
| **"Next"** / **"More"** | Navigate to next badge page |
| **"Back"** / **"Previous"** | Navigate to previous badge page |

### Crosshair Laser Scanner

| Spoken Command | Function |
|---|---|
| **"Crosshair"** / **"Scanner"** / **"Laser"** | Launch dual-axis laser sweep across screen |
| **"Lock"** / **"Freeze"** / **"Mark"** | Phase 1: Lock horizontal line, start vertical sweep |
| **"Hit"** / **"Click"** | Phase 2: Lock vertical line, snap cursor to intersection, click |
| **"Slow"** / **"Fast"** / **"Normal"** | Adjust sweep speed (100 / 320 / 180 px/s) |
| **"Left"** / **"Right"** / **"Up"** / **"Down"** | Reverse sweep direction mid-scan |

### Continuous Cursor Glider

| Spoken Command | Function |
|---|---|
| **"Glide"** / **"Canvas"** / **"Draw"** / **"Move"** | Enter continuous cursor glide mode |
| **"Glide left"** / **"Glide right"** / **"Glide up"** / **"Glide down"** | Glide in a specific direction |
| **"Left"** / **"Right"** / **"Up"** / **"Down"** *(during glide)* | Steer glide heading direction |
| **"Hit"** / **"Click"** *(during glide)* | Halt glide and execute click |
| **"Stop"** / **"Halt"** *(during glide)* | Halt glide at current position |

### Fluid Scrolling

| Spoken Command | Function |
|---|---|
| **"Scroll down"** / **"Scroll"** | Start continuous downward scroll |
| **"Scroll up"** | Start continuous upward scroll |
| **"Up"** / **"Down"** *(while scrolling)* | Reverse scroll direction |
| **"Faster"** / **"Fast"** *(while scrolling)* | Increase scroll speed |
| **"Slower"** / **"Slow"** *(while scrolling)* | Decrease scroll speed |
| **"Stop"** *(while scrolling)* | Stop scrolling |

### Voice Dictation

| Spoken Command | Function |
|---|---|
| **"Type"** / **"Dictate"** | Enter free-text dictation mode |
| *(speak freely)* | Text is streamed directly into the active input field |
| **"Done"** / **"Stop"** / **"Cancel"** *(during dictation)* | Exit dictation mode |
| **"Enter"** *(during dictation)* | Press the Enter key |
| **"Backspace"** / **"Delete"** *(during dictation)* | Press the Backspace key |
| **"Click"** *(during dictation)* | Commit text, exit dictation, and click |

### Cursor Nudging (in Idle Active)

| Spoken Command | Function |
|---|---|
| **"Up"** / **"Down"** / **"Left"** / **"Right"** | Nudge cursor 65 px (repeating within 1.2s applies kinetic momentum: 2×, 3.5×) |
| **"Nudge up"** / **"Tap left"** / etc. | Micro-nudge cursor 18 px |
| **"Jump up"** / **"Jump right"** / etc. | Large jump 160 px |
| **"Up up up"** *(chained in single utterance)* | Multi-step nudge (65 px × word count) |
| **"Enter"** *(in idle)* | Press Enter key |
| **"Backspace"** *(in idle)* | Press Backspace key |

### Desktop App Launchers

| Spoken Command | Function |
|---|---|
| **"Open browser"** / **"Browser"** | Launch Edge or Chrome with accessibility pre-warmed |
| **"Open paint"** / **"Paint"** | Launch Windows Paint |
| **"Open explorer"** / **"Open this PC"** / **"Explorer"** | Launch Windows File Explorer |
| **"Open YouTube"** / **"YouTube"** | Open YouTube homepage in browser |
| **"Play on YouTube [query]"** | Search YouTube for spoken query (two-phase dictation if query unclear) |

### Window Management

| Spoken Command | Function |
|---|---|
| **"Switch window"** | Alt+Tab to switch active window |
| **"Close window"** | Alt+F4 to close active window |
| **"Show desktop"** | Win+D to toggle desktop visibility |

### Control Panel

| Spoken Command | Function |
|---|---|
| **"Menu"** / **"Show menu"** / **"Help"** / **"Commands"** | Open on-screen command cheat sheet |
| **"Close menu"** | Close command cheat sheet |

### Emergency Stop

| Command | Function |
|---|---|
| **"Halt"** / **"Cancel"** | Instant voice emergency stop — dismiss all overlays, abort motion |
| **"Close"** / **"Dismiss"** / **"Clear"** / **"Exit"** / **"Hide"** | Dismiss active overlays |
| `Escape` key *(physical)* | Global hotkey emergency stop |
| `Ctrl+Shift+Q` *(physical)* | Global hotkey emergency stop |

---

## Project Structure

```
Nova-Desktop-Companion/
├── assets/                  # Production visual assets
│   ├── hud/                 # Target badges, reticles, pagination pills (4 SVGs)
│   └── mascot/              # 256×256 SVG vectors for all 7 mascot states
├── models/                  # Offline Vosk acoustic model storage (downloaded)
│   └── .gitkeep
├── nova/                    # Main application package
│   ├── __main__.py          # Application entry point & orchestrator
│   ├── audio/               # Audio capture, DSP impulse detection, ducking
│   ├── automation/          # UI Automation crawler, system shortcuts, vision
│   ├── core/                # State machine, coordinator, glider, safety
│   ├── input/               # Win32 mouse driver, scroll controller, text injector
│   ├── speech/              # Vosk engine, dictation pipeline
│   └── ui/                  # Mascot widget, HUD overlay, crosshair, tray, control panel
├── tests/                   # Unit and integration tests
├── scripts/                 # Operational and setup automation
│   ├── download_model.py    # Offline model downloader
│   └── package_release.py   # Standalone .exe packaging & checksum generator
├── nova.spec                # PyInstaller build specification
├── requirements.txt         # Pinned production Python dependencies
└── README.md                # Documentation
```

---

## Packaging as Standalone Windows Executable

To compile Project NOVA into a standalone, portable Windows distribution with zero external Python requirements:

```powershell
pip install pyinstaller
python scripts/package_release.py
```

This automated script will:
1. Build the application using [`nova.spec`](nova.spec) via PyInstaller.
2. Verify bundled assets, Vosk acoustic model, and native DLLs.
3. Run a `--check` self-test on the compiled binary.
4. Create a portable zip: `dist/NOVA-Desktop-Companion-v1.0.0-win64.zip`.
5. Generate cryptographic checksums: `dist/SHA256SUMS.txt`.

The compiled standalone executable will be at `dist/nova/nova.exe`.

---

## Running Tests

```bash
pip install pytest
python -m pytest tests/
```

---

## Accessibility & Contrast Standards

Project NOVA is engineered in accordance with **WCAG 2.2 Level AAA** contrast standards:
- **Target Badges**: Solid obsidian `#0A0E17` background with 2px neon cyan `#00F0FF` borders and pure white `#FFFFFF` bold digits, achieving an **18.5:1** contrast ratio against all application backgrounds.
- **Glanceable Mascot**: Non-flashing, color-independent state cues (distinct facial geometries, eye shapes, and chest meter modes) complement high-contrast color indicators.
- **Per-Monitor DPI V2**: Full Per-Monitor-V2 DPI awareness prevents scaling distortion and coordinate drift across multi-monitor setups.
- **Reduced Motion**: Launch with `--reduced-motion` to disable ambient floating and motion animations in compliance with WCAG 2.2 AA `prefers-reduced-motion`.

---

## License & Intellectual Property

Proprietary and confidential. Developed specifically for client delivery. All rights reserved.