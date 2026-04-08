# GIF to AnimPack Toolchain

This toolchain converts a folder of GIF animation sources into SD-card ready
animation assets:

- `release/v0.1.7/sdcard/anim/anim_manifest.bin`
- `release/v0.1.7/sdcard/anim/<type>.animpack`

## Source Layout

Place GIF sources in:

- `firmware/s3/assets/gif/`

Supported source names are the canonical animation names:

- `boot.gif`
- `happy.gif`
- `error.gif`
- `bluetooth.gif`
- `speaking.gif`
- `listening.gif`
- `processing.gif`
- `standby.gif`
- `thinking.gif`
- `custom1.gif`
- `custom2.gif`
- `custom3.gif`

Legacy names such as `watcher-boot.gif` remain accepted by the converter, and
legacy PNG sequence folders are still supported as a fallback during the
transition period.

## Quick Command

From `firmware/s3`:

```powershell
python tools/generate_anim_assets.py --input-dir assets/gif --output-dir release/v0.1.7/sdcard/anim --clean
```

If you only want the default project paths, the command can be shortened to:

```powershell
python tools/generate_anim_assets.py
```

## Output Rules

- The output directory is recreated when `--clean` is enabled.
- Each GIF is expanded into a full-frame RGB565 `animpack`.
- The manifest stores pack path, dimensions, frame count, and timing metadata.

## Notes

- This toolchain is for offline asset generation only.
- The firmware runtime consumes SD-backed `animpack` files and does not decode
  GIF files on-device.
