"""Example Custom JSON script ('hero' layout): free zero-key BTC/ETH/EUR market snapshot."""
from __future__ import annotations

import datetime
import json
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parents[2] / "cache" / "custom_market.json"


def main() -> None:
    r = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": "bitcoin,ethereum", "vs_currencies": "usd", "include_24hr_change": "true"},
        timeout=8,
    )
    r.raise_for_status()
    data = r.json()
    btc = data.get("bitcoin", {})
    eth = data.get("ethereum", {})
    btc_p = float(btc.get("usd", 0))
    btc_chg = float(btc.get("usd_24h_change", 0))
    eth_p = float(eth.get("usd", 0))
    eth_chg = float(eth.get("usd_24h_change", 0))

    payload = {
        "title": "Market Pulse",
        "subtitle": datetime.datetime.now().strftime("%H:%M"),
        "badge": "Live",
        "layout": "hero",
        "url": "https://www.coingecko.com/",
        "hero_value": f"${btc_p:,.0f}",
        "hero_sub": f"BTC {btc_chg:+.1f}%",
        "hero_status": "ok" if btc_chg >= 0 else "danger",
        "metrics": [
            {"label": "Ethereum (24h)", "value": f"${eth_p:,.0f} ({eth_chg:+.1f}%)", "status": "ok" if eth_chg >= 0 else "danger"},
            {"label": "Feed", "value": "CoinGecko Free API", "status": "info"},
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
