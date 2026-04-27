#!/usr/bin/env python3
"""Run a STM32 IP5306 5V power toggle HIL check over the debug UART.

This test validates the STM32-side control signal path. On the current bench,
ESP32 is powered from USB-C, so ESP32 logs are captured for context but are not
expected to stop when the STM32 disables the IP5306-controlled peripheral 5V
rail.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

import serial


DEFAULT_BAUD = 115200


@dataclass
class PowerToggleResult:
    result: str
    cycles_requested: int
    off_commands_seen: int
    on_commands_seen: int
    off_actions_seen: int
    on_actions_seen: int
    irq_reports_seen: int
    esp32_lines_seen: int
    stm32_lines_seen: int
    failures: list[str]
    merged_log: str
    esp32_log: str
    stm32_log: str


class DualSerialCapture:
    def __init__(self, esp_port: str, stm32_port: str, baud: int, output_dir: Path) -> None:
        self.esp_port = esp_port
        self.stm32_port = stm32_port
        self.baud = baud
        self.output_dir = output_dir
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.serials: dict[str, serial.Serial] = {}
        self.files: dict[str, TextIO] = {}
        self.merged: TextIO | None = None
        self.stm32_lines: list[str] = []
        self.esp32_line_count = 0
        self.stm32_line_count = 0

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.merged_path = output_dir / f"{stamp}-power-5v-toggle-merged.log"
        self.esp32_path = output_dir / f"{stamp}-power-5v-toggle-esp32-{esp_port}.log"
        self.stm32_path = output_dir / f"{stamp}-power-5v-toggle-stm32-{stm32_port}.log"

    def __enter__(self) -> "DualSerialCapture":
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.files["ESP32"] = self.esp32_path.open("w", encoding="utf-8", errors="replace")
        self.files["STM32"] = self.stm32_path.open("w", encoding="utf-8", errors="replace")
        self.merged = self.merged_path.open("w", encoding="utf-8", errors="replace")

        self.serials["ESP32"] = serial.Serial(self.esp_port, self.baud, timeout=0.05, rtscts=False, dsrdtr=False)
        self.serials["STM32"] = serial.Serial(self.stm32_port, self.baud, timeout=0.05, rtscts=False, dsrdtr=False)
        for handle in self.serials.values():
            handle.dtr = False
            handle.rts = False

        for tag, handle in self.serials.items():
            threading.Thread(target=self._reader, args=(tag, handle), daemon=True).start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.stop_event.set()
        time.sleep(0.2)
        for handle in self.serials.values():
            try:
                handle.close()
            except Exception:
                pass
        for handle in self.files.values():
            handle.close()
        if self.merged is not None:
            self.merged.close()

    def send_stm32_command(self, command: str) -> None:
        self._write_line("STM32", f">>> {command}")
        payload = f"{command}\r\n".encode("ascii")
        self.serials["STM32"].write(payload)
        self.serials["STM32"].flush()

    def _reader(self, tag: str, handle: serial.Serial) -> None:
        buffer = bytearray()
        while not self.stop_event.is_set():
            try:
                data = handle.read(256)
            except Exception as exc:
                self._write_line(tag, f"<serial read error: {exc}>")
                break
            if not data:
                continue
            for byte in data:
                if byte in (10, 13):
                    if buffer:
                        self._record_serial_line(tag, buffer.decode("utf-8", errors="replace"))
                        buffer.clear()
                else:
                    buffer.append(byte)
            if len(buffer) > 400:
                self._record_serial_line(tag, buffer.decode("utf-8", errors="replace"))
                buffer.clear()
        if buffer:
            self._record_serial_line(tag, buffer.decode("utf-8", errors="replace"))

    def _record_serial_line(self, tag: str, text: str) -> None:
        if tag == "STM32":
            self.stm32_lines.append(text)
            self.stm32_line_count += 1
        elif tag == "ESP32":
            self.esp32_line_count += 1
        self._write_line(tag, text)

    def _write_line(self, tag: str, text: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] {tag}: {text}\n"
        with self.lock:
            self.files[tag].write(f"[{timestamp}] {text}\n")
            self.files[tag].flush()
            assert self.merged is not None
            self.merged.write(line)
            self.merged.flush()
            sys.stdout.write(line)
            sys.stdout.flush()


def count_contains(lines: list[str], needle: str) -> int:
    return sum(1 for line in lines if needle in line)


def evaluate(capture: DualSerialCapture, cycles: int) -> PowerToggleResult:
    lines = capture.stm32_lines
    off_commands = count_contains(lines, "ip5306_off")
    on_commands = count_contains(lines, "ip5306_on")
    off_actions = count_contains(lines, "Action: Drive NMOS gate HIGH twice for 100ms")
    on_actions = count_contains(lines, "Action: Drive NMOS gate HIGH for 100ms")
    irq_reports = count_contains(lines, "========== IP5306 IRQ ==========")

    failures: list[str] = []
    if off_commands < cycles:
        failures.append(f"off_commands_seen_below_cycles:{off_commands}<{cycles}")
    if on_commands < cycles:
        failures.append(f"on_commands_seen_below_cycles:{on_commands}<{cycles}")
    if off_actions < cycles:
        failures.append(f"off_actions_seen_below_cycles:{off_actions}<{cycles}")
    if on_actions < cycles:
        failures.append(f"on_actions_seen_below_cycles:{on_actions}<{cycles}")
    if capture.stm32_line_count == 0:
        failures.append("stm32_log_empty")
    if capture.esp32_line_count == 0:
        failures.append("esp32_log_empty")

    return PowerToggleResult(
        result="pass" if not failures else "failed",
        cycles_requested=cycles,
        off_commands_seen=off_commands,
        on_commands_seen=on_commands,
        off_actions_seen=off_actions,
        on_actions_seen=on_actions,
        irq_reports_seen=irq_reports,
        esp32_lines_seen=capture.esp32_line_count,
        stm32_lines_seen=capture.stm32_line_count,
        failures=failures,
        merged_log=str(capture.merged_path),
        esp32_log=str(capture.esp32_path),
        stm32_log=str(capture.stm32_path),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run 20-cycle STM32 IP5306 5V power toggle HIL test")
    parser.add_argument("--esp-port", default="COM37", help="ESP32 log UART port")
    parser.add_argument("--stm32-port", default="COM56", help="STM32 debug UART port")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help="Debug UART baud rate")
    parser.add_argument("--cycles", type=int, default=20, help="Number of off/on cycles")
    parser.add_argument("--settle-sec", type=float, default=2.0, help="Initial capture settle time")
    parser.add_argument("--between-command-sec", type=float, default=0.8, help="Delay after each command")
    parser.add_argument("--between-cycle-sec", type=float, default=0.5, help="Delay after each off/on cycle")
    parser.add_argument(
        "--output-root",
        default=str(Path("artifacts") / "power-5v-toggle-hil"),
        help="Directory where logs and summary JSON are written",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_root).resolve()

    with DualSerialCapture(args.esp_port, args.stm32_port, args.baud, output_dir) as capture:
        time.sleep(args.settle_sec)
        capture.send_stm32_command("ip5306_irq")
        time.sleep(args.between_command_sec)
        for index in range(args.cycles):
            capture.send_stm32_command("ip5306_off")
            time.sleep(args.between_command_sec)
            capture.send_stm32_command("ip5306_on")
            time.sleep(args.between_command_sec)
            if index != args.cycles - 1:
                time.sleep(args.between_cycle_sec)
        capture.send_stm32_command("ip5306_irq")
        time.sleep(max(args.between_command_sec, 1.0))
        result = evaluate(capture, args.cycles)

    summary_path = output_dir / (Path(result.merged_log).stem + "-summary.json")
    summary_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
    print(json.dumps({**asdict(result), "summary": str(summary_path)}, indent=2))
    return 0 if result.result == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
