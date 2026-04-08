from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from tools.win_flasher.package_parser import PackageParseError, parse_flash_package
from tools.win_flasher.releases import get_repo_root


class PackageParserTests(unittest.TestCase):
    def test_parse_existing_release_zip(self) -> None:
        repo_root = get_repo_root()
        package_path = repo_root / "firmware" / "s3" / "release" / "v0.1.8" / "WatcheRobot-S3-v0.1.8-esp32s3.zip"
        package = parse_flash_package(package_path)

        self.assertEqual(package.version, "v0.1.8")
        self.assertEqual(package.chip, "esp32s3")
        self.assertEqual(len(package.segments), 5)
        self.assertEqual(package.segments[0].file_name, "bootloader.bin")

    def test_missing_flash_args_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / "bad.zip"
            with ZipFile(zip_path, "w") as zf:
                zf.writestr("bootloader.bin", b"boot")

            with self.assertRaises(PackageParseError):
                parse_flash_package(zip_path)

    def test_basename_fallback_resolves_nested_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = Path(temp_dir) / "fallback.zip"
            with ZipFile(zip_path, "w") as zf:
                zf.writestr(
                    "flash_args.txt",
                    "\n".join(
                        [
                            "--flash_mode dio --flash_freq 80m --flash_size 16MB",
                            "0x0 bootloader/bootloader.bin",
                            "0x8000 partition_table/partition-table.bin",
                            "0x10000 app/WatcheRobot-S3.bin",
                        ]
                    ),
                )
                zf.writestr("bootloader.bin", b"boot")
                zf.writestr("partition-table.bin", b"table")
                zf.writestr("WatcheRobot-S3.bin", b"app")

            package = parse_flash_package(zip_path)
            self.assertEqual([segment.file_name for segment in package.segments], [
                "bootloader.bin",
                "partition-table.bin",
                "WatcheRobot-S3.bin",
            ])


if __name__ == "__main__":
    unittest.main()
