"""Example Custom JSON script ('columns' layout): Pi-hole local DNS stats bridge."""
from __future__ import annotations

import json
import os
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parents[2] / "cache" / "custom_pihole.json"
PIHOLE_HOST = os.environ.get("PIHOLE_URL", "http://pi.hole")


def main() -> None:
    r = requests.get(f"{PIHOLE_HOST.rstrip('/')}/admin/api.php?summaryRaw", timeout=4)
    r.raise_for_status()
    d = r.json()
    pct = float(d.get("ads_percentage_today", 0.0))
    blocked = int(d.get("ads_blocked_today", 0))
    queries = int(d.get("dns_queries_today", 0))
    clients = int(d.get("unique_clients", 0))
    payload = {
        "title": "Pi-hole DNS",
        "badge": f"{clients} clients",
        "layout": "columns",
        "url": f"{PIHOLE_HOST.rstrip('/')}/admin/",
        "metrics": [
            {"label": "Blocked", "value": f"{pct:.1f}%", "percent": round(pct), "sublabel": f"{blocked:,} ads", "tag": "DNS", "status": "ok"},
            {"label": "Queries", "value": f"{queries // 1000}k" if queries >= 1000 else str(queries), "percent": min(100, round(queries / 1000)), "sublabel": "Today", "tag": "24h", "status": "info"},
            {"label": "Status", "value": str(d.get("status", "ok")).upper(), "percent": 100, "sublabel": "Filtering active", "tag": "OK", "status": "ok"},
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
