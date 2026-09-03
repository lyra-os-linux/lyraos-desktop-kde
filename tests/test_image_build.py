from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("lyra_image_build", ROOT / "scripts/image-build.py")
assert SPEC and SPEC.loader
image_build = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = image_build
SPEC.loader.exec_module(image_build)


class ImagePolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = image_build.Manifest.load()

    def test_recovery_editors_are_available_in_every_profile(self) -> None:
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        shared_image_packages = {
            package.attrib["name"]
            for packages in root.findall("packages")
            if packages.attrib.get("type") == "image"
            and "profiles" not in packages.attrib
            for package in packages.findall("package")
        }
        self.assertTrue({"vim", "neovim", "nano"}.issubset(shared_image_packages))

    def test_man_is_available_in_every_profile(self) -> None:
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        shared_image_packages = {
            package.attrib["name"]
            for packages in root.findall("packages")
            if packages.attrib.get("type") == "image"
            and "profiles" not in packages.attrib
            for package in packages.findall("package")
        }
        self.assertIn("man", shared_image_packages)

    def test_btrfs_scrub_is_monthly_without_write_heavy_maintenance(self) -> None:
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        shared_image_packages = {
            package.attrib["name"]
            for packages in root.findall("packages")
            if packages.attrib.get("type") == "image"
            and "profiles" not in packages.attrib
            for package in packages.findall("package")
        }
        self.assertIn("btrfsmaintenance", shared_image_packages)

        config_sh = (ROOT / "kiwi/config.sh").read_text(encoding="utf-8")
        maintenance = config_sh[
            config_sh.index("# Verify Btrfs checksums monthly") :
            config_sh.index("# Flathub is shipped")
        ]
        for setting in (
            "BTRFS_SCRUB_MOUNTPOINTS /",
            "BTRFS_SCRUB_PERIOD monthly",
            "BTRFS_SCRUB_PRIORITY idle",
            "BTRFS_SCRUB_READ_ONLY false",
            "BTRFS_BALANCE_PERIOD none",
            "BTRFS_DEFRAG_PERIOD none",
            "BTRFS_TRIM_PERIOD none",
            "BTRFS_ALLOW_CONCURRENCY false",
        ):
            self.assertIn(setting, maintenance)
        self.assertIn(
            "systemctl enable btrfsmaintenance-refresh.path btrfs-scrub.timer",
            maintenance,
        )
        self.assertIn(
            "systemctl disable btrfs-balance.timer btrfs-defrag.timer btrfs-trim.timer",
            maintenance,
        )

    def test_product_release_identity_is_owned_by_an_rpm(self) -> None:
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        packages = {node.attrib["name"] for node in root.findall("packages/package")}
        self.assertIn("lyra-release", packages)

    def test_zypper_cache_policy_matches_vega_update_flow(self) -> None:
        config = (
            ROOT / "kiwi/root/etc/zypp/zypp.conf.d/90-lyra-refresh.conf"
        ).read_text(encoding="utf-8")
        self.assertIn("repo.refresh.delay = 2880", config)
        self.assertIn("download.max_concurrent_connections = 5", config)
        self.assertIn("download.use_deltarpm = false", config)

    def test_localsearch_failure_is_contained(self) -> None:
        preflight = ROOT / "kiwi/root/usr/libexec/lyra-localsearch-preflight"
        self.assertTrue(preflight.stat().st_mode & stat.S_IXUSR)
        script = preflight.read_text(encoding="utf-8")
        self.assertIn("localsearch-extractor-3", script)
        self.assertIn("=> not found", script)

        drop_in = (
            ROOT
            / "kiwi/root/usr/lib/systemd/user/localsearch-3.service.d/90-lyra-stability.conf"
        ).read_text(encoding="utf-8")
        for policy in (
            "ExecStartPre=/usr/libexec/lyra-localsearch-preflight",
            "Environment=LD_LIBRARY_PATH=/usr/lib64/zlib-ng-compat",
            "StartLimitBurst=3",
            "CPUWeight=10",
            "MemoryHigh=512M",
            "MemoryMax=1G",
            "TasksMax=64",
            "LogRateLimitBurst=100",
        ):
            self.assertIn(policy, drop_in)

    def test_vega_update_indicator_is_enabled_by_default(self) -> None:
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        desktop_packages = {
            node.attrib["name"] for node in root.findall("packages/package")
        }
        self.assertIn("vega-qt", desktop_packages)

    def test_plasma_panel_uses_lyra_launcher_and_vega(self) -> None:
        setup_dir = (
            ROOT
            / "kiwi/root/usr/share/plasma/look-and-feel/org.kde.breeze.desktop"
            / "contents/plasmoidsetupscripts"
        )
        kickoff = (setup_dir / "org.kde.plasma.kickoff.js").read_text(
            encoding="utf-8"
        )
        icon_tasks = (setup_dir / "org.kde.plasma.icontasks.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('applet.writeConfig("icon", "lyra-launcher")', kickoff)
        self.assertIn("applications:org.lyraos.Vega.Qt.desktop", icon_tasks)
        self.assertIn('applet.readConfig("launchers", [])', icon_tasks)
        self.assertIn('entry.indexOf("org.kde.discover") === -1', icon_tasks)
        self.assertIn("applet.reloadConfig()", kickoff)
        self.assertIn("applet.reloadConfig()", icon_tasks)
        self.assertFalse(
            (ROOT / "kiwi/root/etc/xdg/autostart/lyra-plasma-brand-panel.desktop").exists()
        )

    def test_breeze_theme_variants_keep_panel_and_wallpaper_on_screen(self) -> None:
        look_and_feel = ROOT / "kiwi/root/usr/share/plasma/look-and-feel"
        for theme in (
            "org.kde.breeze.desktop",
            "org.kde.breezedark.desktop",
            "org.kde.breezetwilight.desktop",
        ):
            layout = (
                look_and_feel
                / theme
                / "contents/layouts/org.kde.plasma.desktop-layout.js"
            ).read_text(encoding="utf-8")
            self.assertIn('loadTemplate("org.kde.plasma.desktop.defaultPanel")', layout)
            self.assertIn("panelList[panelIndex].screen = 0", layout)
            self.assertIn("file:///usr/share/backgrounds/lyra/2702-dawn.png", layout)

    def test_live_sddm_autologin_permits_live_account(self) -> None:
        config = (ROOT / "kiwi/config.sh").read_text(encoding="utf-8")

        self.assertIn("account  required       pam_permit.so", config)
        self.assertIn("suseInsertService lyra-live-autologin-retry", config)
        self.assertIn(
            "DISPLAYMANAGER_AUTOLOGIN liveuser",
            config,
        )

    def test_installer_image_includes_split_pkexec_runtime(self) -> None:
        image = (ROOT / "kiwi/config.xml").read_text(encoding="utf-8")
        spec = (ROOT / "installer/packaging/lyra-installer.spec").read_text(
            encoding="utf-8"
        )
        helper = (ROOT / "kiwi/test/build-and-run-vm.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn('<package name="pkexec"/>', image)
        self.assertIn("Requires:       pkexec", spec)
        self.assertIn('IMAGE_PKEXEC="$BUILD_DIR/build/image-root/usr/bin/pkexec"', helper)

    def test_live_sddm_retries_once_after_early_boot_failure(self) -> None:
        retry = ROOT / "kiwi/root/usr/libexec/lyra-live-sddm-autologin-retry"
        unit = (
            ROOT
            / "kiwi/root/usr/lib/systemd/system/lyra-live-autologin-retry.service"
        ).read_text(encoding="utf-8")

        self.assertTrue(retry.stat().st_mode & stat.S_IXUSR)
        retry_script = retry.read_text(encoding="utf-8")
        self.assertIn("loginctl list-sessions", retry_script)
        self.assertIn("try-restart display-manager.service", retry_script)
        self.assertIn("lyra-live-sddm-autologin-retried", retry_script)
        self.assertIn("After=display-manager.service", unit)
        self.assertIn("WantedBy=graphical.target", unit)

    def test_canonical_sources_pass_repository_and_signature_policy(self) -> None:
        image_build.validate_sources(self.manifest)

    def test_empty_personal_obs_repository_is_not_configured(self) -> None:
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        repository = root.find("repository[@alias='repo-rodrigosbrito']")
        self.assertIsNone(repository)

    def test_release_evidence_tools_are_executable(self) -> None:
        for name in (
            "lyra-hardware-matrix",
            "lyra-live-smoke",
            "lyra-performance",
            "lyra-report",
            "lyra-system-smoke",
            "lyra-update-smoke",
        ):
            path = ROOT / "kiwi/root/usr/bin" / name
            self.assertTrue(path.is_file(), name)
            self.assertNotEqual(path.stat().st_mode & 0o111, 0, name)

    def test_installer_identity_matches_tauri_desktop_and_rpm(self) -> None:
        image_build.validate_installer_identity()

        config = json.loads(
            (ROOT / "installer/src-tauri/tauri.conf.json").read_text(encoding="utf-8")
        )
        self.assertEqual(config["identifier"], image_build.INSTALLER_APP_ID)
        self.assertTrue(config["app"]["enableGTKAppId"])

    def test_obs_is_restricted_to_ordered_rpm_package_sources(self) -> None:
        self.assertEqual(self.manifest.obs_role, "packages-only")
        projects = [source.project for source in self.manifest.package_sources]
        self.assertEqual(
            projects,
            [
                "home:rodrigosbrito:lyra",
                "home:rodrigosbrito:vega",
                "home:rodrigosbrito:fina",
            ],
        )
        self.assertEqual(
            {source.repository for source in self.manifest.package_sources},
            {"openSUSE_Leap_16.1"},
        )
        self.assertFalse(hasattr(self.manifest, "project"))
        self.assertFalse(hasattr(self.manifest, "package"))

    def test_distribution_policy_uses_github_and_sourceforge(self) -> None:
        self.assertEqual(
            self.manifest.source_repository,
            "https://github.com/lyra-os-linux/lyraos-desktop-kde",
        )
        self.assertEqual(self.manifest.iso_provider, "sourceforge")
        help_text = image_build.parser().format_help()
        self.assertNotIn("publish", help_text)
        self.assertNotIn("check-remote", help_text)

    def test_manifest_rejects_an_obs_image_publication_target(self) -> None:
        source = (ROOT / "image-build.toml").read_text(encoding="utf-8")
        source = source.replace(
            'role = "packages-only"',
            'project = "home:rodrigosbrito:lyra:images"\nrole = "packages-only"',
        )
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "image-build.toml"
            manifest.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(image_build.PolicyError, "publication targets"):
                image_build.Manifest.load(manifest)

    def test_live_module_is_part_of_the_installed_image(self) -> None:
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        image_packages = root.find("packages[@type='image']")
        assert image_packages is not None
        self.assertIsNotNone(image_packages.find("package[@name='dracut-kiwi-live']"))
        self.assertIsNone(root.find("packages[@type='iso']/package[@name='dracut-kiwi-live']"))

    def test_desktop_image_has_emoji_and_microsoft_compatible_fonts(self) -> None:
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        packages = {node.attrib["name"] for node in root.findall("packages/package")}
        self.assertIn("google-noto-coloremoji-fonts", packages)
        self.assertIn("liberation-fonts", packages)
        self.assertIn("google-carlito-fonts", packages)
        self.assertIn("google-noto-sans-cjk-fonts", packages)

    def test_fish_and_nvm_are_available(self) -> None:
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        packages = {node.attrib["name"] for node in root.findall("packages/package")}

        for package in ("fish", "nvm-fish", "git", "linuxtoys"):
            self.assertIn(package, packages)

        # The published Welcome currently requires vega-gtk, whose desktop
        # file/icon payload conflicts with the KDE edition's vega-qt package.
        self.assertNotIn("lyra-welcome", packages)

        live_user = root.find("users/user[@name='liveuser']")
        assert live_user is not None
        self.assertEqual(live_user.attrib["shell"], "/usr/bin/fish")

        prompt = ROOT / "kiwi/root/usr/share/fish/vendor_functions.d/fish_prompt.fish"
        defaults = ROOT / "kiwi/root/usr/share/fish/vendor_conf.d/lyra-defaults.fish"
        self.assertTrue(prompt.is_file())
        self.assertTrue(defaults.is_file())

    def test_fastfetch_uses_lyra_branding_without_gnome_theme(self) -> None:
        config_path = ROOT / "kiwi/root/etc/skel/.config/fastfetch/config.jsonc"
        logo_path = ROOT / "kiwi/root/usr/share/lyra-os/fastfetch/logo.txt"
        config = json.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(config["logo"]["type"], "file")
        self.assertEqual(
            config["logo"]["source"], "/usr/share/lyra-os/fastfetch/logo.txt"
        )
        logo = logo_path.read_text(encoding="utf-8")
        self.assertIn("$1█", logo)
        self.assertIn("$2──────────────────────────", logo)

        deploy = (
            ROOT / "installer/src/service/operations/deploy.rs"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'const DEFAULT_DESKTOP_SHELL: &str = "/usr/bin/fish";', deploy
        )
        self.assertIn("DEFAULT_DESKTOP_SHELL.to_string()", deploy)
        self.assertNotIn("ConfigureUserBashrc", deploy)
        self.assertNotIn('join(".bashrc")', deploy)

    def test_fish_z_state_is_always_owned_by_the_logged_in_user(self) -> None:
        early_defaults = (
            ROOT / "kiwi/root/etc/fish/conf.d/00-lyra-home.fish"
        ).read_text()
        image_config = (ROOT / "kiwi/config.sh").read_text()

        self.assertIn('set -gx Z_DATA_DIR "$XDG_DATA_HOME/z"', early_defaults)
        self.assertIn('set -gx Z_DATA "$Z_DATA_DIR/data"', early_defaults)
        self.assertNotIn("_ZO_DATA_DIR", early_defaults)
        self.assertIn("SETUVAR Z_DATA:/root/", image_config)
        self.assertIn("SETUVAR Z_DATA_DIR:/root/", image_config)

    def test_beta_two_uses_only_the_rust_installer(self) -> None:
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        packages = {node.attrib["name"] for node in root.findall("packages/package")}
        self.assertIn("lyra-installer", packages)
        self.assertNotIn("calamares", packages)
        self.assertFalse((ROOT / "kiwi/root/etc/calamares").exists())
        self.assertFalse(
            (ROOT / "kiwi/root/usr/share/applications/calamares.desktop").exists()
        )

        autostart = (
            ROOT / "kiwi/root/etc/xdg/autostart/lyra-installer-autostart.desktop"
        ).read_text(encoding="utf-8")
        self.assertIn("TryExec=/usr/bin/lyra-installer", autostart)
        self.assertIn("Exec=/usr/bin/lyra-install-lock /usr/bin/lyra-installer", autostart)
        self.assertIn("StartupWMClass=lyra-installer", autostart)

        self.assertNotIn("pkexec", autostart)

        packaged_wrapper = ROOT / "installer/packaging/lyra-install-lock"
        image_wrapper = ROOT / "kiwi/root/usr/bin/lyra-install-lock"
        self.assertEqual(image_wrapper.read_bytes(), packaged_wrapper.read_bytes())
        wrapper = image_wrapper.read_text(encoding="utf-8")
        self.assertIn("XDG_RUNTIME_DIR", wrapper)
        self.assertNotIn("/run/lock/lyra-install.lock", wrapper)
        self.assertNotEqual(image_wrapper.stat().st_mode & 0o111, 0)

        packaged_launcher = ROOT / "installer/packaging/org.lyraos.LyraInstaller.desktop"
        image_launcher = (
            ROOT
            / "kiwi/root/usr/share/applications/org.lyraos.LyraInstaller.desktop"
        )
        self.assertEqual(image_launcher.read_bytes(), packaged_launcher.read_bytes())

        packaged_icon = ROOT / "installer/src-tauri/icons/256x256.png"
        image_icon = (
            ROOT
            / "kiwi/root/usr/share/icons/hicolor/256x256/apps"
            / "org.lyraos.LyraInstaller.png"
        )
        self.assertEqual(image_icon.read_bytes(), packaged_icon.read_bytes())

        live_smoke = ROOT / "kiwi/root/usr/bin/lyra-live-smoke"
        self.assertTrue(live_smoke.is_file())
        self.assertNotEqual(live_smoke.stat().st_mode & 0o111, 0)
        deploy = (ROOT / "installer/src/service/operations/deploy.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn('"usr/bin/lyra-live-smoke"', deploy)

        update_smoke = ROOT / "kiwi/root/usr/bin/lyra-update-smoke"
        self.assertTrue(update_smoke.is_file())
        self.assertNotEqual(update_smoke.stat().st_mode & 0o111, 0)

    def test_installed_desktop_sudo_uses_the_user_password(self) -> None:
        deploy = (ROOT / "installer/src/service/operations/deploy.rs").read_text(
            encoding="utf-8"
        )
        changes = (ROOT / "installer/packaging/lyra-installer.changes").read_text(
            encoding="utf-8"
        )

        self.assertIn('"Defaults !targetpw\\n%wheel ALL=(ALL) ALL\\n"', deploy)
        self.assertIn("Defaults targetpw", changes)

    def test_chord_is_not_installed_or_pinned_on_the_desktop(self) -> None:
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        desktop_packages = {
            node.attrib["name"] for node in root.findall("packages/package")
        }
        self.assertNotIn("chord", desktop_packages)


    def test_bluetooth_and_screen_recording_are_installed_and_enabled(self) -> None:
        # Real gap found on an installed image: onlyRequired dropped both
        # (neither is a hard Requires of gnome_basic/gnome), so Bluetooth
        # never turned on and GNOME Shell's Ctrl+Shift+Alt+R screen
        # recorder silently failed while plain screenshots (a different,
        # non-GStreamer code path) kept working.
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        desktop_packages = {
            node.attrib["name"] for node in root.findall("packages/package")
        }
        for name in ("bluez", "bluez-firmware", "bluedevil6", "gstreamer-plugins-good"):
            self.assertIn(name, desktop_packages, name)

        config_sh = (ROOT / "kiwi/config.sh").read_text(encoding="utf-8")
        # Must be inside the display-manager block.
        desktop_branch = config_sh[
            config_sh.index("# Plasma display manager") : config_sh.index("# zram-generator")
        ]
        self.assertIn("suseInsertService bluetooth", desktop_branch)

    def test_desktop_installs_upower_for_battery_status(self) -> None:
        # onlyRequired kept libupower but omitted the daemon on Alpha 3. The
        # kernel exposed BAT1 normally, yet GNOME had no service from which to
        # obtain battery state and therefore displayed no battery icon.
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        desktop_packages = {
            node.attrib["name"] for node in root.findall("packages/package")
        }
        self.assertIn("upower", desktop_packages)

    def test_desktop_installs_explicit_alsa_userspace_stack(self) -> None:
        # PipeWire remains the desktop audio server, while these packages
        # provide ALSA hardware profiles, diagnostics and compatibility for
        # applications that do not use PipeWire directly.
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        desktop_packages = {
            node.attrib["name"] for node in root.findall("packages/package")
        }
        alsa_packages = {
            "alsa",
            "alsa-oss",
            "alsa-plugins",
            "alsa-plugins-speexrate",
            "alsa-plugins-upmix",
            "alsa-ucm-conf",
            "alsa-utils",
            "libatopology2",
        }
        self.assertTrue(alsa_packages.issubset(desktop_packages))

    def test_mozilla_apps_follow_installed_system_locale(self) -> None:
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        desktop_packages = {
            node.attrib["name"] for node in root.findall("packages/package")
        }
        self.assertIn("MozillaFirefox", desktop_packages)
        self.assertIn("MozillaFirefox-translations-common", desktop_packages)
        self.assertNotIn("MozillaFirefox-translations-other", desktop_packages)
        self.assertIn("MozillaThunderbird", desktop_packages)
        self.assertIn("MozillaThunderbird-translations-common", desktop_packages)
        self.assertNotIn("MozillaThunderbird-translations-other", desktop_packages)

        image_config = (ROOT / "kiwi/config.xml").read_text(encoding="utf-8")
        for locale in ("en_US", "pt_BR", "es_ES"):
            self.assertIn(locale, image_config)

        locales = root.findtext("preferences/locale")
        self.assertEqual(locales, "en_US,pt_BR,es_ES")

        installer_core = (ROOT / "installer/src/lib.rs").read_text(encoding="utf-8")
        self.assertIn('"pt_BR.UTF-8" | "en_US.UTF-8" | "es_ES.UTF-8"', installer_core)
        deploy = (
            ROOT / "installer/src/service/operations/deploy.rs"
        ).read_text(encoding="utf-8")
        self.assertIn('etc.join("locale.conf")', deploy)

        policies = json.loads(
            (
                ROOT
                / "kiwi/root/usr/lib64/firefox/distribution/policies.json"
            ).read_text(encoding="utf-8")
        )
        homepage = policies["policies"]["Homepage"]
        self.assertEqual(homepage["URL"], "https://lyraos.com.br/")
        self.assertEqual(homepage["StartPage"], "homepage")
        self.assertTrue(homepage["ShowHomeButton"])
        self.assertFalse(homepage["Locked"])
        preferences = policies["policies"].get("Preferences", {})
        self.assertNotIn("intl.locale.requested", preferences)

    def test_office_apps_and_locales_match_image_policy(self) -> None:
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        packages = {node.attrib["name"] for node in root.findall("packages/package")}
        libreoffice = {
            "libreoffice",
            "libreoffice-base",
            "libreoffice-calc",
            "libreoffice-draw",
            "libreoffice-impress",
            "libreoffice-math",
            "libreoffice-writer",
            "libreoffice-qt6",
            "libreoffice-l10n-en",
            "libreoffice-l10n-pt_BR",
            "libreoffice-l10n-es",
        }
        self.assertTrue(libreoffice.issubset(packages))

        self.assertIn("libreoffice-writer", packages)

    def test_desktop_app_curation_uses_vlc_without_gnome_software_or_monitor(self) -> None:
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        desktop_packages = {
            node.attrib["name"] for node in root.findall("packages/package")
        }

        self.assertIn("vlc", desktop_packages)
        self.assertIn("vlc-lang", desktop_packages)
        for name in (
            "vlc-codecs",
            "ffmpeg-7",
            "gstreamer-plugins-bad",
            "gstreamer-plugins-ugly",
            "gstreamer-plugins-libav",
            "gstreamer-plugins-good-extra",
            "ivtv-firmware",
            "bladeRF-fpga-firmware",
            "bladeRF-fx3-firmware",
        ):
            self.assertIn(name, desktop_packages, name)
        for incompatible_packman_addon in (
            "gstreamer-plugins-bad-codecs",
            "gstreamer-plugins-ugly-codecs",
        ):
            self.assertNotIn(incompatible_packman_addon, desktop_packages)
        for name in (
            "gnome-software",
            "gnome-software-lang",
            "gnome-software-plugin-packagekit",
            "gnome-system-monitor",
            "gnome-system-monitor-lang",
        ):
            self.assertNotIn(name, desktop_packages, name)

        language_remediation = (
            ROOT / "scripts/fix-gnome-lang-packages.sh"
        ).read_text(encoding="utf-8")
        self.assertNotIn("gnome-software", language_remediation)

    def test_installed_grub_theme_is_conditional_per_desktop_edition(self) -> None:
        deploy = (ROOT / "installer/src/service/operations/deploy.rs").read_text(
            encoding="utf-8"
        )
        self.assertIn("GRUB_THEME_PATH", deploy)
        self.assertIn("if theme.is_file()", deploy)
        self.assertIn('if key == "GRUB_THEME" && !theme.is_file()', deploy)
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        build_type = root.find("preferences/type")
        self.assertIsNotNone(build_type)
        self.assertEqual(build_type.attrib.get("editbootconfig"), "edit_boot_config.sh")
        hook_path = ROOT / "kiwi/edit_boot_config.sh"
        self.assertNotEqual(hook_path.stat().st_mode & 0o111, 0)
        hook = hook_path.read_text(encoding="utf-8")
        self.assertIn("sed -i '/^[[:space:]]*GRUB_THEME=/d'", hook)
        self.assertNotIn("GRUB_THEME_ASSET", hook)
        helper = (ROOT / "kiwi/test/build-and-run-vm.sh").read_text(encoding="utf-8")
        self.assertNotIn("IMAGE_INSTALLED_GRUB_THEME", helper)
        self.assertIn('"$KIWI_DESC/edit_boot_config.sh"', helper)

    def test_vm_helper_can_build_without_destroying_existing_vm(self) -> None:
        helper = (ROOT / "kiwi/test/build-and-run-vm.sh").read_text(encoding="utf-8")
        self.assertIn("--build-only", helper)
        self.assertIn('--signing-key "$PACKAGE_SIGNING_KEYRING"', helper)
        self.assertIn(
            "build-only complete; existing VM disk and UEFI state were not changed",
            helper,
        )
        iso_ready = helper.index('echo "--- ISO ready:')
        build_only_exit = helper.index("build-only complete; existing VM disk")
        qemu_requirements = helper.index("for command in qemu-img qemu-system-x86_64")
        destructive_vm_reset = helper.rindex("\nstop_previous_vm\n")
        self.assertLess(build_only_exit, qemu_requirements)
        self.assertLess(iso_ready, destructive_vm_reset)

    def test_vm_helper_validates_product_and_artifact_versions(self) -> None:
        helper = (ROOT / "kiwi/test/build-and-run-vm.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            r'VERSION_ID=\"$("$RELEASE_TOOL" field product_version)\"', helper
        )
        self.assertIn(
            r'IMAGE_VERSION=\"$("$RELEASE_TOOL" field version_id)\"', helper
        )

    def test_vm_helper_guards_host_loader_cache_during_kiwi_build(self) -> None:
        helper = (ROOT / "kiwi/test/build-and-run-vm.sh").read_text(encoding="utf-8")
        self.assertIn("host_loader_is_healthy", helper)
        self.assertIn("repair_host_loader_cache", helper)
        self.assertIn("start_loader_guard", helper)
        self.assertIn("stop_loader_guard", helper)
        self.assertIn("sudo -n ldconfig", helper)
        kiwi_build = helper.index("if run_privileged kiwi-ng")
        self.assertLess(helper.index("start_loader_guard"), kiwi_build)
        self.assertGreater(helper.rindex("stop_loader_guard"), kiwi_build)

    def test_vm_helper_can_boot_installed_disk_without_iso_or_reset(self) -> None:
        helper = (ROOT / "kiwi/test/build-and-run-vm.sh").read_text(encoding="utf-8")
        self.assertIn("--boot-installed", helper)
        self.assertIn('VM_MONITOR_SOCKET="$VM_DIR/qemu-monitor.sock"', helper)
        self.assertEqual(
            helper.count('-monitor "unix:$VM_MONITOR_SOCKET,server=on,wait=off"'),
            2,
        )
        self.assertIn('VM_ID_FILE="$VM_DIR/installation.uuid"', helper)
        self.assertEqual(helper.count('-uuid "$VM_UUID"'), 4)
        self.assertIn('VM_GUEST_EVIDENCE_FILE="$VM_DIR/upgrade-guest-evidence.jsonl"', helper)
        self.assertEqual(helper.count("name=org.lyraos.UpgradeEvidence"), 2)

    def test_upgrade_rehearsal_trace_is_atomic_and_bound_to_vm_artifacts(self) -> None:
        tool = ROOT / "kiwi/test/rehearsal-trace.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); disk, nvram, trace = root / "disk", root / "nvram", root / "trace.json"
            disk.write_bytes(b"disk"); nvram.write_bytes(b"nvram")
            base = [sys.executable, str(tool), "--trace", str(trace), "--uuid", "12345678-1234-4234-8234-123456789abc", "--disk", str(disk), "--nvram", str(nvram)]
            subprocess.run([*base, "--mode", "live"], check=True); subprocess.run([*base, "--mode", "installed"], check=True)
            document = json.loads(trace.read_text(encoding="utf-8")); self.assertEqual(document["status"], "in-progress"); self.assertEqual(document["qemu_launch_count"], 2)
            disk.unlink(); disk.write_bytes(b"replacement")
            self.assertNotEqual(subprocess.run([*base, "--mode", "installed"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode, 0)

    def test_vm_helper_summarizes_rehearsal_without_launching_qemu(self) -> None:
        helper = (ROOT / "kiwi/test/build-and-run-vm.sh").read_text(encoding="utf-8")
        self.assertIn("--summarize-upgrade", helper)
        self.assertIn("LYRA_REHEARSAL_OBSERVER", helper)
        self.assertIn("upgrade-rehearsal-observations.json", helper)
        self.assertIn("--baseline-build-id lyra-release-1.1", helper)
        self.assertIn("--target-build-id lyra-release-1.2-beta.1", helper)

    def test_vm_uses_supported_virtio_gtk_display(self) -> None:
        helper = (ROOT / "kiwi/test/build-and-run-vm.sh").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("-display spice-app", helper)
        self.assertIn("-display gtk", helper)
        self.assertNotIn("-vga qxl", helper)
        self.assertIn("-vga virtio", helper)
        self.assertIn('VM_MONITOR_SOCKET="$VM_DIR/qemu-monitor.sock"', helper)
        self.assertIn('-monitor "unix:$VM_MONITOR_SOCKET,server=on,wait=off"', helper)
        installed_branch = helper.index('if [ "$BOOT_INSTALLED" -eq 1 ]; then')
        installed_exit = helper.index('exit "$INSTALLED_QEMU_STATUS"')
        destructive_reset = helper.index('echo "--- deleting previous VM disk')
        self.assertLess(installed_branch, installed_exit)
        self.assertLess(installed_exit, destructive_reset)
        branch = helper[installed_branch:installed_exit]
        self.assertIn("-boot order=c,menu=on", branch)
        self.assertNotIn("-cdrom", branch)
        self.assertNotIn('rm -f "$DISK_IMG"', branch)
        self.assertIn("preserving VM disk and UEFI state", branch)

    def test_vm_helper_rejects_a_stale_published_installer(self) -> None:
        helper = (ROOT / "kiwi/test/build-and-run-vm.sh").read_text(encoding="utf-8")
        self.assertIn("grep -a -F 'bin/fish' \"$IMAGE_INSTALLER_SERVICE\"", helper)
        self.assertIn("grep -a -F '.bashrc' \"$IMAGE_INSTALLER_SERVICE\"", helper)
        self.assertNotIn('strings "$IMAGE_INSTALLER_SERVICE"', helper)
        self.assertIn("stale or incompatible installer RPM", helper)
        self.assertIn("build-source.txt", helper)

    def test_development_bootstrap_installs_obs_local_build_runner(self) -> None:
        bootstrap = (ROOT / "scripts/bootstrap-development.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("build rpm-build rpmdevtools rpmlint spec-cleaner osc", bootstrap)
        self.assertIn("git git-lfs gh osc build", bootstrap)

    def test_vm_helper_fully_extracts_squashfs_before_promoting_iso(self) -> None:
        helper = (ROOT / "kiwi/test/build-and-run-vm.sh").read_text(encoding="utf-8")
        extract_image = helper.index('-extract /LiveOS/squashfs.img "$ISO_SQUASHFS"')
        verify_rootfs = helper.index(
            "unsquashfs -processors 1 -no-xattrs -no-exit-code -f"
        )
        promote_iso = helper.index('echo "--- promoting new ISO')

        self.assertLess(extract_image, verify_rootfs)
        self.assertLess(verify_rootfs, promote_iso)
        self.assertIn("generated ISO contains an unreadable/corrupt live SquashFS", helper)
        self.assertIn("existing ISO contains an unreadable/corrupt live SquashFS", helper)
        self.assertIn("refusing to boot with --skip-build", helper)
        self.assertEqual(helper.count('validate_live_rootfs_homes "$SQUASHFS_VERIFY_DIR"'), 2)
        self.assertIn("refusing an ISO that may contain host build data", helper)
        self.assertEqual(helper.count('audit_live_rootfs \\'), 2)
        self.assertIn("generated-iso-security-audit.json", helper)
        self.assertIn("reused-iso-security-audit.json", helper)
        self.assertIn("failed the build-host data security audit", helper)

    def test_vm_helper_stages_description_without_python_bytecode(self) -> None:
        helper = (ROOT / "kiwi/test/build-and-run-vm.sh").read_text(encoding="utf-8")
        self.assertIn('BUILD_DESCRIPTION="$BUILD_DESCRIPTION_DIR"', helper)
        self.assertIn("-type d -name __pycache__ -prune -exec rm -rf -- {} +", helper)
        self.assertIn("-type f -name '*.pyc' -delete", helper)
        self.assertLess(
            helper.index("-type f -name '*.pyc' -delete"),
            helper.index('echo "--- building ISO with kiwi-ng'),
        )

    def test_kde_image_does_not_install_the_gnome_theme(self) -> None:
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        packages = {node.attrib["name"] for node in root.findall("packages/package")}
        self.assertNotIn("lyra-os-theme", packages)

    def test_kde_image_installs_sddm_xorg_input_driver(self) -> None:
        root = ET.parse(ROOT / "kiwi/config.xml").getroot()
        packages = {node.attrib["name"] for node in root.findall("packages/package")}
        helper = (ROOT / "kiwi/test/build-and-run-vm.sh").read_text(encoding="utf-8")

        self.assertIn("xf86-input-libinput", packages)
        self.assertIn("libinput_drv.so", helper)

    def test_live_sddm_accepts_empty_password_without_leaking_to_install(self) -> None:
        config = (ROOT / "kiwi/config.sh").read_text(encoding="utf-8")
        deploy = (
            ROOT / "installer/src/service/operations/deploy.rs"
        ).read_text(encoding="utf-8")
        helper = (ROOT / "kiwi/test/build-and-run-vm.sh").read_text(encoding="utf-8")

        for path in (
            "etc/pam.d/common-auth-lyra-live",
            "etc/pam.d/sddm",
            "etc/pam.d/sddm-autologin",
        ):
            self.assertIn(path, deploy)
        self.assertIn("pam_unix.so nullok try_first_pass", config)
        self.assertIn("account  required       pam_permit.so", config)
        self.assertIn("common-auth-lyra-live", helper)
        self.assertIn("pam_nologin.so", helper)

    def test_first_plasma_login_waits_for_screen_before_creating_default_layout(self) -> None:
        startup = (
            ROOT / "kiwi/root/usr/libexec/lyra-live-plasma-start"
        ).read_text(encoding="utf-8")
        autostart = (
            ROOT / "kiwi/root/etc/xdg/autostart/lyra-plasma-initialize.desktop"
        ).read_text(encoding="utf-8")
        deploy = (
            ROOT / "installer/src/service/operations/deploy.rs"
        ).read_text(encoding="utf-8")

        kdeglobals = (
            ROOT / "kiwi/root/etc/skel/.config/kdeglobals"
        ).read_text(encoding="utf-8")
        plasmarc = (
            ROOT / "kiwi/root/etc/skel/.config/plasmarc"
        ).read_text(encoding="utf-8")

        self.assertIn("kscreen-doctor -o", startup)
        self.assertNotIn("lookandfeeltool", startup)
        self.assertNotIn("--resetLayout", startup)
        self.assertIn("org.kde.PlasmaShell.evaluateScript", startup)
        self.assertIn('panelList[panelIndex].screen = 0', startup)
        self.assertIn("plasma-apply-wallpaperimage", startup)
        self.assertIn("2702-dawn.png", startup)
        self.assertIn("plasma-initialized", startup)
        self.assertIn("ColorScheme=BreezeDark", kdeglobals)
        self.assertIn(
            "LookAndFeelPackage=org.kde.breezedark.desktop", kdeglobals
        )
        self.assertIn("name=breeze-dark", plasmarc)
        self.assertIn("Exec=/usr/libexec/lyra-live-plasma-start", autostart)
        live_only = deploy.split("const LIVE_ONLY_ARTIFACTS", 1)[1].split("];", 1)[0]
        self.assertNotIn('"usr/libexec/lyra-live-plasma-start",', live_only)
        self.assertNotIn(
            '"etc/xdg/autostart/lyra-plasma-initialize.desktop",', live_only
        )

    def test_kde_image_uses_native_lyra_sddm_theme(self) -> None:
        theme = ROOT / "kiwi/root/usr/share/sddm/themes/lyra"
        main = (theme / "Main.qml").read_text(encoding="utf-8")
        config = (theme / "theme.conf").read_text(encoding="utf-8")
        selection = (
            ROOT / "kiwi/root/etc/sddm.conf.d/20-lyra-theme.conf"
        ).read_text(encoding="utf-8")
        breeze_override = (
            ROOT
            / "kiwi/root/usr/share/sddm/themes/breeze/theme.conf.user"
        ).read_text(encoding="utf-8")

        self.assertTrue((theme / "metadata.desktop").is_file())
        self.assertTrue((theme / "logo.svg").is_file())
        self.assertIn("Current=breeze", selection)
        self.assertIn("2702-dawn.png", config)
        self.assertIn("2702-dawn.png", breeze_override)
        self.assertIn("/usr/share/sddm/themes/lyra/logo.svg", breeze_override)
        self.assertNotIn("Current=lyra", selection)
        schema_files = list(
            (ROOT / "kiwi/root/usr/share/glib-2.0/schemas").glob("*.gschema.override")
        )
        self.assertEqual(schema_files, [])

    def test_vm_helper_keeps_build_output_outside_the_source_checkout(self) -> None:
        helper = (ROOT / "kiwi/test/build-and-run-vm.sh").read_text(encoding="utf-8")
        alpha6 = (ROOT / "scripts/build-desktop-alpha6.sh").read_text(encoding="utf-8")
        alpha7 = (ROOT / "scripts/build-desktop-alpha7.sh").read_text(encoding="utf-8")
        upload = (ROOT / "scripts/upload-desktop-alpha6-sourceforge.sh").read_text(
            encoding="utf-8"
        )
        safe_default = "/var/tmp/lyraos-desktop-test-$(id -u)"
        self.assertIn("Work directory must be outside the repository", helper)
        self.assertNotIn('$KIWI_DESC/.kiwi/test-$CURRENT_UID', helper)
        self.assertIn(safe_default, alpha6)
        self.assertIn("build-desktop-alpha6.sh", alpha7)
        self.assertIn(safe_default, upload)

    def test_export_is_derived_from_canonical_kiwi_without_duplicate_package_list(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "export"
            real_git = image_build.git
            with mock.patch.object(
                image_build,
                "git",
                side_effect=lambda *args: "" if args[0] == "status" else real_git(*args),
            ):
                image_build.export(self.manifest, destination, "HEAD", allow_dirty=False)
            image_build.verify_export(self.manifest, destination)
            canonical = ET.parse(ROOT / "kiwi/config.xml").getroot()
            exported = ET.parse(destination / self.manifest.description).getroot()
            canonical_packages = [node.attrib["name"] for node in canonical.findall("packages/package")]
            exported_packages = [node.attrib["name"] for node in exported.findall("packages/package")]
            self.assertEqual(exported_packages, canonical_packages)
            self.assertFalse((destination / "_multibuild").exists())
            self.assertEqual(
                image_build.sha256(
                    destination / "keys/obs-package-signing-keyring.asc"
                ),
                image_build.sha256(image_build.PACKAGE_SIGNING_KEYRING),
            )
            self.assertEqual(
                image_build.sha256(destination / "config.xml"),
                image_build.sha256(ROOT / "kiwi/config.xml"),
            )
            source = json.loads((destination / "build-source.json").read_text(encoding="utf-8"))
            self.assertRegex(source["commit"], r"^[0-9a-f]{40}$")
            self.assertFalse(source["dirty"])
            self.assertTrue((destination / "root.tar.gz").is_file())

    def test_root_archive_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first"
            second = Path(temporary) / "second"
            real_git = image_build.git
            with mock.patch.object(
                image_build,
                "git",
                side_effect=lambda *args: "" if args[0] == "status" else real_git(*args),
            ):
                image_build.export(self.manifest, first, "HEAD", allow_dirty=False)
                image_build.export(self.manifest, second, "HEAD", allow_dirty=False)
            self.assertEqual(
                image_build.sha256(first / "root.tar.gz"),
                image_build.sha256(second / "root.tar.gz"),
            )

    def test_export_refuses_nonempty_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            (destination / "existing").write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(image_build.PolicyError, "not empty"):
                image_build.export(self.manifest, destination, "HEAD", allow_dirty=True)

    def test_dirty_inspection_export_cannot_pass_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "export"
            real_git = image_build.git
            with mock.patch.object(
                image_build,
                "git",
                side_effect=lambda *args: " M kiwi/config.xml" if args[0] == "status" else real_git(*args),
            ):
                image_build.export(self.manifest, destination, "HEAD", allow_dirty=True)
            with self.assertRaisesRegex(image_build.PolicyError, "source identity"):
                image_build.verify_export(self.manifest, destination)


class ArtifactTests(unittest.TestCase):
    def alpha8_release_file(self, directory: Path) -> Path:
        path = directory / "release-alpha8.toml"
        path.write_text(
            """[release]
version = "1.0"\nbase_distribution = "opensuse-leap"\nbase_version = "16.1"
stage = "alpha"
iteration = 8
codename = "Odisseia"
codename_id = "odisseia"
image_name = "lyra-os"
architecture = "x86_64"
""",
            encoding="utf-8",
        )
        return path

    def create_artifacts(self, directory: Path) -> None:
        (directory / "lyra.iso").write_bytes(b"iso")
        (directory / "lyra.iso.manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "version": image_build.version_id(),
                    "source": {"commit": "a" * 40, "dirty": False},
                    "iso": {
                        "filename": "lyra.iso",
                        "sha256": image_build.sha256(directory / "lyra.iso"),
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (directory / "lyra.packages").write_text(
            "fina|(none)|0.4.0|12.1|x86_64|obs://build.opensuse.org/"
            "home:rodrigosbrito:fina/repo/revision-fina|MIT\n",
            encoding="utf-8",
        )
        (directory / "lyra.verified").write_text("verified\n", encoding="utf-8")
        (directory / "lyra.report").write_text("<report/>\n", encoding="utf-8")
        (directory / "lyra.iso.sha256").write_text(
            "checksum  lyra.iso\n", encoding="utf-8"
        )
        (directory / "lyra.iso.sha256.asc").write_text(
            "signature\n", encoding="utf-8"
        )
        (directory / "lyra.cdx.json").write_text("{}\n", encoding="utf-8")
        (directory / "lyra.spdx.json").write_text("{}\n", encoding="utf-8")

    def create_test_results(
        self, manifest: image_build.Manifest, directory: Path
    ) -> list[str]:
        results = []
        for name in manifest.required_test_results:
            path = directory / f"{name}.json"
            if name == "obs-repositories":
                document = {
                    "schema": 1,
                    "status": "passed",
                    "projects": [{"packages": ["fina"], "targets": ["Leap"]}],
                }
            elif name == "hardware-matrix":
                document = {
                    "schema": 1,
                    "status": "passed",
                    "mode": "hardware-matrix",
                    "iso": {
                        "filename": "lyra.iso",
                        "sha256": image_build.sha256(directory / "lyra.iso"),
                    },
                    "coverage": {
                        "desktops": 1,
                        "notebooks": 2,
                        "cpu_vendors": ["amd", "intel"],
                        "gpu_vendors": ["amd", "intel"],
                    },
                    "scenarios": [{"machine": str(index)} for index in range(3)],
                }
            else:
                modes = {
                    "live-session": "live-session",
                    "installer": "installer",
                    "first-boot": "first-boot",
                    "uefi-secure-boot": "uefi-secure-boot",
                    "rollback": "rollback",
                }
                document = {
                    "schema": 1,
                    "status": "passed",
                    "mode": modes[name],
                    "checks": [{"id": "fixture", "status": "passed"}],
                }
                if name == "rollback":
                    document["phase"] = "rollback-verified"
            path.write_text(json.dumps(document) + "\n", encoding="utf-8")
            results.append(f"{name}={path}")
        return results

    def test_manifest_hashes_all_evidence_and_records_exact_package_sources(self) -> None:
        manifest = image_build.Manifest.load()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.create_artifacts(directory)
            output = directory / "manifest.json"
            tests = self.create_test_results(manifest, directory)
            real_git = image_build.git
            with mock.patch.object(
                image_build,
                "git",
                side_effect=lambda *args: "" if args[0] == "status" else real_git(*args),
            ):
                image_build.artifact_manifest(manifest, directory, output, tests)
            document = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                set(document["artifacts"]),
                set(image_build.required_artifact_roles(manifest, image_build.RELEASE)),
            )
            self.assertNotIn("checksum_signature", document["artifacts"])
            self.assertEqual(document["packages"][0]["license"], "MIT")
            self.assertIn("revision-fina", document["packages"][0]["source"])
            self.assertEqual(
                set(document["test_results"]), set(manifest.required_test_results)
            )
            self.assertFalse(document["source"]["dirty"])
            self.assertEqual(document["source"]["commit"], "a" * 40)

    def test_manifest_rejects_iso_build_manifest_with_wrong_checksum(self) -> None:
        manifest = image_build.Manifest.load()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.create_artifacts(directory)
            build_manifest_path = directory / "lyra.iso.manifest.json"
            build_manifest = json.loads(build_manifest_path.read_text(encoding="utf-8"))
            build_manifest["iso"]["sha256"] = "0" * 64
            build_manifest_path.write_text(
                json.dumps(build_manifest) + "\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                image_build.PolicyError, "does not match the candidate ISO"
            ):
                image_build.artifact_manifest(
                    manifest,
                    directory,
                    directory / "manifest.json",
                    self.create_test_results(manifest, directory),
                )

    def test_alpha_manifest_accepts_checksum_without_detached_signature(self) -> None:
        manifest = image_build.Manifest.load()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.create_artifacts(directory)
            (directory / "lyra.iso.sha256.asc").unlink()
            output = directory / "manifest.json"
            tests = self.create_test_results(manifest, directory)
            real_git = image_build.git
            with mock.patch.object(
                image_build,
                "git",
                side_effect=lambda *args: "" if args[0] == "status" else real_git(*args),
            ):
                image_build.artifact_manifest(manifest, directory, output, tests)
            document = json.loads(output.read_text(encoding="utf-8"))
            self.assertNotIn("checksum_signature", document["artifacts"])

    def test_alpha8_adds_upgrade_compliance_i18n_and_freeze_evidence(self) -> None:
        manifest = image_build.Manifest.load()
        with tempfile.TemporaryDirectory() as temporary:
            release_file = self.alpha8_release_file(Path(temporary))
            required = set(image_build.required_test_result_names(manifest, release_file))
        self.assertEqual(required - set(manifest.required_test_results), image_build.ALPHA8_TEST_RESULTS)

    def test_upgrade_rehearsal_requires_faults_reboot_signature_and_rollback(self) -> None:
        valid = {
            "schema": 1,
            "status": "passed",
            "mode": "upgrade-rehearsal",
            "phase": "rollback-verified",
            "checks": [{"id": "successor", "status": "passed"}],
            "facts": {
                "baseline_version": "1.0",
                "target_version": "1.0.1",
                "manifest_signature_verified": True,
                "offline_applied": True,
                "reboot_count": 2,
                "rollback_baseline_verified": True,
                "fault_scenarios": [
                    "network-loss", "low-space", "ui-terminated",
                    "state-truncated", "rpm-failure", "initramfs-failure",
                ],
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            iso = Path(temporary) / "candidate.iso"
            iso.write_bytes(b"iso")
            image_build.validate_test_result("upgrade-rehearsal", valid, iso_path=iso)
            valid["facts"]["fault_scenarios"].remove("initramfs-failure")
            with self.assertRaisesRegex(image_build.PolicyError, "incomplete"):
                image_build.validate_test_result("upgrade-rehearsal", valid, iso_path=iso)

    def test_freeze_gate_is_fail_closed_and_has_fixed_locale_scope(self) -> None:
        valid = {
            "schema": 1,
            "status": "passed",
            "mode": "feature-freeze",
            "checks": [{"id": "scope", "status": "passed"}],
            "decision": "GO",
            "open_p0": 0,
            "open_p1": 0,
            "locales": ["en-US", "pt-BR", "es-ES"],
            "all_features_implemented_or_removed": True,
            "documentation_consistent": True,
        }
        with tempfile.TemporaryDirectory() as temporary:
            iso = Path(temporary) / "candidate.iso"
            iso.write_bytes(b"iso")
            image_build.validate_test_result("feature-freeze", valid, iso_path=iso)
            valid["open_p1"] = 1
            with self.assertRaisesRegex(image_build.PolicyError, "not eligible"):
                image_build.validate_test_result("feature-freeze", valid, iso_path=iso)

    def test_eca_and_i18n_gates_require_the_fixed_three_locale_scope(self) -> None:
        common = {
            "schema": 1,
            "status": "passed",
            "checks": [{"id": "coverage", "status": "passed"}],
            "locales": ["en-US", "pt-BR", "es-ES"],
        }
        eca = {
            **common,
            "mode": "eca-digital",
            "legal_review": "review-1",
            "security_review": "review-2",
            "privacy_impact_assessment": "review-3",
            "negative_and_evasion_tests": True,
            "retains_sensitive_age_evidence": False,
        }
        i18n = {**common, "mode": "i18n", "fallback": "en-US"}
        with tempfile.TemporaryDirectory() as temporary:
            iso = Path(temporary) / "candidate.iso"
            iso.write_bytes(b"iso")
            image_build.validate_test_result("eca-digital", eca, iso_path=iso)
            image_build.validate_test_result("i18n", i18n, iso_path=iso)
            eca["retains_sensitive_age_evidence"] = True
            with self.assertRaisesRegex(image_build.PolicyError, "incomplete"):
                image_build.validate_test_result("eca-digital", eca, iso_path=iso)

    def test_beta_manifest_rejects_missing_detached_signature(self) -> None:
        manifest = image_build.Manifest.load()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.create_artifacts(directory)
            (directory / "lyra.iso.sha256.asc").unlink()
            output = directory / "manifest.json"
            tests = self.create_test_results(manifest, directory)
            real_release_values = image_build.release_values

            def beta_release(path: Path = image_build.RELEASE) -> dict[str, object]:
                values = real_release_values(path)
                return {**values, "stage": "beta", "iteration": 1}

            with mock.patch.object(image_build, "release_values", side_effect=beta_release):
                with self.assertRaisesRegex(
                    image_build.PolicyError, "checksum signature.*found 0"
                ):
                    image_build.artifact_manifest(manifest, directory, output, tests)

    def test_manifest_rejects_missing_or_failed_release_evidence(self) -> None:
        manifest = image_build.Manifest.load()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.create_artifacts(directory)
            failed = directory / "obs.json"
            failed.write_text('{"schema":1,"status":"failed"}\n', encoding="utf-8")
            with self.assertRaisesRegex(image_build.PolicyError, "did not pass"):
                image_build.artifact_manifest(
                    manifest,
                    directory,
                    directory / "manifest.json",
                    [f"obs-repositories={failed}"],
                )

    def test_hardware_matrix_with_a_single_machine_still_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            iso = Path(temporary) / "lyra.iso"
            iso.write_bytes(b"iso payload")
            result = image_build.validate_test_result(
                "hardware-matrix",
                {
                    "schema": 1,
                    "status": "passed",
                    "mode": "hardware-matrix",
                    "iso": {
                        "filename": iso.name,
                        "sha256": image_build.sha256(iso),
                    },
                    "coverage": {
                        "desktops": 1,
                        "notebooks": 0,
                        "cpu_vendors": ["amd"],
                        "gpu_vendors": ["amd"],
                        "gap": ["notebooks<2", "cpu:intel", "gpu:intel"],
                    },
                    "scenarios": [{"machine": "only-physical-machine"}],
                },
                iso_path=iso,
            )
            self.assertEqual(result["coverage"]["gap"], ["notebooks<2", "cpu:intel", "gpu:intel"])

    def test_manifest_rejects_empty_passed_or_mislabeled_evidence(self) -> None:
        manifest = image_build.Manifest.load()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.create_artifacts(directory)
            empty = directory / "empty.json"
            empty.write_text('{"schema":1,"status":"passed"}\n', encoding="utf-8")
            with self.assertRaisesRegex(image_build.PolicyError, "mode"):
                image_build.validate_test_result(
                    "first-boot",
                    json.loads(empty.read_text(encoding="utf-8")),
                    iso_path=directory / "lyra.iso",
                )


if __name__ == "__main__":
    unittest.main()
