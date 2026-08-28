#!/usr/bin/env python3
"""Render and verify Lyra OS release metadata from release.toml."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
RELEASE_FILE = REPOSITORY / "release.toml"


@dataclasses.dataclass(frozen=True)
class Release:
    calendar_version: str
    stage: str
    iteration: int
    codename: str
    codename_id: str
    image_name: str
    architecture: str

    @classmethod
    def from_file(cls, path: Path = RELEASE_FILE) -> "Release":
        with path.open("rb") as stream:
            document = tomllib.load(stream)
        try:
            values = document["release"]
            release = cls(
                calendar_version=values["calendar_version"],
                stage=values["stage"],
                iteration=values.get("iteration", 0),
                codename=values["codename"],
                codename_id=values["codename_id"],
                image_name=values["image_name"],
                architecture=values["architecture"],
            )
        except (KeyError, TypeError) as error:
            raise ValueError(f"invalid release manifest: missing {error}") from error
        release.validate()
        return release

    def validate(self) -> None:
        scalar_fields = {
            "calendar_version": self.calendar_version,
            "stage": self.stage,
            "codename": self.codename,
            "codename_id": self.codename_id,
            "image_name": self.image_name,
            "architecture": self.architecture,
        }
        if any(not isinstance(value, str) for value in scalar_fields.values()):
            raise ValueError("release text fields must be strings")
        if isinstance(self.iteration, bool) or not isinstance(self.iteration, int):
            raise ValueError("iteration must be an integer")
        if not re.fullmatch(r"\d{2}\.(?:0[1-9]|1[0-2])", self.calendar_version):
            raise ValueError("calendar_version must use YY.MM")
        if self.stage not in {"alpha", "beta", "rc", "release"}:
            raise ValueError("stage must be alpha, beta, rc, or release")
        if self.stage == "release" and self.iteration != 0:
            raise ValueError("a final release must use iteration = 0")
        if self.stage != "release" and self.iteration < 1:
            raise ValueError("beta and rc releases require a positive iteration")
        if not re.fullmatch(r"[A-Z][A-Za-z0-9-]*", self.codename):
            raise ValueError("codename must be a display-safe identifier")
        if not re.fullmatch(r"[a-z][a-z0-9-]*", self.codename_id):
            raise ValueError("codename_id must be lowercase and machine-safe")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", self.image_name):
            raise ValueError("image_name must be machine-safe")
        if not re.fullmatch(r"[A-Za-z0-9_]+", self.architecture):
            raise ValueError("architecture must be machine-safe")

    @property
    def version_id(self) -> str:
        if self.stage == "release":
            return self.calendar_version
        return f"{self.calendar_version}-{self.stage}{self.iteration}"

    @property
    def stage_label(self) -> str:
        if self.stage == "release":
            return "Release"
        prefix = {"alpha": "Alpha", "beta": "Beta", "rc": "RC"}[self.stage]
        return f"{prefix} {self.iteration}"

    @property
    def display_version(self) -> str:
        if self.stage == "release":
            return self.calendar_version
        return f"{self.calendar_version} {self.stage_label}"

    @property
    def pretty_name(self) -> str:
        return f"Lyra OS {self.display_version} ({self.codename})"

    @property
    def version_name(self) -> str:
        return f"{self.display_version} ({self.codename})"

    @property
    def codename_version(self) -> str:
        return f"{self.codename} {self.display_version}"

    @property
    def tag(self) -> str:
        return f"v{self.version_id}"

    @property
    def volume_id(self) -> str:
        value = f"LYRA_OS_{self.version_id}".upper().replace(".", "_").replace("-", "_")
        if len(value) > 32:
            raise ValueError("generated ISO volume ID exceeds 32 characters")
        return value

    @property
    def iso_filename(self) -> str:
        return f"{self.image_name}.{self.architecture}-{self.version_id}.iso"

    @property
    def specification(self) -> str:
        return (
            f'Lyra OS "{self.codename}" {self.display_version} - live/installer ISO, '
            f"openSUSE Leap 16 base, KDE Plasma desktop, {self.architecture}"
        )

    def fields(self) -> dict[str, str]:
        return {
            "architecture": self.architecture,
            "calendar_version": self.calendar_version,
            "codename": self.codename,
            "codename_id": self.codename_id,
            "display_version": self.display_version,
            "image_name": self.image_name,
            "iso_filename": self.iso_filename,
            "pretty_name": self.pretty_name,
            "release_iteration": str(self.iteration),
            "stage": self.stage,
            "stage_label": self.stage_label,
            "tag": self.tag,
            "version_id": self.version_id,
            "volume_id": self.volume_id,
        }


def replace_once(text: str, pattern: str, replacement: str, path: Path) -> str:
    # No count= limit here on purpose: re.subn(..., count=1) always reports
    # count=1 for any match count >= 1, since it stops after the first
    # substitution - it can never detect "more than one match", which is
    # exactly the failure mode this guard exists to catch.
    updated, count = re.subn(pattern, lambda _: replacement, text, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"expected one release field matching {pattern!r} in {path}")
    return updated


def shell_value(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def release_environment(release: Release) -> str:
    values = {
        "LYRA_ARCHITECTURE": release.architecture,
        "LYRA_CALENDAR_VERSION": release.calendar_version,
        "LYRA_CODENAME": release.codename,
        "LYRA_CODENAME_ID": release.codename_id,
        "LYRA_DISPLAY_VERSION": release.display_version,
        "LYRA_IMAGE_NAME": release.image_name,
        "LYRA_ISO_FILENAME": release.iso_filename,
        "LYRA_PRETTY_NAME": release.pretty_name,
        "LYRA_RELEASE_STAGE": release.stage,
        "LYRA_RELEASE_ITERATION": str(release.iteration),
        "LYRA_RELEASE_TAG": release.tag,
        "LYRA_STAGE_LABEL": release.stage_label,
        "LYRA_VERSION_ID": release.version_id,
        "LYRA_VERSION_NAME": release.version_name,
        "LYRA_VOLUME_ID": release.volume_id,
    }
    lines = [
        "# Generated by scripts/release.py from release.toml; do not edit.",
        *(f"{key}={shell_value(value)}" for key, value in values.items()),
        "",
    ]
    return "\n".join(lines)


def render_files(release: Release) -> dict[Path, str]:
    rendered: dict[Path, str] = {}

    xml_path = REPOSITORY / "kiwi/config.xml"
    xml = xml_path.read_text(encoding="utf-8")
    xml = replace_once(
        xml,
        r"^[ \t]*<specification>.*</specification>$",
        f"    <specification>{release.specification}</specification>",
        xml_path,
    )
    xml = replace_once(
        xml,
        r"^[ \t]*<version>[^<]+</version>$",
        f"    <version>{release.version_id}</version>",
        xml_path,
    )
    xml = replace_once(
        xml,
        r'volid="[^"]+"',
        f'volid="{release.volume_id}"',
        xml_path,
    )
    rendered[xml_path] = xml

    ui_path = REPOSITORY / "installer/ui/index.html"
    ui = ui_path.read_text(encoding="utf-8")
    ui = replace_once(
        ui,
        r'^\s*<div class="topbar-note">.*</div>$',
        f'          <div class="topbar-note">{release.codename} <span>{release.display_version}</span></div>',
        ui_path,
    )
    rendered[ui_path] = ui

    readme_path = REPOSITORY / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    readme = replace_once(
        readme,
        r"o instalador da edição \*\*[^*]+\*\* para computadores",
        f"o instalador da edição **{release.codename} {release.display_version}** para computadores",
        readme_path,
    )
    rendered[readme_path] = readme

    rendered[REPOSITORY / "kiwi/root/usr/lib/lyra-os/release"] = release_environment(release)
    return rendered


def render(release: Release, check: bool) -> int:
    stale: list[Path] = []
    for path, expected in render_files(release).items():
        actual = path.read_text(encoding="utf-8") if path.exists() else None
        if actual == expected:
            continue
        stale.append(path)
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")

    if stale and check:
        for path in stale:
            print(f"stale release metadata: {path.relative_to(REPOSITORY)}", file=sys.stderr)
        print("run ./scripts/release.py render", file=sys.stderr)
        return 1
    if stale:
        for path in stale:
            print(f"rendered {path.relative_to(REPOSITORY)}")
    else:
        print("release metadata is up to date")
    return 0


def git_output(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=REPOSITORY,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_build_manifest(release: Release, iso: Path, output: Path | None) -> int:
    iso = iso.resolve()
    if not iso.is_file():
        raise ValueError(f"ISO does not exist: {iso}")
    if iso.name != release.iso_filename:
        raise ValueError(f"expected ISO name {release.iso_filename}, got {iso.name}")
    output = output or Path(f"{iso}.manifest.json")
    dirty = bool(git_output("status", "--porcelain", "--untracked-files=normal"))
    document = {
        "schema_version": 1,
        "product": "Lyra OS",
        "version": release.version_id,
        "channel": release.stage,
        "channel_iteration": release.iteration,
        "codename": release.codename,
        "architecture": release.architecture,
        "release_tag": release.tag,
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "commit": git_output("rev-parse", "HEAD"),
            "dirty": dirty,
        },
        "iso": {
            "filename": iso.name,
            "size_bytes": iso.stat().st_size,
            "sha256": sha256(iso),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.new")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(output)
    return 0


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="fail if generated release metadata is stale")
    commands.add_parser("render", help="update generated release metadata")
    field = commands.add_parser("field", help="print one derived release field")
    field.add_argument("name")
    manifest = commands.add_parser("build-manifest", help="write traceability metadata for an ISO")
    manifest.add_argument("--iso", required=True, type=Path)
    manifest.add_argument("--output", type=Path)
    return cli


def main() -> int:
    args = parser().parse_args()
    try:
        release = Release.from_file()
        if args.command == "check":
            return render(release, check=True)
        if args.command == "render":
            return render(release, check=False)
        if args.command == "field":
            fields = release.fields()
            if args.name not in fields:
                raise ValueError(f"unknown field {args.name}; choose from: {', '.join(sorted(fields))}")
            print(fields[args.name])
            return 0
        return write_build_manifest(release, args.iso, args.output)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"release metadata error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
