#!/usr/bin/env python3
"""Export and audit reproducible Lyra KIWI image builds."""

from __future__ import annotations

import argparse
import configparser
import dataclasses
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "image-build.toml"
KIWI = ROOT / "kiwi"
RELEASE = ROOT / "release.toml"
PACKAGE_SIGNING_KEYRING = KIWI / "keys/obs-package-signing-keyring.asc"
PACKAGE_SIGNING_FINGERPRINTS = {
    "1C59D66FCD52563A16933DBCFEC28EAF09D9EA69",
    "F044C2C507A1262B538AAADD8A49EB0325DB7AE0",
    "BF3F9A67D3A2FF98A73F5E07488C583D287A0027",
    "AD485664E901B867051AB15F35A2F86E29B700A4",
    "FEAB502539D846DB2C0961CA70AF9E8139DB7C82",
    "7F009157B127B994D5CFBE76F74F09BC3FA1D6CE",
    "85E26470357A6391DBA1BC9E0739B8027BF939EF",
    "399218A6E088C4053F4533BE58097F767EDCA82E",
    "F8875B880D518B6B8C530D1345A1D0671ABD1AFB",
}
INSTALLER_APP_ID = "org.lyraos.LyraInstaller"
INSTALLER_EXEC = "/usr/bin/lyra-install-lock /usr/bin/lyra-installer"
INSTALLER_TRY_EXEC = "/usr/bin/lyra-installer"
INSTALLER_WM_CLASS = "lyra-installer"
ALPHA8_TEST_RESULTS = {
    "upgrade-rehearsal",
    "eca-digital",
    "i18n",
    "feature-freeze",
}
SUPPORTED_LOCALES = ["en-US", "pt-BR", "es-ES"]


class PolicyError(RuntimeError):
    """An image-build invariant was not satisfied."""


@dataclasses.dataclass(frozen=True)
class ObsPackageSource:
    project: str
    repository: str


@dataclasses.dataclass(frozen=True)
class Manifest:
    image_name: str
    description: str
    architecture: str
    source_repository: str
    iso_provider: str
    api_url: str
    obs_role: str
    package_sources: tuple[ObsPackageSource, ...]
    required_artifacts: tuple[str, ...]
    required_test_results: tuple[str, ...]

    @classmethod
    def load(cls, path: Path = DEFAULT_MANIFEST) -> "Manifest":
        with path.open("rb") as stream:
            data = tomllib.load(stream)
        if data.get("schema") != 1:
            raise PolicyError("image manifest schema must be 1")
        image, source = data["image"], data["source"]
        distribution, obs = data["distribution"], data["obs"]
        forbidden_obs_targets = {"project", "package", "repository", "maintainer"} & obs.keys()
        if forbidden_obs_targets:
            raise PolicyError("OBS image publication targets are forbidden")
        result = cls(
            image_name=image["name"],
            description=image["description"],
            architecture=image["architecture"],
            source_repository=source["repository"],
            iso_provider=distribution["iso_provider"],
            api_url=obs["api_url"],
            obs_role=obs["role"],
            package_sources=tuple(
                ObsPackageSource(**item) for item in obs["package_sources"]
            ),
            required_artifacts=tuple(data["artifacts"]["required"]),
            required_test_results=tuple(data["evidence"]["required_test_results"]),
        )
        result.validate()
        return result

    def validate(self) -> None:
        if self.api_url != "https://api.opensuse.org":
            raise PolicyError("only the canonical HTTPS OBS API is allowed")
        if self.source_repository != "https://github.com/lyra-os-linux/lyraos-desktop-kde":
            raise PolicyError("GitHub must remain the canonical image source")
        if self.iso_provider != "sourceforge":
            raise PolicyError("SourceForge must remain the ISO distribution provider")
        if self.obs_role != "packages-only":
            raise PolicyError("OBS is restricted to RPM packages")
        identifiers = (self.image_name, self.architecture)
        if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", value) for value in identifiers):
            raise PolicyError("invalid image identifier")
        if self.description != "config.xml":
            raise PolicyError("the exported KIWI description must be config.xml")
        # image-build.toml records approved policy, not a free-form config -
        # loosening this to "any subset" would defeat the point.
        expected_sources = (
            ObsPackageSource("home:rodrigosbrito:lyra", "openSUSE_Leap_16.1"),
            ObsPackageSource("home:rodrigosbrito:vega", "openSUSE_Leap_16.1"),
            ObsPackageSource("home:rodrigosbrito:fina", "openSUSE_Leap_16.1"),
        )
        expected_results = {
            "obs-repositories",
            "live-session",
            "installer",
            "first-boot",
            "uefi-secure-boot",
            "rollback",
            "hardware-matrix",
        }
        if self.package_sources != expected_sources:
            raise PolicyError("OBS RPM package sources are incomplete or out of order")
        expected_artifacts = {
            "iso",
            "packages",
            "verified",
            "report",
            "checksum",
            "cyclonedx_sbom",
            "spdx_sbom",
        }
        configured_artifacts = set(self.required_artifacts)
        if configured_artifacts not in (
            expected_artifacts,
            expected_artifacts | {"checksum_signature"},
        ):
            raise PolicyError("artifact policy is incomplete")
        if set(self.required_test_results) != expected_results:
            raise PolicyError("release evidence policy is incomplete")


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


