from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("lyra_release", ROOT / "scripts/release.py")
assert SPEC and SPEC.loader
release_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release_module
SPEC.loader.exec_module(release_module)
Release = release_module.Release


def sample_release(**overrides: object) -> Release:
    values: dict[str, object] = {
        "product_version": "1.0",
        "base_distribution": "opensuse-leap",
        "base_version": "16.1",
        "stage": "beta",
        "iteration": 2,
        "codename": "Odisseia",
        "codename_id": "odisseia",
        "image_name": "lyra-os",
        "architecture": "x86_64",
    }
    values.update(overrides)
    release = Release(**values)
    release.validate()
    return release


class ReleaseConventionTests(unittest.TestCase):
    def test_alpha_identifiers(self) -> None:
        release = sample_release(stage="alpha", iteration=5)
        self.assertEqual(release.version_id, "1.0-alpha.5")
        self.assertEqual(release.tag, "v1.0-alpha.5")
        self.assertEqual(release.iso_filename, "lyra-os-1.0-alpha.5-x86_64.iso")
        self.assertEqual(release.volume_id, "LYRA_OS_1_0_ALPHA_5")
        self.assertEqual(release.pretty_name, "Lyra OS 1.0 Alpha 5 (Odisseia)")

    def test_beta_identifiers(self) -> None:
        release = sample_release()
        self.assertEqual(release.version_id, "1.0-beta.2")
        self.assertEqual(release.tag, "v1.0-beta.2")
        self.assertEqual(release.iso_filename, "lyra-os-1.0-beta.2-x86_64.iso")
        self.assertEqual(release.volume_id, "LYRA_OS_1_0_BETA_2")
        self.assertEqual(release.pretty_name, "Lyra OS 1.0 Beta 2 (Odisseia)")

    def test_rc_identifiers(self) -> None:
        release = sample_release(stage="rc", iteration=1)
        self.assertEqual(release.version_id, "1.0-rc.1")
        self.assertEqual(release.stage_label, "RC 1")

    def test_final_identifiers(self) -> None:
        release = sample_release(stage="release", iteration=0)
        self.assertEqual(release.version_id, "1.0")
        self.assertEqual(release.tag, "v1.0")
        self.assertEqual(release.pretty_name, "Lyra OS 1.0 (Odisseia)")

    def test_prerelease_requires_iteration(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive iteration"):
            sample_release(iteration=0)

    def test_final_rejects_iteration(self) -> None:
        with self.assertRaisesRegex(ValueError, "iteration = 0"):
            sample_release(stage="release", iteration=1)

    def test_iteration_must_be_an_integer(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be an integer"):
            sample_release(iteration="2")


class RepositoryMetadataTests(unittest.TestCase):
    def test_generated_files_are_current(self) -> None:
        release = Release.from_file()
        for path, expected in release_module.render_files(release).items():
            self.assertTrue(path.exists(), path)
            self.assertEqual(path.read_text(encoding="utf-8"), expected, path)

    def test_desktop_schedule_has_no_obsolete_2026_final_date(self) -> None:
        schedule_files = (
            ROOT / "PROMPT-LYRA-OS.md",
            ROOT / "docs/roadmap.md",
            ROOT / "docs/nvidia-iso.md",
        )
        for path in schedule_files:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("20/09/2026", text, path)

    def test_versioning_policy_separates_product_base_and_build(self) -> None:
        versioning = (ROOT / "docs/release-versioning.md").read_text(encoding="utf-8")
        self.assertIn("MAJOR.MINOR.PATCH", versioning)
        self.assertIn("Lyra OS 1 — Odisseia", versioning)
        self.assertIn("openSUSE Leap 16.1", versioning)
        self.assertIn("BUILD_ID", versioning)
        self.assertIn("independente", versioning)
        self.assertNotIn("ano.mês", versioning)

    def test_release_artifact_signing_starts_at_beta1(self) -> None:
        adr = (ROOT / "docs/adr/0005-release-signing-starts-at-beta1.md").read_text(
            encoding="utf-8"
        )
        alpha4 = (
            ROOT / "docs/releases/lyra-os-desktop-2026.08-alpha4.md"
        ).read_text(encoding="utf-8")
        uploader = (
            ROOT / "scripts/upload-desktop-alpha4-sourceforge.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("sem `*.iso.sha256.asc`", adr)
        self.assertIn("começa na Beta 1", alpha4)
        self.assertNotIn('"$PREFIX.iso.sha256.asc"', uploader)

    def test_alpha4_build_prepares_the_complete_upload_bundle(self) -> None:
        builder = (ROOT / "scripts/build-desktop-alpha4.sh").read_text(encoding="utf-8")
        self.assertIn("--artifacts-only", builder)
        self.assertIn("release-artifacts.py generate", builder)
        self.assertIn("docs/releases/lyra-os-desktop-$EXPECTED_VERSION.md", builder)
        for suffix in (".iso.sha256", ".cdx.json", ".spdx.json", ".report"):
            self.assertIn(suffix, builder)

    def test_alpha5_build_prepares_the_complete_upload_bundle(self) -> None:
        builder = (ROOT / "scripts/build-desktop-alpha5.sh").read_text(encoding="utf-8")
        uploader = (
            ROOT / "scripts/upload-desktop-alpha5-sourceforge.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('EXPECTED_VERSION="2026.08-alpha5"', builder)
        self.assertIn("--artifacts-only", builder)
        self.assertIn("release-artifacts.py generate", builder)
        self.assertIn("desktop/alpha5/", uploader)
        self.assertNotIn('"$PREFIX.iso.sha256.asc"', uploader)

    def test_alpha6_release_requires_published_components_and_full_evidence(self) -> None:
        builder = (ROOT / "scripts/build-desktop-alpha6.sh").read_text(encoding="utf-8")
        uploader = (
            ROOT / "scripts/upload-desktop-alpha6-sourceforge.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('LYRA_EXPECTED_VERSION:-1.0-alpha.6', builder)
        self.assertIn("--published-installer", builder)
        self.assertNotIn("--published-welcome", builder)
        self.assertIn("obs-release.py health", builder)
        self.assertIn("--evidence-dir", builder)
        for evidence in (
            "obs-repositories",
            "live-session",
            "installer",
            "first-boot",
            "uefi-secure-boot",
            "rollback",
            "hardware-matrix",
        ):
            self.assertIn(evidence, builder)
            self.assertIn(evidence, uploader)
        self.assertIn('LYRA_RELEASE_SLUG:-alpha6', uploader)
        self.assertIn("--decision-file", uploader)
        self.assertNotIn("iso.sha256.asc", uploader)

    def test_alpha7_release_uses_leap_16_1_and_preserves_full_evidence_gate(self) -> None:
        self.assertEqual(Release.from_file().version_id, "1.1-alpha.7")
        wrapper = (ROOT / "scripts/build-desktop-alpha7.sh").read_text(
            encoding="utf-8"
        )
        builder = (ROOT / "scripts/build-desktop-alpha6.sh").read_text(
            encoding="utf-8"
        )
        uploader_wrapper = (
            ROOT / "scripts/upload-desktop-alpha7-sourceforge.sh"
        ).read_text(encoding="utf-8")
        kde_uploader = (
            ROOT / "scripts/upload-kde-alpha7-sourceforge.sh"
        ).read_text(encoding="utf-8")
        uploader = (
            ROOT / "scripts/upload-desktop-alpha6-sourceforge.sh"
        ).read_text(encoding="utf-8")
        kiwi = (ROOT / "kiwi/config.xml").read_text(encoding="utf-8")

        self.assertIn('LYRA_EXPECTED_VERSION="1.1-alpha.7"', wrapper)
        self.assertIn('LYRA_RELEASE_LABEL="KDE Alpha 7"', wrapper)
        self.assertIn(
            'LYRA_RELEASE_NOTES="$SCRIPT_DIR/../docs/releases/lyra-os-desktop-1.1-alpha7.md"',
            wrapper,
        )
        self.assertIn('LYRA_RELEASE_SLUG="alpha7"', uploader_wrapper)
        self.assertIn('LYRA_RELEASE_EDITION="kde"', kde_uploader)
        self.assertIn('LYRA_RELEASE_LAYOUT="release-first"', kde_uploader)
        self.assertIn('LYRA_VERIFY_DOWNLOAD="0"', kde_uploader)
        self.assertIn('LYRA_REQUIRE_DECISION="0"', kde_uploader)
        self.assertIn('LYRA_CHECK_OPEN_BLOCKERS="0"', kde_uploader)
        self.assertIn(
            'release-first) RELEASE_PATH="$RELEASE_SERIES/$RELEASE_SLUG/$RELEASE_EDITION"',
            uploader,
        )
        self.assertLess(
            uploader.index('if [ "$VERIFY_DOWNLOAD" -eq 0 ]'),
            uploader.index("curl --fail --location"),
        )
        self.assertIn("--published-installer", builder)
        self.assertIn("obs-release.py health", builder)
        self.assertNotIn("openSUSE_Leap_16.0/", kiwi)
        self.assertIn("openSUSE_Leap_16.1/", kiwi)
        for evidence in (
            "obs-repositories",
            "live-session",
            "installer",
            "first-boot",
            "uefi-secure-boot",
            "rollback",
            "hardware-matrix",
        ):
            self.assertIn(evidence, builder)

    def test_vm_helper_can_pair_local_installer_with_published_vega_qt(self) -> None:
        helper = (ROOT / "kiwi/test/build-and-run-vm.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("--published-vega-qt", helper)
        self.assertIn("--published-vega-qt) USE_LOCAL_VEGA_QT=0; shift ;;", helper)
        self.assertNotIn(
            "--published-vega-qt) USE_LOCAL_INSTALLER=0", helper
        )

    def test_alpha8_wrapper_uses_the_stage_aware_release_gate(self) -> None:
        wrapper = (ROOT / "scripts/build-desktop-alpha8.sh").read_text(encoding="utf-8")
        uploader_wrapper = (ROOT / "scripts/upload-desktop-alpha8-sourceforge.sh").read_text(encoding="utf-8")
        builder = (ROOT / "scripts/build-desktop-alpha6.sh").read_text(encoding="utf-8")
        uploader = (ROOT / "scripts/upload-desktop-alpha6-sourceforge.sh").read_text(encoding="utf-8")
        gate = (ROOT / "docs/release-gate.md").read_text(encoding="utf-8")
        contract = (ROOT / "docs/alpha8-evidence.md").read_text(encoding="utf-8")

        self.assertIn('LYRA_EXPECTED_VERSION="1.1-alpha.8"', wrapper)
        self.assertIn('LYRA_RELEASE_SLUG="alpha8"', uploader_wrapper)
        self.assertIn("required-test-results", builder)
        self.assertIn("required-test-results", uploader)
        for evidence in ("upgrade-rehearsal", "eca-digital", "i18n", "feature-freeze"):
            self.assertIn(evidence, gate)
            self.assertIn(evidence, contract)

    def test_build_manifest_is_traceable(self) -> None:
        release = Release.from_file()
        with tempfile.TemporaryDirectory() as directory:
            iso = Path(directory) / release.iso_filename
            iso.write_bytes(b"test ISO payload")
            output = Path(directory) / "build.json"
            self.assertEqual(release_module.write_build_manifest(release, iso, output), 0)
            document = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(document["version"], release.version_id)
            self.assertEqual(document["iso"]["filename"], release.iso_filename)
            self.assertEqual(
                document["iso"]["sha256"],
                "1d39ee59b83b0847958cdee279101b6ac2531d8575839a6e3fa72167be729661",
            )
            self.assertRegex(document["source"]["commit"], r"^[0-9a-f]{40}$")
            self.assertIn("built_at", document)


if __name__ == "__main__":
    unittest.main()
