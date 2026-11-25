"""Example Custom JSON script ('list' layout): local Ollama models & running status."""
from __future__ import annotations

import json
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parents[2] / "cache" / "custom_ollama.json"


def main() -> None:
    try:
        tags = requests.get("http://127.0.0.1:11434/api/tags", timeout=2.5).json()
        models = tags.get("models") or []
        running = requests.get("http://127.0.0.1:11434/api/ps", timeout=2.5).json().get("models") or []
        running_names = {m.get("name") for m in running if isinstance(m, dict)}
        items = []
        for m in models[:4]:
            name = str(m.get("name") or "model")
            size_gb = float(m.get("size", 0)) / (1024**3)
            active = name in running_names
            items.append(
                {
                    "label": name,
                    "value": f"ACTIVE · {size_gb:.1f} GB" if active else f"{size_gb:.1f} GB",
                    "status": "ok" if active else "info",
                }
            )
        payload = {
            "title": "Ollama Local AI",
            "badge": f"{len(models)} models",
            "subtitle": f"{len(running_names)} loaded",
            "layout": "list",
            "items": items or [{"label": "No models installed", "value": "ollama pull ...", "status": "warn"}],
        }
    except Exception:
        payload = {
            "title": "Ollama Local AI",
            "badge": "Stopped",
            "layout": "list",
            "items": [{"label": "127.0.0.1:11434", "value": "Not running", "status": "warn"}],
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