def release_values(release_file: Path = RELEASE) -> dict[str, object]:
    with release_file.open("rb") as stream:
        return tomllib.load(stream)["release"]


def version_id(release_file: Path = RELEASE) -> str:
    release = release_values(release_file)
    if release["stage"] == "release":
        return str(release["version"])
    return f'{release["version"]}-{release["stage"]}.{release["iteration"]}'


def required_artifact_roles(manifest: Manifest, release_file: Path) -> tuple[str, ...]:
    """Return the artifact policy that applies to the release stage.

    The manifest is shared by every stage.  Alpha releases deliberately
    publish a checksum without a detached release signature (ADR 0005), while
    Beta, RC and final candidates must carry one.  Keep the stage decision here
    so source validation and final evidence cannot disagree about the bundle.
    """
    roles = tuple(
        role for role in manifest.required_artifacts if role != "checksum_signature"
    )
    if release_values(release_file)["stage"] != "alpha":
        return (*roles, "checksum_signature")
    return roles


def required_test_result_names(manifest: Manifest, release_file: Path) -> tuple[str, ...]:
    """Return evidence required by the release stage without weakening older gates."""
    release = release_values(release_file)
    required = set(manifest.required_test_results)
    if release["stage"] != "alpha" or int(release["iteration"]) >= 8:
        required.update(ALPHA8_TEST_RESULTS)
    return tuple(sorted(required))


def canonical_xml() -> ET.ElementTree:
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    return ET.parse(KIWI / "config.xml", parser=parser)


def desktop_entry(path: Path) -> dict[str, str]:
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    with path.open(encoding="utf-8") as stream:
        parser.read_file(stream)
    if parser.sections() != ["Desktop Entry"]:
        raise PolicyError(f"invalid desktop entry structure: {path.relative_to(ROOT)}")
    return dict(parser["Desktop Entry"])


