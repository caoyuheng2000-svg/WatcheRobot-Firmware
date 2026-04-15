#!/usr/bin/env python3
"""Lightweight UART fault injection CLI scaffold.

The script defines the supported fault categories and a minimal command surface
for later integration with the HIL transport layer.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from typing import Iterable, Optional


FAULT_TYPES = ("crc", "truncated_frame", "heartbeat_loss", "ack_timeout", "busy_nack")


@dataclass(slots=True)
class FaultInjectResult:
    fault_type: str
    count: int
    transport: str
    applied: bool
    notes: list[str]

    def to_json(self) -> dict:
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


def _run_injection(args: argparse.Namespace) -> FaultInjectResult:
    notes = {
        "crc": ["emit frame with invalid CRC"],
        "truncated_frame": ["emit partial frame and stop mid-payload"],
        "heartbeat_loss": ["suppress heartbeat traffic for a configured window"],
        "ack_timeout": ["accept transmit request but do not return ACK within timeout window"],
        "busy_nack": ["respond with NACK reason=busy for the target command"],
    }[args.fault]
    return FaultInjectResult(
        fault_type=args.fault,
        count=args.count,
        transport=args.transport,
        applied=True,
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
