from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tools.power_5v_toggle_hil import evaluate


def test_evaluate_power_toggle_passes_when_stm32_logs_all_cycles() -> None:
    stm32_lines: list[str] = []
    for _ in range(20):
        stm32_lines.extend(
            [
                "ip5306_off",
                "Action: Drive NMOS gate HIGH twice for 100ms",
                "ip5306_on",
                "Action: Drive NMOS gate HIGH for 100ms",
            ]
        )

    capture = SimpleNamespace(
        stm32_lines=stm32_lines,
        stm32_line_count=len(stm32_lines),
        esp32_line_count=10,
        merged_path=Path("merged.log"),
        esp32_path=Path("esp32.log"),
        stm32_path=Path("stm32.log"),
    )

    result = evaluate(capture, cycles=20)

    assert result.result == "pass"
    assert result.off_actions_seen == 20
    assert result.on_actions_seen == 20
    assert result.failures == []


def test_evaluate_power_toggle_reports_missing_on_action() -> None:
    capture = SimpleNamespace(
        stm32_lines=[
            "ip5306_off",
            "Action: Drive NMOS gate HIGH twice for 100ms",
            "ip5306_on",
        ],
        stm32_line_count=3,
        esp32_line_count=10,
        merged_path=Path("merged.log"),
        esp32_path=Path("esp32.log"),
        stm32_path=Path("stm32.log"),
    )

    result = evaluate(capture, cycles=1)

    assert result.result == "failed"
    assert "on_actions_seen_below_cycles:0<1" in result.failures
