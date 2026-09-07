"""Legitimate, replaceable live-provider boundary.

The configured endpoint must return either a JSON list or {"items": [...]} using
the same fields as data/manual_sources.csv. This module does not scrape TikTok.
"""
from __future__ import annotations

import json
import os
from typing import Any
from urllib.request import Request, urlopen


def fetch_live() -> list[dict[str, Any]]:
    endpoint = os.environ.get("LIVE_PROVIDER_URL")
    token = os.environ.get("LIVE_PROVIDER_TOKEN")
    if not endpoint:
        raise RuntimeError("LIVE_PROVIDER_URL is not configured")
    headers = {"Accept": "application/json", "User-Agent": "ViralAngleRadar/0.1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(endpoint, headers=headers)
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise RuntimeError("Live provider response must be a list or contain an items list")
    return items

