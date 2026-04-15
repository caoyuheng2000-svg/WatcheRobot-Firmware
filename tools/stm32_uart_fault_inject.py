#!/usr/bin/env python3
"""Lightweight UART fault injection CLI scaffold.

The tool stays self-contained and mirrors the HIL runner's structured output
style so that fault injection can be consumed by the same reporting pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Iterable, Optional


SCHEMA_VERSION = "v1"
TRANSPORT_MOCK = "mock"
TRANSPORT_SERIAL = "serial"
EXECUTION_MODE_DETERMINISTIC = "deterministic"
EXECUTION_MODE_PLACEHOLDER = "placeholder"


@dataclass(slots=True)
class FaultSpec:
    fault_type: str
    category: str
    expected_observation: str
    note: str
    expected_counter_deltas: dict[str, int] = field(default_factory=dict)
    aliases: tuple[str, ...] = ()


FAULT_SPECS: dict[str, FaultSpec] = {
    "crc_fault_injection": FaultSpec(
        fault_type="crc_fault_injection",
        category="link_integrity",
        expected_observation="crc_error_count increments and the frame is dropped",
        note="emit frame with invalid CRC",
        expected_counter_deltas={"crc_error_count": 1, "dropped_state_count": 1},
        aliases=("crc",),
    ),
    "truncated_frame_injection": FaultSpec(
        fault_type="truncated_frame_injection",
        category="link_integrity",
        expected_observation="decoder resyncs after partial frame loss",
        note="emit partial frame and stop mid-payload",
        expected_counter_deltas={"dropped_state_count": 1},
        aliases=("truncated_frame",),
    ),
    "heartbeat_loss_simulation": FaultSpec(
        fault_type="heartbeat_loss_simulation",
        category="link_liveness",
        expected_observation="recovery logic observes a missed heartbeat window",
        note="suppress heartbeat traffic for a configured window",
        expected_counter_deltas={"reconnect_count": 1},
        aliases=("heartbeat_loss",),
    ),
    "ack_timeout_simulation": FaultSpec(
        fault_type="ack_timeout_simulation",
        category="command_timing",
        expected_observation="command transitions into timeout handling",
        note="accept transmit request but do not return ACK within timeout window",
        expected_counter_deltas={"ack_timeout_count": 1},
        aliases=("ack_timeout",),
    ),
    "busy_nack_path": FaultSpec(
        fault_type="busy_nack_path",
        category="command_rejection",
        expected_observation="command is rejected with a deterministic busy NACK",
        note="respond with NACK reason=busy for the target command",
        expected_counter_deltas={},
        aliases=("busy_nack",),
    ),
}

FAULT_LOOKUP: dict[str, FaultSpec] = {}
for spec in FAULT_SPECS.values():
    FAULT_LOOKUP[spec.fault_type] = spec
    for alias in spec.aliases:
        FAULT_LOOKUP[alias] = spec

FAULT_TYPES = tuple(sorted(FAULT_LOOKUP))


@dataclass(slots=True)
class FaultInjectResult:
    schema_version: str
    scenario: str
    fault_type: str
    requested_fault: str
    count: int
    applied_count: int
    result: str
    result_reason: str
    transport: str
    execution_mode: str
    scenario_metadata: dict[str, object]
    notes: list[str]

    def to_json(self) -> dict[str, object]:
        return asdict(self)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python tools/stm32_uart_fault_inject.py",
        description="STM32 UART fault injection scaffold",
    )
    parser.add_argument(
        "--fault",
        choices=FAULT_TYPES,
        required=True,
        help="Fault type to inject",
    )
    parser.add_argument("--count", type=int, default=1, help="Number of injections to perform")
    parser.add_argument(
        "--transport",
        choices=(TRANSPORT_MOCK, TRANSPORT_SERIAL),
        default=TRANSPORT_MOCK,
        help="Transport backend",
    )
    parser.add_argument("--port", help="Optional serial port for future hardware injection hooks")
    parser.add_argument(
        "--json-indent",
        type=int,
        default=2,
        help="Pretty-print JSON with this indent; use 0 for compact output",
    )
    return parser


def _resolve_fault(requested_fault: str) -> tuple[str, FaultSpec]:
    spec = FAULT_LOOKUP.get(requested_fault)
    if spec is None:
        raise SystemExit(f"unknown fault type: {requested_fault}")
    return spec.fault_type, spec


def _build_notes(spec: FaultSpec, count: int) -> list[str]:
    if count == 1:
        return [spec.note]
    return [f"{index}/{count}: {spec.note}" for index in range(1, count + 1)]


def _run_injection(args: argparse.Namespace) -> FaultInjectResult:
    if args.count <= 0:
        raise SystemExit("--count must be greater than zero")

    canonical_fault, spec = _resolve_fault(args.fault)
    notes = _build_notes(spec, args.count)
    expected_counter_deltas = {
        metric: delta * args.count for metric, delta in spec.expected_counter_deltas.items()
    }

    scenario_metadata = {
        "transport": args.transport,
        "transport_state": "placeholder" if args.transport == TRANSPORT_SERIAL else "deterministic",
        "category": spec.category,
        "expected_observation": spec.expected_observation,
        "expected_counter_deltas": expected_counter_deltas,
        "requested_fault": args.fault,
        "canonical_fault": canonical_fault,
        "aliases": list(spec.aliases),
        "simulated_duration_ms": 5 * args.count,
    }

    if args.transport == TRANSPORT_SERIAL:
        notes.append("serial transport is a placeholder until hardware is wired")
        scenario_metadata["result_reason"] = "serial_placeholder"
        return FaultInjectResult(
            schema_version=SCHEMA_VERSION,
            scenario=canonical_fault,
            fault_type=canonical_fault,
            requested_fault=args.fault,
            count=args.count,
            applied_count=0,
            result="skipped",
            result_reason="serial_placeholder",
            transport=args.transport,
            execution_mode=EXECUTION_MODE_PLACEHOLDER,
            scenario_metadata=scenario_metadata,
            notes=notes,
        )

    scenario_metadata["result_reason"] = "applied"
    return FaultInjectResult(
        schema_version=SCHEMA_VERSION,
        scenario=canonical_fault,
        fault_type=canonical_fault,
        requested_fault=args.fault,
        count=args.count,
        applied_count=args.count,
        result="applied",
        result_reason="applied",
        transport=args.transport,
        execution_mode=EXECUTION_MODE_DETERMINISTIC,
        scenario_metadata=scenario_metadata,
        notes=notes,
    )


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = _run_injection(args)
    indent = None if args.json_indent == 0 else args.json_indent
    json.dump(result.to_json(), sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
