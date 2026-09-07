from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .store import ROOT


BASELINE_PATH = ROOT / "data" / "trend_baseline.json"
ALERT_PATH = ROOT / "outputs" / "trend-alert.json"


def _summaries(dataset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in dataset.get("viral_videos", []):
        grouped[item.get("format") or "unknown"].append(item)
    result = {}
    for name, items in grouped.items():
        result[name] = {
            "qualified_sources": len(items),
            "creators": len({item.get("creator_handle") for item in items if item.get("creator_handle")}),
            "brands": len({item.get("benchmark_brand") for item in items if item.get("benchmark_brand")}),
            "max_likes": max((item.get("likes") or 0 for item in items), default=0),
            "max_views": max((item.get("views") or 0 for item in items), default=0),
            "angles": sorted({item.get("primary_angle") for item in items if item.get("primary_angle")}),
        }
    return result


def detect_format_changes(dataset: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    current = _summaries(dataset)
    alerts = []
    if previous:
        old_formats = previous.get("formats", {})
        for name, stats in current.items():
            old = old_formats.get(name, {})
            old_count = old.get("qualified_sources", 0)
            if not old and stats["qualified_sources"] >= 2 and stats["creators"] >= 2:
                alerts.append({"level": "new_format", "format": name, "reason": f"Replicated by {stats['creators']} creators across {stats['qualified_sources']} viral-qualified posts."})
            elif stats["qualified_sources"] - old_count >= 2 and stats["creators"] >= 2:
                alerts.append({"level": "accelerating", "format": name, "reason": f"Added {stats['qualified_sources'] - old_count} qualifying examples since the prior snapshot."})
            if stats["max_likes"] >= 1_000_000 and old.get("max_likes", 0) < 1_000_000:
                alerts.append({"level": "mega", "format": name, "reason": "A source crossed 1M likes."})
            elif (stats["max_likes"] >= 100_000 or stats["max_views"] >= 3_000_000) and not (old.get("max_likes", 0) >= 100_000 or old.get("max_views", 0) >= 3_000_000):
                alerts.append({"level": "breakout", "format": name, "reason": "A source crossed 100K likes or 3M views."})
        old_creators = set(previous.get("shortlist_creators", []))
        for creator in dataset.get("creator_candidates", []):
            if creator.get("shortlist_status") == "Shortlist ready" and creator.get("handle") not in old_creators:
                alerts.append({"level": "new_creator", "format": creator.get("handle"), "reason": f"Verified-US micro creator reached shortlist score {creator.get('shortlist_score')} with 3+ audited posts; rate remains unconfirmed."})
    return {
        "generated_at": dataset.get("generated_at"),
        "status": "material_change" if alerts else ("baseline_created" if previous is None else "no_material_change"),
        "alerts": alerts,
        "formats": current,
        "shortlist_creators": sorted(item.get("handle") for item in dataset.get("creator_candidates", []) if item.get("shortlist_status") == "Shortlist ready"),
        "rules": {
            "new_format": "At least 2 viral-qualified posts from at least 2 creators and absent from the prior snapshot.",
            "accelerating": "At least 2 additional viral-qualified examples from at least 2 creators since the prior snapshot.",
            "breakout": "A format source newly crosses 100K likes or 3M views.",
            "mega": "A format source newly crosses 1M likes."
        },
    }


def _post_slack(report: dict[str, Any]) -> dict[str, Any]:
    webhook = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        return {"configured": False, "sent": False, "reason": "SLACK_WEBHOOK_URL is not configured"}
    if not report["alerts"]:
        return {"configured": True, "sent": False, "reason": "No material change; alert suppressed"}
    dashboard = os.getenv("RADAR_DASHBOARD_URL", "https://taogiangmyvn-ux.github.io/viral-angle-radar/")
    lines = ["*:rotating_light: CoBa Viral Format Alert*", f"{len(report['alerts'])} material signal(s) detected:"]
    for item in report["alerts"][:6]:
        lines.append(f"• *{item['format']}* — {item['level'].replace('_', ' ').title()}: {item['reason']}")
    lines += [f"<{dashboard}|Open the Viral Gift Radar>", "Use the signal to create a test brief; do not treat it as a guarantee of virality."]
    payload = json.dumps({"text": "\n".join(lines)}).encode("utf-8")
    request = Request(webhook, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=15) as response:
        response.read()
    return {"configured": True, "sent": True, "reason": "Material format change sent to Slack"}


def run_alert_cycle(dataset: dict[str, Any]) -> dict[str, Any]:
    previous = json.loads(BASELINE_PATH.read_text(encoding="utf-8")) if BASELINE_PATH.exists() else None
    report = detect_format_changes(dataset, previous)
    try:
        report["slack"] = _post_slack(report)
    except Exception as exc:  # Keep the daily build alive and surface delivery failure in the output.
        report["slack"] = {"configured": True, "sent": False, "reason": f"Slack delivery failed: {exc}"}
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALERT_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps({"generated_at": report["generated_at"], "formats": report["formats"], "shortlist_creators": report["shortlist_creators"]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ALERT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
