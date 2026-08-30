#!/usr/bin/env python3
"""Generate the release evidence artifacts a KIWI build does not produce.

`kiwi-ng system build` only writes `.iso`, `.packages`, `.verified` and
`.changes`. `scripts/image-build.py artifact-manifest` additionally requires
`.iso.sha256`, `.iso.sha256.asc`, `.cdx.json`, `.spdx.json` and `.report` to
exist next to those files (see `docs/image-builds.md`). This script builds
the ones that can be derived deterministically from the ISO and the KIWI
package manifest: checksum, CycloneDX SBOM, SPDX SBOM and a build report.

The checksum *signature* (`.iso.sha256.asc`) is deliberately not produced
here - it must be a real detached GPG signature from the release
coordinator's own key, which this script has no business holding or
prompting for. Sign the generated `.iso.sha256` file directly:

    gpg --detach-sign --armor -o <iso>.sha256.asc <iso>.sha256
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
import tomllib
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release.toml"
SBOM_NAMESPACE = uuid.UUID("b3f6b6d0-2f1a-4a35-9c5a-8f5f6c9a2b10")


class ArtifactError(RuntimeError):
    """A precondition needed to generate an artifact was not met."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


def commit_identity(commit: str) -> tuple[str, int, str]:
    full_commit = git("rev-parse", f"{commit}^{{commit}}")
    epoch = int(git("show", "-s", "--format=%ct", full_commit))
    built_at = dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat().replace("+00:00", "Z")
    return full_commit, epoch, built_at


def load_packages(path: Path) -> list[dict[str, str]]:
    fields = ("name", "epoch", "version", "release", "arch", "source", "license")
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line:
            continue
        parts = line.split("|")
        if len(parts) != 7:
            raise ArtifactError(f"{path}:{line_number}: expected 7 pipe-separated fields, found {len(parts)}")
        rows.append(dict(zip(fields, parts)))
    if not rows:
        raise ArtifactError(f"{path}: no packages found")
    return rows


def purl(package: dict[str, str]) -> str:
    version = package["version"] if package["release"] in ("", "(none)") else f'{package["version"]}-{package["release"]}'
    return f'pkg:rpm/opensuse/{package["name"]}@{version}?arch={package["arch"]}'


def write_checksum(iso: Path, output_dir: Path) -> Path:
    path = output_dir / f"{iso.name}.sha256"
    path.write_text(f"{sha256(iso)}  {iso.name}\n", encoding="utf-8")
    return path


