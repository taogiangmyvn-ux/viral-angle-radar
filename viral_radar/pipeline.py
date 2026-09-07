from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .store import ROOT, connect, log_run, rows


VIDEO_RE = re.compile(r"^https://(?:www\.)?tiktok\.com/@[^/]+/(?:video|photo)/(\d+)")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def canonicalize_url(value: str) -> tuple[str, str]:
    value = value.strip()
    match = VIDEO_RE.match(value)
    if not match:
        raise ValueError(f"Unsupported or malformed TikTok post URL: {value}")
    parts = urlsplit(value)
    canonical = urlunsplit(("https", "www.tiktok.com", parts.path.rstrip("/"), "", ""))
    return canonical, match.group(1)


def _integer(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    return int(float(str(value).replace(",", "")))


def _boolean(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def viral_tier(views: int | None, likes: int | None) -> str:
    """Return an evidence tier. Opportunity scoring never upgrades a Watchlist post."""
    views = views or 0
    likes = likes or 0
    if likes >= 1_000_000 or views >= 10_000_000:
        return "Mega"
    if likes >= 100_000 or views >= 3_000_000:
        return "Breakout"
    if likes >= 10_000 or views >= 1_000_000:
        return "Qualified"
    return "Watchlist"


def normalize(raw: dict[str, Any], provider: str) -> dict[str, Any]:
    url, video_id = canonicalize_url(str(raw.get("canonical_url", "")))
    timestamp = now_iso()
    return {
        "video_id": video_id,
        "platform": raw.get("platform") or "TikTok",
        "canonical_url": url,
        "creator_handle": raw.get("creator_handle"),
        "creator_name": raw.get("creator_name"),
        "creator_country": raw.get("creator_country") or "Unverified",
        "creator_country_evidence": raw.get("creator_country_evidence"),
        "language": raw.get("language") or "Unverified",
        "caption": raw.get("caption"),
        "published_at": raw.get("published_at"),
        "category": raw.get("category") or "Uncategorized",
        "format": raw.get("format") or "Unclassified",
        "campaign_territory": raw.get("campaign_territory") or "Unclassified",
        "benchmark_brand": raw.get("benchmark_brand") or "Unspecified",
        "source_type": raw.get("source_type") or "creator organic",
        "primary_angle": raw.get("primary_angle") or "Unclassified",
        "q4_pillars": raw.get("q4_pillars") or "",
        "gifting_keywords": raw.get("gifting_keywords") or "",
        "product_focus": raw.get("product_focus") or "",
        "occasion": raw.get("occasion") or "",
        "brand_fit_notes": raw.get("brand_fit_notes") or "",
        "hook_summary": raw.get("hook_summary"),
        "proof_mechanism": raw.get("proof_mechanism"),
        "paid_partnership": _boolean(raw.get("paid_partnership")),
        "evidence_quality": raw.get("evidence_quality") or "low",
        "source_provider": provider,
        "is_fixture": _boolean(raw.get("is_fixture")),
        "collected_at": timestamp,
        "last_verified_at": timestamp,
        "metrics": {key: _integer(raw.get(key)) for key in ("views", "likes", "comments", "shares", "saves", "followers")},
    }


def load_fixture() -> list[dict[str, Any]]:
    return json.loads((ROOT / "data" / "fixture_sources.json").read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def discover(*, fixture: bool = False, csv_path: Path | None = None, observed_at: str | None = None, live: bool = False) -> dict[str, Any]:
    if live:
        from .providers import fetch_live
        provider, raw_items = "live_http_provider", fetch_live()
    elif fixture:
        provider, raw_items = "fixture", load_fixture()
    else:
        provider, raw_items = "manual_csv", load_csv(csv_path or ROOT / "data" / "manual_sources.csv")
    normalized: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, raw in enumerate(raw_items, start=1):
        try:
            normalized.append(normalize(raw, provider))
        except (ValueError, TypeError) as exc:
            errors.append(f"row {index}: {exc}")

    snapshot_time = observed_at or now_iso()
    conn = connect()
    try:
        if provider == "manual_csv":
            stale_ids = [item["video_id"] for item in rows(conn, "SELECT video_id FROM videos WHERE source_provider='manual_csv'")]
            for stale_id in stale_ids:
                conn.execute("DELETE FROM trend_scores WHERE video_id=?", (stale_id,))
                conn.execute("DELETE FROM metric_snapshots WHERE video_id=?", (stale_id,))
                conn.execute("DELETE FROM videos WHERE video_id=?", (stale_id,))
        for item in normalized:
            conn.execute(
                """INSERT INTO videos (
                video_id, platform, canonical_url, creator_handle, creator_name,
                creator_country, creator_country_evidence, language, caption,
                published_at, category, format, campaign_territory, benchmark_brand, source_type, primary_angle, q4_pillars,
                gifting_keywords, product_focus, occasion, brand_fit_notes, hook_summary,
                proof_mechanism, paid_partnership, evidence_quality, source_provider,
                is_fixture, collected_at, last_verified_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(video_id) DO UPDATE SET
                  canonical_url=excluded.canonical_url,
                  creator_handle=excluded.creator_handle,
                  creator_name=excluded.creator_name,
                  creator_country=excluded.creator_country,
                  creator_country_evidence=excluded.creator_country_evidence,
                  language=excluded.language,
                  caption=excluded.caption,
                  published_at=excluded.published_at,
                  category=excluded.category,
                  format=excluded.format,
                  campaign_territory=excluded.campaign_territory,
                  benchmark_brand=excluded.benchmark_brand,
                  source_type=excluded.source_type,
                  primary_angle=excluded.primary_angle,
                  q4_pillars=excluded.q4_pillars,
                  gifting_keywords=excluded.gifting_keywords,
                  product_focus=excluded.product_focus,
                  occasion=excluded.occasion,
                  brand_fit_notes=excluded.brand_fit_notes,
                  hook_summary=excluded.hook_summary,
                  proof_mechanism=excluded.proof_mechanism,
                  paid_partnership=excluded.paid_partnership,
                  evidence_quality=excluded.evidence_quality,
                  source_provider=excluded.source_provider,
                  is_fixture=excluded.is_fixture,
                  last_verified_at=excluded.last_verified_at
                """,
                tuple(item[key] for key in (
                    "video_id", "platform", "canonical_url", "creator_handle", "creator_name",
                    "creator_country", "creator_country_evidence", "language", "caption",
                    "published_at", "category", "format", "campaign_territory", "benchmark_brand", "source_type", "primary_angle", "q4_pillars",
                    "gifting_keywords", "product_focus", "occasion", "brand_fit_notes", "hook_summary",
                    "proof_mechanism", "paid_partnership", "evidence_quality", "source_provider",
                    "is_fixture", "collected_at", "last_verified_at"
                )),
            )
            metrics = item["metrics"]
            conn.execute(
                """INSERT OR REPLACE INTO metric_snapshots
                (video_id, observed_at, views, likes, comments, shares, saves, followers, field_provenance)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (item["video_id"], snapshot_time, metrics["views"], metrics["likes"], metrics["comments"],
                 metrics["shares"], metrics["saves"], metrics["followers"], provider),
            )
        conn.commit()
    finally:
        conn.close()
    result = {"provider": provider, "imported": len(normalized), "errors": errors, "observed_at": snapshot_time}
    log_run({"event": "discover", "at": now_iso(), **result})
    return result


def _log_score(value: int | None, scale: float) -> float:
    if value is None or value <= 0:
        return 0.0
    return min(100.0, math.log10(value + 1) / scale * 100.0)


def _recency(published_at: str | None) -> float:
    if not published_at:
        return 20.0
    try:
        days = max(0, (date.today() - date.fromisoformat(published_at[:10])).days)
    except ValueError:
        return 20.0
    return max(0.0, 100.0 * math.exp(-days / 45.0))


def _term_score(text: str, terms: list[str]) -> float:
    lowered = text.lower()
    matches = sum(1 for term in terms if term.lower() in lowered)
    return min(100.0, matches / max(1, min(4, len(terms))) * 100.0)


def score(config_name: str = "cobas-daughter-bodycare-q4") -> list[dict[str, Any]]:
    config = json.loads((ROOT / "config" / f"{config_name}.json").read_text(encoding="utf-8"))
    weights = config["opportunity_scoring"]
    conn = connect()
    videos = rows(conn, "SELECT * FROM videos")
    angle_counts = Counter(video["primary_angle"] for video in videos)
    calculated_at = now_iso()
    scored: list[dict[str, Any]] = []
    for video in videos:
        snapshots = rows(conn, "SELECT * FROM metric_snapshots WHERE video_id=? ORDER BY observed_at", (video["video_id"],))
        latest = snapshots[-1] if snapshots else {}
        if len(snapshots) >= 2 and latest.get("views") is not None and snapshots[-2].get("views") is not None:
            delta = max(0, latest["views"] - snapshots[-2]["views"])
            velocity = _log_score(delta, 6.0)
            velocity_status = "measured"
        else:
            velocity = 25.0 if latest.get("views") else 0.0
            velocity_status = "insufficient_history"

        views = latest.get("views") or 0
        interactions = sum(latest.get(field) or 0 for field in ("likes", "comments", "shares"))
        if views:
            rate = interactions / views
            engagement = min(100.0, rate / 0.12 * 100.0)
        else:
            engagement = _log_score(interactions, 5.0)

        relevant = 0
        relevant += 35 if config["category"].lower() in str(video["category"]).lower() else 0
        relevant += 25 if video["creator_country"] == config["market"] else 0
        relevant += 15 if video["language"] == config["language"] else 0
        relevant += 25 if video["format"] in config["formats"] else 0
        novelty = 100.0 / max(1, angle_counts[video["primary_angle"]])
        evidence_map = {"high": 100.0, "medium": 70.0, "low": 35.0, "fixture": 15.0}
        evidence = evidence_map.get(video["evidence_quality"], 20.0)
        text = " ".join(str(video.get(field) or "") for field in (
            "caption", "primary_angle", "hook_summary", "proof_mechanism", "q4_pillars",
            "gifting_keywords", "product_focus", "occasion", "brand_fit_notes"
        ))
        brand_fit = (
            (25.0 if "bodycare" in str(video["category"]).lower() or "body care" in text.lower() else 0.0)
            + _term_score(text, config["brand_fit_terms"]["ritual"]) * 0.20
            + _term_score(text, config["brand_fit_terms"]["sensory_luxury"]) * 0.20
            + _term_score(text, config["brand_fit_terms"]["gift_object"]) * 0.20
            + _term_score(text, config["brand_fit_terms"]["product_match"]) * 0.15
        )
        brand_fit = min(100.0, brand_fit)
        gifting = min(100.0,
            _term_score(text, config["gifting_terms"]) * 0.70
            + (20.0 if video.get("occasion") else 0.0)
            + (10.0 if any(term in text.lower() for term in ("set", "bundle", "gift box", "unboxing")) else 0.0)
        )
        q4 = min(100.0,
            _term_score(str(video.get("q4_pillars") or ""), config["q4_pillars"]) * 0.50
            + _term_score(text, config["q4_terms"]) * 0.30
            + (10.0 if video.get("occasion") else 0.0)
            + _recency(video["published_at"]) * 0.10
        )
        momentum = (
            velocity * 0.30 + engagement * 0.30 + _recency(video["published_at"]) * 0.25
            + novelty * 0.15
        )
        components = {
            "velocity_score": round(velocity, 2),
            "engagement_score": round(engagement, 2),
            "recency_score": round(_recency(video["published_at"]), 2),
            "relevance_score": round(float(relevant), 2),
            "novelty_score": round(novelty, 2),
            "evidence_score": round(evidence, 2),
            "momentum_score": round(momentum, 2),
            "brand_fit_score": round(brand_fit, 2),
            "q4_potential_score": round(q4, 2),
            "gifting_relevance_score": round(gifting, 2),
        }
        total = sum(components[f"{name}_score"] * weight for name, weight in weights.items())
        explanation = (
            f"Brand fit {brand_fit:.0f}/100; Q4 {q4:.0f}/100; gifting {gifting:.0f}/100; "
            f"momentum {momentum:.0f}/100. Velocity {velocity_status}; evidence {video['evidence_quality']}."
        )
        conn.execute(
            """INSERT OR REPLACE INTO trend_scores
            (video_id, calculated_at, trend_score, velocity_score, velocity_status,
             engagement_score, recency_score, relevance_score, novelty_score,
             evidence_score, momentum_score, brand_fit_score, q4_potential_score,
             gifting_relevance_score, explanation) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (video["video_id"], calculated_at, round(total, 2), components["velocity_score"], velocity_status,
             components["engagement_score"], components["recency_score"], components["relevance_score"],
             components["novelty_score"], components["evidence_score"], components["momentum_score"],
             components["brand_fit_score"], components["q4_potential_score"],
             components["gifting_relevance_score"], explanation),
        )
        tier = viral_tier(latest.get("views"), latest.get("likes"))
        signal = max(
            _log_score(latest.get("likes"), 6.0),
            _log_score(latest.get("views"), 7.0),
        )
        scored.append({**video, **latest, **components, "trend_score": round(total, 2),
                       "velocity_status": velocity_status, "explanation": explanation,
                       "viral_tier": tier, "viral_qualified": tier != "Watchlist",
                       "viral_signal_score": round(signal, 2)})
    conn.commit()
    conn.close()
    scored.sort(key=lambda item: item["trend_score"], reverse=True)
    log_run({"event": "score", "at": calculated_at, "count": len(scored)})
    return scored


def build_dataset() -> dict[str, Any]:
    scored = score()
    if any(not item["is_fixture"] for item in scored):
        scored = [item for item in scored if not item["is_fixture"]]
    viral_videos = [item for item in scored if item["viral_qualified"]]
    watchlist = [item for item in scored if not item["viral_qualified"]]
    viral_videos.sort(key=lambda item: (
        {"Mega": 3, "Breakout": 2, "Qualified": 1}.get(item["viral_tier"], 0),
        item.get("likes") or 0,
        item.get("views") or 0,
    ), reverse=True)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in viral_videos:
        grouped.setdefault(item["primary_angle"], []).append(item)
    angles = []
    for angle, items in grouped.items():
        values = sorted(item["trend_score"] for item in items)
        midpoint = len(values) // 2
        median = values[midpoint] if len(values) % 2 else (values[midpoint - 1] + values[midpoint]) / 2
        angles.append({
            "angle": angle,
            "video_count": len(items),
            "campaign_territories": sorted({item["campaign_territory"] for item in items}),
            "median_score": round(median, 2),
            "max_score": max(values),
            "representative_url": items[0]["canonical_url"],
            "median_brand_fit": round(sum(item["brand_fit_score"] for item in items) / len(items), 2),
            "median_q4_potential": round(sum(item["q4_potential_score"] for item in items) / len(items), 2),
            "median_gifting_relevance": round(sum(item["gifting_relevance_score"] for item in items) / len(items), 2),
            "total_likes": sum(item.get("likes") or 0 for item in items),
            "max_likes": max(item.get("likes") or 0 for item in items),
            "breakout_count": sum(item["viral_tier"] in {"Breakout", "Mega"} for item in items),
        })
    angles.sort(key=lambda item: (item["breakout_count"], item["max_likes"], item["max_score"]), reverse=True)
    return {
        "generated_at": now_iso(),
        "is_fixture_only": bool(scored) and all(item["is_fixture"] for item in scored),
        "videos": viral_videos,
        "viral_videos": viral_videos,
        "watchlist": watchlist,
        "angles": angles,
        "viral_rule": {"minimum_likes": 10000, "minimum_views": 1000000,
                       "definition": "Qualified when likes >= 10,000 OR views >= 1,000,000"},
    }


def ingest_brand(slug: str) -> dict[str, Any]:
    folder = ROOT / "brands" / slug
    if not folder.exists():
        raise FileNotFoundError(f"Brand folder not found: {folder}")
    documents = []
    for path in sorted(folder.iterdir()):
        if path.name == "brand_profile.json" or path.name.startswith("extracted_context"):
            continue
        text = ""
        status = "extracted"
        try:
            if path.suffix.lower() in {".md", ".txt", ".csv"}:
                text = path.read_text(encoding="utf-8")
            elif path.suffix.lower() == ".pdf":
                from pypdf import PdfReader  # type: ignore
                text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
            elif path.suffix.lower() == ".docx":
                from docx import Document  # type: ignore
                text = "\n".join(p.text for p in Document(path).paragraphs)
            else:
                continue
        except (ImportError, OSError) as exc:
            status = f"unavailable: {exc}"
        documents.append({
            "file": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "status": status,
            "text": text[:50000],
        })
    profile_path = folder / "brand_profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else {"brand": slug}
    output = {"brand": slug, "ingested_at": now_iso(), "profile": profile, "documents": documents,
              "notice": "Extracted text is context only. Claims require explicit approval in brand_profile.json."}
    target = folder / "extracted_context.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    log_run({"event": "ingest_brand", "at": now_iso(), "brand": slug, "documents": len(documents)})
    return output


def generate_brief(slug: str, product: str, top_angles: int = 3) -> dict[str, Any]:
    context_path = ROOT / "brands" / slug / "extracted_context.json"
    context = json.loads(context_path.read_text(encoding="utf-8")) if context_path.exists() else ingest_brand(slug)
    profile = context["profile"]
    dataset = build_dataset()
    selected_angles = dataset["angles"][:top_angles]
    selected_videos = []
    for angle in selected_angles:
        candidate = next(item for item in dataset["videos"] if item["primary_angle"] == angle["angle"])
        selected_videos.append(candidate)
    brief_id = f"{slug}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    tone = ", ".join(profile.get("tone", ["clear", "credible"]))
    hooks = [
        f"What do you give the woman who already has everything? A body-care ritual she will actually keep.",
        f"This is the rare {product} that feels as considered as the person receiving it.",
        f"I almost kept this gift for myself—and the handwoven case is why.",
    ]
    sources = [{"url": item["canonical_url"], "creator": item["creator_name"], "angle": item["primary_angle"],
                "relevance": f"Uses {item['format']} with {item['proof_mechanism'] or 'observable product evidence'}."} for item in selected_videos]
    brief = {
        "brief_id": brief_id,
        "brand": profile.get("brand", slug),
        "product": product,
        "generated_at": now_iso(),
        "status": "draft",
        "fixture_warning": dataset["is_fixture_only"],
        "objective": f"Create a giftable, credible short-form bodycare review for {product}.",
        "audience": profile.get("audience", "Audience not supplied"),
        "single_minded_message": profile.get("positioning", "Positioning not supplied"),
        "selected_angles": [item["angle"] for item in selected_angles],
        "source_videos": sources,
        "hooks": hooks,
        "structure_30s": [
            "0–3s: Direct-to-camera gifting tension with the full set in frame.",
            "3–8s: Name the recipient or occasion and why generic beauty gifts miss.",
            "8–18s: Open the handwoven case with both hands; show the ritual sequence.",
            "18–25s: Demonstrate one texture and give approved, observable proof.",
            "25–30s: Return to the keepsake and close with a gift-or-keep CTA.",
        ],
        "tone": tone,
        "talking_points": profile.get("approved_claims", []),
        "do_not_say": profile.get("prohibited_claims", []),
        "cta_options": profile.get("cta_preferences", ["Learn more"]),
        "assumptions": ["No verbatim transcript was available; hooks are original adaptations.",
                        "All product claims require brand/legal review before publishing."],
    }
    out_dir = ROOT / "exports" / "briefs"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{brief_id}.json"
    md_path = out_dir / f"{brief_id}.md"
    json_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# {brief['brand']} — {product}", "", f"Generated: {brief['generated_at']}", ""]
    if brief["fixture_warning"]:
        lines += ["> Demo mode: source performance data is synthetic fixture data, not live trend evidence.", ""]
    lines += ["## Objective", "", brief["objective"], "", "## Audience", "", brief["audience"], "",
              "## Single-minded message", "", brief["single_minded_message"], "", "## Hooks", ""]
    lines += [f"- {hook}" for hook in hooks]
    lines += ["", "## 30-second structure", ""] + [f"- {step}" for step in brief["structure_30s"]]
    lines += ["", "## Source references", ""] + [f"- [{s['creator']}]({s['url']}) — {s['angle']}. {s['relevance']}" for s in sources]
    lines += ["", "## Approved talking points", ""] + [f"- {claim}" for claim in brief["talking_points"]]
    lines += ["", "## Do not say", ""] + [f"- {claim}" for claim in brief["do_not_say"]]
    lines += ["", "## Assumptions", ""] + [f"- {item}" for item in brief["assumptions"]]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    conn = connect()
    conn.execute("INSERT OR REPLACE INTO briefs VALUES (?,?,?,?,?,?,?,?)",
                 (brief_id, brief["brand"], product, brief["generated_at"], str(md_path.relative_to(ROOT)),
                  str(json_path.relative_to(ROOT)), json.dumps([item["video_id"] for item in selected_videos]), "draft"))
    conn.commit()
    conn.close()
    log_run({"event": "brief", "at": now_iso(), "brief_id": brief_id})
    return brief


def export_site() -> Path:
    dataset = build_dataset()
    site = ROOT / "site"
    site.mkdir(parents=True, exist_ok=True)
    (site / "data.json").write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    static = ROOT / "web" / "static"
    for name in ("index.html", "app.js", "styles.css"):
        shutil.copy2(static / name, site / name)
    return site


def export_excel() -> Path:
    dataset = build_dataset()
    staging = ROOT / "work" / "excel-data.json"
    staging.parent.mkdir(parents=True, exist_ok=True)
    staging.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    output = ROOT / "outputs" / "viral-angle-radar.xlsx"
    node = shutil.which("node")
    if node:
        try:
            subprocess.run([node, str(ROOT / "scripts" / "build_workbook.mjs"), str(staging), str(output)], check=True, cwd=ROOT)
            return output
        except subprocess.CalledProcessError:
            pass
    try:
        from openpyxl import Workbook  # type: ignore
        from openpyxl.styles import Font
    except ImportError as exc:
        raise RuntimeError("Excel export requires Node artifact-tool locally or openpyxl in CI") from exc
    wb = Workbook()
    ws = wb.active
    ws.title = "Top Videos"
    headers = ["Trend", "Creator", "Video", "Angle", "Hook", "Views", "Likes", "Observed", "Relevance", "Evidence"]
    ws.append(headers)
    for cell in ws[1]: cell.font = Font(bold=True, color="FFFFFF")
    for item in dataset["videos"]:
        ws.append([item["trend_score"], item["creator_name"], item["canonical_url"], item["primary_angle"], item["hook_summary"],
                   item.get("views"), item.get("likes"), item.get("observed_at"), item["relevance_score"], item["evidence_quality"]])
        ws.cell(ws.max_row, 3).hyperlink = item["canonical_url"]
    angle_ws = wb.create_sheet("Angle Radar")
    angle_ws.append(["Angle", "Videos", "Median score", "Max score", "Representative source"])
    for item in dataset["angles"]:
        angle_ws.append([item["angle"], item["video_count"], item["median_score"], item["max_score"], item["representative_url"]])
        angle_ws.cell(angle_ws.max_row, 5).hyperlink = item["representative_url"]
    creator_ws = wb.create_sheet("Creators")
    creator_ws.append(["Creator", "Handle", "Country", "Country evidence"])
    seen = set()
    for item in dataset["videos"]:
        if item["creator_handle"] in seen: continue
        seen.add(item["creator_handle"])
        creator_ws.append([item["creator_name"], item["creator_handle"], item["creator_country"], item["creator_country_evidence"]])
    metric_ws = wb.create_sheet("Metric History")
    metric_ws.append(["Video ID", "Observed", "Views", "Likes", "Comments", "Shares", "Followers", "Source"])
    for item in dataset["videos"]:
        metric_ws.append([item["video_id"], item.get("observed_at"), item.get("views"), item.get("likes"), item.get("comments"), item.get("shares"), item.get("followers"), item["source_provider"]])
    relevance_ws = wb.create_sheet("Brand Relevance")
    relevance_ws.append(["Angle", "Relevance score", "Representative source"])
    for angle in dataset["angles"]:
        video = next(v for v in dataset["videos"] if v["primary_angle"] == angle["angle"])
        relevance_ws.append([angle["angle"], video["relevance_score"], angle["representative_url"]])
        relevance_ws.cell(relevance_ws.max_row, 3).hyperlink = angle["representative_url"]
    briefs_ws = wb.create_sheet("Generated Briefs")
    briefs_ws.append(["Brand", "Product", "Generated", "Brief path", "Status"])
    quality_ws = wb.create_sheet("Data Quality")
    quality_ws.append(["Check", "Count", "Action"])
    quality_ws.append(["Fixture records", sum(v["is_fixture"] for v in dataset["videos"]), "Replace with verified sources"])
    quality_ws.append(["Missing views", sum(v.get("views") is None for v in dataset["videos"]), "Collect a new snapshot"])
    quality_ws.append(["Unverified country", sum(v["creator_country"] == "Unverified" for v in dataset["videos"]), "Add profile/provider evidence"])
    run_ws = wb.create_sheet("Run Log")
    run_ws.append(["Field", "Value"])
    run_ws.append(["Generated at", dataset["generated_at"]])
    run_ws.append(["Video count", len(dataset["videos"])])
    run_ws.append(["Fixture only", dataset["is_fixture_only"]])
    for sheet in wb.worksheets:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = __import__("openpyxl").styles.PatternFill("solid", fgColor="163328")
        for column in sheet.columns:
            letter = column[0].column_letter
            sheet.column_dimensions[letter].width = min(55, max(12, max(len(str(c.value or "")) for c in column) + 2))
    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
    return output


def daily(fixture: bool, live: bool = False) -> dict[str, Any]:
    discovery = discover(fixture=fixture, live=live)
    ingest_brand("cobas-daughter")
    brief = generate_brief("cobas-daughter", "Bath & Body Care Gift Set")
    site = export_site()
    workbook = export_excel()
    result = {"discovery": discovery, "brief_id": brief["brief_id"], "site": str(site), "workbook": str(workbook)}
    log_run({"event": "daily_complete", "at": now_iso(), **result})
    return result
