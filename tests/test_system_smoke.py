from __future__ import annotations

import importlib.machinery
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "kiwi/root/usr/bin/lyra-system-smoke"
LOADER = importlib.machinery.SourceFileLoader("lyra_system_smoke", str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC
system_smoke = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(system_smoke)


class SystemSmokeTests(unittest.TestCase):
    def create_installed_root(self, root: Path) -> None:
        files = {
            "usr/lib/lyra-os/release": "VERSION_ID=1.0-beta.2\n",
            "usr/lib/lyra-os/build-info": "LYRA_SOURCE_COMMIT=fixture\n",
            "etc/machine-id": "0123456789abcdef0123456789abcdef\n",
            "boot/grub2/grub.cfg": "menuentry 'Lyra OS' {}\n",
            "boot/efi/EFI/BOOT/BOOTX64.EFI": "fixture\n",
            "usr/share/dbus-1/system-services/org.lyraos.Vega1.service": "[D-BUS Service]\n",
        }
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        (root / "sys/firmware/efi/efivars").mkdir(parents=True)
        (root / "home/alice").mkdir(parents=True)

    @staticmethod
    def runner(arguments: list[str]) -> tuple[int, str]:
        if arguments[:3] == ["getent", "passwd", "alice"]:
            return 0, "alice:x:1000:100::/home/alice:/bin/bash"
        if arguments[:3] == ["getent", "passwd", "liveuser"]:
            return 2, ""
        if arguments[:2] == ["stat", "--format=%u:%g:%a"]:
            return 0, "1000:100:700"
        if arguments[0] == "rpm":
            return 1, "package lyra-installer is not installed"
        if arguments[:4] == ["findmnt", "-n", "-o", "FSTYPE"]:
            return 0, "btrfs"
        if arguments[:2] == ["findmnt", "-n"]:
            return 0, "/dev/vda1 /boot/efi vfat rw"
        if arguments[:2] == ["findmnt", "--verify"]:
            return 0, "Success, no errors or warnings detected"
        if arguments[0] == "snapper":
            return 0, " # | Type   | Description\n0 | single | current"
        if arguments[:2] == ["systemctl", "is-active"]:
            return 0, "active"
        if arguments[:2] == ["systemctl", "is-enabled"]:
            return 0, "static"
        if arguments[:2] == ["systemctl", "--failed"]:
            return 0, ""
        if arguments[0] == "pgrep":
            return 0, "123"
        if arguments[0] == "journalctl":
            return 0, ""
        if arguments[0] == "mokutil":
            return 0, "SecureBoot enabled"
        if arguments[0] == "busctl":
            return 0, "u 1"
        return 1, "unavailable in fixture"

    def test_clean_installed_system_produces_first_boot_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.create_installed_root(root)
            report = system_smoke.validate_first_boot(
                root=root,
                username="alice",
                environment={
                    "XDG_CURRENT_DESKTOP": "KDE",
                    "XDG_SESSION_TYPE": "wayland",
                },
                runner=self.runner,
            )
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["mode"], "first-boot")

    def test_installer_or_live_artifact_blocks_first_boot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.create_installed_root(root)
            installer = root / "usr/libexec/lyra-installer-service"
            installer.parent.mkdir(parents=True, exist_ok=True)
            installer.write_text("fixture", encoding="utf-8")

            def runner(arguments: list[str]) -> tuple[int, str]:
                if arguments[0] == "rpm":
                    return 0, "lyra-installer-0.1.0"
                return self.runner(arguments)

            report = system_smoke.validate_first_boot(
                root=root, username="alice", runner=runner
            )
            failed = {
                item["id"]
                for item in report["checks"]
                if item["status"] == "failed"
            }
            self.assertEqual(report["status"], "failed")
            self.assertIn("live-artifacts-removed", failed)
            self.assertIn("installer-package-removed", failed)

    def test_root_owned_home_blocks_first_boot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.create_installed_root(root)

            def runner(arguments: list[str]) -> tuple[int, str]:
                if arguments[:2] == ["stat", "--format=%u:%g:%a"]:
                    return 0, "0:0:755"
                return self.runner(arguments)

            report = system_smoke.validate_first_boot(
                root=root, username="alice", runner=runner
            )
            failed = {
                item["id"]
                for item in report["checks"]
                if item["status"] == "failed"
            }
            self.assertEqual(report["status"], "failed")
            self.assertIn("installed-user-home-ownership", failed)
            self.assertIn("installed-user-home-writable", failed)

    def test_unreadable_grub_is_a_structured_failure_not_a_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.create_installed_root(root)
            grub = root / "boot/grub2/grub.cfg"
            grub.chmod(0)
            try:
                report = system_smoke.validate_first_boot(
                    root=root, username="alice", runner=self.runner
                )
            finally:
                grub.chmod(0o600)
            grub_check = next(
                item for item in report["checks"] if item["id"] == "grub-config"
            )
            self.assertEqual(report["status"], "failed")
            self.assertEqual(grub_check["status"], "failed")

    def test_privileged_fallback_reads_a_protected_system_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "grub.cfg"
            path.write_text("menuentry 'Lyra OS' {}\n", encoding="utf-8")
            path.chmod(0)

            def runner(arguments: list[str]) -> tuple[int, str]:
                self.assertEqual(arguments[:4], ["sudo", "-n", "--", "cat"])
                return 0, "menuentry 'Lyra OS' {}"

            try:
                code, content = system_smoke.read_system_text(
                    path, runner=runner, privileged_fallback=True
                )
            finally:
                path.chmod(0o600)
            self.assertEqual(code, 0)
            self.assertIn("menuentry ", content)

    def test_unknown_profile_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.create_installed_root(root)
            with self.assertRaises(ValueError):
                system_smoke.validate_first_boot(
                    root=root, username="alice", runner=self.runner, profile="bogus"
                )

    def test_secure_boot_requires_enabled_firmware(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.create_installed_root(root)
            report = system_smoke.validate_secure_boot(
                root=root, runner=self.runner
            )
            self.assertEqual(report["status"], "passed")

            report = system_smoke.validate_secure_boot(
                root=root,
                runner=lambda arguments: (0, "SecureBoot disabled")
                if arguments[0] == "mokutil"
                else self.runner(arguments),
            )
            self.assertEqual(report["status"], "failed")

    def test_report_is_replaced_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "first-boot.json"
            system_smoke.write_report({"status": "passed"}, output)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                output.read_text(encoding="utf-8").strip(),
                '{\n  "status": "passed"\n}',
            )


if __name__ == "__main__":
    unittest.main()
