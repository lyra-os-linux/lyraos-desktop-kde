#!/usr/bin/env python3
"""Validate the Lyra 1.0 localization inventory against OBS policy."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "i18n/inventory.json"
OBS = ROOT / "obs/projects.toml"
LOCALES = ["en-US", "pt-BR", "es-ES"]
STATUSES = {"complete", "scheduled", "not-applicable"}


def validate() -> list[str]:
    errors: list[str] = []
    document = json.loads(INVENTORY.read_text(encoding="utf-8"))
    with OBS.open("rb") as stream:
        obs = tomllib.load(stream)
    expected = {
        (project["id"], package)
        for project in obs["projects"]
        for package in project["packages"]
    }
    # lyra-installer is already in OBS; this expression deliberately derives
    # every package from policy rather than keeping another hand-written list.
    entries = document.get("packages", [])
    actual = {(entry.get("project"), entry.get("id")) for entry in entries}
    if actual != expected:
        errors.append(
            f"inventory differs from OBS packages: missing={sorted(expected-actual)}, "
            f"extra={sorted(actual-expected)}"
        )
    if document.get("locales") != LOCALES:
        errors.append("locale scope must be exactly en-US, pt-BR and es-ES")
    if document.get("default_locale") != "en-US" or document.get("fallback_locale") != "en-US":
        errors.append("en-US must be both default and fallback")
    seen: set[tuple[object, object]] = set()
    for entry in entries:
        identity = (entry.get("project"), entry.get("id"))
        if identity in seen:
            errors.append(f"duplicate package: {identity}")
        seen.add(identity)
        status = entry.get("status")
        if status not in STATUSES:
            errors.append(f"{identity}: invalid status {status!r}")
        for field in ("wave", "format", "domain", "selection", "lint", "rationale"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                errors.append(f"{identity}: missing {field}")
        if status == "not-applicable":
            if entry.get("format") != "none" or entry.get("domain") != "none":
                errors.append(f"{identity}: N/A package must use format/domain none")
        elif entry.get("format") == "none" or entry.get("domain") == "none":
            errors.append(f"{identity}: localizable package lacks a catalog contract")
    return errors


def main() -> int:
    try:
        errors = validate()
    except (OSError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        print(f"i18n inventory: {error}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"i18n inventory: {error}", file=sys.stderr)
        return 1
    print("OK: i18n inventory covers every OBS package")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
