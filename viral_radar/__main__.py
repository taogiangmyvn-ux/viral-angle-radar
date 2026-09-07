from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import daily, discover, export_excel, export_site, generate_brief, ingest_brand, score


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="viral_radar")
    commands = root.add_subparsers(dest="command", required=True)
    discover_cmd = commands.add_parser("discover")
    discover_cmd.add_argument("--fixture", action="store_true")
    discover_cmd.add_argument("--live", action="store_true")
    discover_cmd.add_argument("--csv", type=Path)
    discover_cmd.add_argument("--observed-at")
    commands.add_parser("score")
    brand = commands.add_parser("ingest-brand")
    brand.add_argument("--brand", required=True)
    brief = commands.add_parser("brief")
    brief.add_argument("--brand", required=True)
    brief.add_argument("--product", required=True)
    brief.add_argument("--top-angles", type=int, default=3)
    commands.add_parser("export-site")
    commands.add_parser("export-excel")
    daily_cmd = commands.add_parser("daily")
    daily_cmd.add_argument("--fixture", action="store_true")
    daily_cmd.add_argument("--live", action="store_true")
    return root


def main() -> None:
    args = parser().parse_args()
    if args.command == "discover":
        result = discover(fixture=args.fixture, csv_path=args.csv, observed_at=args.observed_at, live=args.live)
    elif args.command == "score":
        result = score()
    elif args.command == "ingest-brand":
        result = ingest_brand(args.brand)
    elif args.command == "brief":
        result = generate_brief(args.brand, args.product, args.top_angles)
    elif args.command == "export-site":
        result = {"site": str(export_site())}
    elif args.command == "export-excel":
        result = {"workbook": str(export_excel())}
    else:
        result = daily(args.fixture, args.live)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