def write_cyclonedx_sbom(
    *, iso: Path, packages: list[dict[str, str]], version: str, commit: str, built_at: str, output_dir: Path
) -> Path:
    serial = uuid.uuid5(SBOM_NAMESPACE, f"cyclonedx:{commit}:{iso.name}")
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "timestamp": built_at,
            "component": {
                "type": "operating-system",
                "bom-ref": "lyra-os",
                "name": "lyra-os",
                "version": version,
                "purl": f"pkg:generic/lyra-os@{version}",
            },
        },
        "components": [
            {
                "type": "library",
                "bom-ref": f'rpm:{package["name"]}',
                "name": package["name"],
                "version": (
                    package["version"]
                    if package["release"] in ("", "(none)")
                    else f'{package["version"]}-{package["release"]}'
                ),
                "purl": purl(package),
                "licenses": [{"license": {"name": package["license"]}}] if package["license"] not in ("", "(none)") else [],
                "properties": [{"name": "lyra:obs-source", "value": package["source"]}],
            }
            for package in packages
        ],
    }
    path = output_dir / f"{iso.stem}.cdx.json"
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_spdx_sbom(
    *, iso: Path, packages: list[dict[str, str]], version: str, commit: str, built_at: str, output_dir: Path
) -> Path:
    document_id = f"lyra-os-{version}-{commit[:12]}"
    package_refs = [f'SPDXRef-Package-{index}-{package["name"]}' for index, package in enumerate(packages)]
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": document_id,
        "documentNamespace": f"https://github.com/lyra-os-linux/lyraos-desktop/spdx/{document_id}",
        "creationInfo": {
            "created": built_at,
            "creators": ["Tool: lyra-release-artifacts", "Organization: Lyra OS Project"],
        },
        "packages": [
            {
                "SPDXID": "SPDXRef-Package-lyra-os",
                "name": "lyra-os",
                "versionInfo": version,
                "downloadLocation": "NOASSERTION",
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "copyrightText": "NOASSERTION",
            },
            *(
                {
                    "SPDXID": ref,
                    "name": package["name"],
                    "versionInfo": (
                        package["version"]
                        if package["release"] in ("", "(none)")
                        else f'{package["version"]}-{package["release"]}'
                    ),
                    "downloadLocation": package["source"] if package["source"] else "NOASSERTION",
                    "licenseConcluded": "NOASSERTION",
                    "licenseDeclared": package["license"] if package["license"] not in ("", "(none)") else "NOASSERTION",
                    "copyrightText": "NOASSERTION",
                    "externalRefs": [
                        {
                            "referenceCategory": "PACKAGE-MANAGER",
                            "referenceType": "purl",
                            "referenceLocator": purl(package),
                        }
                    ],
                }
                for ref, package in zip(package_refs, packages)
            ),
        ],
        "relationships": [
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": "SPDXRef-Package-lyra-os",
            },
            *(
                {
                    "spdxElementId": "SPDXRef-Package-lyra-os",
                    "relationshipType": "CONTAINS",
                    "relatedSpdxElement": ref,
                }
                for ref in package_refs
            ),
        ],
    }
    path = output_dir / f"{iso.stem}.spdx.json"
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_report(
    *,
    iso: Path,
    packages_path: Path,
    packages: list[dict[str, str]],
    verified_path: Path,
    version: str,
    commit: str,
    epoch: int,
    built_at: str,
    output_dir: Path,
    release_file: Path = RELEASE,
    product: str = "Lyra OS",
) -> Path:
    release = release_values(release_file)
    document = {
        "schema_version": 1,
        "product": product,
        "version": version,
        "codename": release.get("codename"),
        "source": {"commit": commit, "commit_epoch": epoch, "built_at": built_at},
        "iso": {"filename": iso.name, "size_bytes": iso.stat().st_size, "sha256": sha256(iso)},
        "packages": {"count": len(packages), "filename": packages_path.name, "sha256": sha256(packages_path)},
        "verified": {"filename": verified_path.name, "sha256": sha256(verified_path)},
        "generated_by": "scripts/release-artifacts.py",
    }
    path = output_dir / f"{iso.stem}.report"
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def generate(
    *,
    iso: Path,
    packages_path: Path,
    verified_path: Path,
    output_dir: Path,
    commit: str,
    release_file: Path = RELEASE,
    product: str = "Lyra OS",
) -> list[Path]:
    if not iso.is_file():
        raise ArtifactError(f"ISO does not exist: {iso}")
    if not packages_path.is_file():
        raise ArtifactError(f"package manifest does not exist: {packages_path}")
    if not verified_path.is_file():
        raise ArtifactError(f"verification report does not exist: {verified_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    packages = load_packages(packages_path)
    version = version_id(release_file)
    full_commit, epoch, built_at = commit_identity(commit)
    return [
        write_checksum(iso, output_dir),
        write_cyclonedx_sbom(
            iso=iso, packages=packages, version=version, commit=full_commit, built_at=built_at, output_dir=output_dir
        ),
        write_spdx_sbom(
            iso=iso, packages=packages, version=version, commit=full_commit, built_at=built_at, output_dir=output_dir
        ),
        write_report(
            iso=iso,
            packages_path=packages_path,
            packages=packages,
            verified_path=verified_path,
            version=version,
            commit=full_commit,
            epoch=epoch,
            built_at=built_at,
            output_dir=output_dir,
            release_file=release_file,
            product=product,
        ),
    ]


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = cli.add_subparsers(dest="command", required=True)
    generate_command = commands.add_parser("generate", help="write checksum, SBOMs and report next to a built ISO")
    generate_command.add_argument("--iso", required=True, type=Path)
    generate_command.add_argument("--packages", required=True, type=Path)
    generate_command.add_argument("--verified", required=True, type=Path)
    generate_command.add_argument("--output-dir", required=True, type=Path)
    generate_command.add_argument("--commit", default="HEAD")
    generate_command.add_argument(
        "--release-file",
        type=Path,
        default=RELEASE,
        help="release metadata TOML file (default: release.toml)",
    )
    generate_command.add_argument(
        "--product",
        default="Lyra OS",
        help='report "product" field',
    )
    return cli


def main() -> int:
    args = parser().parse_args()
    try:
        paths = generate(
            iso=args.iso.resolve(),
            packages_path=args.packages.resolve(),
            verified_path=args.verified.resolve(),
            output_dir=args.output_dir.resolve(),
            commit=args.commit,
            release_file=args.release_file.resolve(),
            product=args.product,
        )
    except (ArtifactError, OSError, subprocess.CalledProcessError, tomllib.TOMLDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    for path in paths:
        print(path)
    print(
        "Sign the checksum yourself, this tool does not hold release keys:\n"
        f"  gpg --detach-sign --armor -o {paths[0]}.asc {paths[0]}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
