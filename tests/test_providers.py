"""Tests for Tier 1/2 providers, EcoFlow decoder & logging, Tile Switcher, and Privacy Scanner."""
from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from starthub.providers.custom_json import CustomJsonProvider, is_allowed_source_url
from starthub.providers.ecoflow import (
    Delta3Decoder,
    EcoFlowMqttClient,
    attach_ecoflow_rotating_log,
    logger as ecoflow_logger,
)
from starthub.providers.hue import HueProvider, fetch_ha_catalog, is_valid_ha_url, is_valid_lan_ip
from starthub.providers.weather import build_open_meteo_url, validate_open_meteo_payload
from tools import scan_private, tile_switcher


def test_hue_lan_ip_validation():
    assert is_valid_lan_ip("192.168.1.50") is True
    assert is_valid_lan_ip("10.0.0.15") is True
    assert is_valid_lan_ip("172.16.4.2") is True
    assert is_valid_lan_ip("8.8.8.8") is False
    assert is_valid_lan_ip("evil.example.com") is False
    assert is_valid_lan_ip("") is False
    assert is_valid_ha_url("http://homeassistant.local:8123") is True
    assert is_valid_ha_url("http://127.0.0.1:8123") is True
    assert is_valid_ha_url("ftp://homeassistant.local") is False


def test_smart_lights_home_assistant_and_wled_backends_and_4tile_render():
    from PIL import Image, ImageDraw
    from starthub.config import load_config
    from starthub.i18n import I18n
    from starthub.surface import FontBank
    from starthub.theme import Theme
    from starthub.widgets import RenderContext
    from starthub.widgets.hue import draw_hue_card

    class _FakeResp:
        def __init__(self, payload):
            self._payload = payload
            self.content = b"ok"

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    class _FakeHaSession:
        def __init__(self):
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append(("GET", url, None))
            return _FakeResp(
                [
                    {"entity_id": "light.office_ceiling", "attributes": {"friendly_name": "Office Ceiling"}},
                    {"entity_id": "switch.desk_plug", "attributes": {"friendly_name": "Desk Plug"}},
                    {"entity_id": "sensor.temp", "attributes": {"friendly_name": "Temp"}},
                ]
            )

        def request(self, method, url, json=None, **kwargs):
            self.calls.append((method, url, json))
            if method == "GET" and url.endswith("/api/states/light.office_ceiling"):
                return _FakeResp({"state": "on", "attributes": {"brightness": 191}})
            if method == "GET" and url.endswith("/api/states/switch.desk_plug"):
                return _FakeResp({"state": "off", "attributes": {}})
            return _FakeResp({})

    ha_sess = _FakeHaSession()
    cat = fetch_ha_catalog("http://homeassistant.local:8123", "dummy_tok", session=ha_sess)
    assert [c["id"] for c in cat] == ["light.office_ceiling", "switch.desk_plug"]

    ha_prov = HueProvider(
        {
            "enabled": True,
            "backend": "home_assistant",
            "ha_url": "http://homeassistant.local:8123",
            "ha_token": "dummy_tok",
            "targets": [
                {"id": "light.office_ceiling", "label": "Office", "icon": "bulb", "dimmer": True},
                {"id": "switch.desk_plug", "label": "Plug", "icon": "monitor", "dimmer": False},
            ],
        },
        I18n("en"),
        session=ha_sess,
    )
    snap = ha_prov.poll_once()
    assert snap["ready"] is True and len(snap["targets"]) == 2
    assert snap["targets"][0]["on"] is True and snap["targets"][0]["bri"] >= 188
    assert snap["targets"][1]["on"] is False
    ha_prov._send_command(snap["targets"][0]["key"], 50)
    assert any(c[0] == "POST" and "/api/services/light/turn_on" in c[1] and c[2]["brightness"] == 128 for c in ha_sess.calls)

    class _FakeWledSession:
        def __init__(self):
            self.posts = []

        def request(self, method, url, json=None, **kwargs):
            if method == "POST":
                self.posts.append((url, json))
                return _FakeResp({"on": True, "bri": 200})
            return _FakeResp({"on": True, "bri": 128})

    wled_sess = _FakeWledSession()
    wled_prov = HueProvider(
        {
            "enabled": True,
            "backend": "wled",
            "bridge_ip": "192.168.1.77",
            "targets": [{"id": "192.168.1.77", "label": "Monitor Strip", "icon": "monitor", "dimmer": True}],
        },
        I18n("en"),
        session=wled_sess,
    )
    wsnap = wled_prov.poll_once()
    assert wsnap["ready"] is True and wsnap["targets"][0]["on"] is True
    wled_prov._send_command(wsnap["targets"][0]["key"], "toggle")
    assert wled_sess.posts == [("http://192.168.1.77/json/state", {"on": False})]

    # 4-tile 2x2 grid renders cleanly in Fluent Light
    theme = Theme.from_config(load_config(overrides={"theme": {"preset": "fluent_light"}}))
    img = Image.new("RGBA", (832, 420), (*theme.panel_rgb, 255))
    ctx = RenderContext(img=img, draw=ImageDraw.Draw(img), scale=2, theme=theme, fonts=FontBank(), i18n=I18n("en"), hover=None, hotspots=[], img_cache={})
    four_state = {
        "ready": True,
        "dimmer_key": "k2",
        "targets": [
            {"key": f"k{i}", "label": f"Lamp {i}", "icon": "bulb" if i % 2 == 0 else "monitor", "on": i % 2 == 0, "bri": 180, "reachable": True, "dimmer": i == 0}
            for i in range(4)
        ],
    }
    draw_hue_card(ctx, (12, 12, 404, 198), four_state, on_command=lambda k, a: None)
    assert len(ctx.hotspots) >= 14


