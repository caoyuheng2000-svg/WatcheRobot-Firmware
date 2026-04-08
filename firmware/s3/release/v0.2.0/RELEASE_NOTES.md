## v0.2.0

Formal release baseline for the GIF-authored animation system on the ESP32-S3 mainline.

### Highlights
- Replace PNG-sequence runtime playback with SD-backed `animpack` streaming generated from GIF source assets.
- Move boot animation onto the same SD animation pipeline used at runtime.
- Keep UI text visible above animated backgrounds and remove the transient white / `No data` frame during GIF switches.
- Package both the firmware flashing bundle and the SD-card animation asset bundle for release distribution.
- Carry the validated runtime refactor forward together with the current mainline reconnect, Bluetooth feedback, cached resume, and audio recovery behavior.

### Release Scope
- SD mount, manifest loading, and boot animation startup
- Runtime state switching across the currently generated GIF states
- On-screen text visibility above animated backgrounds
- Deployment flow for `release/v0.2.0/sdcard/anim` onto removable media
- Current release animation bundle contains 10 generated types; `custom1` and `custom2` are not included because their source GIFs are not present yet

### Release Assets
This release includes two deliverables:
- `WatcheRobot-S3-v0.2.0-esp32s3.zip`
- `WatcheRobot-S3-v0.2.0-sdcard-anim.zip`

The firmware flash bundle contains:
- `bootloader.bin`
- `partition-table.bin`
- `WatcheRobot-S3.bin`
- `srmodels.bin`
- `storage.bin`

The SD-card animation bundle contains:
- `anim_manifest.bin`
- `*.animpack` for the currently generated state set (`boot`, `happy`, `error`, `bluetooth`, `speaking`, `listening`, `processing`, `standby`, `thinking`, `custom3`)
