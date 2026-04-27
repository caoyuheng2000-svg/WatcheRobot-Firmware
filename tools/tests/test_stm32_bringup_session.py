from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import serial

from tools.stm32_bringup_session import (
    SessionError,
    build_log_record,
    load_device_map,
    open_serial_port,
    parse_observation_line,
    sort_records,
)


class Stm32BringupSessionTests(unittest.TestCase):
    def test_load_device_map_reads_shared_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            device_map_path = Path(temp_dir) / "device-map.toml"
            device_map_path.write_text(
                "\n".join(
                    [
                        "[devices.s3-c]",
                        'firmware = "s3"',
                        'port = "COM28"',
                        "",
                        "[devices.stm32-c]",
                        'firmware = "stm32"',
                        'port = "COM18"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            mappings = load_device_map(device_map_path)

        self.assertEqual(mappings["s3-c"].port, "COM28")
        self.assertEqual(mappings["stm32-c"].firmware, "stm32")

    def test_parse_observation_line_extracts_structured_fields(self) -> None:
        kind, kv = parse_observation_line("I (123) MCU_OBS: evt=hello_rsp seq=7 link_state=READY")
        self.assertEqual(kind, "obs")
        self.assertEqual(kv, {"evt": "hello_rsp", "seq": "7", "link_state": "READY"})

        kind, kv = parse_observation_line("STM32 bring-up ready")
        self.assertEqual(kind, "log")
        self.assertEqual(kv, {})

    def test_sort_records_merges_by_host_timestamp(self) -> None:
        later = build_log_record("stm32", "COM18", "STM32_OBS evt=boot", ts_ns=2_000_000_000)
        earlier = build_log_record("esp32", "COM28", "MCU_OBS evt=hello_req seq=1", ts_ns=1_000_000_000)

        records = sort_records([later, earlier])

        self.assertEqual([record.source for record in records], ["esp32", "stm32"])
        self.assertEqual(records[0].kv["evt"], "hello_req")
        self.assertEqual(records[1].kv["evt"], "boot")

    def test_open_serial_port_fails_fast(self) -> None:
        with mock.patch("tools.stm32_bringup_session.serial.Serial", side_effect=serial.SerialException("busy")):
            with self.assertRaises(SessionError):
                open_serial_port("COM18", 115200)


if __name__ == "__main__":
    unittest.main()
