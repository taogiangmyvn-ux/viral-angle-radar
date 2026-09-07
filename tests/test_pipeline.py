import tempfile
import unittest
from pathlib import Path

from viral_radar.alerts import detect_format_changes
from viral_radar.pipeline import canonicalize_url, normalize, score_creator_candidate, viral_tier


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

    def test_new_format_requires_cross_creator_replication(self):
        dataset = {"generated_at": "2026-09-07T00:00:00Z", "viral_videos": [
            {"format": "gift build", "creator_handle": "@a", "benchmark_brand": "A", "likes": 20_000, "views": None, "primary_angle": "Recipient ritual"},
            {"format": "gift build", "creator_handle": "@b", "benchmark_brand": "B", "likes": 30_000, "views": None, "primary_angle": "Recipient ritual"},
        ]}
        report = detect_format_changes(dataset, {"formats": {}})
        self.assertEqual(report["alerts"][0]["level"], "new_format")

    def test_repeated_snapshot_does_not_alert(self):
        dataset = {"generated_at": "2026-09-07T00:00:00Z", "viral_videos": [
            {"format": "gift build", "creator_handle": "@a", "benchmark_brand": "A", "likes": 20_000, "views": None, "primary_angle": "Recipient ritual"},
        ]}
        previous = {"formats": {"gift build": {"qualified_sources": 1, "creators": 1, "brands": 1, "max_likes": 20_000, "max_views": 0, "angles": ["Recipient ritual"]}}}
        report = detect_format_changes(dataset, previous)
        self.assertEqual(report["status"], "no_material_change")

    def test_creator_rate_is_not_treated_as_confirmed(self):
        candidate = score_creator_candidate({
            "country": "United States", "follower_count": 20_000, "audited_post_count": 1,
            "observed_reference_likes": 12_000, "viral_post_count": 1,
            "voiceover_fit": 90, "music_edit_fit": 80, "candid_fit": 90,
            "rate_likelihood_under_200": "High"
        })
        self.assertEqual(candidate["shortlist_status"], "Needs 3-post audit")
        self.assertLess(candidate["evidence_confidence_score"], 100)

    def test_creator_alert_requires_ready_status(self):
        dataset = {"generated_at": "2026-09-07T00:00:00Z", "viral_videos": [], "creator_candidates": [
            {"handle": "@ready", "shortlist_status": "Shortlist ready", "shortlist_score": 84},
            {"handle": "@research", "shortlist_status": "Needs 3-post audit", "shortlist_score": 88},
        ]}
        report = detect_format_changes(dataset, {"formats": {}, "shortlist_creators": []})
        self.assertEqual([a["format"] for a in report["alerts"]], ["@ready"])


if __name__ == "__main__":
    unittest.main()
