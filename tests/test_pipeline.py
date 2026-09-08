import json
import tempfile
import unittest
from pathlib import Path

from viral_radar.alerts import detect_format_changes
from viral_radar.pipeline import allocate_pieces, build_monthly_strategy, canonicalize_url, normalize, score_creator_candidate, viral_tier
from viral_radar.scout import adapt_post, build_creator_candidates, build_sound_snapshot


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

    def test_apify_post_adapter_preserves_real_metrics(self):
        post = adapt_post({
            "id": "777", "text": "my honest review of this body care routine #bodycare",
            "createTime": 1_725_000_000, "playCount": 1_200_000, "diggCount": 42_000,
            "commentCount": 410, "shareCount": 900,
            "authorMeta": {"name": "smallcreator", "nickName": "Small Creator", "fans": 18_000, "region": "US"}
        })
        self.assertEqual(post["canonical_url"], "https://www.tiktok.com/@smallcreator/video/777")
        self.assertEqual(post["creator_country"], "United States")
        self.assertEqual(post["views"], 1_200_000)
        self.assertEqual(post["primary_angle"], "Earn the right to recommend it as a gift")

    def test_apify_flattened_output_fields_are_supported(self):
        post = adapt_post({"id": "778", "text": "post shower body care", "playCount": 9000,
                           "authorMeta.name": "flatcreator", "authorMeta.fans": 7000,
                           "authorMeta.region": "US", "textLanguage": "en"})
        self.assertEqual(post["creator_handle"], "@flatcreator")
        self.assertEqual(post["followers"], 7000)
        self.assertEqual(post["language"], "English")

    def test_creator_scout_requires_three_distinct_posts(self):
        raw = [{"id": str(i), "text": "body care routine", "playCount": 100_000 * i,
                "diggCount": 2_000 * i, "authorMeta": {"name": "micro", "fans": 12_000, "region": "US"}}
               for i in range(1, 4)]
        candidates = build_creator_candidates(raw)
        self.assertEqual(candidates[0]["audited_post_count"], 3)
        self.assertEqual(candidates[0]["country"], "United States")

    def test_sound_signal_requires_cross_creator_replication(self):
        rows = [
            {"id": "1", "text": "body care routine", "authorMeta": {"name": "a"},
             "musicMeta": {"musicId": "m1", "musicName": "Rising", "musicAuthor": "Artist"}, "playCount": 1000},
            {"id": "2", "text": "body scrub routine", "authorMeta": {"name": "b"},
             "musicMeta": {"musicId": "m1", "musicName": "Rising", "musicAuthor": "Artist"}, "playCount": 2000},
            {"id": "3", "text": "body care", "authorMeta": {"name": "a"},
             "musicMeta": {"musicId": "m2", "musicName": "One off", "musicAuthor": "Artist"}, "playCount": 9000},
        ]
        snapshot = build_sound_snapshot(rows)
        self.assertEqual([sound["track"] for sound in snapshot["sounds"]], ["Rising"])

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

    def test_monthly_strategy_preserves_occasion_growth(self):
        plan = {"months": {m: {"seasonal_fit": {"occasions": score}} for m, score in zip(("sep", "oct", "nov", "dec"), (10, 65, 95, 100))},
                "pillars": [{"id": "occasions", "name": "The Occasions", "monthly": {"sep": 2, "oct": 8, "nov": 22, "dec": 29}, "evidence_tier": 75, "reference_urls": []}],
                "streams": []}
        result = build_monthly_strategy(plan, [], [])
        pillar = result["pillars"][0]
        self.assertEqual([pillar["monthly_potential"][m]["planned_posts"] for m in result["month_order"]], [2, 8, 22, 29])
        self.assertLess(pillar["monthly_potential"]["sep"]["score"], pillar["monthly_potential"]["dec"]["score"])

    def test_piece_allocation_reconciles_exactly(self):
        self.assertEqual(allocate_pieces(7, {"a": 50, "b": 30, "c": 20}), {"a": 4, "b": 2, "c": 1})
        plan = json.loads((Path(__file__).parents[1] / "data" / "monthly_content_plan.json").read_text())
        result = build_monthly_strategy(plan, [], [])
        for month, expected in {"sep": 100, "oct": 120, "nov": 140, "dec": 150}.items():
            allocation = result["month_allocations"][month]
            self.assertEqual(allocation["total_pieces"], expected)
            self.assertEqual(sum(x["pieces"] for x in allocation["products"]), expected)
            self.assertEqual(sum(x["pieces"] for x in allocation["angles"]), expected)
            self.assertTrue(allocation["reconciled"])

    def test_monthly_priority_shift_alerts(self):
        dataset = {"generated_at": "2026-09-07T00:00:00Z", "viral_videos": [], "creator_candidates": [],
                   "monthly_strategy": {"month_order": ["nov"], "pillars": [
                       {"name": "The Occasions", "monthly_potential": {"nov": {"score": 82}}}
                   ]}}
        previous = {"formats": {}, "shortlist_creators": [], "monthly_priorities": {"nov": {"pillar": "The Gift Guide", "score": 70}}}
        report = detect_format_changes(dataset, previous)
        self.assertEqual(report["alerts"][0]["level"], "monthly_shift")


if __name__ == "__main__":
    unittest.main()
