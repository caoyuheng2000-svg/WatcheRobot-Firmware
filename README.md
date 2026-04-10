# WatcheRobot Firmware

> ESP32-S3 based AI assistant robot firmware — voice interaction, servo control, LVGL display, BLE, and camera streaming.

[![Build](https://github.com/Ro-In-AI/WatcheRobot-Firmware/actions/workflows/build.yml/badge.svg)](https://github.com/Ro-In-AI/WatcheRobot-Firmware/actions/workflows/build.yml)
[![License: Apache-2.0](https://img.shields.io/badge/Firmware-Apache--2.0-blue.svg)](LICENSE)
[![ESP-IDF](https://img.shields.io/badge/ESP--IDF-v5.2.1-green.svg)](https://docs.espressif.com/projects/esp-idf/en/v5.2.1/)
[![Target](https://img.shields.io/badge/Target-ESP32--S3-orange.svg)](https://www.espressif.com/en/products/socs/esp32-s3)

---

## What is WatcheRobot?

WatcheRobot is an open-source AI assistant robot built on the **SenseCAP Watcher** hardware (ESP32-S3 + Himax vision AI). It integrates:

- 🎙️ **Voice interaction** — offline wake word + cloud ASR/LLM/TTS pipeline
- 🤖 **Servo gimbal** — dual-axis direct GPIO PWM control (no secondary MCU)
- 📺 **LVGL display** — 30fps animated expressions (412×412 QSPI LCD)
- 📡 **BLE** — phone control + WiFi provisioning
- 📷 **Camera streaming** — Himax JPEG frames over WebSocket
- 🔄 **OTA** — firmware updates over HTTP, animation assets over WebSocket

### Current Release Track

- Current release target: `v0.2.4`
- `v0.2.4` is the recommended formal baseline for the GIF-authored animation system on the ESP32-S3 mainline:
  - PNG-sequence runtime playback has been replaced by SD-backed `animpack` streaming generated from GIF source assets
  - Boot animation now runs from `/sdcard/anim/boot.animpack`, and missing SD animation resources fail into a deterministic boot error path
  - UI text remains visible above animated backgrounds, and runtime GIF switches no longer flash white or show `No data`
  - Cloud TTS playback now runs through a dedicated buffered worker instead of depending directly on WebSocket receive timing
  - Runtime memory diagnostics now rely on lifecycle snapshots instead of a permanent background monitor task, which reduces steady-state heap pressure
  - Action handoff latency is improved so behavior changes can preempt servo and expression playback more cleanly during mixed voice/control activity
  - The packaged behavior actions still use the existing legacy SPIFFS action JSON set under `firmware/s3/spiffs/actions`
  - The branch still carries the reconnect hardening, Bluetooth feedback, cached WebSocket resume, audio recovery work from `v0.1.7`, and the packaged Windows flashing workflow added on main in `v0.1.8`
- This release is suitable for repeated validation of SD-backed animation startup, on-screen text behavior, runtime state switching, buffered audio playback, and mixed local/cloud UI transitions
- The current packaged GIF resource set includes 10 generated animation types; `custom1` and `custom2` are not included yet because their source GIFs are not present
- Release deliverables now include both a firmware flash bundle and an SD-card animation asset bundle under `firmware/s3/release/v0.2.4`
- Windows release ZIP flashing remains available through `tools\flash-release.cmd` and `tools\win_flasher` for packaged validation workflows
- After `v0.2.4`, the main remaining roadmap work is:
  - dual OTA partitioning and full firmware OTA
  - camera runtime stability and recovery hardening
  - future animation delivery refinement such as animation OTA

---

## Hardware Requirements

| Component | Details |
|-----------|---------|
| **Main board** | SenseCAP Watcher (ESP32-S3, 16MB Flash, 8MB PSRAM) |
| **Display** | SPD2010 QSPI LCD, 412×412 |
| **Microphone** | I2S DMIC (onboard) |
| **Speaker** | I2S amplifier (onboard) |
| **Camera** | Himax HX6538 (onboard, via SSCMA protocol) |
| **Servos** | Standard PWM servo × 2, connected to GPIO 19 (X) and GPIO 20 (Y) |
| **Cloud server** | PC running `watcher-server` (Python WebSocket) |

---

## Quick Start

### 1. Prerequisites

```powershell
# Install ESP-IDF v5.2.1
# https://docs.espressif.com/projects/esp-idf/en/v5.2.1/get-started/

# Activate ESP-IDF environment (Windows PowerShell)
C:\Espressif\frameworks\esp-idf-v5.2.1\export.ps1
```

### 2. Clone & Configure

```bash
git clone https://github.com/Ro-In-AI/WatcheRobot-Firmware.git
cd WatcheRobot-Firmware/firmware/s3

# Edit server settings if needed. Wi-Fi credentials are no longer baked into firmware;
# first-time setup should use BLE provisioning or previously stored STA credentials.
idf.py menuconfig
# Navigate: Watcher Configuration → Server / BLE
```

### 3. Build & Flash

```bash
idf.py set-target esp32s3
idf.py build
idf.py -p COM3 flash monitor
```

### Windows Release ZIP Flasher

For packaged Windows flashing without entering the ESP-IDF build flow:

```powershell
cd D:\GithubRep\WatcheRobot-Firmware
python -m pip install -r tools\win_flasher\requirements.txt
tools\flash-release.cmd
```

This CLI scans `firmware\s3\release\` for the newest release ZIP, lets you choose a COM port, parses `flash_args.txt`, and flashes the package with `esptool`.

Useful commands:

```powershell
python -m tools.win_flasher list-releases
python -m tools.win_flasher list-ports
python -m tools.win_flasher flash --port COM41
```

Full usage is documented in [docs/development/windows-release-flasher.md](docs/development/windows-release-flasher.md).

### 4. Start the Cloud Server

```bash
# In a separate terminal (Python 3.10+)
cd watcher-server      # see: https://github.com/Ro-In-AI/watcher-server
pip install -r requirements.txt
python src/main.py
```

> The device auto-discovers the server via UDP broadcast on the local network.

---

## Architecture Overview

```
┌────────────────────────────────────────────────────┐
│              ESP32-S3 (WatcheRobot Firmware)        │
│                                                     │
│  services/  voice_service  anim_service  ota_service│
│             camera_service                          │
│  protocols/ ws_client      discovery    ble_service │
│  hal/       hal_audio      hal_display  hal_servo   │
│             hal_camera                              │
│  drivers/   bsp_watcher                             │
└──────────────────┬─────────────────────────────────┘
                   │ WebSocket (WiFi)
                   ▼
┌────────────────────────────────────────────────────┐
│              Cloud Server (Python)                  │
│   ASR (Aliyun) → LLM (Claude) → TTS (Volcengine)  │
└────────────────────────────────────────────────────┘
```

See [docs/architecture.md](docs/architecture.md) for the full system design.

---

## Repository Structure

```
WatcheRobot-Firmware/
├── firmware/s3/           # ESP32-S3 firmware (main development)
│   ├── main/              # App entry point (≤100 lines)
│   └── components/        # Layered components (drivers/hal/protocols/services/utils)
├── firmware/mcu/          # ⚠️ DEPRECATED — kept for reference only
├── hardware/              # Hardware design files (KiCad)
├── docs/                  # Documentation
├── tools/                 # PC-side helper scripts
└── .github/               # CI/CD and issue templates
```

---

## Documentation

### Getting Started

| Document | Description |
|----------|-------------|
| [docs/getting-started.md](docs/getting-started.md) | Full setup guide |
| [docs/roadmap.md](docs/roadmap.md) | Current status, completed tracks, and next priorities synchronized to `v0.2.4` |

### Architecture & Design

| Document | Description |
|----------|-------------|
| [docs/architecture.md](docs/architecture.md) | System architecture & component design |
| [docs/hardware/gpio-mapping.md](docs/hardware/gpio-mapping.md) | GPIO pin assignment |
| [docs/hardware/bom.md](docs/hardware/bom.md) | Bill of materials |

### Protocols

| Document | Description |
|----------|-------------|
| [docs/protocol/websocket-protocol.md](docs/protocol/websocket-protocol.md) | WebSocket protocol v2.3 |
| [docs/protocol/voice-stream.md](docs/protocol/voice-stream.md) | Audio streaming specification |

### Development

| Document | Description |
|----------|-------------|
| [docs/development/known-issues.md](docs/development/known-issues.md) | Known issues & workarounds |
| [docs/development/testing.md](docs/development/testing.md) | Testing guide |
| [docs/development/codex-multi-device-workflow.md](docs/development/codex-multi-device-workflow.md) | Codex lane workflow for multi-feature / multi-device development |
| [docs/development/windows-release-flasher.md](docs/development/windows-release-flasher.md) | Windows CLI flasher for packaged release ZIP files |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

---

## License

- **Firmware**: [Apache License 2.0](LICENSE)
- **Hardware designs**: [CERN-OHL-P 2.0](hardware/LICENSE) *(permissive open hardware)*

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development environment setup, code style, and PR process.
