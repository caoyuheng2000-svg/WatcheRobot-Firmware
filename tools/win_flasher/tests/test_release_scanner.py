from __future__ import annotations

import unittest

from tools.win_flasher.releases import get_latest_release, scan_release_entries


class ReleaseScannerTests(unittest.TestCase):
    def test_scans_and_sorts_releases(self) -> None:
        entries = scan_release_entries()
        versions = [entry.version for entry in entries[:4]]
        self.assertEqual(versions, ["v0.1.8", "v0.1.7", "v0.1.6", "v0.1.5"])

    def test_latest_release_is_v018(self) -> None:
        latest = get_latest_release()
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.version, "v0.1.8")
        self.assertTrue(latest.zip_path.name.endswith(".zip"))


if __name__ == "__main__":
    unittest.main()
