# Custom JSON Widget Examples

StartHub's `custom_json` widget turns **any** local JSON file or `localhost` HTTP endpoint (`http://127.0.0.1:...`) into a native-acrylic card supporting three layouts:

| Layout | Best for | Required fields |
|---|---|---|
| `columns` (default) | 1–3 progress metrics (**AI agent quotas**, NAS, Pi-hole, UPS) | `metrics: [{label, value, percent, sublabel, tag, status}]` |
| `hero` | Big headline metric + 2 stat pills (**Monthly income/budget**, Portfolio, FX/Crypto) | `hero_value`, `hero_sub`, `hero_status`, optional `metrics` |
| `list` | Compact 1–5 row status list (Ollama models, Docker containers, Services) | `items: [{label, value, status}]` |

## Included Ready-to-Run Scripts

| Script | Layout | Output file | What it tracks |
|---|---|---|---|
| **`ai_quotas_example.py`** | `columns` | `cache/custom_ai_quotas.json` | Live **OpenRouter** credits (`OPENROUTER_API_KEY`) + Claude Code / Codex / Gemini quota bars & reset timers |
| **`income_budget_example.py`** | `hero` | `cache/custom_budget.json` | Monthly total + Daily Average + Month Forecast (supports `--add 250 --note "Client"`) |
| **`homelab_sample.py`** | `columns` | `cache/custom_homelab.json` | Local workstation RAM, SSD, and active processes |
| **`crypto_fx_rates.py`** | `hero` | `cache/custom_market.json` | Free live BTC / ETH / EUR rates (zero API keys) |
| **`ollama_status.py`** | `list` | `cache/custom_ollama.json` | Local Ollama models (`http://127.0.0.1:11434/api/tags`) |
| **`pihole_bridge.py`** | `columns` | `cache/custom_pihole.json` | Local Pi-hole blocked queries & percentage |

## Quick Setup (GUI or `config.json`)

1. Run any script once to generate its JSON file:
   ```powershell
   .\.venv\Scripts\python.exe examples\custom_json\ai_quotas_example.py
   ```
2. Open **Tray → Settings → Custom Cards & Actions → Custom JSON Cards** (or edit `config.json`):
   ```json
   "custom_json": {
     "enabled": true,
     "allow_remote_urls": false,
     "cards": [
       { "id": "ai_quotas", "title": "AI Agent Quotas", "layout": "columns", "source": "cache/custom_ai_quotas.json", "refresh_sec": 30 },
       { "id": "budget",    "title": "Monthly Tracker", "layout": "hero",    "source": "cache/custom_budget.json",    "refresh_sec": 60 },
       { "id": "ollama",    "title": "Ollama",          "layout": "list",    "source": "cache/custom_ollama.json",    "refresh_sec": 30 }
     ]
   }
   ```

## Auto-Refresh Silently Every 5 Minutes (Windows Task Scheduler)

Run this PowerShell snippet from your StartHub folder to refresh a script silently via `pythonw.exe` (no console window flash):

```powershell
$Repo = (Get-Location).Path
$Action = New-ScheduledTaskAction -Execute "$Repo\.venv\Scripts\pythonw.exe" -Argument "`"$Repo\examples\custom_json\ai_quotas_example.py`"" -WorkingDirectory $Repo
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName "StartHub-AI-Quotas" -Action $Action -Trigger $Trigger -Force
```

> Tip: For full step-by-step instructions on plugging in Claude Code, Codex, OpenRouter, or your own CLI tools, see **[docs/WIDGETS.md](../../docs/WIDGETS.md#4-ai-agent-quotas-budgets--custom-json-cards-custom_json)** (or **[docs/WIDGETS.ru.md](../../docs/WIDGETS.ru.md)** in Russian).
