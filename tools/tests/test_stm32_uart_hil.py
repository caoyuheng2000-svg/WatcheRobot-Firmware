from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.stm32_uart_hil import evaluate_stress_standard_session


def _write_timeline(session_dir: Path, records: list[dict[str, object]]) -> None:
    (session_dir / "timeline.ndjson").write_text(
        "\n".join(json.dumps(record, ensure_ascii=True) for record in records) + "\n",
        encoding="utf-8",
    )


class Stm32UartHilTests(unittest.TestCase):
    def test_evaluate_stress_standard_session_passes_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir)
            _write_timeline(
                session_dir,
                [
                    {"source": "esp32", "kv": {"evt": "ready"}},
                    {
                        "source": "esp32",
                        "kv": {
                            "evt": "stress_stats",
                            "servo_submit_count": "3000",
                            "motion_ack_count": "3000",
                            "motion_done_count": "3000",
                            "touch_rx_count": "600",
                            "mag_rx_count": "1200",
                            "imu_rx_count": "0",
                            "ack_timeout_count": "0",
                            "crc_error_count": "0",
                            "dropped_state_count": "0",
                            "reconnect_count": "0",
                            "motion_done_fault_count": "0",
                        },
                    },
                ],
            )

            metrics, failures, metadata = evaluate_stress_standard_session(session_dir)

        self.assertEqual(failures, [])
        self.assertEqual(metrics.servo_submit_count, 3000)
        self.assertEqual(metrics.motion_done_count, 3000)
        self.assertEqual(metadata["session_dir"], str(session_dir))

    def test_evaluate_stress_standard_session_reports_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_dir = Path(temp_dir)
            _write_timeline(
                session_dir,
                [
                    {
                        "source": "esp32",
                        "kv": {
                            "evt": "stress_stats",
                            "servo_submit_count": "100",
                            "motion_ack_count": "99",
                            "motion_done_count": "98",
                            "touch_rx_count": "5",
                            "mag_rx_count": "20",
                            "imu_rx_count": "0",
                            "ack_timeout_count": "1",
                            "crc_error_count": "2",
                            "dropped_state_count": "0",
                            "reconnect_count": "1",
                            "motion_done_fault_count": "1",
                        },
                    },
                    {"source": "stm32", "kv": {"evt": "dispatch_fail"}},
                ],
            )

            _metrics, failures, _metadata = evaluate_stress_standard_session(session_dir)

        self.assertIn("missing_ready", failures)
        self.assertIn("stm32_dispatch_fail_seen", failures)
        self.assertIn("servo_submit_count_below_threshold", failures)
        self.assertIn("motion_ack_count_mismatch", failures)
        self.assertIn("motion_done_count_mismatch", failures)


if __name__ == "__main__":
    unittest.main()
