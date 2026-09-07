from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "radar.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
  video_id TEXT PRIMARY KEY,
  platform TEXT NOT NULL,
  canonical_url TEXT NOT NULL UNIQUE,
  creator_handle TEXT,
  creator_name TEXT,
  creator_country TEXT,
  creator_country_evidence TEXT,
  language TEXT,
  caption TEXT,
  published_at TEXT,
  category TEXT,
  format TEXT,
  primary_angle TEXT,
  hook_summary TEXT,
  proof_mechanism TEXT,
  paid_partnership INTEGER NOT NULL DEFAULT 0,
  evidence_quality TEXT,
  source_provider TEXT,
  is_fixture INTEGER NOT NULL DEFAULT 0,
  collected_at TEXT NOT NULL,
  last_verified_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metric_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  views INTEGER,
  likes INTEGER,
  comments INTEGER,
  shares INTEGER,
  saves INTEGER,
  followers INTEGER,
  field_provenance TEXT,
  UNIQUE(video_id, observed_at),
  FOREIGN KEY(video_id) REFERENCES videos(video_id)
);

CREATE TABLE IF NOT EXISTS trend_scores (
  video_id TEXT PRIMARY KEY,
  calculated_at TEXT NOT NULL,
  trend_score REAL NOT NULL,
  velocity_score REAL,
  velocity_status TEXT,
  engagement_score REAL,
  recency_score REAL,
  relevance_score REAL,
  novelty_score REAL,
  evidence_score REAL,
  explanation TEXT,
  FOREIGN KEY(video_id) REFERENCES videos(video_id)
);

CREATE TABLE IF NOT EXISTS briefs (
  brief_id TEXT PRIMARY KEY,
  brand TEXT NOT NULL,
  product TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  markdown_path TEXT NOT NULL,
  json_path TEXT NOT NULL,
  source_video_ids TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft'
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def log_run(event: dict[str, Any]) -> None:
    path = ROOT / "data" / "run-log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")

