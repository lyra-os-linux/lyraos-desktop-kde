from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("lyra_release_artifacts", ROOT / "scripts/release-artifacts.py")
assert SPEC and SPEC.loader
release_artifacts = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release_artifacts
SPEC.loader.exec_module(release_artifacts)


class ReleaseArtifactsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.iso = self.root / "lyra-os-1.0-beta.2-x86_64.iso"
        self.iso.write_bytes(b"fake iso payload")
        self.packages = self.root / "lyra-os-1.0-beta.2.packages"
        self.packages.write_text(
            "fina|(none)|0.4.0|12.1|x86_64|obs://build.opensuse.org/"
            "home:rodrigosbrito:fina/repo/revision-fina|MIT\n"
            "Leap-release|(none)|16.0+leap|lp160.263.1|x86_64|obs://build.opensuse.org/"
            "openSUSE:Leap:16.0/standard/revision-leap|MIT\n",
            encoding="utf-8",
        )
        self.verified = self.root / "lyra-os-1.0-beta.2.verified"
        self.verified.write_text("verified\n", encoding="utf-8")
        self.output_dir = self.root / "out"

    def generate(self) -> list[Path]:
        return release_artifacts.generate(
            iso=self.iso,
            packages_path=self.packages,
            verified_path=self.verified,
            output_dir=self.output_dir,
            commit="HEAD",
        )

    def test_generates_exactly_the_four_missing_roles(self) -> None:
        paths = self.generate()
        names = {path.name for path in paths}
        self.assertEqual(
            names,
            {
                f"{self.iso.name}.sha256",
                f"{self.iso.stem}.cdx.json",
                f"{self.iso.stem}.spdx.json",
                f"{self.iso.stem}.report",
            },
        )

    def test_checksum_matches_the_iso_and_sha256sum_format(self) -> None:
        self.generate()
        checksum_path = self.output_dir / f"{self.iso.name}.sha256"
        digest, _, filename = checksum_path.read_text(encoding="utf-8").strip().partition("  ")
        self.assertEqual(digest, release_artifacts.sha256(self.iso))
        self.assertEqual(filename, self.iso.name)

    def test_cyclonedx_sbom_lists_every_package(self) -> None:
        self.generate()
        document = json.loads((self.output_dir / f"{self.iso.stem}.cdx.json").read_text(encoding="utf-8"))
        self.assertEqual(document["bomFormat"], "CycloneDX")
        names = {component["name"] for component in document["components"]}
        self.assertEqual(names, {"fina", "Leap-release"})
        fina = next(c for c in document["components"] if c["name"] == "fina")
        self.assertEqual(fina["purl"], "pkg:rpm/opensuse/fina@0.4.0-12.1?arch=x86_64")

    def test_spdx_sbom_describes_a_root_package_containing_every_rpm(self) -> None:
        self.generate()
        document = json.loads((self.output_dir / f"{self.iso.stem}.spdx.json").read_text(encoding="utf-8"))
        self.assertEqual(document["spdxVersion"], "SPDX-2.3")
        self.assertEqual(len(document["packages"]), 3)  # root + 2 RPMs
        describes = [r for r in document["relationships"] if r["relationshipType"] == "DESCRIBES"]
        self.assertEqual(describes[0]["relatedSpdxElement"], "SPDXRef-Package-lyra-os")
        contains = [r for r in document["relationships"] if r["relationshipType"] == "CONTAINS"]
        self.assertEqual(len(contains), 2)

    def test_report_is_schema_1_and_ties_artifacts_to_the_source_commit(self) -> None:
        self.generate()
        document = json.loads((self.output_dir / f"{self.iso.stem}.report").read_text(encoding="utf-8"))
        self.assertEqual(document["schema_version"], 1)
        self.assertEqual(document["iso"]["sha256"], release_artifacts.sha256(self.iso))
        self.assertEqual(document["packages"]["count"], 2)
        self.assertRegex(document["source"]["commit"], r"^[0-9a-f]{40}$")

    def test_rejects_a_malformed_package_line(self) -> None:
        self.packages.write_text("not-enough-fields|x86_64\n", encoding="utf-8")
        with self.assertRaisesRegex(release_artifacts.ArtifactError, "7 pipe-separated fields"):
            self.generate()

    def test_rejects_a_missing_iso(self) -> None:
        self.iso.unlink()
        with self.assertRaisesRegex(release_artifacts.ArtifactError, "ISO does not exist"):
            self.generate()

    def test_release_file_and_product_are_overridable(self) -> None:
        release_file = self.root / "release-alternate.toml"
        release_file.write_text(
            'schema = 1\n\n[release]\nversion = "1.0"\nbase_distribution = "opensuse-leap"\nbase_version = "16.1"\nstage = "alpha"\n'
            'iteration = 1\nimage_name = "lyra-os-alternate"\narchitecture = "x86_64"\n',
            encoding="utf-8",
        )
        paths = release_artifacts.generate(
            iso=self.iso,
            packages_path=self.packages,
            verified_path=self.verified,
            output_dir=self.output_dir,
            commit="HEAD",
            release_file=release_file,
            product="Lyra OS Alternate",
        )
        report = next(p for p in paths if p.suffix == ".report")
        document = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(document["product"], "Lyra OS Alternate")
        self.assertEqual(document["version"], "1.0-alpha.1")
        self.assertIsNone(document["codename"])


if __name__ == "__main__":
    unittest.main()
