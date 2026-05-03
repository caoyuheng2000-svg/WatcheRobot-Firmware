## v2.2.0

Release package for the ESP32 touch-expression response baseline with ESP-IDF
app metadata set to `V2.2.0`.

### Highlights
- Route STM32 touch sensor events through the ESP32 MCU link runtime path.
- Cache latest touch, magnetometer, and IMU sensor states in `mcu_sensor_service`.
- Trigger the `fondle_love` behavior and SD animation on touch press when the
  behavior system is idle and the animation exists in the SD manifest.
- Add host-side `mcu_sensor_service` tests for touch, magnetometer, IMU, and
  invalid-frame handling.
- Refresh communication and animation workflow documentation for the `V2.2.0`
  release track.

### Release Scope
- Current mainline ESP32-S3 firmware binary and partition payloads.
- Current SD-backed animation bundle for `/sdcard/anim`.
- Touch-expression runtime integration over the board-internal MCU link.
- Release packaging and validation assets for repeatable device flashing.

### Release Assets
This release includes two deliverables:
- `WatcheRobot-S3-V2.2.0-esp32s3.zip`
- `WatcheRobot-S3-V2.2.0-sdcard-anim.zip`

The firmware flash bundle contains:
- `bootloader.bin`
- `partition-table.bin`
- `WatcheRobot-S3.bin`
- `srmodels.bin`
- `storage.bin`

The SD-card animation bundle contains:
- `anim_manifest.bin`
- `*.animpack` for the generated state set (`boot`, `happy`, `error`,
  `bluetooth`, `speaking`, `listening`, `processing`, `standby`, `thinking`,
  `custom1`, `custom2`, `custom3`, `standby1`, `standby2`, `standby3`,
  `standby4`, `disconnect`, `shock`, `sunglasses`, `sad`, `get`, `smile`,
  `recharge`, `speechless`, `concentration`, `fondle_love`, `fondle_anger`,
  `blink`)

### Validation
- `mcu_sensor_service` host tests pass.
- ESP-IDF release build completes for `esp32s3`.
- Generated app metadata reports `V2.2.0`.
