from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "kiwi/root/usr/bin/lyra-live-smoke"
LOADER = importlib.machinery.SourceFileLoader("lyra_live_smoke", str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC
live_smoke = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(live_smoke)


class LiveSmokeTests(unittest.TestCase):
    def create_root(self, root: Path) -> None:
        for path in (
            "run/overlay/live/LiveOS/squashfs.img",
            "usr/lib/lyra-os/release",
            "usr/lib/lyra-os/build-info",
            "usr/bin/lyra-installer",
            "usr/bin/lyra-install-lock",
        ):
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("fixture\n", encoding="utf-8")
        for path in ("usr/bin/lyra-installer", "usr/bin/lyra-install-lock"):
            os.chmod(root / path, 0o755)
        sddm = root / "etc/sddm.conf.d/10-lyra-live.conf"
        sddm.parent.mkdir(parents=True)
        sddm.write_text(
            "[Autologin]\nUser=liveuser\nSession=plasmawayland.desktop\n",
            encoding="utf-8",
        )
        desktop = root / "usr/share/applications/org.lyraos.LyraInstaller.desktop"
        desktop.parent.mkdir(parents=True)
        desktop.write_text(
            "TryExec=/usr/bin/lyra-installer\n"
            "Exec=/usr/bin/lyra-install-lock /usr/bin/lyra-installer\n"
            "Icon=org.lyraos.LyraInstaller\n"
            "StartupWMClass=lyra-installer\n",
            encoding="utf-8",
        )
        (root / "dev/input").mkdir(parents=True)

    @staticmethod
    def runner(arguments: list[str]) -> tuple[int, str]:
        if arguments[:2] == ["systemctl", "is-active"]:
            return 0, "active"
        if arguments[:2] == ["systemctl", "--failed"]:
            return 0, ""
        if arguments[0] == "pgrep":
            return 0, "123"
        if arguments[0] == "journalctl":
            return 0, ""
        if arguments[0] == "nmcli":
            return 0, "none"
        return 1, "unavailable in fixture"

    def test_green_live_session_produces_passed_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.create_root(root)
            report = live_smoke.validate_live_session(
                root=root,
                username="liveuser",
                environment={
                    "XDG_CURRENT_DESKTOP": "KDE",
                    "XDG_SESSION_TYPE": "wayland",
                },
                runner=self.runner,
                expect_offline=True,
            )
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["observations"]["network_connectivity"], "none")
            check_ids = {item["id"] for item in report["checks"]}
            self.assertIn("unit-display-manager.service", check_ids)
            self.assertNotIn("unit-sddm.service", check_ids)

    def test_failed_unit_and_unreviewed_journal_block_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.create_root(root)

            def failing_runner(arguments: list[str]) -> tuple[int, str]:
                if arguments[:2] == ["systemctl", "--failed"]:
                    return 0, "bad.service loaded failed failed"
                if arguments[0] == "journalctl":
                    return 0, "kernel: critical fixture"
                return self.runner(arguments)

            report = live_smoke.validate_live_session(
                root=root,
                username="liveuser",
                runner=failing_runner,
            )
            self.assertEqual(report["status"], "failed")
            failed = {
                item["id"]
                for item in report["checks"]
                if item["status"] == "failed"
            }
            self.assertEqual(failed, {"failed-units", "critical-journal"})

    def test_missing_command_is_reported_instead_of_crashing(self) -> None:
        with mock.patch.object(
            live_smoke.subprocess,
            "run",
            side_effect=FileNotFoundError("fixture command is missing"),
        ):
            code, output = live_smoke.run_command(["missing-fixture"])

        self.assertEqual(code, 127)
        self.assertIn("fixture command is missing", output)


if __name__ == "__main__":
    unittest.main()