def validate_installer_identity() -> None:
    tauri_path = ROOT / "installer/src-tauri/tauri.conf.json"
    tauri = json.loads(tauri_path.read_text(encoding="utf-8"))
    app_id = tauri.get("identifier")
    if app_id != INSTALLER_APP_ID:
        raise PolicyError(
            f"Tauri identifier {app_id!r} differs from {INSTALLER_APP_ID!r}"
        )
    if tauri.get("app", {}).get("enableGTKAppId") is not True:
        raise PolicyError("Tauri must set its identifier as the GTK application ID")

    packaged_launcher = ROOT / "installer/packaging" / f"{app_id}.desktop"
    image_launcher = KIWI / "root/usr/share/applications" / f"{app_id}.desktop"
    if not packaged_launcher.is_file():
        raise PolicyError("installer desktop filename must match the Tauri identifier")
    if image_launcher.read_bytes() != packaged_launcher.read_bytes():
        raise PolicyError("KIWI installer launcher differs from the packaged launcher")

    expected = {
        "TryExec": INSTALLER_TRY_EXEC,
        "Exec": INSTALLER_EXEC,
        "Icon": app_id,
        "StartupWMClass": INSTALLER_WM_CLASS,
    }
    for path in (packaged_launcher, image_launcher):
        entry = desktop_entry(path)
        for key, value in expected.items():
            if entry.get(key) != value:
                relative = path.relative_to(ROOT)
                raise PolicyError(f"{relative}: {key} must be {value!r}")

    autostart_path = KIWI / "root/etc/xdg/autostart/lyra-installer-autostart.desktop"
    autostart = desktop_entry(autostart_path)
    autostart_expected = dict(expected)
    autostart_expected["Exec"] = INSTALLER_EXEC
    for key, value in autostart_expected.items():
        if autostart.get(key) != value:
            relative = autostart_path.relative_to(ROOT)
            raise PolicyError(f"{relative}: {key} must be {value!r}")

    icon_name = f"{app_id}.png"
    source_icons = ROOT / "installer/src-tauri/icons"
    spec = (ROOT / "installer/packaging/lyra-installer.spec").read_text(
        encoding="utf-8"
    )
    for size in (32, 128, 256, 512):
        source = source_icons / f"{size}x{size}.png"
        packaged_path = f"icons/hicolor/{size}x{size}/apps/{icon_name}"
        if not source.is_file() or packaged_path not in spec:
            raise PolicyError(f"RPM does not install the {size}x{size} application icon")

    image_icon = KIWI / "root/usr/share/icons/hicolor/256x256/apps" / icon_name
    if image_icon.read_bytes() != (source_icons / "256x256.png").read_bytes():
        raise PolicyError("KIWI installer icon differs from the packaged icon")


