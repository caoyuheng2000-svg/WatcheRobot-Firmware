## v0.2.4

Formal release baseline for the current mainline after playback buffering, action handoff, and runtime memory diagnostics updates.

### Highlights
- Carry forward the GIF / AnimPack SD-backed animation runtime introduced in the `v0.2.x` line.
- Move cloud TTS playback onto a dedicated buffered worker so audio output is less sensitive to WebSocket receive jitter.
- Replace the permanent runtime memory monitor task with lifecycle and post-playback heap snapshots to reduce steady-state RAM pressure.
- Include the latest action handoff responsiveness improvements so behavior-state changes preempt active motion and expression playback more cleanly.
- Keep the currently shipped legacy SPIFFS action data set in place; this release updates runtime handling, not the action content payloads.

### Release Scope
- Current mainline firmware binary and partition payloads
- Current SD-backed animation bundle for `/sdcard/anim`
- Release packaging and validation assets for repeatable device flashing

### Release Assets
This release includes two deliverables:
- `WatcheRobot-S3-v0.2.4-esp32s3.zip`
- `WatcheRobot-S3-v0.2.4-sdcard-anim.zip`

The firmware flash bundle contains:
- `bootloader.bin`
- `partition-table.bin`
- `WatcheRobot-S3.bin`
- `srmodels.bin`
- `storage.bin`

The SD-card animation bundle contains:
- `anim_manifest.bin`
- `*.animpack` for the currently generated state set (`boot`, `happy`, `error`, `bluetooth`, `speaking`, `listening`, `processing`, `standby`, `thinking`, `custom3`)
