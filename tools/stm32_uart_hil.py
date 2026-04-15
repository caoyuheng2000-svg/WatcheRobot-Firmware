#!/usr/bin/env python3
"""Minimal STM32 UART HIL runner scaffold.

The script stays self-contained and supports two execution modes:

- ``mock``: deterministic offline execution with capability-gated scenarios
- ``serial``: placeholder transport for later real hardware wiring

The JSON output is intentionally aligned with the integration docs: the core
top-level fields are the documented scenario/result/metric/notes entries, while
auxiliary metadata is grouped under ``scenario_metadata``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Iterable, Optional, Protocol


SCHEMA_VERSION = "v1"
DEFAULT_STREAM_PROFILE = "v1_default"
DEFAULT_SCENARIO = "hello_heartbeat_smoke"

SNAPSHOT_REQUIRED = "required"
SNAPSHOT_FORBIDDEN = "forbidden"
SNAPSHOT_OPTIONAL = "optional"

RESULT_PASSED = "passed"
RESULT_SKIPPED = "skipped"
RESULT_TIMEOUT = "timeout"
RESULT_FAILED = "failed"

TRANSPORT_MOCK = "mock"
TRANSPORT_SERIAL = "serial"

EXECUTION_MODE_DETERMINISTIC = "deterministic"
EXECUTION_MODE_PLACEHOLDER = "placeholder"


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
            ScenarioStep("inject", "IMU_STATE collapse=latest", {"dropped_state_count": 4}),
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

    def to_json(self) -> dict[str, int]:
        return asdict(self)


@dataclass(slots=True)
class HILScenarioResult:
    schema_version: str
    scenario: str
    scenario_index: int
    result: str
    result_reason: str
    transport: str
    execution_mode: str
    scenario_metadata: dict[str, object]
    metrics: HILMetrics
    notes: list[str]

    @property
    def ok(self) -> bool:
        return self.result in {RESULT_PASSED, RESULT_SKIPPED}

    def to_json(self) -> dict[str, object]:
        payload = {
            "schema_version": self.schema_version,
            "scenario": self.scenario,
            "scenario_index": self.scenario_index,
            "result": self.result,
            "result_reason": self.result_reason,
            "transport": self.transport,
            "execution_mode": self.execution_mode,
            "scenario_metadata": self.scenario_metadata,
            "ack_timeout_count": self.metrics.ack_timeout_count,
            "crc_error_count": self.metrics.crc_error_count,
            "dropped_state_count": self.metrics.dropped_state_count,
            "reconnect_count": self.metrics.reconnect_count,
            "motion_done_fault_count": self.metrics.motion_done_fault_count,
            "notes": self.notes,
        }
        return payload


@dataclass(slots=True)
class HILSuiteResult:
    schema_version: str
    result: str
    result_reason: str
    transport: str
    execution_mode: str
    scenario_filter: dict[str, object]
    selected_scenarios: list[str]
    summary: dict[str, int]
    scenario_results: list[dict[str, object]]
    scenario_metadata: dict[str, object]
    metrics: HILMetrics
    notes: list[str]

    @property
    def ok(self) -> bool:
        return self.result in {RESULT_PASSED, RESULT_SKIPPED}

    def to_json(self) -> dict[str, object]:
        payload = {
            "schema_version": self.schema_version,
            "result": self.result,
            "result_reason": self.result_reason,
            "transport": self.transport,
            "execution_mode": self.execution_mode,
            "scenario_filter": self.scenario_filter,
            "selected_scenarios": self.selected_scenarios,
            "summary": self.summary,
            "scenario_results": self.scenario_results,
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

    name = TRANSPORT_MOCK

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

    name = TRANSPORT_SERIAL

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
        action="append",
        metavar="NAME",
        help="Scenario name to run; repeat to run multiple scenarios",
    )
    parser.add_argument(
        "--scenario-filter",
        help="Regular expression used to select scenarios by name or description",
    )
    parser.add_argument(
        "--exclude-scenario",
        action="append",
        default=[],
        metavar="NAME",
        help="Scenario name to remove after filtering",
    )
    parser.add_argument(
        "--all-scenarios",
        action="store_true",
        help="Run every built-in scenario in declaration order",
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="Print the available scenario catalog and exit",
    )
    parser.add_argument(
        "--transport",
        choices=(TRANSPORT_MOCK, TRANSPORT_SERIAL),
        default=TRANSPORT_MOCK,
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
    if args.transport == TRANSPORT_SERIAL:
        return SerialTransport(args.port or "PLACEHOLDER", args.baud)
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


def _scenario_transcript(spec: ScenarioSpec) -> list[dict[str, object]]:
    return [
        {
            "action": step.action,
            "message": step.message,
            "metric_deltas": dict(step.metric_deltas),
        }
        for step in spec.steps
    ]


def _build_scenario_metadata(
    spec: ScenarioSpec,
    transport: Transport,
    selected_snapshot_capability: bool,
    scenario_index: int,
) -> dict[str, object]:
    return {
        "capability_gate": {"snapshot": spec.snapshot_gate},
        "snapshot_capability": selected_snapshot_capability,
        "default_stream_profile": DEFAULT_STREAM_PROFILE,
        "description": spec.description,
        "transport": transport.name,
        "execution_index": scenario_index,
        "simulated_duration_ms": spec.duration_ms,
        "transcript": _scenario_transcript(spec),
    }


def _run_single_scenario(
    spec: ScenarioSpec,
    transport: Transport,
    timeout: float,
    snapshot_capability: str,
    scenario_index: int,
) -> HILScenarioResult:
    selected_snapshot_capability = _resolve_snapshot_capability(spec, snapshot_capability)
    notes = [f"scenario={spec.name}", f"execution_index={scenario_index}"]
    metrics = HILMetrics()
    scenario_metadata = _build_scenario_metadata(
        spec,
        transport,
        selected_snapshot_capability,
        scenario_index,
    )

    if transport.name == TRANSPORT_SERIAL:
        notes.append("serial transport is a placeholder until hardware is wired")
        scenario_metadata["transport_state"] = "placeholder"
        scenario_metadata["result_reason"] = "serial_placeholder"
        return HILScenarioResult(
            schema_version=SCHEMA_VERSION,
            scenario=spec.name,
            scenario_index=scenario_index,
            result=RESULT_SKIPPED,
            result_reason="serial_placeholder",
            transport=transport.name,
            execution_mode=EXECUTION_MODE_PLACEHOLDER,
            scenario_metadata=scenario_metadata,
            metrics=metrics,
            notes=notes,
        )

    try:
        transport.open()
    except Exception as exc:
        notes.append(f"transport open failed: {exc}")
        scenario_metadata["transport_state"] = "unavailable"
        scenario_metadata["result_reason"] = "transport_open_failed"
        return HILScenarioResult(
            schema_version=SCHEMA_VERSION,
            scenario=spec.name,
            scenario_index=scenario_index,
            result=RESULT_FAILED,
            result_reason="transport_open_failed",
            transport=transport.name,
            execution_mode=EXECUTION_MODE_DETERMINISTIC,
            scenario_metadata=scenario_metadata,
            metrics=metrics,
            notes=notes,
        )

    try:
        if not _snapshot_gate_satisfied(spec, selected_snapshot_capability):
            notes.append("scenario skipped because snapshot capability gate is not satisfied")
            scenario_metadata["result_reason"] = "capability_gate_not_satisfied"
            return HILScenarioResult(
                schema_version=SCHEMA_VERSION,
                scenario=spec.name,
                scenario_index=scenario_index,
                result=RESULT_SKIPPED,
                result_reason="capability_gate_not_satisfied",
                transport=transport.name,
                execution_mode=EXECUTION_MODE_DETERMINISTIC,
                scenario_metadata=scenario_metadata,
                metrics=metrics,
                notes=notes,
            )

        simulated_timeout_ms = int(timeout * 1000)
        if spec.duration_ms > simulated_timeout_ms:
            notes.append(
                f"scenario timed out after {simulated_timeout_ms} ms budget before deterministic completion"
            )
            scenario_metadata["result_reason"] = "timeout"
            return HILScenarioResult(
                schema_version=SCHEMA_VERSION,
                scenario=spec.name,
                scenario_index=scenario_index,
                result=RESULT_TIMEOUT,
                result_reason="timeout",
                transport=transport.name,
                execution_mode=EXECUTION_MODE_DETERMINISTIC,
                scenario_metadata=scenario_metadata,
                metrics=metrics,
                notes=notes,
            )

        for step in spec.steps:
            payload = step.message.encode("utf-8")
            if step.action == "send":
                transport.write(payload)
            elif step.action == "inject":
                transport.inject_rx(payload)
            elif step.action == "expect":
                transport.read(size=len(payload) or 1, timeout=0.0)
            else:
                raise KeyError(f"unknown scenario action {step.action!r}")
            if step.metric_deltas:
                metrics.apply(step.metric_deltas)

        scenario_metadata["result_reason"] = "completed"
        return HILScenarioResult(
            schema_version=SCHEMA_VERSION,
            scenario=spec.name,
            scenario_index=scenario_index,
            result=RESULT_PASSED,
            result_reason="completed",
            transport=transport.name,
            execution_mode=EXECUTION_MODE_DETERMINISTIC,
            scenario_metadata=scenario_metadata,
            metrics=metrics,
            notes=notes,
        )
    finally:
        transport.close()


def _summarize_results(results: list[HILScenarioResult]) -> dict[str, int]:
    counts = {
        RESULT_PASSED: 0,
        RESULT_SKIPPED: 0,
        RESULT_TIMEOUT: 0,
        RESULT_FAILED: 0,
    }
    for result in results:
        counts[result.result] = counts.get(result.result, 0) + 1
    counts["selected"] = len(results)
    counts["executed"] = counts[RESULT_PASSED] + counts[RESULT_TIMEOUT] + counts[RESULT_FAILED]
    counts["completed"] = counts[RESULT_PASSED] + counts[RESULT_SKIPPED]
    return counts


def _aggregate_metrics(results: list[HILScenarioResult]) -> HILMetrics:
    totals = HILMetrics()
    for result in results:
        totals.apply(result.metrics.to_json())
    return totals


def _build_suite_result(
    selected_specs: list[ScenarioSpec],
    transport_factory: Callable[[], Transport],
    timeout: float,
    snapshot_capability: str,
    scenario_filter: dict[str, object],
) -> HILSuiteResult:
    results: list[HILScenarioResult] = []
    for index, spec in enumerate(selected_specs):
        transport = transport_factory()
        results.append(
            _run_single_scenario(
                spec,
                transport,
                timeout,
                snapshot_capability,
                index,
            )
        )

    summary = _summarize_results(results)
    aggregated_metrics = _aggregate_metrics(results)
    if summary[RESULT_FAILED] > 0:
        suite_result = RESULT_FAILED
        suite_reason = "one_or_more_scenarios_failed"
    elif summary[RESULT_TIMEOUT] > 0:
        suite_result = RESULT_TIMEOUT
        suite_reason = "one_or_more_scenarios_timed_out"
    elif summary[RESULT_PASSED] > 0:
        suite_result = RESULT_PASSED
        suite_reason = "all_selected_scenarios_completed"
    else:
        suite_result = RESULT_SKIPPED
        suite_reason = "all_selected_scenarios_skipped"

    scenario_metadata = {
        "default_stream_profile": DEFAULT_STREAM_PROFILE,
        "scenario_count": len(selected_specs),
        "selected_scenarios": [spec.name for spec in selected_specs],
        "scenario_filter": scenario_filter,
    }

    return HILSuiteResult(
        schema_version=SCHEMA_VERSION,
        result=suite_result,
        result_reason=suite_reason,
        transport=str(scenario_filter.get("transport", TRANSPORT_MOCK)),
        execution_mode=EXECUTION_MODE_PLACEHOLDER if scenario_filter.get("transport") == TRANSPORT_SERIAL else EXECUTION_MODE_DETERMINISTIC,
        scenario_filter=scenario_filter,
        selected_scenarios=[spec.name for spec in selected_specs],
        summary=summary,
        scenario_results=[result.to_json() for result in results],
        scenario_metadata=scenario_metadata,
        metrics=aggregated_metrics,
        notes=[
            f"selected_count={len(selected_specs)}",
            f"filter={scenario_filter.get('pattern') or 'none'}",
        ],
    )


def _list_scenarios_payload() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "scenarios": [
            {
                "name": spec.name,
                "description": spec.description,
                "snapshot_gate": spec.snapshot_gate,
                "duration_ms": spec.duration_ms,
                "transcript": _scenario_transcript(spec),
            }
            for spec in SCENARIO_SPECS.values()
        ],
    }


def _select_scenarios(args: argparse.Namespace) -> tuple[list[ScenarioSpec], dict[str, object]]:
    if args.all_scenarios and args.scenario:
        raise SystemExit("--all-scenarios cannot be combined with --scenario")

    if args.list_scenarios:
        scenario_names = [spec.name for spec in SCENARIO_SPECS.values()]
        return list(SCENARIO_SPECS.values()), {
            "transport": args.transport,
            "pattern": args.scenario_filter,
            "requested": args.scenario or [],
            "all_scenarios": args.all_scenarios,
            "excluded": list(args.exclude_scenario),
            "mode": "list",
            "available_scenarios": scenario_names,
        }

    if args.all_scenarios:
        base_specs = list(SCENARIO_SPECS.values())
    elif args.scenario:
        missing = [name for name in args.scenario if name not in SCENARIO_SPECS]
        if missing:
            raise SystemExit(f"unknown scenario(s): {', '.join(missing)}")
        seen: set[str] = set()
        base_specs = []
        for name in args.scenario:
            if name in seen:
                continue
            seen.add(name)
            base_specs.append(SCENARIO_SPECS[name])
    elif args.scenario_filter:
        base_specs = list(SCENARIO_SPECS.values())
    else:
        base_specs = [SCENARIO_SPECS[DEFAULT_SCENARIO]]

    pattern = re.compile(args.scenario_filter) if args.scenario_filter else None
    excluded = set(args.exclude_scenario or [])

    selected_specs = []
    for spec in base_specs:
        if pattern and not (pattern.search(spec.name) or pattern.search(spec.description)):
            continue
        if spec.name in excluded:
            continue
        selected_specs.append(spec)

    if not selected_specs:
        raise SystemExit("no scenarios matched the requested filters")

    return selected_specs, {
        "transport": args.transport,
        "pattern": args.scenario_filter,
        "requested": args.scenario or [],
        "all_scenarios": args.all_scenarios,
        "excluded": list(args.exclude_scenario),
        "mode": "suite" if len(selected_specs) > 1 else "single",
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.list_scenarios:
        payload = _list_scenarios_payload()
        indent = None if args.json_indent == 0 else args.json_indent
        json.dump(payload, sys.stdout, indent=indent, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    selected_specs, scenario_filter = _select_scenarios(args)
    transport_factory = lambda: _make_transport(args)

    if len(selected_specs) == 1 and scenario_filter["mode"] == "single":
        result = _run_single_scenario(
            selected_specs[0],
            transport_factory(),
            args.timeout,
            args.snapshot_capability,
            0,
        )
        payload = result.to_json()
        exit_code = 0 if result.ok else 1
    else:
        result = _build_suite_result(
            selected_specs,
            transport_factory,
            args.timeout,
            args.snapshot_capability,
            scenario_filter,
        )
        payload = result.to_json()
        exit_code = 0 if result.ok else 1

    indent = None if args.json_indent == 0 else args.json_indent
    json.dump(payload, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
