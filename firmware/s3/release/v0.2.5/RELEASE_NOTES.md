## v0.2.5

Release for the updated action set and refreshed SD-card animation bundle, including newly added `custom1` and `custom2` motion assets.

### Highlights
- Update the packaged SPIFFS action payloads under `spiffs/actions` for the latest behavior flow tuning.
- Add `custom1` and `custom2` to the generated SD animation bundle so the device can load two additional custom AnimPack states from `/sdcard/anim`.
- Keep the current SD-backed AnimPack runtime and manifest format (`v2`) used by the firmware.
- Set the project and asset-tool default release version to `v0.2.5` for future builds and SD sync operations.

### Release Scope
- Current mainline firmware binary and partition payloads
- Current SD-backed animation bundle for `/sdcard/anim`
- Release packaging and validation assets for repeatable device flashing

### Release Assets
This release includes two deliverables:
- `WatcheRobot-S3-v0.2.5-esp32s3.zip`
- `WatcheRobot-S3-v0.2.5-sdcard-anim.zip`

The firmware flash bundle contains:
- `bootloader.bin`
- `partition-table.bin`
- `WatcheRobot-S3.bin`
- `srmodels.bin`
- `storage.bin`

The SD-card animation bundle contains:
- `anim_manifest.bin`
- `*.animpack` for the generated state set (`boot`, `happy`, `error`, `bluetooth`, `speaking`, `listening`, `processing`, `standby`, `thinking`, `custom1`, `custom2`, `custom3`)
