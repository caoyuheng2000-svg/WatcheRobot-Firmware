## v0.1.8

Recommended baseline for validating packaged Windows flashing on the current ESP32-S3 mainline.

### Highlights
- Add a Windows-first Python release flasher that scans release ZIP packages, lets you choose COM ports, and flashes with `esptool`.
- Document the packaged release flashing workflow so Windows validation no longer depends on entering the ESP-IDF source build flow.
- Keep the current reconnect stability, UI state consistency, Bluetooth feedback, cached WebSocket resume, and audio recovery baseline already merged on main.

### Validation Focus
- Windows packaged release flashing workflow
- Release ZIP scanning and COM port selection
- BLE / Wi-Fi / WebSocket recovery stability
- On-screen text and font behavior during state transitions

### Release Assets
The attached zip contains all binaries required for full flashing:
- bootloader.bin
- partition-table.bin
- WatcheRobot-S3.bin
- srmodels.bin
- storage.bin
