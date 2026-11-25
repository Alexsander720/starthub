# Custom JSON Widget Examples

StartHub's `custom_json` widget turns **any** local JSON file or `localhost` HTTP endpoint into a native-acrylic card supporting three layouts:

| Layout | Best for | Required fields |
|---|---|---|
| `columns` (default) | 1–3 progress metrics (NAS, AI quotas, Pi-hole, UPS) | `metrics: [{label, value, percent, sublabel, tag, status}]` |
| `hero` | Big headline metric + 2 stat pills (Portfolio, FX/Crypto, Balance) | `hero_value`, `hero_sub`, `hero_status`, optional `metrics` |
| `list` | Compact 1–4 row status list (Docker containers, Ollama models, Services) | `items: [{label, value, status}]` |

## Included Ready-to-Run Scripts

- **`homelab_sample.py`** — writes a `columns` Home Lab card to `cache/custom_homelab.json`
- **`crypto_fx_rates.py`** — fetches free BTC/ETH/EUR rates (zero API keys) and writes a `hero` card to `cache/custom_market.json`
- **`ollama_status.py`** — queries local Ollama (`http://127.0.0.1:11434/api/tags`) and writes a `list` card to `cache/custom_ollama.json`
- **`pihole_bridge.py`** — queries a local Pi-hole instance and writes a `columns` card to `cache/custom_pihole.json`

## Enabling in `config.json`

```json
"custom_json": {
  "enabled": true,
  "allow_remote_urls": false,
  "cards": [
    { "id": "homelab", "title": "Home Lab", "source": "cache/custom_homelab.json", "refresh_sec": 15 },
    { "id": "market",  "title": "Market",   "source": "cache/custom_market.json",  "refresh_sec": 60 },
    { "id": "ollama",  "title": "Ollama",   "source": "cache/custom_ollama.json",  "refresh_sec": 30 }
  ]
}
```
