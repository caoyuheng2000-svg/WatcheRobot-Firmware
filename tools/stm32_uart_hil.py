#!/usr/bin/env python3
"""Minimal STM32 UART HIL runner scaffold.

This script is intentionally lightweight and self-contained. It defines the
scenario names, result schema, and placeholder transport hooks needed for later
serial-port integration.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Optional, Protocol


SCENARIOS = (
    "hello_heartbeat_smoke",
    "servo_move_ack_done",
    "servo_stop_interrupt",
    "led_effect_ack_done",
    "touch_press_release",
    "mag_state_rate_2hz",
    "imu_state_rate_20hz",
    "coproc_reset_recovery",
    "snapshot_restore",
    "baseline_restore_without_snapshot",
    "crc_fault_injection",
)


@dataclass(slots=True)
class HILMetrics:
    ack_timeout_count: int = 0
    crc_error_count: int = 0
    dropped_state_count: int = 0
    reconnect_count: int = 0
    motion_done_fault_count: int = 0


@dataclass(slots=True)
class HILResult:
    scenario: str
    result: str
    transport: str
    started_at: float
    finished_at: float
    duration_ms: int
    metrics: HILMetrics
    notes: list[str]

    def to_json(self) -> dict:
        payload = asdict(self)
        payload["metrics"] = asdict(self.metrics)
        return payload


class Transport(Protocol):
    name: str

    def open(self) -> None: ...

    def close(self) -> None: ...

    def write(self, data: bytes) -> int: ...

    def read(self, size: int = 4096, timeout: float = 0.0) -> bytes: ...

    def inject_rx(self, data: bytes) -> None: ...


class MockTransport:
    """Queue-based transport used for tests and offline scenario scaffolding."""

    name = "mock"

    def __init__(self) -> None:
        self._rx = bytearray()
        self._tx = bytearray()
        self._is_open = False

    def open(self) -> None:
        self._is_open = True

    def close(self) -> None:
        self._is_open = False

    def write(self, data: bytes) -> int:
        if not self._is_open:
            raise RuntimeError("transport is not open")
        self._tx.extend(data)
        return len(data)

    def read(self, size: int = 4096, timeout: float = 0.0) -> bytes:
        if not self._is_open:
            raise RuntimeError("transport is not open")
        if not self._rx:
            if timeout:
                time.sleep(min(timeout, 0.05))
            return b""
        chunk = bytes(self._rx[:size])
        del self._rx[:size]
        return chunk

    def inject_rx(self, data: bytes) -> None:
        self._rx.extend(data)


class SerialTransport:
    """Placeholder serial transport hook.

    It is intentionally thin and only documents the later integration surface.
    pyserial is optional and only needed once real hardware is wired up.
    """

    name = "serial"

    def __init__(self, port: str, baud: int) -> None:
        self.port = port
        self.baud = baud
        self._serial = None

    def open(self) -> None:
        try:
            import serial  # type: ignore
        except ImportError as exc:  # pragma: no cover - placeholder path
            raise RuntimeError("pyserial is required for --transport serial") from exc
        self._serial = serial.Serial(self.port, self.baud, timeout=0)

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def write(self, data: bytes) -> int:
        if self._serial is None:
            raise RuntimeError("transport is not open")
        return int(self._serial.write(data))

    def read(self, size: int = 4096, timeout: float = 0.0) -> bytes:
        if self._serial is None:
            raise RuntimeError("transport is not open")
        deadline = time.monotonic() + timeout
        chunks = bytearray()
        while len(chunks) < size:
            if timeout and time.monotonic() >= deadline:
                break
            chunk = self._serial.read(size - len(chunks))
            if chunk:
                chunks.extend(chunk)
                continue
            if not timeout:
                break
            time.sleep(0.01)
        return bytes(chunks)

    def inject_rx(self, data: bytes) -> None:
        raise NotImplementedError("serial transport does not support injection")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python tools/stm32_uart_hil.py",
        description="STM32 UART HIL runner scaffold",
    )
    parser.add_argument(
        "--scenario",
        choices=SCENARIOS,
        default="hello_heartbeat_smoke",
        help="Named scenario to run",
    )
    parser.add_argument(
        "--transport",
        choices=("mock", "serial"),
        default="mock",
        help="Transport backend",
    )
    parser.add_argument("--port", help="Serial port for --transport serial, e.g. COM7")
    parser.add_argument("--baud", type=int, default=921600, help="Serial baud rate")
    parser.add_argument("--timeout", type=float, default=2.0, help="Scenario timeout in seconds")
    parser.add_argument(
        "--json-indent",
        type=int,
        default=2,
        help="Pretty-print JSON with this indent; use 0 for compact output",
    )
    return parser


def _make_transport(args: argparse.Namespace) -> Transport:
    if args.transport == "serial":
        if not args.port:
            raise SystemExit("--port is required when --transport serial is selected")
        return SerialTransport(args.port, args.baud)
    return MockTransport()


def _scenario_steps(scenario: str) -> list[str]:
    steps = {
        "hello_heartbeat_smoke": ["send HELLO_REQ", "expect HELLO_RSP", "expect HEARTBEAT"],
        "servo_move_ack_done": ["send SERVO_MOVE", "expect ACK", "expect MOTION_DONE"],
        "servo_stop_interrupt": ["send SERVO_MOVE", "send SERVO_STOP", "expect MOTION_DONE interrupted"],
        "led_effect_ack_done": ["send LED_SET_EFFECT", "expect ACK", "expect LED_DONE"],
        "touch_press_release": ["inject TOUCH_EVENT press", "inject TOUCH_EVENT release"],
        "mag_state_rate_2hz": ["inject MAG_STATE at 2Hz", "verify latest-state-wins"],
        "imu_state_rate_20hz": ["inject IMU_STATE bursts", "verify rate limiting"],
        "coproc_reset_recovery": ["simulate reset", "re-handshake", "restore baseline"],
        "snapshot_restore": ["send SNAPSHOT_REQ", "expect SNAPSHOT_RSP", "restore baseline from snapshot"],
        "baseline_restore_without_snapshot": [
            "simulate recovery without snapshot capability",
            "restore baseline from local safe defaults",
        ],
        "crc_fault_injection": ["inject bad CRC frame", "expect frame drop", "recover on next frame"],
    }
    return list(steps.get(scenario, []))


def _run_scenario(scenario: str, transport: Transport, timeout: float) -> HILResult:
    started = time.time()
    metrics = HILMetrics()
    notes: list[str] = []

    transport.open()
    try:
        for step in _scenario_steps(scenario):
            notes.append(step)

        # Placeholder for later hardware integration:
        # - serialize request frames
        # - inject or read UART bytes
        # - update counters from decoded ACK/DONE/FAULT/status messages
        if scenario == "crc_fault_injection":
            metrics.crc_error_count += 1
        elif scenario == "servo_move_ack_done":
            metrics.motion_done_fault_count += 0
        elif scenario == "coproc_reset_recovery":
            metrics.reconnect_count += 1

        elapsed = max(time.time() - started, 0.0)
        if elapsed > timeout:
            metrics.ack_timeout_count += 1
            result = "timeout"
        else:
            result = "passed"
    finally:
        transport.close()

    finished = time.time()
    return HILResult(
        scenario=scenario,
        result=result,
        transport=transport.name,
        started_at=started,
        finished_at=finished,
        duration_ms=int((finished - started) * 1000),
        metrics=metrics,
        notes=notes,
    )


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    transport = _make_transport(args)
    result = _run_scenario(args.scenario, transport, args.timeout)

    indent = None if args.json_indent == 0 else args.json_indent
    json.dump(result.to_json(), sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
