# Development Roadmap

> WatcheRobot Firmware development status and next priorities, synchronized to the latest formal tag `v0.2.1`.

---

## Current Baseline

- Current formal release tag: `v0.2.1`
- Baseline focus: GIF-authored animation pipeline, SD-backed `animpack` runtime, BLE provisioning, and current cloud transport recovery behavior
- Current release package includes:
  - ESP32-S3 firmware flash bundle
  - SD-card animation asset bundle

---

## Status Snapshot

| Track | Description | Priority | Status |
|-------|-------------|----------|--------|
| **Track 1** | Architecture Migration | P0 | Complete |
| **Track 2** | Servo Direct Drive | P0 | Complete |
| **Track 3** | GIF / AnimPack Animation Runtime | P0 | Complete |
| **Track 4** | BLE Provisioning + Local Control | P1 | Integrated |
| **Track 5** | Camera Streaming Baseline | P1 | In Progress |
| **Track 6** | Dual OTA Partition | P1 | Pending |
| **Track 7** | Firmware OTA | P1 | Pending |
| **Track 8** | Animation OTA | P2 | Pending |
| **Track 9** | Protocol Hardening / Recovery / Security | P2 | In Progress |

---

## Completed Tracks

### Track 1: Architecture Migration

**Status**: Complete  
**Outcome**:
- Four-layer component structure is now the mainline organization model
- `main/` is reduced to a thin application entry
- Components are split across `drivers / hal / protocols / services / utils`
- ESP-IDF component manifests, dependency wiring, and documentation layout are in place

### Track 2: Servo Direct Drive

**Status**: Complete  
**Mainline status**:
- Direct GPIO PWM servo control replaced the old UART-sidecar model
- `hal_servo` is active in the current firmware
- Current runtime includes:
  - direct X/Y control
  - smooth motion path
  - mechanical protection limits
  - MS90 servo layer and startup stability fixes

### Track 3: GIF / AnimPack Animation Runtime

**Status**: Complete  
**Current baseline**:
- The old PNG-sequence runtime plan is no longer the active roadmap target
- Mainline now uses:
  - GIF as the offline authoring format
  - `animpack` as the runtime asset format
  - SD-backed animation streaming instead of full PNG hot caches
- Boot animation and runtime state animation both run from `/sdcard/anim`
- Current formal package includes 10 generated animation types

### Track 4: BLE Provisioning + Local Control

**Status**: Integrated  
**Current baseline**:
- BLE provisioning is part of the current startup and recovery path
- BLE local control can operate independently of Wi-Fi / WebSocket
- BLE-connected sessions pause background Wi-Fi / WS work to protect local control
- BLE disconnect restores Wi-Fi / WS when saved credentials exist

---

## In-Progress Tracks

### Track 5: Camera Streaming Baseline

**Status**: In Progress  
**What is already done**:
- `hal_camera` and `camera_service` are present in the current codebase
- JPEG single-image capture and MJPEG-style frame streaming have a frozen protocol baseline
- Camera control and media transport are documented against the current WebSocket + `WSPK` framing model

**What is still pending**:
- stronger runtime recovery and stats surfaces
- longer stability validation under mixed audio / BLE / cloud load
- more advanced media transport handling if the current baseline proves insufficient

### Track 9: Protocol Hardening / Recovery / Security

**Status**: In Progress  
**Current baseline already includes**:
- BLE-priority transport coordination
- cached WebSocket endpoint resume before full discovery fallback
- current `Watcher-WS-Protocol v0.1.5` freeze baseline

**Still open**:
- stronger credential / provisioning safety hardening
- tighter discovery / transport security posture
- future protocol cleanup after current integration stabilizes

---

## Pending Tracks

### Track 6: Dual OTA Partition

**Status**: Pending  
**Goal**:
- Move from the current single-app release flow to a formal `ota_0 / ota_1` partition scheme

**Why it matters**:
- Required foundation for robust rollback-safe firmware OTA
- Reduces risk when shipping remote upgrades beyond local validation

### Track 7: Firmware OTA

**Status**: Pending  
**Goal**:
- Implement the end-to-end OTA flow:
  - server notification
  - secure download
  - checksum / version validation
  - boot partition switch
  - success confirmation / rollback handling

**Current status**:
- OTA service stubs and protocol placeholders exist
- full production upgrade flow is not yet closed

### Track 8: Animation OTA

**Status**: Pending  
**Goal**:
- Support hot-swapping animation assets without manual SD bundle replacement

**Current context**:
- `v0.2.1` packages SD-backed animation assets cleanly
- but runtime remote asset update is still future work

---

## Next Priorities

### P1: Formal OTA Foundation
- Introduce dual OTA partition layout
- Close the actual firmware OTA path on top of that layout

### P1: Camera Stability and Runtime Validation
- Strengthen recovery behavior
- Add better operational observability
- Validate mixed-mode runtime behavior with audio, BLE, and cloud traffic

### P2: Animation Delivery Refinement
- Fill the missing `custom1` / `custom2` source assets
- Define whether animation OTA or SD-bundle-only delivery is the long-term product path

### P2: Protocol / Security Hardening
- Improve provisioning UX and credential handling
- Revisit discovery and transport security after current field validation settles

---

## Milestone Direction

| Target | Focus |
|--------|-------|
| **v0.2.x** | Stabilize GIF / AnimPack runtime baseline and supporting release workflow |
| **v0.3.0** | OTA-ready platform foundation |
| **v0.4.0** | Stronger camera runtime baseline and system-level integration hardening |
| **v1.0.0** | Production-oriented firmware baseline with OTA, validated media path, and refined provisioning / recovery behavior |

---

## Notes

- This roadmap intentionally reflects the current real mainline state, not the older PNG-cache animation plan.
- For the currently frozen communication baseline, see `firmware/s3/docs/COMM_PROTOCOL_FREEZE.md`.
- For the current formal animation baseline, see the `v0.2.1` release package and related GIF / AnimPack documentation.

---

*Last updated: 2026-04-09*
