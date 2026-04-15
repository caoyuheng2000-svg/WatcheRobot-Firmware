#!/usr/bin/env python3
"""Minimal STM32 UART HIL runner scaffold.

The script stays self-contained and supports two execution modes:

- `mock`: deterministic offline execution with capability-gated scenarios
- `serial`: optional placeholder transport for later real hardware wiring

The JSON output is intentionally aligned with the integration docs: the core
top-level fields are the documented scenario/result/metric/notes entries, while
auxiliary metadata is grouped under `scenario_metadata`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Iterable, Optional, Protocol


SCHEMA_VERSION = "v1"
DEFAULT_STREAM_PROFILE = "v1_default"
SNAPSHOT_REQUIRED = "required"
SNAPSHOT_FORBIDDEN = "forbidden"
SNAPSHOT_OPTIONAL = "optional"

RESULT_PASSED = "passed"
RESULT_SKIPPED = "skipped"
RESULT_TIMEOUT = "timeout"
RESULT_FAILED = "failed"


@dataclass(slots=True)
class ScenarioStep:
    """One deterministic transcript entry in a named scenario."""

    action: str
    message: str
    metric_deltas: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class ScenarioSpec:
    """Capability-gated scenario metadata."""

    name: str
    snapshot_gate: str
    duration_ms: int
    steps: tuple[ScenarioStep, ...]
    description: str


SCENARIO_SPECS: dict[str, ScenarioSpec] = {
    "hello_heartbeat_smoke": ScenarioSpec(
        name="hello_heartbeat_smoke",
        snapshot_gate=SNAPSHOT_OPTIONAL,
        duration_ms=120,
        description="Verify handshake, capability discovery, and heartbeat",
        steps=(
            ScenarioStep("send", "HELLO_REQ"),
            ScenarioStep("inject", "HELLO_RSP snapshot_capability=1"),
            ScenarioStep("inject", "HEARTBEAT"),
        ),
    ),
    "servo_move_ack_done": ScenarioSpec(
        name="servo_move_ack_done",
        snapshot_gate=SNAPSHOT_OPTIONAL,
        duration_ms=140,
        description="Verify motion accepted and completed",
        steps=(
            ScenarioStep("send", "SERVO_MOVE"),
            ScenarioStep("inject", "ACK status=accepted"),
            ScenarioStep("inject", "MOTION_DONE result=success"),
        ),
    ),
    "servo_stop_interrupt": ScenarioSpec(
        name="servo_stop_interrupt",
        snapshot_gate=SNAPSHOT_OPTIONAL,
        duration_ms=160,
        description="Verify stop interrupts motion and surfaces a non-success completion",
        steps=(
            ScenarioStep("send", "SERVO_MOVE"),
            ScenarioStep("inject", "ACK status=accepted"),
            ScenarioStep("send", "SERVO_STOP"),
            ScenarioStep("inject", "MOTION_DONE result=interrupted", {"motion_done_fault_count": 1}),
        ),
    ),
    "led_effect_ack_done": ScenarioSpec(
        name="led_effect_ack_done",
        snapshot_gate=SNAPSHOT_OPTIONAL,
        duration_ms=110,
        description="Verify LED effect accepted and completed",
        steps=(
            ScenarioStep("send", "LED_SET_EFFECT"),
            ScenarioStep("inject", "ACK status=accepted"),
            ScenarioStep("inject", "LED_DONE result=success"),
        ),
    ),
    "touch_press_release": ScenarioSpec(
        name="touch_press_release",
        snapshot_gate=SNAPSHOT_OPTIONAL,
        duration_ms=70,
        description="Verify touch edge events are observed in order",
        steps=(
            ScenarioStep("inject", "TOUCH_EVENT event=press"),
            ScenarioStep("inject", "TOUCH_EVENT event=release"),
        ),
    ),
    "mag_state_rate_2hz": ScenarioSpec(
        name="mag_state_rate_2hz",
        snapshot_gate=SNAPSHOT_OPTIONAL,
        duration_ms=90,
        description="Verify magnetometer state stays within the low-rate cadence",
        steps=(
            ScenarioStep("inject", "MAG_STATE sample=0"),
            ScenarioStep("inject", "MAG_STATE sample=1"),
        ),
    ),
    "imu_state_rate_20hz": ScenarioSpec(
        name="imu_state_rate_20hz",
        snapshot_gate=SNAPSHOT_OPTIONAL,
        duration_ms=130,
        description="Verify IMU state uses latest-state-wins under burst load",
        steps=(
            ScenarioStep("inject", "IMU_STATE burst=20hz"),
            ScenarioStep(
                "inject",
                "IMU_STATE collapse=latest",
                {"dropped_state_count": 4},
            ),
        ),
    ),
    "coproc_reset_recovery": ScenarioSpec(
        name="coproc_reset_recovery",
        snapshot_gate=SNAPSHOT_OPTIONAL,
        duration_ms=180,
        description="Verify reset recovery and reconnect accounting",
        steps=(
            ScenarioStep("send", "HELLO_REQ"),
            ScenarioStep("inject", "HELLO_RSP snapshot_capability=1"),
            ScenarioStep("inject", "HEARTBEAT after_reset"),
            ScenarioStep("inject", "RECOVERY complete", {"reconnect_count": 1}),
        ),
    ),
    "snapshot_restore": ScenarioSpec(
        name="snapshot_restore",
        snapshot_gate=SNAPSHOT_REQUIRED,
        duration_ms=150,
        description="Verify restore via runtime snapshot",
        steps=(
            ScenarioStep("send", "HELLO_REQ"),
            ScenarioStep("inject", "HELLO_RSP snapshot_capability=1"),
            ScenarioStep("send", "SNAPSHOT_REQ"),
            ScenarioStep("inject", "SNAPSHOT_RSP"),
            ScenarioStep("inject", "BASELINE restored", {"reconnect_count": 1}),
        ),
    ),
    "baseline_restore_without_snapshot": ScenarioSpec(
        name="baseline_restore_without_snapshot",
        snapshot_gate=SNAPSHOT_FORBIDDEN,
        duration_ms=100,
        description="Verify recovery path that uses safe defaults without snapshot",
        steps=(
            ScenarioStep("send", "HELLO_REQ"),
            ScenarioStep("inject", "HELLO_RSP snapshot_capability=0"),
            ScenarioStep("inject", "BASELINE restored from safe defaults", {"reconnect_count": 1}),
        ),
    ),
    "crc_fault_injection": ScenarioSpec(
        name="crc_fault_injection",
        snapshot_gate=SNAPSHOT_OPTIONAL,
        duration_ms=60,
        description="Verify bad CRC frames are dropped and counted",
        steps=(
            ScenarioStep("inject", "BAD_FRAME crc=invalid", {"crc_error_count": 1, "dropped_state_count": 1}),
            ScenarioStep("inject", "GOOD_FRAME resync"),
        ),
    ),
}

SCENARIOS = tuple(SCENARIO_SPECS)


@dataclass(slots=True)
class HILMetrics:
    ack_timeout_count: int = 0
    crc_error_count: int = 0
    dropped_state_count: int = 0
    reconnect_count: int = 0
    motion_done_fault_count: int = 0

    def apply(self, deltas: dict[str, int]) -> None:
        for name, delta in deltas.items():
            if not hasattr(self, name):
                raise KeyError(f"unknown metric {name!r}")
            setattr(self, name, getattr(self, name) + delta)


@dataclass(slots=True)
class HILResult:
    schema_version: str
    scenario: str
    result: str
    scenario_metadata: dict[str, object]
    metrics: HILMetrics
    notes: list[str]

    @property
    def ok(self) -> bool:
        return self.result in {RESULT_PASSED, RESULT_SKIPPED}

    def to_json(self) -> dict:
        payload = {
            "schema_version": self.schema_version,
            "scenario": self.scenario,
            "result": self.result,
            "scenario_metadata": self.scenario_metadata,
            "ack_timeout_count": self.metrics.ack_timeout_count,
            "crc_error_count": self.metrics.crc_error_count,
            "dropped_state_count": self.metrics.dropped_state_count,
            "reconnect_count": self.metrics.reconnect_count,
            "motion_done_fault_count": self.metrics.motion_done_fault_count,
            "notes": self.notes,
        }
        return payload


class Transport(Protocol):
    name: str

    def open(self) -> None: ...

    def close(self) -> None: ...

    def write(self, data: bytes) -> int: ...

    def read(self, size: int = 4096, timeout: float = 0.0) -> bytes: ...

    def inject_rx(self, data: bytes) -> None: ...


class MockTransport:
    """Queue-based transport used for deterministic offline scenario scaffolding."""

    name = "mock"

    def __init__(self) -> None:
        self._rx = bytearray()
        self._tx = bytearray()
        self._is_open = False
        self.events: list[str] = []

    def open(self) -> None:
        self._is_open = True
        self.events.append("open")

    def close(self) -> None:
        self._is_open = False
        self.events.append("close")

    def write(self, data: bytes) -> int:
        if not self._is_open:
            raise RuntimeError("transport is not open")
        self._tx.extend(data)
        self.events.append(f"tx:{data.decode('utf-8', errors='replace')}")
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
        self.events.append(f"rx:{chunk.decode('utf-8', errors='replace')}")
        return chunk

    def inject_rx(self, data: bytes) -> None:
        self._rx.extend(data)
        self.events.append(f"inject:{data.decode('utf-8', errors='replace')}")


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
    parser.add_argument(
        "--snapshot-capability",
        choices=("auto", "yes", "no"),
        default="auto",
        help="Override the scenario's snapshot capability gate",
    )
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


def _resolve_snapshot_capability(spec: ScenarioSpec, requested: str) -> bool:
    if requested == "auto":
        return spec.snapshot_gate != SNAPSHOT_FORBIDDEN
    if requested == "yes":
        return True
    return False


def _snapshot_gate_satisfied(spec: ScenarioSpec, selected: bool) -> bool:
    if spec.snapshot_gate == SNAPSHOT_REQUIRED:
        return selected
    if spec.snapshot_gate == SNAPSHOT_FORBIDDEN:
        return not selected
    return True


def _scenario_transcript(spec: ScenarioSpec) -> list[dict[str, str]]:
    return [{"action": step.action, "message": step.message} for step in spec.steps]


def _apply_step_to_mock_transport(transport: Transport, step: ScenarioStep) -> None:
    if not isinstance(transport, MockTransport):
        return
    payload = step.message.encode("utf-8")
    if step.action == "send":
        transport.write(payload)
    elif step.action == "inject":
        transport.inject_rx(payload)
    elif step.action == "expect":
        transport.read(size=len(payload) or 1, timeout=0.0)


def _run_scenario(scenario: str, transport: Transport, timeout: float, snapshot_capability: str) -> HILResult:
    spec = SCENARIO_SPECS[scenario]
    selected_snapshot_capability = _resolve_snapshot_capability(spec, snapshot_capability)
    transcript = _scenario_transcript(spec)
    notes = [step.message for step in spec.steps]
    notes.append(
        f"snapshot_capability={'yes' if selected_snapshot_capability else 'no'} gate={spec.snapshot_gate}"
    )

    metrics = HILMetrics()
    scenario_metadata = {
        "capability_gate": {"snapshot": spec.snapshot_gate},
        "snapshot_capability": selected_snapshot_capability,
        "default_stream_profile": DEFAULT_STREAM_PROFILE,
        "description": spec.description,
        "transport": transport.name,
        "simulated_duration_ms": spec.duration_ms,
        "transcript": transcript,
    }

    try:
        transport.open()
    except Exception as exc:
        notes.append(f"transport open failed: {exc}")
        scenario_metadata["result_reason"] = "transport_open_failed"
        return HILResult(
            schema_version=SCHEMA_VERSION,
            scenario=scenario,
            result=RESULT_FAILED,
            scenario_metadata=scenario_metadata,
            metrics=metrics,
            notes=notes,
        )

    result = RESULT_PASSED
    try:
        if not _snapshot_gate_satisfied(spec, selected_snapshot_capability):
            result = RESULT_SKIPPED
            notes.append("scenario skipped because snapshot capability gate is not satisfied")
            scenario_metadata["result_reason"] = "capability_gate_not_satisfied"
            return HILResult(
                schema_version=SCHEMA_VERSION,
                scenario=scenario,
                result=result,
                scenario_metadata=scenario_metadata,
                metrics=metrics,
                notes=notes,
            )

        simulated_timeout_ms = int(timeout * 1000)
        if spec.duration_ms > simulated_timeout_ms:
            result = RESULT_TIMEOUT
            notes.append(
                f"scenario timed out after {simulated_timeout_ms} ms budget before deterministic completion"
            )
            scenario_metadata["result_reason"] = "timeout"
            return HILResult(
                schema_version=SCHEMA_VERSION,
                scenario=scenario,
                result=result,
                scenario_metadata=scenario_metadata,
                metrics=metrics,
                notes=notes,
            )

        for step in spec.steps:
            _apply_step_to_mock_transport(transport, step)
            for metric_name, delta in step.metric_deltas.items():
                metrics.apply({metric_name: delta})

        scenario_metadata["result_reason"] = "completed"
        return HILResult(
            schema_version=SCHEMA_VERSION,
            scenario=scenario,
            result=result,
            scenario_metadata=scenario_metadata,
            metrics=metrics,
            notes=notes,
        )
    finally:
        transport.close()


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    transport = _make_transport(args)
    result = _run_scenario(args.scenario, transport, args.timeout, args.snapshot_capability)

    indent = None if args.json_indent == 0 else args.json_indent
    json.dump(result.to_json(), sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
