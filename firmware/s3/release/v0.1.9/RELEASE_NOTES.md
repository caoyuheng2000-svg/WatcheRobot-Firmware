## v0.1.9

Formal release baseline for the MS90 servo layer on the ESP32-S3 mainline.

### Highlights
- Introduce the direct LEDC-driven MS90 servo layer for X/Y control.
- Keep the installed neutral position centered at logical `90°` on both axes.
- Preserve the current behavior and control-path updates that align with the new servo model.
- Package a standalone Windows-flashable firmware bundle for repeatable validation.

### Validation Focus
- Servo startup neutral position at `X=90°` and `Y=90°`
- MS90 logical-angle mapping and smooth move behavior
- Packaged release flashing workflow on Windows
- Regression check for the updated behavior / control ingress path

### Release Assets
This release includes one firmware flash bundle:
- `WatcheRobot-S3-v0.1.9-esp32s3.zip`

The flash bundle contains:
- `bootloader.bin`
- `partition-table.bin`
- `WatcheRobot-S3.bin`
- `srmodels.bin`
- `storage.bin`