def test_custom_json_local_file_and_localhost_guard(tmp_path: Path):
    assert is_allowed_source_url("http://127.0.0.1:9000/stats") is True
    assert is_allowed_source_url("http://localhost:8080/api") is True
    assert is_allowed_source_url("https://example.com/api", allow_remote=False) is False
    assert is_allowed_source_url("https://example.com/api", allow_remote=True) is True

    metrics_file = tmp_path / "metrics.json"
    metrics_file.write_text(
        json.dumps(
            {
                "title": "NAS Status",
                "badge": "Healthy",
                "metrics": [
                    {"label": "Disk", "value": "55%", "percent": 55, "sublabel": "6.6 / 12 TB", "status": "ok"},
                    {"label": "Temp", "value": "38°C", "percent": 38, "status": "info"},
                ],
            }
        ),
        encoding="utf-8",
    )
    prov = CustomJsonProvider(
        {"enabled": True, "cards": [{"id": "nas", "title": "Fallback", "source": str(metrics_file)}]},
        base_dir=tmp_path,
    )
    cards = prov.poll_all()
    assert len(cards) == 1
    assert cards[0]["ok"] is True
    assert cards[0]["title"] == "NAS Status"
    assert len(cards[0]["metrics"]) == 2
    assert cards[0]["metrics"][0]["percent"] == 55


def test_ecoflow_decoder_json_and_protobuf_and_rotating_log(tmp_path: Path):
    # JSON fallback (DELTA 2 / JSON topics)
    decoded_json = Delta3Decoder.decode_payload(b'{"params": {"soc": 88, "wattsInSum": 120, "wattsOutSum": 95}}')
    assert decoded_json["soc"] == 88

    # Protobuf roundtrip (DELTA 3)
    from starthub.providers import ef_delta3_pb2 as pb

    prop = pb.Delta3DisplayPropertyUpload()
    prop.bms_batt_soc = 91.5
    prop.pow_in_sum_w = 0.0
    prop.pow_out_sum_w = 240.0
    prop.plug_in_info_ac_in_chg_pow_max = 600
    prop.cfg_ac_out_open = 1

    hdr_msg = pb.Delta3HeaderMessage()
    hdr = hdr_msg.header.add()
    hdr.cmd_func = 254
    hdr.cmd_id = 21
    hdr.src = 2
    hdr.pdata = prop.SerializeToString()

    decoded_pb = Delta3Decoder.decode_payload(hdr_msg.SerializeToString())
    assert decoded_pb["pow_out_sum_w"] == pytest.approx(240.0)
    assert decoded_pb["plug_in_info_ac_in_chg_pow_max"] == 600

    # State calculation detects blackout cleanly
    updates = []
    client = EcoFlowMqttClient(email="", password="", on_state_update=updates.append)
    assert client.apply_decoded(decoded_pb) is True
    assert client.current_state["soc"] == 92
    assert client.current_state["is_grid"] is False
    assert client.current_state["chg_pow_max"] == 600
    assert client.current_state["stale"] is False

    # RotatingFileHandler bounded to 2 MB
    attach_ecoflow_rotating_log(tmp_path)
    rot_handlers = [h for h in ecoflow_logger.handlers if isinstance(h, RotatingFileHandler)]
    assert rot_handlers
    assert rot_handlers[-1].maxBytes == 2 * 1024 * 1024
    # Clean up test handler so tmp_path unlocks on Windows
    for h in list(ecoflow_logger.handlers):
        if isinstance(h, RotatingFileHandler) and str(tmp_path) in getattr(h, "baseFilename", ""):
            h.close()
            ecoflow_logger.removeHandler(h)


