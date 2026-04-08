# Windows Release Flasher

`tools\flash-release.cmd` is a Windows-first CLI for flashing packaged release ZIP files without entering the ESP-IDF build flow.

## What It Does

The tool is aimed at packaged firmware validation on Windows:

1. Scan `firmware\s3\release\vX.Y.Z`
2. Pick the newest valid ZIP by default
3. Let you switch to another scanned release or a manual ZIP
4. List COM ports and let you choose one
5. Parse `flash_args.txt`
6. Flash every segment with `esptool`
7. Optionally open a short serial monitor

It does not build firmware from source. The existing `firmware\s3\tools\flash-monitor.ps1` flow still owns source build plus `idf.py` flashing.

## Run From The Repository Root

Use the repository root as the working directory:

```powershell
cd D:\GithubRep\WatcheRobot-Firmware
```

If you are working from a Codex feature worktree, switch into that worktree root instead:

```powershell
cd C:\Users\50533\.codex\worktrees\53fc\WatcheRobot-Firmware
```

## Install Dependencies

```powershell
python -m pip install -r tools\win_flasher\requirements.txt
```

## Interactive Wizard

This is the easiest path for day-to-day release flashing:

```powershell
tools\flash-release.cmd
```

The wizard will show the latest scanned release ZIP first, then let you confirm or override it before selecting a COM port.

## Non-Interactive Commands

List discovered release ZIP files:

```powershell
python -m tools.win_flasher list-releases
```

List current COM ports:

```powershell
python -m tools.win_flasher list-ports
```

Flash the latest scanned release ZIP to a specific port:

```powershell
python -m tools.win_flasher flash --port COM41
```

Flash a manually selected ZIP:

```powershell
python -m tools.win_flasher flash --zip C:\path\to\WatcheRobot-S3-v0.1.8-esp32s3.zip --port COM41
```

Flash and then open a short serial monitor:

```powershell
python -m tools.win_flasher flash --port COM41 --monitor --monitor-seconds 20
```

## Common Notes

- The default flash baud is `460800`.
- The default monitor baud is `115200`.
- The CLI uses `flash_args.txt` inside the ZIP as the single source of truth for layout and flash options.
- If multiple COM ports are present, use `list-ports` first and then pass `--port COMx` explicitly.

## Troubleshooting

`Could not open requirements file`

- You are probably in the wrong directory or on the wrong worktree.
- First run `pwd`, then make sure `tools\win_flasher\requirements.txt` exists under the current repository root.

`未安装 esptool`

- Install dependencies again:

```powershell
python -m pip install -r tools\win_flasher\requirements.txt
```

`未检测到可用串口`

- Confirm the device is connected.
- Run `python -m tools.win_flasher list-ports`.
- If Windows assigned a different COM port than expected, pass it explicitly with `--port`.

`检测到多个串口，请使用 --port`

- This is expected when Bluetooth virtual ports and USB serial ports are both present.
- Use `list-ports` to identify the correct USB serial device and then rerun with `--port COMx`.
