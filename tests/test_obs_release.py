from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("lyra_obs_release", ROOT / "scripts/obs-release.py")
assert SPEC and SPEC.loader
obs_release = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = obs_release
SPEC.loader.exec_module(obs_release)


class FakeObs:
    def __init__(self, documents: dict[str, str]) -> None:
        self.documents = documents

    def api_xml(self, path: str) -> ET.Element:
        return ET.fromstring(self.documents[path])


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = obs_release.Manifest.load()

    def test_project_inventory_matches_release_contract(self) -> None:
        self.assertEqual([project.id for project in self.manifest.projects], ["lyra", "vega", "fina"])
        self.assertEqual(len(self.manifest.project("lyra").packages), 13)
        self.assertNotIn("chord", self.manifest.project("lyra").packages)
        self.assertIn("linuxtoys", self.manifest.project("lyra").packages)
        self.assertIn("zed", self.manifest.project("lyra").packages)
        self.assertIn("vscode-repo", self.manifest.project("lyra").packages)
        self.assertIn("lyra-welcome", self.manifest.project("lyra").packages)
        self.assertIn("nvm-fish", self.manifest.project("lyra").packages)
        self.assertIn("lyra-fish-productivity", self.manifest.project("lyra").packages)
        self.assertNotIn("calamares", self.manifest.project("lyra").packages)
        self.assertEqual(
            self.manifest.project("lyra").legacy_packages, ("calco", "prosa")
        )
        for project in self.manifest.projects:
            self.assertNotIn("openSUSE_Leap_16.0", [target.name for target in project.targets])
            self.assertEqual(project.targets[0].name, "openSUSE_Leap_16.1")
            self.assertTrue(project.targets[0].iso_consumer)
            self.assertEqual(
                project.targets[0].upstream_project, "openSUSE:Leap:16.1"
            )
        self.assertEqual(self.manifest.project("fina").targets[1].name, "openSUSE_Tumbleweed")

    def test_staging_is_never_an_iso_consumer(self) -> None:
        for project in self.manifest.projects:
            metadata = obs_release.render_project_meta(self.manifest, project)
            self.assertIn("Not consumed by Lyra ISO", metadata)
            self.assertNotIn(project.release + "</", metadata)

    def test_legacy_packages_are_expected_only_in_release(self) -> None:
        project = self.manifest.project("lyra")
        self.assertIn(
            "calco", obs_release.expected_source_packages(project, project.release)
        )
        self.assertNotIn(
            "calco", obs_release.expected_source_packages(project, project.staging)
        )

    def test_local_priority_contract_is_current(self) -> None:
        obs_release.check_local_priorities(self.manifest)

    def test_signing_key_is_pinned(self) -> None:
        self.assertEqual(self.manifest.signing_project, "home:rodrigosbrito")
        self.assertEqual(
            self.manifest.signing_fingerprint,
            "399218A6E088C4053F4533BE58097F767EDCA82E",
        )

    def test_stable_tag_pins_only_packages_that_existed_at_the_tag(self) -> None:
        self.assertEqual(
            self.manifest.baseline_tag, "v2026.08-beta2-stable-20260809"
        )
        for project in self.manifest.projects:
            self.assertTrue(
                set(self.manifest.approved_baselines[project.id]).issubset(project.packages)
            )

    def test_public_repository_url_uses_obs_download_layout(self) -> None:
        self.assertEqual(
            obs_release.repository_url(
                "home:rodrigosbrito:lyra", "openSUSE_Leap_16.1"
            ),
            "https://download.opensuse.org/repositories/"
            "home:/rodrigosbrito:/lyra/openSUSE_Leap_16.1",
        )

    def test_staging_metadata_builds_and_publishes_leap_16_1(self) -> None:
        metadata = obs_release.render_project_meta(
            self.manifest, self.manifest.project("lyra")
        )
        root = ET.fromstring(metadata)
        repository = root.find("./repository[@name='openSUSE_Leap_16.1']")
        self.assertIsNotNone(repository)
        self.assertEqual(
            repository.find("path").attrib,
            {"project": "openSUSE:Leap:16.1", "repository": "standard"},
        )
        self.assertIsNotNone(
            root.find("./publish/enable[@repository='openSUSE_Leap_16.1'][@arch='x86_64']")
        )


class BuildGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project = obs_release.Manifest.load().project("lyra")
        self.target = self.project.targets[0]

    def test_multibuild_parent_may_be_excluded_when_all_flavors_succeed(self) -> None:
        statuses = []
        for package in self.project.packages:
            code = "excluded" if package == "lyra-theme" else "succeeded"
            statuses.append(f'<status package="{package}" code="{code}"/>')
        statuses.extend(
            [
                '<status package="lyra-theme:lyra-os-icons" code="succeeded"/>',
                '<status package="lyra-theme:lyra-os-theme" code="succeeded"/>',
            ]
        )
        path = (
            "/build/home:example/_result?repository=openSUSE_Leap_16.1"
            "&arch=x86_64&view=status"
        )
        document = (
            '<resultlist><result code="published" state="published">'
            + "".join(statuses)
            + "</result></resultlist>"
        )
        obs_release.check_target_result(FakeObs({path: document}), self.project, "home:example", self.target, "x86_64")

    def test_failed_flavor_blocks_promotion(self) -> None:
        statuses = [
            f'<status package="{package}" code="succeeded"/>'
            for package in self.project.packages
            if package != "lyra-theme"
        ]
        statuses.extend(
            [
                '<status package="lyra-theme" code="excluded"/>',
                '<status package="lyra-theme:lyra-os-icons" code="failed"/>',
            ]
        )
        path = (
            "/build/home:example/_result?repository=openSUSE_Leap_16.1"
            "&arch=x86_64&view=status"
        )
        document = '<resultlist><result code="published">' + "".join(statuses) + "</result></resultlist>"
        with self.assertRaisesRegex(obs_release.PolicyError, "build gate failed"):
            obs_release.check_target_result(
                FakeObs({path: document}), self.project, "home:example", self.target, "x86_64"
            )

    def test_unpublished_repository_blocks_promotion(self) -> None:
        path = (
            "/build/home:example/_result?repository=openSUSE_Leap_16.1"
            "&arch=x86_64&view=status"
        )
        document = '<resultlist><result code="building" state="building"/></resultlist>'
        with self.assertRaisesRegex(obs_release.PolicyError, "not published"):
            obs_release.check_target_result(
                FakeObs({path: document}), self.project, "home:example", self.target, "x86_64"
            )


class SafetyTests(unittest.TestCase):
    def test_single_maintainer_may_accept_a_reviewed_request(self) -> None:
        policy = (ROOT / "docs" / "obs-release.md").read_text(encoding="utf-8")
        self.assertIn("request author may accept their own request", policy)
        self.assertNotIn("SECOND_REVIEWER", policy)

    def test_mutation_is_a_plan_without_execute(self) -> None:
        obs = obs_release.Obs("https://api.opensuse.org", execute=False)
        self.assertEqual(obs.run(["request", "accept", "123"], mutating=True), "")

    def test_command_formatter_does_not_interpolate_shell(self) -> None:
        rendered = obs_release.Obs.format_command(["osc", "-m", "test; $(bad)"])
        self.assertEqual(rendered, "osc -m 'test; $(bad)'")


class HttpDownloaderTests(unittest.TestCase):
    def test_transient_failures_are_retried_with_bounded_backoff(self) -> None:
        attempts = 0
        delays: list[int] = []

        class Response:
            status = 200

            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return b"rpm"

        def opener(_request: object, *, timeout: int) -> Response:
            nonlocal attempts
            attempts += 1
            self.assertEqual(timeout, 120)
            if attempts < 3:
                raise urllib.error.URLError("temporary mirror failure")
            return Response()

        downloader = obs_release.HttpDownloader(opener=opener, sleeper=delays.append)
        self.assertEqual(downloader.get("https://example.invalid/package.rpm"), b"rpm")
        self.assertEqual(attempts, 3)
        self.assertEqual(delays, [1, 2])

    def test_client_error_is_not_retried(self) -> None:
        attempts = 0

        def opener(request: object, *, timeout: int) -> None:
            nonlocal attempts
            attempts += 1
            raise urllib.error.HTTPError(
                request.full_url, 404, "not found", {}, None
            )

        downloader = obs_release.HttpDownloader(opener=opener, sleeper=lambda _: None)
        with self.assertRaisesRegex(obs_release.PolicyError, "returned HTTP 404"):
            downloader.get("https://example.invalid/missing.rpm")
        self.assertEqual(attempts, 1)


class PromotionTraceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = obs_release.Manifest.load()
        self.project = self.manifest.project("lyra")

    def test_current_release_revision_requires_an_accepted_staging_request(self) -> None:
        revision = {
            "revision": "9",
            "srcmd5": "a" * 32,
            "version": "1.0",
            "request_id": "1370000",
        }
        request = f"""
        <request id="1370000">
          <action type="submit">
            <source project="{self.project.staging}" package="beam" rev="{'a' * 32}"/>
            <target project="{self.project.release}" package="beam"/>
            <acceptinfo srcmd5="{'a' * 32}"/>
          </action>
          <state name="accepted"/>
        </request>
        """
        obs_release.validate_accepted_promotion(
            FakeObs({"/request/1370000": request}), self.project, "beam", revision
        )

    def test_direct_release_commit_is_rejected(self) -> None:
        revision = {
            "revision": "9",
            "srcmd5": "a" * 32,
            "version": "1.0",
            "request_id": "",
        }
        with self.assertRaisesRegex(obs_release.PolicyError, "accepted staging submit request"):
            obs_release.validate_accepted_promotion(FakeObs({}), self.project, "beam", revision)

    def test_pinned_stable_baseline_is_accepted_without_a_legacy_request(self) -> None:
        revision = {
            "revision": "12",
            "srcmd5": self.manifest.approved_baselines["lyra"]["beam"],
            "version": "1.0",
            "request_id": "",
        }
        self.assertEqual(
            obs_release.release_provenance(
                FakeObs({}), self.manifest, self.project, "beam", revision
            ),
            {
                "kind": "stable-tag-baseline",
                "tag": "v2026.08-beta2-stable-20260809",
                "srcmd5": self.manifest.approved_baselines["lyra"]["beam"],
            },
        )

    def test_unreviewed_drift_from_stable_baseline_is_rejected(self) -> None:
        revision = {
            "revision": "13",
            "srcmd5": "f" * 32,
            "version": "1.0",
            "request_id": "",
        }
        with self.assertRaisesRegex(obs_release.PolicyError, "neither an accepted staging request"):
            obs_release.release_provenance(
                FakeObs({}), self.manifest, self.project, "beam", revision
            )

    def test_multibuild_baseline_uses_published_not_raw_history_md5(self) -> None:
        published = self.manifest.approved_baselines["lyra"]["lyra-theme"]
        revision = {
            "revision": "24",
            "srcmd5": "a59ee06378f7aa5c8d1b99433d8b2031",
            "published_srcmd5": published,
            "version": "unknown",
            "request_id": "",
        }
        self.assertEqual(
            obs_release.release_provenance(
                FakeObs({}), self.manifest, self.project, "lyra-theme", revision
            )["srcmd5"],
            published,
        )

    def test_binary_inventory_ignores_source_rpm_and_requires_binary(self) -> None:
        target = self.project.targets[0]
        path = f"/build/{self.project.release}/{target.name}/x86_64/beam"
        document = """
        <binarylist>
          <binary filename="beam-1.0-1.src.rpm"/>
          <binary filename="beam-1.0-1.x86_64.rpm"/>
          <binary filename="rpmlint.log"/>
        </binarylist>
        """
        self.assertEqual(
            obs_release.binary_rpms(
                FakeObs({path: document}), self.project.release, target, "x86_64", "beam"
            ),
            ["beam-1.0-1.x86_64.rpm"],
        )

    def test_multibuild_binary_inventory_uses_successful_flavors(self) -> None:
        self.assertEqual(
            obs_release.binary_build_packages(
                "lyra-theme",
                {
                    "state": "excluded",
                    "flavors": {
                        "lyra-theme:lyra-os-theme": "succeeded",
                        "lyra-theme:lyra-os-icons": "succeeded",
                    },
                },
            ),
            ["lyra-theme:lyra-os-icons", "lyra-theme:lyra-os-theme"],
        )


class HealthReportTests(unittest.TestCase):
    def test_report_is_written_as_stable_json(self) -> None:
        report = {
            "schema": 1,
            "status": "passed",
            "projects": [{"id": "lyra", "packages": []}],
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "obs-health.json"
            obs_release.write_health_report(report, output)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), report)


if __name__ == "__main__":
    unittest.main()
