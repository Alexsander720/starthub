"""Example Custom JSON script ('hero' layout): Monthly Income / Budget / Goal tracker.

Stores entries locally in cache/budget_entries.json and outputs a StartHub 'hero' card
to cache/custom_budget.json with:
- Headline monthly total
- Daily average
- End-of-month linear forecast

Usage:
    # Generate initial card (auto-creates sample entries on first run)
    python examples/custom_json/income_budget_example.py

    # Log a new entry and refresh the card immediately
    python examples/custom_json/income_budget_example.py --add 250 --note "Freelance project"
"""
from __future__ import annotations

import argparse
import calendar
import datetime
import json
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER = REPO_ROOT / "cache" / "budget_entries.json"
OUT = REPO_ROOT / "cache" / "custom_budget.json"
CURRENCY = "$"


def _load_entries() -> List[Dict[str, Any]]:
    if LEDGER.is_file():
        try:
            data = json.loads(LEDGER.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    today = datetime.date.today()
    ym = today.strftime("%Y-%m")
    sample = [
        {"date": f"{ym}-01", "amount": 420.0, "note": "Client milestone"},
        {"date": f"{ym}-{min(today.day, 10):02d}", "amount": 310.0, "note": "Design sprint"},
        {"date": today.isoformat(), "amount": 190.0, "note": "Consulting"},
    ]
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
    return sample


def build_payload(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    today = datetime.date.today()
    ym_prefix = today.strftime("%Y-%m")
    month_total = sum(
        float(e.get("amount") or 0.0)
        for e in entries
        if str(e.get("date") or "").startswith(ym_prefix)
    )
    days_elapsed = max(1, today.day)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    daily_avg = month_total / days_elapsed
    forecast = daily_avg * days_in_month

    return {
        "title": "Monthly Tracker",
        "subtitle": today.strftime("%B %Y"),
        "badge": f"{len([e for e in entries if str(e.get('date', '')).startswith(ym_prefix)])} items",
        "layout": "hero",
        "hero_value": f"{CURRENCY}{month_total:,.0f}",
        "hero_sub": f"Day {days_elapsed} of {days_in_month}",
        "hero_status": "ok" if month_total > 0 else "info",
        "metrics": [
            {
                "label": "Daily Avg",
                "value": f"{CURRENCY}{daily_avg:,.0f}",
                "status": "info",
            },
            {
                "label": "Month Forecast",
                "value": f"{CURRENCY}{forecast:,.0f}",
                "status": "ok",
            },
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Update StartHub Monthly Tracker Custom JSON card.")
    parser.add_argument("--add", type=float, default=None, help="Add an income/budget entry for today")
    parser.add_argument("--note", type=str, default="Entry", help="Optional label for --add")
    args = parser.parse_args()

    entries = _load_entries()
    if args.add is not None:
        entries.append(
            {
                "date": datetime.date.today().isoformat(),
                "amount": float(args.add),
                "note": args.note,
            }
        )
        LEDGER.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(build_payload(entries), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