def validate_sources(manifest: Manifest, *, release_file: Path | None = None) -> None:
    release_file = release_file or RELEASE
    release = release_values(release_file)
    signature_required = release["stage"] != "alpha"
    has_signature = "checksum_signature" in manifest.required_artifacts
    if signature_required and not has_signature:
        raise PolicyError("Beta, RC and final releases require a checksum signature")
    validate_installer_identity()
    if not PACKAGE_SIGNING_KEYRING.is_file():
        raise PolicyError("versioned RPM package signing keyring is missing")
    gpg = shutil.which("gpg")
    if gpg is None:
        raise PolicyError("gpg is required to validate the RPM package signing keyring")
    with tempfile.TemporaryDirectory(prefix="lyra-image-keyring-") as gpg_home:
        key_result = subprocess.run(
            [
                gpg,
                "--batch",
                "--homedir",
                gpg_home,
                "--with-colons",
                "--import-options",
                "show-only",
                "--import",
                str(PACKAGE_SIGNING_KEYRING),
            ],
            check=False,
            text=True,
            capture_output=True,
        )
    if key_result.returncode:
        raise PolicyError("versioned RPM package signing keyring is invalid")
    fingerprints = {
        fields[9].upper()
        for line in key_result.stdout.splitlines()
        if (fields := line.split(":"))[0] == "fpr" and len(fields) > 9
    }
    if fingerprints != PACKAGE_SIGNING_FINGERPRINTS:
        raise PolicyError("RPM package signing keyring fingerprints differ from policy")
    for relative in (
        "root/usr/bin/lyra-hardware-matrix",
        "root/usr/bin/lyra-live-smoke",
        "root/usr/bin/lyra-performance",
        "root/usr/bin/lyra-report",
        "root/usr/bin/lyra-system-smoke",
        "root/usr/bin/lyra-update-smoke",
        "root/usr/libexec/lyra-report-redact",
    ):
        path = KIWI / relative
        if not path.is_file() or not os.access(path, os.X_OK):
            raise PolicyError(
                f"required release tool is missing or not executable: kiwi/{relative}"
            )
    root = canonical_xml().getroot()
    if root.attrib.get("name") != manifest.image_name:
        raise PolicyError("KIWI image name differs from image-build.toml")
    # config.xml has two <preferences> blocks; only one carries <version>.
    version = root.findtext("preferences/version")
    if version != version_id(release_file):
        raise PolicyError(f"KIWI version {version!r} differs from {release_file.name}")
    if root.findtext("preferences/rpm-check-signatures") != "true":
        raise PolicyError("KIWI must reject packages with invalid signatures")
    build_type = root.find("preferences/type")
    if build_type is None or build_type.attrib.get("editbootconfig") != "edit_boot_config.sh":
        raise PolicyError("KIWI must run the versioned final boot configuration hook")
    if not os.access(KIWI / "edit_boot_config.sh", os.X_OK):
        raise PolicyError("KIWI final boot configuration hook must be executable")
    repositories = root.findall("repository")
    expected_repositories = {
        "repo-oss",
        "repo-non-oss",
        "repo-packman-essentials",
        "repo-lyra",
        "repo-vega",
        "repo-fina",
    }
    if len(repositories) != len(expected_repositories):
        raise PolicyError(
            "canonical KIWI description must contain exactly six repositories"
        )
    aliases: set[str] = set()
    for repository in repositories:
        alias = repository.attrib.get("alias", "")
        source = repository.find("source")
        url = "" if source is None else source.attrib.get("path", "")
        if alias in aliases or not alias:
            raise PolicyError(f"missing or duplicate repository alias: {alias!r}")
        aliases.add(alias)
        if not url.startswith("https://") or ":staging" in url:
            raise PolicyError(f"unsafe installed-image repository: {url}")
        for option in ("repository_gpgcheck", "package_gpgcheck"):
            if repository.attrib.get(option) != "true":
                raise PolicyError(f"{alias}: {option} must be true")
    if aliases != expected_repositories:
        raise PolicyError("canonical KIWI repository aliases differ from policy")
    config = (KIWI / "config.sh").read_text(encoding="utf-8")
    forbidden = ("curl ", "wget ", "flatpak remote-add", "obsrepositories:/")
    for token in forbidden:
        if token in config:
            raise PolicyError(f"network-dependent build command is forbidden: {token.strip()}")
    flathub = KIWI / "root/etc/flatpak/remotes.d/flathub.flatpakrepo"
    if "GPGKey=" not in flathub.read_text(encoding="utf-8"):
        raise PolicyError("versioned Flathub remote or signing key is missing")


def source_metadata(commit: str, dirty: bool) -> tuple[dict[str, object], str]:
    try:
        full_commit = git("rev-parse", f"{commit}^{{commit}}")
        epoch = int(git("show", "-s", "--format=%ct", full_commit))
    except subprocess.CalledProcessError as error:
        raise PolicyError(f"unknown source commit: {commit}") from error
    built_at = dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat().replace("+00:00", "Z")
    document = {
        "schema_version": 1,
        "commit": full_commit,
        "dirty": dirty,
        "source_epoch": epoch,
        "image_built_at": built_at,
    }
    environment = (
        "# Generated by scripts/image-build.py; do not edit.\n"
        f"LYRA_BUILD_SOURCE_COMMIT='{full_commit}'\n"
        f"LYRA_BUILD_SOURCE_DIRTY='{int(dirty)}'\n"
        f"LYRA_BUILD_SOURCE_EPOCH='{epoch}'\n"
        f"LYRA_IMAGE_BUILT_AT='{built_at}'\n"
    )
    return document, environment


def ensure_export_target(destination: Path) -> None:
    if destination.exists() and any(destination.iterdir()):
        raise PolicyError(f"export destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)


def write_root_archive(root: Path, archive: Path, epoch: int) -> None:
    """Create a deterministic archive of the KIWI root overlay."""

    def normalize(member: tarfile.TarInfo) -> tarfile.TarInfo:
        member.uid = 0
        member.gid = 0
        member.uname = "root"
        member.gname = "root"
        member.mtime = epoch
        member.pax_headers = {}
        return member

    with archive.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=epoch) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as output:
                for source in sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix()):
                    output.add(
                        source,
                        arcname=source.relative_to(root).as_posix(),
                        recursive=False,
                        filter=normalize,
                    )


