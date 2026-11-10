import unittest
from unittest.mock import patch
import sys

import Script


class ScriptSanitizationTests(unittest.TestCase):
    def test_rejects_impossible_ping_values(self):
        result = {
            "download_mbps": 100.39,
            "upload_mbps": 99.68,
            "ping_ms": 600404.99,
            "method": "speedtest",
        }

        cleaned = Script.sanitize_speedtest_result(result)

        self.assertIsNone(cleaned["ping_ms"])

    def test_keeps_normal_speedtest_values(self):
        result = {
            "download_mbps": 102.5,
            "upload_mbps": 31.4,
            "ping_ms": 47.2,
            "method": "speedtest",
        }

        cleaned = Script.sanitize_speedtest_result(result)

        self.assertEqual(cleaned["download_mbps"], 102.5)
        self.assertEqual(cleaned["upload_mbps"], 31.4)
        self.assertEqual(cleaned["ping_ms"], 47.2)

    def test_no_save_flag_disables_report_output(self):
        with patch.object(sys, "argv", ["Script.py", "--no-save"]):
            args = Script.parse_args()

        self.assertFalse(args.save_report)


if __name__ == "__main__":
    unittest.main()
