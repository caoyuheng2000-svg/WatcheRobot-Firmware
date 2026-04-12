## v0.2.6

Release for the updated default audio playback gain, with the firmware package rebuilt and the current SD-card animation bundle repackaged for this version.

### Highlights
- Raise the default speaker playback volume to `100` for the Watcher audio HAL.
- Switch the audio codec initialization path to read the configured speaker volume instead of relying on a hardcoded literal.
- Rebuild the firmware so the embedded app version reports `v0.2.6`.
- Regenerate and package the current SD animation bundle under `release/v0.2.6/sdcard/anim`.

### Release Scope
- Current mainline firmware binary and partition payloads
- Current SD-backed animation bundle for `/sdcard/anim`
- Release packaging and validation assets for repeatable device flashing

### Release Assets
This release includes two deliverables:
- `WatcheRobot-S3-v0.2.6-esp32s3.zip`
- `WatcheRobot-S3-v0.2.6-sdcard-anim.zip`

The firmware flash bundle contains:
- `bootloader.bin`
- `partition-table.bin`
- `WatcheRobot-S3.bin`
- `srmodels.bin`
- `storage.bin`

The SD-card animation bundle contains:
- `anim_manifest.bin`
- `*.animpack` for the generated state set (`boot`, `happy`, `error`, `bluetooth`, `speaking`, `listening`, `processing`, `standby`, `thinking`, `custom1`, `custom2`, `custom3`)
