import tempfile
import unittest
from pathlib import Path

from viral_radar.pipeline import canonicalize_url, normalize, viral_tier


class PipelineTests(unittest.TestCase):
    def test_canonical_url_removes_tracking(self):
        url, video_id = canonicalize_url("https://www.tiktok.com/@creator/video/1234567890?lang=en")
        self.assertEqual(url, "https://www.tiktok.com/@creator/video/1234567890")
        self.assertEqual(video_id, "1234567890")

    def test_invalid_url_is_rejected(self):
        with self.assertRaises(ValueError):
            canonicalize_url("https://example.com/video/1")

    def test_unknown_metrics_remain_null(self):
        item = normalize({"canonical_url":"https://www.tiktok.com/@creator/video/1234567890"}, "manual_csv")
        self.assertIsNone(item["metrics"]["views"])
        self.assertEqual(item["creator_country"], "Unverified")

    def test_viral_threshold_is_hard_gate(self):
        self.assertEqual(viral_tier(None, 9_999), "Watchlist")
        self.assertEqual(viral_tier(None, 10_000), "Qualified")
        self.assertEqual(viral_tier(1_000_000, None), "Qualified")

    def test_viral_tiers(self):
        self.assertEqual(viral_tier(None, 100_000), "Breakout")
        self.assertEqual(viral_tier(None, 1_000_000), "Mega")


if __name__ == "__main__":
    unittest.main()
