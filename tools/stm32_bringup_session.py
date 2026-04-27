from __future__ import annotations

import argparse
import json
import os
import queue
import re
import sys
import threading
import time
import tomllib
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

import serial

OBS_PATTERN = re.compile(r"(MCU_OBS|STM32_OBS)\s*:?\s*(.*)")
DEFAULT_ESP_ALIAS = "s3-c"
DEFAULT_STM32_ALIAS = "stm32-c"
DEFAULT_ESP_BAUD = 115200
DEFAULT_STM32_BAUD = 115200


class SessionError(RuntimeError):
    """Raised when session setup or capture cannot continue."""


@dataclass(frozen=True)
class DeviceMapping:
    alias: str
    port: str
    firmware: str | None = None


@dataclass(frozen=True)
class LogRecord:
    ts_host: str
    ts_ns: int
    source: str
    port: str
    raw: str
    kind: str
    kv: dict[str, str]


def get_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_default_device_map_path() -> Path:
    explicit = os.environ.get("CODEX_DEVICE_MAP_PATH")
    if explicit:
        return Path(explicit).expanduser()

    user_profile = os.environ.get("USERPROFILE")
    if not user_profile:
        raise SessionError("USERPROFILE is not set and CODEX_DEVICE_MAP_PATH was not provided")
    return Path(user_profile) / ".codex" / "local" / "device-map.toml"


