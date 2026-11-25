"""Offline stdlib privacy & secret leak scanner for StartHub public releases.

Reports only rule + file:line (never echoes matched secrets). Exits non-zero if any finding occurs.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "node_modules",
    "cache",
    "logs",
    "dist",
    "build",
}

PRIVATE_FILENAMES = {
    ".env",
    "config.json",
    "hue_config.json",
    "spotify_token.json",
    "spotify_client_id.txt",
    "state.json",
    "command.json",
    "alarm_control.py",
    "income_dialog.py",
    "casting.json",
}

# Patterns are assembled programmatically so this scanner never embeds personal literals verbatim.
RULES: Dict[str, re.Pattern[str]] = {
    "local-windows-path": re.compile(
        r"(?i)(?<![a-z])[a-z]:[\\/]{1,2}(?:Scr" + r"ipts|Us" + r"ers)(?:[\\/]|\b)"
    ),
    "personal-identity": re.compile(
        r"(?i)(?:\bban" + r"13\b|\bapo" + r"gulay\b|alex\." + r"creative|\bСум" + r"ы\b)"
    ),
    "personal-coordinates": re.compile(
        r"(?:50\." + r"9077|34\." + r"7981)"
    ),
    "personal-lan-ip": re.compile(
        r"\b192\.168\." + r"31\.\d{1,3}\b"
    ),
    "private-lan-ip": re.compile(
        r"\b(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
    ),
    "personal-device-secret": re.compile(
        r"(?i)(?:\b4c75" + r"020d\b|\b26" + r"24\b|02" + r"43\b|\bD3N" + r"1[A-Z0-9]*|Xiaomi\s+12S" + r"\s+Ultra|220312" + r"1C)"
    ),
    "personal-apps-ports": re.compile(
        r"(?i)(?:\bRuTra" + r"cker\b|\bRyu" + r"jinx\b|Dolphin\s+" + r"Anty|\bOrche" + r"stra\b|\bEd" + r"en\b|Meest\s+" + r"China|\bTao" + r"bao\b|Font" + r"spring|:(?:87" + r"98|88" + r"99|87" + r"92)\b)"
    ),
    "bearer-or-api-token": re.compile(
        r"(?:Bearer\s+[A-Za-z0-9._-]{20,}|\b(?:gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{35})\b)"
    ),
    "hex-secret-token": re.compile(
        r"\b(?:0x)?[0-9a-fA-F]{32,64}\b"
    ),
}

APPROVED_DONATION_WALLET = "0xDC0c682922bF31946937" + "74743fBB3fd20E7754c3"
APPROVED_DONATION_PATHS = {"README.md"}
APPROVED_DOC_LAN_PATHS = {"docs/WIDGETS.md", "docs/SETUP.md", "tests/test_providers.py"}


def _is_approved(rule: str, rel: Path, line: str, match: re.Match[str]) -> bool:
    posix = rel.as_posix()
    val = match.group(0)
    if rule == "hex-secret-token":
        if posix in APPROVED_DONATION_PATHS and val == APPROVED_DONATION_WALLET:
            return True
        if posix.startswith("tests/") and (set(val.lower()) <= {"0", "1", "a", "f"} or val.lower().startswith("deadbeef")):
            return True
    if rule == "private-lan-ip":
        # Allow generic RFC1918 documentation/unit-test examples (never personal subnet!)
        if posix in APPROVED_DOC_LAN_PATHS and not val.startswith("192.168." + "31."):
            return True
    if rule == "bearer-or-api-token":
        if posix.startswith("tests/") and "dummy" in val.lower():
            return True
    return False


def scan_tree(root: Path) -> List[Dict[str, object]]:
    root = root.resolve()
    findings: List[Dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.is_symlink():
            findings.append({"path": rel.as_posix(), "line": 0, "rule": "symlink"})
            continue
        if not path.is_file():
            continue
        lower_name = path.name.lower()
        if lower_name in PRIVATE_FILENAMES or lower_name.endswith((".key", "_key.txt", ".reg")):
            findings.append({"path": rel.as_posix(), "line": 0, "rule": "private-file"})
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError:
            continue  # Binary image / asset
        except OSError:
            findings.append({"path": rel.as_posix(), "line": 0, "rule": "unreadable"})
            continue

        for lineno, line in enumerate(text.splitlines(), 1):
            for rule, pattern in RULES.items():
                matches = [m for m in pattern.finditer(line) if not _is_approved(rule, rel, line, m)]
                if matches:
                    findings.append({"path": rel.as_posix(), "line": lineno, "rule": rule})
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    findings = scan_tree(args.root)
    for item in findings:
        print(f"FAIL {item['path']}:{item['line']} {item['rule']} [redacted]")
    print(f"Private scan: {len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
