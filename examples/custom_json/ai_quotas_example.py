"""Example Custom JSON script ('columns' layout): AI Agent Quotas & API Credits tracker.

Supports:
1. Live OpenRouter balance when OPENROUTER_API_KEY is set in your environment.
2. Optional local CLI quota JSON files or environment percentages (e.g. Claude Code,
   Codex, Gemini, or any custom quota helper script).
3. Clean starter output on first run so you can immediately wire it into StartHub.

Run once to test:
    python examples/custom_json/ai_quotas_example.py

Then point a Custom JSON card in StartHub Settings to:
    cache/custom_ai_quotas.json
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "cache" / "custom_ai_quotas.json"


def _status_for_used_pct(pct: int) -> str:
    if pct >= 90:
        return "danger"
    if pct >= 70:
        return "warn"
    return "ok"


def _fetch_openrouter_metric() -> Optional[Dict[str, Any]]:
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        resp = requests.get(
            "https://openrouter.ai/api/v1/key",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5.0,
        )
        resp.raise_for_status()
        data = (resp.json() or {}).get("data") or {}
        usage = float(data.get("usage") or 0.0)
        limit = data.get("limit")
        if isinstance(limit, (int, float)) and limit > 0:
            pct = max(0, min(100, round((usage / float(limit)) * 100)))
            rem = max(0.0, float(limit) - usage)
            return {
                "label": "OpenRouter",
                "value": f"${rem:.2f}",
                "percent": pct,
                "sublabel": f"${usage:.2f} / ${float(limit):.0f} used",
                "tag": "API",
                "status": _status_for_used_pct(pct),
            }
        return {
            "label": "OpenRouter",
            "value": f"${usage:.2f}",
            "percent": 15,
            "sublabel": "Unlimited key",
            "tag": "API",
            "status": "ok",
        }
    except Exception:
        return {
            "label": "OpenRouter",
            "value": "Offline",
            "percent": 0,
            "sublabel": "Check API key / net",
            "tag": "API",
            "status": "warn",
        }


def _read_local_quota_file(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _env_pct(var_name: str, default: int) -> int:
    raw = os.environ.get(var_name, "").strip().rstrip("%")
    try:
        return max(0, min(100, int(float(raw))))
    except ValueError:
        return default


def build_payload() -> Dict[str, Any]:
    """Assemble up to 3 AI agent quota columns for StartHub's 'columns' layout."""
    metrics: List[Dict[str, Any]] = []

    # Optional: load real numbers from a local helper JSON if you maintain one
    local_override = _read_local_quota_file(REPO_ROOT / "cache" / "ai_quotas_raw.json")
    if local_override and isinstance(local_override.get("metrics"), list):
        return {
            "title": str(local_override.get("title") or "AI Agents"),
            "subtitle": datetime.datetime.now().strftime("%H:%M"),
            "badge": str(local_override.get("badge") or "Live"),
            "layout": "columns",
            "url": str(local_override.get("url") or ""),
            "metrics": local_override["metrics"][:3],
        }

    # Column 1: Live OpenRouter credits (if OPENROUTER_API_KEY is set) or Claude Code quota
    or_metric = _fetch_openrouter_metric()
    if or_metric:
        metrics.append(or_metric)
    else:
        claude_used = _env_pct("AI_CLAUDE_USED_PCT", 24)
        metrics.append(
            {
                "label": "Claude Code",
                "value": f"{claude_used}%",
                "percent": claude_used,
                "sublabel": os.environ.get("AI_CLAUDE_RESET", "Resets in 3h 20m"),
                "tag": "5h",
                "status": _status_for_used_pct(claude_used),
            }
        )

    # Column 2: Codex / OpenAI quota (override via env vars or replace with your CLI call)
    codex_used = _env_pct("AI_CODEX_USED_PCT", 58)
    metrics.append(
        {
            "label": "Codex CLI",
            "value": f"{codex_used}%",
            "percent": codex_used,
            "sublabel": os.environ.get("AI_CODEX_RESET", "Weekly window"),
            "tag": "7d",
            "status": _status_for_used_pct(codex_used),
        }
    )

    # Column 3: Gemini / Antigravity remaining pool
    gemini_rem = _env_pct("AI_GEMINI_REM_PCT", 82)
    metrics.append(
        {
            "label": "Gemini",
            "value": f"{gemini_rem}%",
            "percent": gemini_rem,
            "sublabel": os.environ.get("AI_GEMINI_NOTE", "Remaining pool"),
            "tag": "Pro",
            "status": "danger" if gemini_rem <= 15 else ("warn" if gemini_rem <= 35 else "ok"),
        }
    )

    live_badge = "OpenRouter" if or_metric else "Template"
    return {
        "title": "AI Agent Quotas",
        "subtitle": datetime.datetime.now().strftime("%H:%M"),
        "badge": live_badge,
        "layout": "columns",
        "url": "https://openrouter.ai/activity" if or_metric else "",
        "metrics": metrics[:3],
    }


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(build_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
