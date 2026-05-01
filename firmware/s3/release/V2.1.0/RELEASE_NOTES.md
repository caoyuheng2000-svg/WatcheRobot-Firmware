## v2.1.0

Release package for the latest `main` baseline with ESP-IDF app metadata set to `V2.1.0`.

### Highlights
- Enable WakeNet wake-word flow and stabilize the wake-word memory path.
- Add TTS playback backpressure and memory fallback handling.
- Optimize ESP32-S3 memory headroom for the current runtime.
- Integrate the v2 ESP32 runtime baseline with MCU link UART, service routing, and power protocol updates.
- Refresh and extend the SD-card animation asset set to 28 generated animation types.

### Release Scope
- Current mainline ESP32-S3 firmware binary and partition payloads.
- Current SD-backed animation bundle for `/sdcard/anim`.
- Release packaging and validation assets for repeatable device flashing.

### Release Assets
This release includes two deliverables:
- `WatcheRobot-S3-V2.1.0-esp32s3.zip`
- `WatcheRobot-S3-V2.1.0-sdcard-anim.zip`

The firmware flash bundle contains:
- `bootloader.bin`
- `partition-table.bin`
- `WatcheRobot-S3.bin`
- `srmodels.bin`
- `storage.bin`

The SD-card animation bundle contains:
- `anim_manifest.bin`
- `*.animpack` for the generated state set (`boot`, `happy`, `error`, `bluetooth`, `speaking`, `listening`, `processing`, `standby`, `thinking`, `custom1`, `custom2`, `custom3`, `standby1`, `standby2`, `standby3`, `standby4`, `disconnect`, `shock`, `sunglasses`, `sad`, `get`, `smile`, `recharge`, `speechless`, `concentration`, `fondle_love`, `fondle_anger`, `blink`)

### Build Note
The package is built from the requested latest `main` baseline after updating `PROJECT_VER` to `V2.1.0`, so firmware version reporting through `esp_app_desc` and OTA service helpers uses `V2.1.0`.
