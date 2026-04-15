#!/usr/bin/env python3
"""Lightweight UART fault injection CLI scaffold.

The tool stays self-contained and mirrors the HIL runner's structured output
style so that fault injection can be consumed by the same reporting pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from typing import Iterable, Optional


SCHEMA_VERSION = "v1"

FAULT_TYPES = ("crc", "truncated_frame", "heartbeat_loss", "ack_timeout", "busy_nack")


@dataclass(slots=True)
class FaultSpec:
    fault_type: str
    category: str
    expected_observation: str
    note: str
    expected_counter_deltas: dict[str, int] = field(default_factory=dict)


FAULT_SPECS: dict[str, FaultSpec] = {
    "crc": FaultSpec(
        fault_type="crc",
        category="link_integrity",
        expected_observation="crc_error_count increments and the frame is dropped",
        note="emit frame with invalid CRC",
        expected_counter_deltas={"crc_error_count": 1, "dropped_state_count": 1},
    ),
    "truncated_frame": FaultSpec(
        fault_type="truncated_frame",
        category="link_integrity",
        expected_observation="decoder resyncs after partial frame loss",
        note="emit partial frame and stop mid-payload",
        expected_counter_deltas={"dropped_state_count": 1},
    ),
    "heartbeat_loss": FaultSpec(
        fault_type="heartbeat_loss",
        category="link_liveness",
        expected_observation="recovery logic observes a missed heartbeat window",
        note="suppress heartbeat traffic for a configured window",
        expected_counter_deltas={"reconnect_count": 1},
    ),
    "ack_timeout": FaultSpec(
        fault_type="ack_timeout",
        category="command_timing",
        expected_observation="command transitions into timeout handling",
        note="accept transmit request but do not return ACK within timeout window",
        expected_counter_deltas={"ack_timeout_count": 1},
    ),
    "busy_nack": FaultSpec(
        fault_type="busy_nack",
        category="command_rejection",
        expected_observation="command is rejected with a deterministic busy NACK",
        note="respond with NACK reason=busy for the target command",
        expected_counter_deltas={},
    ),
}


@dataclass(slots=True)
class FaultInjectResult:
    schema_version: str
    fault_type: str
    count: int
    result: str
    scenario_metadata: dict[str, object]
    notes: list[str]

    def to_json(self) -> dict:
        payload = asdict(self)
        return payload


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
        choices=("mock", "serial"),
        default="mock",
        help="Transport backend",
    )
    parser.add_argument("--port", help="Serial port for future hardware injection hooks")
    parser.add_argument(
        "--json-indent",
        type=int,
        default=2,
        help="Pretty-print JSON with this indent; use 0 for compact output",
    )
    return parser


def _build_notes(spec: FaultSpec, count: int) -> list[str]:
    if count <= 0:
        return ["count must be greater than zero"]
    if count == 1:
        return [spec.note]
    return [f"{index}/{count}: {spec.note}" for index in range(1, count + 1)]


def _run_injection(args: argparse.Namespace) -> FaultInjectResult:
    if args.count <= 0:
        raise SystemExit("--count must be greater than zero")

    spec = FAULT_SPECS[args.fault]
    notes = _build_notes(spec, args.count)

    expected_counter_deltas = {
        metric: delta * args.count for metric, delta in spec.expected_counter_deltas.items()
    }

    scenario_metadata = {
        "transport": args.transport,
        "category": spec.category,
        "expected_observation": spec.expected_observation,
        "expected_counter_deltas": expected_counter_deltas,
        "simulated_duration_ms": 5 * args.count,
    }

    return FaultInjectResult(
        schema_version=SCHEMA_VERSION,
        fault_type=args.fault,
        count=args.count,
        result="applied",
        scenario_metadata=scenario_metadata,
        notes=notes,
    )


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.transport == "serial" and not args.port:
        parser.error("--port is required when --transport serial is selected")

    result = _run_injection(args)
    indent = None if args.json_indent == 0 else args.json_indent
    json.dump(result.to_json(), sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
