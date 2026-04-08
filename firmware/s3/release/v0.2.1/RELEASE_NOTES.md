## v0.2.1

Formal release baseline for the GIF-authored animation system on the ESP32-S3 mainline.

### Highlights
- Carry the validated GIF-to-AnimPack runtime architecture forward as the formal `v0.2.1` package.
- Keep boot animation and runtime state playback on the SD-backed `animpack` pipeline.
- Preserve UI text visibility above animated backgrounds and the white-frame / `No data` switch fix.
- Align top-level documentation, protocol notes, and tooling defaults with the current formal release path.
- Package both the firmware flashing bundle and the SD-card animation asset bundle for repeatable validation.

### Release Scope
- SD mount, manifest loading, and boot animation startup
- Runtime state switching across the currently generated GIF states
- On-screen text visibility above animated backgrounds
- Deployment flow for `release/v0.2.1/sdcard/anim` onto removable media
- Current release animation bundle contains 10 generated types; `custom1` and `custom2` are not included because their source GIFs are not present yet

### Release Assets
This release includes two deliverables:
- `WatcheRobot-S3-v0.2.1-esp32s3.zip`
- `WatcheRobot-S3-v0.2.1-sdcard-anim.zip`

The firmware flash bundle contains:
- `bootloader.bin`
- `partition-table.bin`
- `WatcheRobot-S3.bin`
- `srmodels.bin`
- `storage.bin`

The SD-card animation bundle contains:
- `anim_manifest.bin`
- `*.animpack` for the currently generated state set (`boot`, `happy`, `error`, `bluetooth`, `speaking`, `listening`, `processing`, `standby`, `thinking`, `custom3`)
