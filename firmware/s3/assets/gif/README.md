# GIF Sources

Drop animation source GIFs here for the `generate_anim_assets.py` toolchain.

Recommended canonical filenames:

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

Legacy names such as `watcher-boot.gif` are still accepted for compatibility.

Typical workflow from `firmware/s3`:

```powershell
python tools/generate_anim_assets.py
python tools/sync_anim_sdcard.py --target-root F:\
```

Generated output is written to:

- `release/v0.2.6/sdcard/anim/`

Current release note:

- The runtime pipeline is already integrated into the current release flow.
- The current packaged animation set includes 12 generated types.
- `custom1`, `custom2`, and `custom3` are packaged in the current release.

For the full branch guide and roadmap, see:

- `docs/GIF_ANIMATION_BRANCH_GUIDE.md`
- `docs/GIF_ANIMPACK_TOOLCHAIN.md`
- `docs/GIF_ANIMATION_ROADMAP.md`