def load_device_map(path: Path) -> dict[str, DeviceMapping]:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SessionError(f"Device map not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise SessionError(f"Failed to parse device map {path}: {exc}") from exc

    devices = raw.get("devices")
    if not isinstance(devices, dict):
        raise SessionError(f"Device map {path} does not contain a [devices] table")

    mappings: dict[str, DeviceMapping] = {}
    for alias, value in devices.items():
        if not isinstance(value, dict):
            continue
        port = value.get("port")
        if not isinstance(port, str) or not port.strip():
            continue
        firmware = value.get("firmware")
        mappings[alias] = DeviceMapping(alias=alias, port=port.strip(), firmware=firmware if isinstance(firmware, str) else None)

    if not mappings:
        raise SessionError(f"Device map {path} does not define any device ports")
    return mappings


def resolve_device_alias(mappings: dict[str, DeviceMapping], alias: str) -> DeviceMapping:
    try:
        return mappings[alias]
    except KeyError as exc:
        raise SessionError(f"Device alias '{alias}' was not found in the shared device map") from exc


def parse_key_value_fields(raw_payload: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in raw_payload.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        fields[key] = value
    return fields


def parse_observation_line(raw_line: str) -> tuple[str, dict[str, str]]:
    match = OBS_PATTERN.search(raw_line)
    if not match:
        return "log", {}

    fields = parse_key_value_fields(match.group(2).strip())
    return "obs", fields


def build_log_record(source: str, port: str, raw_line: str, *, ts_ns: int | None = None) -> LogRecord:
    ts_ns = ts_ns if ts_ns is not None else time.time_ns()
    ts_host = datetime.fromtimestamp(ts_ns / 1_000_000_000, tz=timezone.utc).isoformat(timespec="milliseconds")
    kind, kv = parse_observation_line(raw_line)
    return LogRecord(ts_host=ts_host, ts_ns=ts_ns, source=source, port=port, raw=raw_line, kind=kind, kv=kv)


def sort_records(records: list[LogRecord]) -> list[LogRecord]:
    return sorted(records, key=lambda record: (record.ts_ns, record.source, record.port, record.raw))


def format_merged_line(record: LogRecord) -> str:
    return f"{record.ts_host} [{record.source} {record.port}] {record.raw}"


def open_serial_port(port: str, baudrate: int) -> serial.Serial:
    try:
        serial_handle = serial.Serial(port=None, baudrate=baudrate, timeout=0.2, rtscts=False, dsrdtr=False)
        serial_handle.dtr = False
        serial_handle.rts = False
        serial_handle.port = port
        serial_handle.open()
        serial_handle.reset_input_buffer()
        return serial_handle
    except serial.SerialException as exc:
        raise SessionError(f"Failed to open serial port {port} @ {baudrate}: {exc}") from exc


def serial_reader_loop(
    serial_handle: serial.Serial,
    source: str,
    out_queue: queue.Queue[LogRecord],
    stop_event: threading.Event,
) -> None:
    while not stop_event.is_set():
        try:
            chunk = serial_handle.readline()
        except serial.SerialException:
            return

        if not chunk:
            continue

        raw_line = chunk.decode("utf-8", errors="replace").rstrip("\r\n")
        if not raw_line:
            continue
        out_queue.put(build_log_record(source, serial_handle.port, raw_line))


def drain_record_queue(record_queue: queue.Queue[LogRecord], sink: list[LogRecord], timeout: float = 0.0) -> None:
    while True:
        try:
            record = record_queue.get(timeout=timeout)
        except queue.Empty:
            return
        sink.append(record)
        timeout = 0.0


def write_raw_record(file_handle: TextIO, record: LogRecord) -> None:
    file_handle.write(record.raw)
    file_handle.write("\n")
    file_handle.flush()


def write_session_outputs(session_dir: Path, records: list[LogRecord], session_metadata: dict[str, Any]) -> None:
    merged_path = session_dir / "merged.log"
    timeline_path = session_dir / "timeline.ndjson"
    sorted_records = sort_records(records)

    with merged_path.open("w", encoding="utf-8", newline="\n") as merged_handle:
        for record in sorted_records:
            merged_handle.write(format_merged_line(record))
            merged_handle.write("\n")

    with timeline_path.open("w", encoding="utf-8", newline="\n") as timeline_handle:
        for record in sorted_records:
            timeline_handle.write(
                json.dumps(
                    {
                        "ts_host": record.ts_host,
                        "source": record.source,
                        "port": record.port,
                        "kind": record.kind,
                        "raw": record.raw,
                        "kv": record.kv,
                    },
                    ensure_ascii=True,
                )
            )
            timeline_handle.write("\n")

    session_metadata["record_count"] = len(sorted_records)
    session_metadata["obs_record_count"] = sum(1 for record in sorted_records if record.kind == "obs")
    session_metadata["outputs"] = {
        "session": str(session_dir / "session.json"),
        "esp32_raw": str(session_dir / "esp32.raw.log"),
        "stm32_raw": str(session_dir / "stm32.raw.log"),
        "merged": str(merged_path),
        "timeline": str(timeline_path),
    }

    (session_dir / "session.json").write_text(json.dumps(session_metadata, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def build_output_dir(output_root: Path, operator: str, feature: str, esp_alias: str, stm32_alias: str) -> Path:
    session_stamp = datetime.now(timezone.utc).strftime("session-%Y%m%dT%H%M%SZ")
    return output_root / operator / feature / f"{esp_alias}--{stm32_alias}" / session_stamp


def capture_session(
    *,
    esp_device: DeviceMapping,
    stm32_device: DeviceMapping,
    esp_baud: int,
    stm32_baud: int,
    duration_sec: float,
    session_dir: Path,
) -> dict[str, Any]:
    session_dir.mkdir(parents=True, exist_ok=True)
    record_queue: queue.Queue[LogRecord] = queue.Queue()
    records: list[LogRecord] = []
    stop_event = threading.Event()
    started_at = datetime.now(timezone.utc)
    start_monotonic = time.monotonic()
    deadline = start_monotonic + duration_sec

    with ExitStack() as stack:
        esp_serial = stack.enter_context(open_serial_port(esp_device.port, esp_baud))
        stm32_serial = stack.enter_context(open_serial_port(stm32_device.port, stm32_baud))
        esp_log_handle = stack.enter_context((session_dir / "esp32.raw.log").open("w", encoding="utf-8", newline="\n"))
        stm32_log_handle = stack.enter_context((session_dir / "stm32.raw.log").open("w", encoding="utf-8", newline="\n"))

        esp_thread = threading.Thread(
            target=serial_reader_loop,
            name="esp32-reader",
            args=(esp_serial, "esp32", record_queue, stop_event),
            daemon=True,
        )
        stm32_thread = threading.Thread(
            target=serial_reader_loop,
            name="stm32-reader",
            args=(stm32_serial, "stm32", record_queue, stop_event),
            daemon=True,
        )
        esp_thread.start()
        stm32_thread.start()

        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break

                try:
                    record = record_queue.get(timeout=min(0.25, remaining))
                except queue.Empty:
                    continue

                records.append(record)
                if record.source == "esp32":
                    write_raw_record(esp_log_handle, record)
                else:
                    write_raw_record(stm32_log_handle, record)
        finally:
            stop_event.set()
            esp_thread.join(timeout=1.0)
            stm32_thread.join(timeout=1.0)
            drained_records: list[LogRecord] = []
            drain_record_queue(record_queue, drained_records)
            for record in drained_records:
                records.append(record)
                if record.source == "esp32":
                    write_raw_record(esp_log_handle, record)
                else:
                    write_raw_record(stm32_log_handle, record)

    finished_at = datetime.now(timezone.utc)
    session_metadata: dict[str, Any] = {
        "started_at": started_at.isoformat(timespec="milliseconds"),
        "finished_at": finished_at.isoformat(timespec="milliseconds"),
        "duration_sec": round(finished_at.timestamp() - started_at.timestamp(), 3),
        "requested_duration_sec": duration_sec,
        "esp32": asdict(esp_device) | {"baud": esp_baud},
        "stm32": asdict(stm32_device) | {"baud": stm32_baud},
    }
    write_session_outputs(session_dir, records, session_metadata)
    return session_metadata


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture a merged ESP32 + STM32 bring-up log session.")
    parser.add_argument("--esp-alias", default=DEFAULT_ESP_ALIAS, help="Shared device-map alias for the ESP32 log UART")
    parser.add_argument("--stm32-alias", default=DEFAULT_STM32_ALIAS, help="Shared device-map alias for the STM32 USART1 debug UART")
    parser.add_argument("--feature", required=True, help="Feature name used in the output session path")
    parser.add_argument("--duration-sec", type=float, required=True, help="Session duration in seconds")
    parser.add_argument("--esp-baud", type=int, default=DEFAULT_ESP_BAUD, help="ESP32 serial baud rate")
    parser.add_argument("--stm32-baud", type=int, default=DEFAULT_STM32_BAUD, help="STM32 serial baud rate")
    parser.add_argument("--output-root", type=Path, default=None, help="Optional override for the session output root")
    parser.add_argument("--device-map-path", type=Path, default=None, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.duration_sec <= 0:
        raise SessionError("--duration-sec must be greater than zero")

    device_map_path = args.device_map_path or get_default_device_map_path()
    mappings = load_device_map(device_map_path)
    esp_device = resolve_device_alias(mappings, args.esp_alias)
    stm32_device = resolve_device_alias(mappings, args.stm32_alias)

    operator = os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"
    output_root = args.output_root or (get_repo_root() / ".codex" / "local" / "logs")
    session_dir = build_output_dir(output_root, operator, args.feature, args.esp_alias, args.stm32_alias)

    metadata = capture_session(
        esp_device=esp_device,
        stm32_device=stm32_device,
        esp_baud=args.esp_baud,
        stm32_baud=args.stm32_baud,
        duration_sec=args.duration_sec,
        session_dir=session_dir,
    )

    print(f"Session captured to {session_dir}")
    print(
        json.dumps(
            {
                "record_count": metadata.get("record_count", 0),
                "obs_record_count": metadata.get("obs_record_count", 0),
                "esp_port": esp_device.port,
                "stm32_port": stm32_device.port,
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SessionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
