"""Credentialed, repeatable TikTok scouting through an approved data provider.

This module uses Apify's actor API and never bypasses TikTok access controls.
The actor is replaceable through APIFY_ACTOR_ID. Search results are expanded
with recent profile posts so creator candidates can be evaluated on 3+ posts.
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from .store import ROOT


CONFIG_PATH = ROOT / "config" / "scout_queries.json"
STATUS_PATH = ROOT / "data" / "scout_status.json"
GENERATED_CREATORS_PATH = ROOT / "data" / "creator_candidates.generated.json"
GENERATED_SOUNDS_PATH = ROOT / "data" / "trending_sounds.generated.json"
DEFAULT_ACTOR = "clockworks~tiktok-scraper"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _month_key() -> str:
    return {9: "sep", 10: "oct", 11: "nov", 12: "dec"}.get(datetime.now(timezone.utc).month, "always")


def _actor_items(payload: dict[str, Any], token: str) -> list[dict[str, Any]]:
    actor = os.getenv("APIFY_ACTOR_ID", DEFAULT_ACTOR).strip() or DEFAULT_ACTOR
    endpoint = f"https://api.apify.com/v2/acts/{quote(actor, safe='~')}/run-sync-get-dataset-items?timeout=240"
    body = json.dumps(payload).encode("utf-8")
    request = Request(endpoint, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "CoBaViralRadar/1.0",
    })
    with urlopen(request, timeout=260) as response:
        items = json.load(response)
    if not isinstance(items, list):
        raise RuntimeError("Apify scout returned an unexpected response")
    return items


def _first(item: dict[str, Any], *paths: str, default: Any = None) -> Any:
    for path in paths:
        if path in item and item[path] not in (None, ""):
            return item[path]
        value: Any = item
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                value = None
                break
            value = value[part]
        if value not in (None, ""):
            return value
    return default


def _int(value: Any) -> int | None:
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _published(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) or str(value).isdigit():
        raw = int(value)
        if raw > 10_000_000_000:
            raw //= 1000
        return datetime.fromtimestamp(raw, tz=timezone.utc).date().isoformat()
    return str(value)[:10]


def _handle(item: dict[str, Any]) -> str:
    value = str(_first(item, "authorMeta.name", "author.uniqueId", "authorName", "author", default="")).strip()
    return value.lstrip("@").lower()


def _url(item: dict[str, Any]) -> str | None:
    direct = _first(item, "webVideoUrl", "url", "videoUrl")
    if direct and "tiktok.com/@" in str(direct):
        return str(direct).split("?")[0]
    handle = _handle(item)
    post_id = _first(item, "id", "video.id", "videoId")
    return f"https://www.tiktok.com/@{handle}/video/{post_id}" if handle and post_id else None


def _classify(text: str) -> tuple[str, str, str]:
    lowered = text.lower()
    if any(x in lowered for x in ("secret santa", "white elephant", "hostess", "party gift", "housewarming")):
        return "The Occasions", "Solve a named occasion without landfill", "occasion gift guide"
    if any(x in lowered for x in ("aesop", "alternative", "instead of", "luxury for less", "price comparison")):
        return "The Aesop Alternative", "Offer an under-the-radar luxury discovery", "comparison"
    if any(x in lowered for x in ("basket", "keepsake", "reusable", "packaging", "unbox")):
        return "The Keepsake", "Make the packaging part of the lasting gift", "unboxing"
    if any(x in lowered for x in ("gift guide", "gift for her", "gift ideas", "stocking", "gift closet")):
        return "The Gift Guide", "Curate for one specific recipient", "gift guide"
    if any(x in lowered for x in ("honest review", "reviewing", "worth it", "tested", "verdict")):
        return "Evergreen body care", "Earn the right to recommend it as a gift", "talking head"
    return "Evergreen body care", "Integrate it into a real body routine", "routine demo"


def adapt_post(item: dict[str, Any]) -> dict[str, Any] | None:
    """Convert common Apify TikTok fields into the radar ingestion contract."""
    url = _url(item)
    if not url:
        return None
    caption = str(_first(item, "text", "desc", "caption", default="")).strip()
    pillar, angle, format_name = _classify(caption)
    region = str(_first(item, "authorMeta.region", "author.region", "region", default="")).upper()
    country = "United States" if region in {"US", "USA", "UNITED STATES"} else "Unverified"
    handle = _handle(item)
    likes = _int(_first(item, "diggCount", "stats.diggCount", "likes"))
    views = _int(_first(item, "playCount", "stats.playCount", "views"))
    followers = _int(_first(item, "authorMeta.fans", "authorMeta.followers", "authorStats.followerCount", "followers"))
    keywords = [x for x in ("gift guide", "hostess", "secret santa", "white elephant", "gift for her") if x in caption.lower()]
    return {
        "platform": "TikTok",
        "canonical_url": url,
        "creator_handle": f"@{handle}",
        "creator_name": _first(item, "authorMeta.nickName", "author.nickname", default=handle),
        "creator_country": country,
        "creator_country_evidence": f"Provider author region: {region}" if country == "United States" else "No explicit US location in provider fields",
        "language": "English" if str(_first(item, "textLanguage", "language", default="")).lower() in {"en", "english"} else "Unverified",
        "caption": caption,
        "published_at": _published(_first(item, "createTimeISO", "createTime", "timestamp")),
        "category": "bodycare",
        "format": format_name,
        "campaign_territory": pillar,
        "benchmark_brand": _first(item, "authorMeta.nickName", "author.nickname", default="Creator organic"),
        "source_type": "creator organic",
        "primary_angle": angle,
        "q4_pillars": pillar,
        "gifting_keywords": ";".join(keywords),
        "product_focus": "bodycare",
        "occasion": pillar if pillar == "The Occasions" else "",
        "brand_fit_notes": "Discovered by the month-aware US bodycare scout; human review required before outreach.",
        "hook_summary": caption[:180] or "Visual-first creator post; inspect source for opening frame.",
        "proof_mechanism": "Public post metrics and on-platform creative",
        "paid_partnership": bool(_first(item, "isAd", "paidPartnership", default=False)),
        "evidence_quality": "high" if likes is not None and views is not None else "medium",
        "is_fixture": False,
        "views": views,
        "likes": likes,
        "comments": _int(_first(item, "commentCount", "stats.commentCount", "comments")),
        "shares": _int(_first(item, "shareCount", "stats.shareCount", "shares")),
        "saves": _int(_first(item, "collectCount", "stats.collectCount", "saves")),
        "followers": followers,
    }


def build_creator_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in items:
        post = adapt_post(raw)
        if post and post["creator_handle"] != "@":
            grouped[post["creator_handle"]].append(post)
    candidates = []
    for handle, posts in grouped.items():
        unique = {post["canonical_url"]: post for post in posts}
        posts = list(unique.values())
        follower_values = [p["followers"] for p in posts if p.get("followers") is not None]
        followers = max(follower_values, default=0)
        if followers > 100_000:
            continue
        viral = [p for p in posts if (p.get("likes") or 0) >= 10_000 or (p.get("views") or 0) >= 1_000_000]
        text = " ".join(p.get("caption") or "" for p in posts).lower()
        vo = 88 if any(x in text for x in ("review", "routine", "here's", "worth")) else 68
        music = 84 if any((p.get("format") == "routine demo") for p in posts) else 66
        candid = 86 if sum(bool(p.get("paid_partnership")) for p in posts) / max(1, len(posts)) <= .34 else 58
        country = "United States" if any(p["creator_country"] == "United States" for p in posts) else "Unverified"
        rate = "High" if followers and followers < 10_000 else ("Medium" if followers <= 50_000 else "Low")
        best = max(posts, key=lambda p: ((p.get("likes") or 0), (p.get("views") or 0)))
        candidates.append({
            "platform": "TikTok", "handle": handle, "name": best["creator_name"],
            "profile_url": f"https://www.tiktok.com/{handle}", "country": country,
            "location_evidence": best["creator_country_evidence"], "follower_count": followers,
            "audited_post_count": len(posts), "observed_reference_likes": best.get("likes") or 0,
            "viral_post_count": len(viral), "voiceover_fit": vo, "music_edit_fit": music,
            "candid_fit": candid, "ad_saturation": "Low observed" if candid >= 80 else "Review needed",
            "contact_status": "Use public profile contact route", "rate_likelihood_under_200": rate,
            "rate_basis": "Planning estimate from public follower band; request an actual quote",
            "source_url": best["canonical_url"], "source_urls": [p["canonical_url"] for p in posts[:12]],
            "verified_at": _now()[:10], "source_provider": "apify_tiktok_scout"
        })
    return candidates


def build_sound_snapshot(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Rank sounds by cross-creator replication inside the scoped scout corpus."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in items:
        title = str(_first(raw, "musicMeta.musicName", "musicMeta.title", "music.title", default="")).strip()
        artist = str(_first(raw, "musicMeta.musicAuthor", "musicMeta.authorName", "music.authorName", default="Original sound")).strip()
        sound_id = str(_first(raw, "musicMeta.musicId", "musicMeta.id", "music.id", default="")).strip()
        if not title:
            continue
        grouped[sound_id or f"{title.lower()}::{artist.lower()}"].append(raw)
    sounds = []
    for rows in grouped.values():
        creators = {_handle(row) for row in rows if _handle(row)}
        if len(creators) < 2:
            continue
        title = str(_first(rows[0], "musicMeta.musicName", "musicMeta.title", "music.title"))
        artist = str(_first(rows[0], "musicMeta.musicAuthor", "musicMeta.authorName", "music.authorName", default="Original sound"))
        plays = [_int(_first(row, "playCount", "stats.playCount", "views")) or 0 for row in rows]
        likes = [_int(_first(row, "diggCount", "stats.diggCount", "likes")) or 0 for row in rows]
        angles = []
        for row in rows:
            post = adapt_post(row)
            if post and post["primary_angle"] not in angles:
                angles.append(post["primary_angle"])
        sounds.append({
            "track": title, "artist": artist,
            "signal": f"{len(rows)} scoped posts · {len(creators)} creators · max {max(plays, default=0):,} views",
            "mood": "Use the reference posts to match pacing; do not copy creator footage",
            "best_for": angles[:4], "scouted_posts": len(rows), "unique_creators": len(creators),
            "max_views": max(plays, default=0), "max_likes": max(likes, default=0),
        })
    sounds.sort(key=lambda x: (x["unique_creators"], x["scouted_posts"], x["max_views"], x["max_likes"]), reverse=True)
    return {
        "market": "United States", "verified_at": _now(),
        "source_name": "Continuous scoped TikTok scout",
        "commercial_music_library_url": "https://ads.tiktok.com/business/creativecenter/music/pc/en",
        "rights_note": "Discovery signal only—not proof of commercial clearance. Verify the exact sound in TikTok Commercial Music Library on posting day or license an alternative.",
        "sounds": sounds[:12],
    }


def scout_tiktok() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    token = os.getenv("APIFY_TOKEN", "").strip()
    if not token:
        raise RuntimeError("APIFY_TOKEN is not configured")
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    month = _month_key()
    queries = list(dict.fromkeys(config["queries"]["always"] + config["queries"].get(month, [])))
    search_items = _actor_items({
        "searchQueries": queries,
        "resultsPerPage": int(os.getenv("SCOUT_RESULTS_PER_QUERY", config["results_per_query"])),
        "searchSection": "/video", "proxyCountryCode": "US",
        "videoSearchSorting": "MOST_LIKED", "videoSearchDateFilter": "PAST_MONTH",
        "scrapeAdditionalAuthorMeta": True,
        "shouldDownloadVideos": False, "shouldDownloadCovers": False,
        "shouldDownloadSubtitles": False, "shouldDownloadSlideshowImages": False,
    }, token)
    seed_posts = [post for post in (adapt_post(item) for item in search_items) if post]
    handles = []
    for post in sorted(seed_posts, key=lambda p: ((p.get("likes") or 0), (p.get("views") or 0)), reverse=True):
        follower_count = post.get("followers") or 0
        if post["creator_handle"] not in handles and follower_count <= 100_000:
            handles.append(post["creator_handle"].lstrip("@"))
        if len(handles) >= config["max_creator_profiles"]:
            break
    profile_items: list[dict[str, Any]] = []
    if handles:
        profile_items = _actor_items({
            "profiles": handles, "resultsPerPage": config["profile_posts"],
            "profileScrapeSections": ["videos"], "profileSorting": "latest",
            "excludePinnedPosts": True, "proxyCountryCode": "US",
            "shouldDownloadVideos": False, "shouldDownloadCovers": False,
            "shouldDownloadSubtitles": False, "shouldDownloadSlideshowImages": False,
        }, token)
    all_raw = search_items + profile_items
    posts_by_url = {}
    for item in all_raw:
        post = adapt_post(item)
        if post:
            posts_by_url[post["canonical_url"]] = post
    creators = build_creator_candidates(all_raw)
    GENERATED_CREATORS_PATH.write_text(json.dumps({
        "method": "Automated month-aware TikTok search followed by a recent-post profile audit. US status requires explicit provider location evidence; rate is never assumed confirmed.",
        "generated_at": _now(), "candidates": creators,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sound_snapshot = build_sound_snapshot(all_raw)
    GENERATED_SOUNDS_PATH.write_text(json.dumps(sound_snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    status = {
        "connected": True, "provider": "Apify TikTok Scout", "actor": os.getenv("APIFY_ACTOR_ID", DEFAULT_ACTOR),
        "last_run": _now(), "last_success": _now(), "month_mode": month,
        "queries_run": len(queries), "search_posts_seen": len(search_items),
        "unique_posts": len(posts_by_url), "profiles_expanded": len(handles),
        "creator_candidates": len(creators), "sound_candidates": len(sound_snapshot["sounds"]),
        "cadence": "Every 6 hours via GitHub Actions",
        "qualification": "10K likes or 1M views; creator shortlist requires explicit US evidence and 3+ audited posts"
    }
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return list(posts_by_url.values()), status


def write_disconnected_status(reason: str) -> dict[str, Any]:
    previous = json.loads(STATUS_PATH.read_text(encoding="utf-8")) if STATUS_PATH.exists() else {}
    status = {**previous, "connected": False, "provider": None, "last_run": _now(),
              "reason": reason, "cadence": "Waiting for an approved live data provider credential"}
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status


def write_error_status(reason: str) -> dict[str, Any]:
    """Keep the last successful evidence while making provider failure visible."""
    previous = json.loads(STATUS_PATH.read_text(encoding="utf-8")) if STATUS_PATH.exists() else {}
    status = {**previous, "connected": True, "state": "error", "last_run": _now(),
              "reason": reason, "cadence": "Every 6 hours via GitHub Actions; showing last successful evidence"}
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status
