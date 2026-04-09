## v0.2.2

Formal release baseline for the current mainline after the latest cloud recovery and SSCMA safety fixes.

### Highlights
- Carry forward the GIF / AnimPack SD-backed animation runtime introduced in the `v0.2.x` line.
- Include the latest cloud reconnect hardening from current `main`.
- Include the latest SSCMA RX buffer overflow fix for safer coprocessor communication under runtime load.
- Keep the firmware flash bundle and SD-card animation bundle aligned under one formal release.

### Release Scope
- Current mainline firmware binary and partition payloads
- Current SD-backed animation bundle for `/sdcard/anim`
- Release packaging and validation assets for repeatable device flashing

### Release Assets
This release includes two deliverables:
- `WatcheRobot-S3-v0.2.2-esp32s3.zip`
- `WatcheRobot-S3-v0.2.2-sdcard-anim.zip`

The firmware flash bundle contains:
- `bootloader.bin`
- `partition-table.bin`
- `WatcheRobot-S3.bin`
- `srmodels.bin`
- `storage.bin`

The SD-card animation bundle contains:
- `anim_manifest.bin`
- `*.animpack` for the currently generated state set (`boot`, `happy`, `error`, `bluetooth`, `speaking`, `listening`, `processing`, `standby`, `thinking`, `custom3`)