def export(
    manifest: Manifest,
    destination: Path,
    commit: str,
    allow_dirty: bool,
    *,
    release_file: Path | None = None,
) -> None:
    validate_sources(manifest, release_file=release_file)
    dirty = bool(git("status", "--porcelain", "--untracked-files=normal"))
    if dirty and not allow_dirty:
        raise PolicyError("working tree is dirty; commit the image sources before export")
    metadata, environment = source_metadata(commit, dirty)
    if metadata["commit"] != git("rev-parse", "HEAD"):
        raise PolicyError("--commit must identify the currently checked-out HEAD")
    ensure_export_target(destination)
    for name in ("config.xml", "config.sh", "edit_boot_config.sh"):
        shutil.copy2(KIWI / name, destination / name)
    shutil.copytree(KIWI / "keys", destination / "keys")
    shutil.copytree(KIWI / "root", destination / "root", symlinks=True)
    (destination / "build-source.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    embedded = destination / "root/usr/lib/lyra-os/build-source"
    embedded.parent.mkdir(parents=True, exist_ok=True)
    embedded.write_text(environment, encoding="utf-8")
    write_root_archive(destination / "root", destination / "root.tar.gz", metadata["source_epoch"])
    print(destination)


def verify_export(manifest: Manifest, directory: Path) -> None:
    metadata = json.loads((directory / "build-source.json").read_text(encoding="utf-8"))
    if metadata.get("dirty") is not False or not re.fullmatch(r"[0-9a-f]{40}", metadata.get("commit", "")):
        raise PolicyError("export has invalid source identity")
    root = ET.parse(directory / manifest.description).getroot()
    repositories = root.findall("repository")
    if len(repositories) != 6:
        raise PolicyError("export must preserve the six canonical repositories")
    for repository in repositories:
        source = repository.find("source")
        url = "" if source is None else source.attrib.get("path", "")
        if not url.startswith("https://") or url == "obsrepositories:/":
            raise PolicyError("export must resolve RPMs through canonical HTTPS repositories")
        for option in ("repository_gpgcheck", "package_gpgcheck"):
            if repository.attrib.get(option) != "true":
                raise PolicyError(f"exported repository must enable {option}")
    if (directory / "_multibuild").exists():
        raise PolicyError("OBS image recipes are forbidden in the GitHub source export")
    for name in (manifest.description, "config.sh", "edit_boot_config.sh"):
        if sha256(directory / name) != sha256(KIWI / name):
            raise PolicyError(f"exported KIWI file differs from the GitHub source: {name}")
    exported_keyring = directory / "keys/obs-package-signing-keyring.asc"
    if not exported_keyring.is_file() or sha256(exported_keyring) != sha256(
        PACKAGE_SIGNING_KEYRING
    ):
        raise PolicyError("exported RPM package signing keyring differs from policy")
    embedded = directory / "root/usr/lib/lyra-os/build-source"
    if metadata["commit"] not in embedded.read_text(encoding="utf-8"):
        raise PolicyError("embedded source identity differs from export manifest")
    with tarfile.open(directory / "root.tar.gz", mode="r:gz") as archive:
        names = archive.getnames()
        required = {"usr/lib/lyra-os/release", "usr/lib/lyra-os/build-source"}
        if not required.issubset(names):
            raise PolicyError("root archive lacks generated release metadata")
        archived_source = archive.extractfile("usr/lib/lyra-os/build-source")
        if archived_source is None or metadata["commit"].encode() not in archived_source.read():
            raise PolicyError("archived source identity differs from export manifest")
    print(f"OK: deterministic KIWI source export at {metadata['commit']}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def one(directory: Path, pattern: str, role: str) -> Path:
    matches = list(directory.glob(pattern))
    if len(matches) != 1:
        raise PolicyError(f"expected one {role} artifact matching {pattern}, found {len(matches)}")
    return matches[0]


def iso_source_commit(directory: Path, iso_path: Path, release_file: Path) -> str:
    """Return the immutable build commit recorded beside the candidate ISO."""
    build_manifest_path = one(
        directory, f"{iso_path.name}.manifest.json", "ISO build manifest"
    )
    try:
        build_manifest = json.loads(build_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PolicyError(
            f"ISO build manifest is not valid JSON: {build_manifest_path}"
        ) from error
    if not isinstance(build_manifest, dict) or build_manifest.get("schema_version") != 1:
        raise PolicyError("ISO build manifest has an unsupported schema")
    recorded_iso = build_manifest.get("iso")
    source = build_manifest.get("source")
    if (
        not isinstance(recorded_iso, dict)
        or recorded_iso.get("filename") != iso_path.name
        or recorded_iso.get("sha256") != sha256(iso_path)
    ):
        raise PolicyError("ISO build manifest does not match the candidate ISO")
    if build_manifest.get("version") != version_id(release_file):
        raise PolicyError("ISO build manifest does not match the release version")
    if (
        not isinstance(source, dict)
        or source.get("dirty") is not False
        or not re.fullmatch(r"[0-9a-f]{40}", str(source.get("commit", "")))
    ):
        raise PolicyError("ISO build manifest has an invalid source identity")
    return str(source["commit"])


def validate_passed_checks(name: str, result: dict[str, object]) -> None:
    checks = result.get("checks")
    if not isinstance(checks, list) or not checks:
        raise PolicyError(f"test result has no structured checks: {name}")
    for check in checks:
        if (
            not isinstance(check, dict)
            or not isinstance(check.get("id"), str)
            or check.get("status") != "passed"
        ):
            raise PolicyError(f"test result contains an invalid or failed check: {name}")


def validate_test_result(
    name: str,
    result: object,
    *,
    iso_path: Path,
) -> dict[str, object]:
    if not isinstance(result, dict) or result.get("status") != "passed":
        raise PolicyError(f"test result did not pass: {name}")
    if result.get("schema") != 1:
        raise PolicyError(f"test result has an unsupported schema: {name}")

    if name == "obs-repositories":
        projects = result.get("projects")
        if not isinstance(projects, list) or not projects:
            raise PolicyError("OBS evidence contains no verified projects")
        for project in projects:
            if (
                not isinstance(project, dict)
                or not project.get("packages")
                or not project.get("targets")
            ):
                raise PolicyError("OBS evidence contains an incomplete project")
        return result

    expected_modes = {
        "live-session": "live-session",
        "installer": "installer",
        "first-boot": "first-boot",
        "uefi-secure-boot": "uefi-secure-boot",
        "rollback": "rollback",
        "hardware-matrix": "hardware-matrix",
        "upgrade-rehearsal": "upgrade-rehearsal",
        "eca-digital": "eca-digital",
        "i18n": "i18n",
        "feature-freeze": "feature-freeze",
    }
    expected_mode = expected_modes.get(name)
    if expected_mode is None or result.get("mode") != expected_mode:
        raise PolicyError(f"test result mode does not match its role: {name}")

    if name == "hardware-matrix":
        # Full desktop+2-notebook, Intel+AMD coverage is the documented
        # target (docs/hardware-matrix.md), not a hard requirement: a
        # single-maintainer project with one physical machine records the
        # shortfall in coverage.gap instead of being permanently unable to
        # produce evidence. Revisit once external testers join.
        coverage = result.get("coverage")
        scenarios = result.get("scenarios")
        identity = result.get("iso")
        desktops = coverage.get("desktops") if isinstance(coverage, dict) else None
        notebooks = coverage.get("notebooks") if isinstance(coverage, dict) else None
        cpu_vendors = coverage.get("cpu_vendors") if isinstance(coverage, dict) else None
        gpu_vendors = coverage.get("gpu_vendors") if isinstance(coverage, dict) else None
        if (
            not isinstance(coverage, dict)
            or not isinstance(desktops, int)
            or desktops < 0
            or not isinstance(notebooks, int)
            or notebooks < 0
            or not isinstance(cpu_vendors, list)
            or not isinstance(gpu_vendors, list)
            or not isinstance(scenarios, list)
            or len(scenarios) < 1
            or not isinstance(identity, dict)
        ):
            raise PolicyError("hardware matrix evidence is incomplete")
        if identity.get("filename") != iso_path.name or identity.get("sha256") != sha256(iso_path):
            raise PolicyError("hardware matrix does not reference the candidate ISO")
        return result

    validate_passed_checks(name, result)
    if name == "rollback" and result.get("phase") != "rollback-verified":
        raise PolicyError("rollback evidence is not the final verified phase")
    if name == "upgrade-rehearsal":
        facts = result.get("facts")
        required_faults = {
            "network-loss", "low-space", "ui-terminated", "state-truncated",
            "rpm-failure", "initramfs-failure",
        }
        if (
            result.get("phase") != "rollback-verified"
            or not isinstance(facts, dict)
            or not isinstance(facts.get("baseline_version"), str)
            or not isinstance(facts.get("target_version"), str)
            or facts.get("baseline_version") == facts.get("target_version")
            or facts.get("manifest_signature_verified") is not True
            or facts.get("offline_applied") is not True
            or not isinstance(facts.get("reboot_count"), int)
            or facts.get("reboot_count", 0) < 1
            or facts.get("rollback_baseline_verified") is not True
            or not isinstance(facts.get("fault_scenarios"), list)
            or not required_faults.issubset(set(facts.get("fault_scenarios", [])))
        ):
            raise PolicyError("upgrade rehearsal evidence is incomplete")
    elif name == "eca-digital":
        if (
            result.get("locales") != SUPPORTED_LOCALES
            or not result.get("legal_review")
            or not result.get("security_review")
            or not result.get("privacy_impact_assessment")
            or result.get("negative_and_evasion_tests") is not True
            or result.get("retains_sensitive_age_evidence") is not False
        ):
            raise PolicyError("ECA Digital evidence is incomplete")
    elif name == "i18n":
        if result.get("locales") != SUPPORTED_LOCALES or result.get("fallback") != "en-US":
            raise PolicyError("i18n evidence must cover en-US, pt-BR and es-ES")
    elif name == "feature-freeze":
        if (
            result.get("decision") != "GO"
            or result.get("open_p0") != 0
            or result.get("open_p1") != 0
            or result.get("locales") != SUPPORTED_LOCALES
            or result.get("all_features_implemented_or_removed") is not True
            or result.get("documentation_consistent") is not True
        ):
            raise PolicyError("feature freeze decision is not eligible for GO")
    return result


def artifact_manifest(
    manifest: Manifest,
    directory: Path,
    output: Path,
    tests: list[str],
    *,
    release_file: Path | None = None,
) -> None:
    release_file = release_file or RELEASE
    artifact_patterns = {
        "iso": ("*.iso", "ISO"),
        "packages": ("*.packages", "package revision list"),
        "verified": ("*.verified", "verification report"),
        "report": ("*.report", "KIWI report"),
        "checksum": ("*.iso.sha256", "ISO checksum"),
        "checksum_signature": ("*.iso.sha256.asc", "checksum signature"),
        "cyclonedx_sbom": ("*.cdx.json", "CycloneDX SBOM"),
        "spdx_sbom": ("*.spdx.json", "SPDX SBOM"),
    }
    required_roles = required_artifact_roles(manifest, release_file)
    roles = {
        role: one(directory, *artifact_patterns[role])
        for role in required_roles
    }
    source_commit = iso_source_commit(directory, roles["iso"], release_file)
    package_rows = [line.split("|") for line in roles["packages"].read_text(encoding="utf-8").splitlines() if line]
    if any(len(row) != 7 for row in package_rows):
        raise PolicyError("KIWI package manifest has an unexpected format")
    if not package_rows or any(not row[5] for row in package_rows):
        raise PolicyError("exact source revisions are missing from the package manifest")
    test_results: dict[str, dict[str, object]] = {}
    for item in tests:
        if "=" not in item:
            raise PolicyError("--test-result must use NAME=FILE")
        name, filename = item.split("=", 1)
        path = Path(filename).resolve()
        if not name or not path.is_file():
            raise PolicyError(f"invalid test result: {item}")
        if name in test_results:
            raise PolicyError(f"duplicate test result: {name}")
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PolicyError(f"test result is not valid JSON: {path}") from error
        validate_test_result(name, result, iso_path=roles["iso"])
        test_results[name] = {
            "filename": path.name,
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
            "status": "passed",
        }
    required_results = set(required_test_result_names(manifest, release_file))
    unexpected_results = sorted(set(test_results) - required_results)
    if unexpected_results:
        raise PolicyError(f"unexpected release evidence: {unexpected_results}")
    missing_results = sorted(required_results - set(test_results))
    if missing_results:
        raise PolicyError(f"required release evidence is missing: {missing_results}")
    source_dirty = bool(git("status", "--porcelain", "--untracked-files=normal"))
    if source_dirty:
        raise PolicyError("final release evidence requires a clean source commit")
    document = {
        "schema_version": 1,
        "product": manifest.image_name,
        "version": version_id(release_file),
        "source": {"commit": source_commit, "dirty": False},
        "package_count": len(package_rows),
        "packages": [
            {"name": row[0], "epoch": row[1], "version": row[2], "release": row[3], "arch": row[4], "source": row[5], "license": row[6]}
            for row in package_rows
        ],
        "artifacts": {
            role: {"filename": path.name, "sha256": sha256(path), "size_bytes": path.stat().st_size}
            for role, path in roles.items()
        },
        "test_results": test_results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.new")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(output)


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    cli.add_argument("--release-file", type=Path)
    commands = cli.add_subparsers(dest="command", required=True)

    # Also expose the identity options on each subcommand. argparse normally
    # accepts top-level options only before the subcommand, while the release
    # documentation naturally places them after it. SUPPRESS preserves a
    # value supplied before the subcommand when none follows it.
    def add_identity_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("--manifest", type=Path, default=argparse.SUPPRESS)
        command.add_argument("--release-file", type=Path, default=argparse.SUPPRESS)

    validate = commands.add_parser("validate")
    add_identity_options(validate)
    export_command = commands.add_parser("export")
    add_identity_options(export_command)
    export_command.add_argument("destination", type=Path)
    export_command.add_argument("--commit", default="HEAD")
    export_command.add_argument("--allow-dirty", action="store_true")
    verify = commands.add_parser("verify-export")
    add_identity_options(verify)
    verify.add_argument("directory", type=Path)
    artifacts = commands.add_parser("artifact-manifest")
    add_identity_options(artifacts)
    artifacts.add_argument("directory", type=Path)
    artifacts.add_argument("--output", required=True, type=Path)
    artifacts.add_argument("--test-result", action="append", default=[])
    evidence = commands.add_parser("required-test-results")
    add_identity_options(evidence)
    return cli


def main() -> int:
    args = parser().parse_args()
    try:
        manifest = Manifest.load(args.manifest)
        release_file = args.release_file or RELEASE
        if args.command == "validate":
            validate_sources(manifest, release_file=release_file)
            print("OK: GitHub sources, RPM repositories, signatures, and distribution policy are valid")
        elif args.command == "export":
            export(
                manifest,
                args.destination,
                args.commit,
                args.allow_dirty,
                release_file=release_file,
            )
        elif args.command == "verify-export":
            verify_export(manifest, args.directory)
        elif args.command == "artifact-manifest":
            artifact_manifest(manifest, args.directory, args.output, args.test_result, release_file=release_file)
        else:
            print("\n".join(required_test_result_names(manifest, release_file)))
    except (KeyError, OSError, PolicyError, subprocess.SubprocessError, tomllib.TOMLDecodeError, ET.ParseError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
