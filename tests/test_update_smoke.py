from __future__ import annotations

import importlib.machinery
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "kiwi/root/usr/bin/lyra-update-smoke"
LOADER = importlib.machinery.SourceFileLoader("lyra_update_smoke", str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC
update_smoke = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(update_smoke)


class FixtureRunner:
    def __init__(self) -> None:
        self.snapshots = [
            "1,single,,yes,first root filesystem",
        ]
        self.next_snapshot = 10
        self.fail_update = False
        self.update_codes: list[int] = []
        self.kernel = "6.12.0-fixture"
        self.calls: list[list[str]] = []

    def __call__(self, arguments: list[str], timeout: int) -> tuple[int, str]:
        self.calls.append(arguments)
        if arguments[0] == "findmnt":
            return 0, "vfat" if arguments[-1] == "/boot/efi" else "btrfs"
        if arguments[0] == "uname":
            return 0, self.kernel
        if arguments[:3] == ["systemctl", "--failed", "--no-legend"]:
            return 0, ""
        if arguments[:3] == ["btrfs", "subvolume", "get-default"]:
            return 0, "ID 256 gen 1 top level 5 path @"
        if arguments[:3] == ["btrfs", "subvolume", "show"]:
            return 0, "Name: @\nSubvolume ID: 256"
        if arguments[0] == "snapper" and "list" in arguments:
            return 0, "\n".join(self.snapshots)
        if arguments[0] == "snapper" and "create" in arguments:
            number = self.next_snapshot
            self.next_snapshot += 1
            snapshot_type = arguments[arguments.index("--type") + 1]
            pre_number = ""
            if "--pre-number" in arguments:
                pre_number = arguments[arguments.index("--pre-number") + 1]
            self.snapshots.append(
                f"{number},{snapshot_type},{pre_number},yes,Lyra Beta 2 update smoke"
            )
            return 0, str(number)
        if arguments[0] == "zypper" and arguments[-1] == "update":
            if self.fail_update:
                return 4, "network unavailable"
            if self.update_codes:
                return self.update_codes.pop(0), "fixture update"
        return 0, "fixture"


class UpdateSmokeTests(unittest.TestCase):
    def create_root(self, root: Path) -> None:
        for path in (
            "usr/lib/lyra-os/release",
            "usr/lib/lyra-os/build-info",
            "boot/initrd-6.12.0-fixture",
            "boot/grub2/grub.cfg",
            "usr/share/grub/themes/Lyra-OS/theme.txt",
        ):
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            content = (
                "set theme=($root)/usr/share/grub/themes/Lyra-OS/theme.txt\n"
                if path == "boot/grub2/grub.cfg"
                else "fixture\n"
            )
            target.write_text(content, encoding="utf-8")

    def test_complete_update_and_rollback_only_passes_at_final_phase(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            root = directory / "root"
            state = directory / "esp/update-state.json"
            self.create_root(root)
            runner = FixtureRunner()
            runner.update_codes = [102]

            baseline = update_smoke.baseline(
                root=root,
                state_path=state,
                runner=runner,
                requested_snapshot=None,
                restart=False,
            )
            self.assertEqual(baseline["status"], "incomplete")

            updated = update_smoke.update_system(root=root, state_path=state, runner=runner)
            self.assertEqual(updated["status"], "incomplete")
            runner.kernel = "6.13.0-fixture"
            (root / "boot/initrd-6.13.0-fixture").write_text(
                "fixture\n", encoding="utf-8"
            )
            verified = update_smoke.verify_updated(root=root, state_path=state, runner=runner)
            self.assertEqual(verified["status"], "incomplete")
            prepared = update_smoke.prepare_rollback(state_path=state, runner=runner)
            self.assertEqual(prepared["status"], "incomplete")
            self.assertIn(
                [
                    "snapper", "--no-dbus", "--config", "root", "--ambit",
                    "classic", "rollback", "1",
                ],
                runner.calls,
            )
            runner.kernel = "6.12.0-fixture"
            rolled_back = update_smoke.verify_rollback(root=root, state_path=state, runner=runner)
            self.assertEqual(rolled_back["status"], "passed")
            self.assertEqual(update_smoke.load_state(state)["phase"], "rollback-verified")

    def test_update_without_reboot_can_be_verified_and_rolled_back(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            root = directory / "root"
            state = directory / "esp/update-state.json"
            self.create_root(root)
            runner = FixtureRunner()

            update_smoke.baseline(
                root=root,
                state_path=state,
                runner=runner,
                requested_snapshot=None,
                restart=False,
            )
            updated = update_smoke.update_system(root=root, state_path=state, runner=runner)
            self.assertIs(updated["facts"]["reboot_suggested"], False)

            verified = update_smoke.verify_updated(root=root, state_path=state, runner=runner)
            self.assertEqual(verified["status"], "incomplete")
            self.assertIs(verified["facts"]["reboot_suggested"], False)
            update_smoke.prepare_rollback(state_path=state, runner=runner)
            rolled_back = update_smoke.verify_rollback(root=root, state_path=state, runner=runner)
            self.assertEqual(rolled_back["status"], "passed")

    def test_package_manager_restart_and_reboot_codes_are_informational(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            root = directory / "root"
            state = directory / "esp/update-state.json"
            self.create_root(root)
            runner = FixtureRunner()
            runner.update_codes = [103, 102]
            update_smoke.baseline(
                root=root,
                state_path=state,
                runner=runner,
                requested_snapshot=None,
                restart=False,
            )

            report = update_smoke.update_system(root=root, state_path=state, runner=runner)

            self.assertEqual(report["status"], "incomplete")
            self.assertEqual(report["facts"]["update_exit_codes"], [103, 102])
            self.assertIs(report["facts"]["reboot_suggested"], True)

    def test_failed_update_is_persisted_and_cannot_be_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            root = directory / "root"
            state = directory / "esp/update-state.json"
            self.create_root(root)
            runner = FixtureRunner()
            update_smoke.baseline(
                root=root,
                state_path=state,
                runner=runner,
                requested_snapshot=1,
                restart=False,
            )
            runner.fail_update = True

            with self.assertRaisesRegex(update_smoke.WorkflowError, "update failed"):
                update_smoke.update_system(root=root, state_path=state, runner=runner)

            self.assertEqual(update_smoke.load_state(state)["phase"], "update-failed")
            with self.assertRaisesRegex(update_smoke.WorkflowError, "update-failed"):
                update_smoke.verify_updated(root=root, state_path=state, runner=runner)

    def test_baseline_refuses_to_silently_replace_existing_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            root = directory / "root"
            state = directory / "esp/update-state.json"
            self.create_root(root)
            runner = FixtureRunner()
            update_smoke.baseline(
                root=root,
                state_path=state,
                runner=runner,
                requested_snapshot=None,
                restart=False,
            )
            with self.assertRaisesRegex(update_smoke.WorkflowError, "state already exists"):
                update_smoke.baseline(
                    root=root,
                    state_path=state,
                    runner=runner,
                    requested_snapshot=None,
                    restart=False,
                )

    def test_failed_baseline_cannot_start_update(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            root = directory / "root"
            state = directory / "esp/update-state.json"
            self.create_root(root)
            runner = FixtureRunner()

            def failing_runner(arguments: list[str], timeout: int) -> tuple[int, str]:
                if arguments[0] == "findmnt" and arguments[-1] == "/":
                    return 0, "ext4"
                return runner(arguments, timeout)

            report = update_smoke.baseline(
                root=root,
                state_path=state,
                runner=failing_runner,
                requested_snapshot=None,
                restart=False,
            )
            self.assertEqual(report["status"], "failed")
            self.assertEqual(update_smoke.load_state(state)["phase"], "baseline-failed")
            with self.assertRaisesRegex(update_smoke.WorkflowError, "baseline-failed"):
                update_smoke.update_system(root=root, state_path=state, runner=runner)


if __name__ == "__main__":
    unittest.main()
