"""Example Custom JSON script ('columns' layout): local workstation / Home Lab snapshot."""
from __future__ import annotations

import datetime
import json
from pathlib import Path
import psutil

OUT = Path(__file__).resolve().parents[2] / "cache" / "custom_homelab.json"


def build_payload() -> dict:
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(str(Path.home().anchor or "/"))
    procs = len(psutil.pids())
    return {
        "title": "Workstation Pro",
        "subtitle": datetime.datetime.now().strftime("%H:%M"),
        "badge": f"{procs} procs",
        "layout": "columns",
        "metrics": [
            {
                "label": "Memory",
                "value": f"{mem.percent:.0f}%",
                "percent": round(mem.percent),
                "sublabel": f"{mem.used / (1024**3):.1f} / {mem.total / (1024**3):.0f} GB",
                "tag": "RAM",
                "status": "warn" if mem.percent > 80 else "info",
            },
            {
                "label": "System Disk",
                "value": f"{disk.percent:.0f}%",
                "percent": round(disk.percent),
                "sublabel": f"{disk.free / (1024**3):.0f} GB free",
                "tag": "SSD",
                "status": "danger" if disk.percent > 90 else "ok",
            },
            {
                "label": "Processes",
                "value": str(procs),
                "percent": min(100, round(procs / 4)),
                "sublabel": "Active tasks",
                "tag": "OS",
                "status": "info",
            },
        ],
    }


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build_payload(), indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