def test_weather_url_and_payload_validation():
    url = build_open_meteo_url({"latitude": 50.4501, "longitude": 30.5234, "units": "imperial"})
    assert "temperature_unit=fahrenheit" in url
    assert "wind_speed_unit=mph" in url

    good = {
        "current": {"temperature_2m": 18.0, "apparent_temperature": 17.0, "wind_speed_10m": 3.0, "weather_code": 1},
        "daily": {
            "time": ["2026-11-25", "2026-11-26", "2026-11-27"],
            "temperature_2m_max": [20, 21, 19],
            "temperature_2m_min": [10, 11, 9],
            "weather_code": [1, 0, 3],
        },
    }
    cur, daily = validate_open_meteo_payload(good)
    assert cur["temperature_2m"] == 18.0
    assert len(daily["time"]) == 3

    with pytest.raises(ValueError):
        validate_open_meteo_payload({"current": {}, "daily": {}})


def test_tile_switcher_discovers_and_blocks_traversal(tmp_path: Path):
    pack = tmp_path / "clean_pack"
    pack.mkdir()
    (pack / "app.png").write_bytes(b"PNG")
    (pack / "pack.json").write_text(json.dumps({"name": "Clean", "tiles": {"App\\Test.lnk": "app.png"}}), encoding="utf-8")

    packs = tile_switcher.discover_packs(tmp_path)
    assert len(packs) == 1
    res = tile_switcher.apply_pack("clean_pack", packs_dir=tmp_path, dry_run=True)
    assert res["dry_run"] is True
    assert res["tiles"] == 1

    # Path traversal must be rejected
    evil = tmp_path / "evil_pack"
    evil.mkdir()
    (evil / "pack.json").write_text(json.dumps({"name": "Evil", "tiles": {"A": "../secret.png"}}), encoding="utf-8")
    with pytest.raises(ValueError):
        tile_switcher.resolve_pack_tiles(evil, {"tiles": {"A": "../secret.png"}})


def test_tile_switcher_export_current_tiles_dedupes_and_copies(tmp_path: Path):
    src_dir = tmp_path / "src_imgs"
    src_dir.mkdir()
    img_a = src_dir / "code.png"
    img_b = src_dir / "term.png"
    img_a.write_bytes(b"PNG-A")
    img_b.write_bytes(b"PNG-B")

    packs_dir = tmp_path / "packs"
    entries = {
        r"C:\Apps\Code.lnk": str(img_a),
        r"C:_Apps_Code.lnk": str(img_a),  # Start11 twin key should be deduplicated
        r"C:\Apps\Term.lnk": str(img_b),
        r"C:\Apps\Missing.lnk": str(src_dir / "missing.png"),
    }
    res = tile_switcher.export_current_tiles(
        "my_setup",
        display_name="My Setup",
        packs_dir=packs_dir,
        entries=entries,
    )
    assert res["pack"] == "my_setup"
    assert res["tiles_exported"] == 2
    assert res["images_copied"] == 2
    assert res["skipped"] == 1

    # Exported pack must immediately pass discovery & dry-run validation
    packs = tile_switcher.discover_packs(packs_dir)
    assert len(packs) == 1
    dry = tile_switcher.apply_pack("my_setup", packs_dir=packs_dir, dry_run=True)
    assert dry["tiles"] == 2 and dry["name"] == "My Setup"

    # Overwrite protection works unless overwrite=True
    with pytest.raises(FileExistsError):
        tile_switcher.export_current_tiles("my_setup", packs_dir=packs_dir, entries=entries)


def test_privacy_scanner_catches_leaks_and_passes_repo(tmp_path: Path):
    # Clean tree passes
    assert scan_private.scan_tree(scan_private.ROOT) == []

    # Synthetic secret triggers scanner
    leak_file = tmp_path / "leak.txt"
    leak_file.write_text("token = " + "a1b2c3d4" * 5 + "\n", encoding="utf-8")
    findings = scan_private.scan_tree(tmp_path)
    assert any(f["rule"] == "hex-secret-token" for f in findings)

    # Private config.json filename triggers scanner
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    findings2 = scan_private.scan_tree(tmp_path)
    assert any(f["rule"] == "private-file" for f in findings2)
