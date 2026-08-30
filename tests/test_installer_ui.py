from __future__ import annotations

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "installer" / "ui"


class IdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element_id = dict(attrs).get("id")
        if element_id:
            self.ids.append(element_id)


class InstallerUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = (UI / "index.html").read_text(encoding="utf-8")
        self.css = (UI / "styles.css").read_text(encoding="utf-8")
        self.javascript = (UI / "app.js").read_text(encoding="utf-8")
        self.i18n = (UI / "i18n.js").read_text(encoding="utf-8")

    def test_element_ids_are_unique(self) -> None:
        parser = IdCollector()
        parser.feed(self.html)
        duplicates = sorted({element_id for element_id in parser.ids if parser.ids.count(element_id) > 1})
        self.assertEqual(duplicates, [])

    def test_final_install_flow_lives_in_bottom_action_area(self) -> None:
        footer = self.html.split('<footer class="actions">', 1)[1].split("</footer>", 1)[0]
        controls = ("install-confirm", "install", "install-status", "reboot")
        positions = []
        for element_id in controls:
            marker = re.search(rf'id="{re.escape(element_id)}"', footer)
            self.assertIsNotNone(marker, f"{element_id} must be in the bottom action area")
            positions.append(marker.start())
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("execution-events", self.html)

    def test_final_flow_replaces_each_control_in_sequence(self) -> None:
        self.assertIn(
            "installConfirmControl.hidden=current!==6||installConfirm.checked||installing||installationTerminal",
            self.javascript,
        )
        self.assertIn(
            "install.hidden=current!==6||!installConfirm.checked||installing||installationTerminal",
            self.javascript,
        )
        self.assertIn("installStatus.hidden=true;\n      reboot.hidden=false;", self.javascript)
        self.assertNotIn("executionEvents", self.javascript)

    def test_final_controls_are_right_aligned(self) -> None:
        self.assertRegex(
            self.css,
            r"\.final-actions\{[^}]*justify-content:flex-end",
        )
        self.assertRegex(self.css, r"\.install-confirm\{[^}]*text-align:right")
        self.assertRegex(self.css, r"\.install-status\{[^}]*text-align:right")

    def test_text_and_select_controls_use_larger_consistent_type(self) -> None:
        self.assertIn("--form-control-font-size:13px", self.css)
        selectors = (
            ".form-grid input",
            ".keyboard-search input",
            ".manual-entry-row input",
            ".lvm-preset-row select",
            ".lv-row input",
            ".lv-row select",
        )
        rule = ",".join(selectors) + "{font-size:var(--form-control-font-size)}"
        self.assertIn(rule, self.css)

    def test_storage_only_offers_the_supported_direct_disk_layout(self) -> None:
        for unsupported in ("layout-choice", "raid-level-row", "lvm-editor", "manual-entry-row"):
            self.assertNotIn(f'id="{unsupported}"', self.html)
        self.assertNotIn("NewRaid", self.javascript)
        self.assertNotIn("NewVolumeGroup", self.javascript)
        self.assertIn("volume_layer:'Direct'", self.javascript)

    def test_language_picker_only_offers_backend_supported_locales(self) -> None:
        language_block = self.javascript.split("const languages=[", 1)[1].split("];", 1)[0]
        locales = re.findall(
            r"^\s{2}\['([a-z]{2}_[A-Z]{2}\.UTF-8)'", language_block, re.MULTILINE
        )
        self.assertEqual(locales, ["en_US.UTF-8", "pt_BR.UTF-8", "es_ES.UTF-8"])

        core = (ROOT / "installer/src/lib.rs").read_text(encoding="utf-8")

    def test_installer_language_has_english_default_and_catalog_fallback(self) -> None:
        self.assertIn("const DEFAULT_LOCALE='en_US.UTF-8'", self.javascript)
        self.assertIn("i18n.apply(uiLocale(event.target.value))", self.javascript)
        self.assertIn("'en-US':{", self.i18n)
        self.assertIn("'pt-BR':{", self.i18n)
        self.assertIn("'es-ES':{", self.i18n)
        self.assertIn("lookup(catalogs['en-US'],key)", self.i18n)
        self.assertIn("function register(locale,catalog)", self.i18n)
        self.assertIn('<script src="i18n.js"></script>', self.html)

    def test_welcome_highlight_is_flavor_neutral_security(self) -> None:
        combined = "\n".join((self.html, self.i18n))

        for desktop in ("Integrated GNOME", "Integrated KDE", "GNOME integrado", "KDE integrado"):
            self.assertNotIn(desktop, combined)
        self.assertNotIn('<ellipse cx="17" cy="20"', self.html)
        self.assertIn('M16 3 27 7v8c0 7-4.6 11.8-11 14', self.html)
        for label in ("Security", "Segurança", "Seguridad"):
            self.assertIn(
                f".feature-item:nth-child(2) strong':'{label}'",
                self.i18n,
            )

    def test_install_progress_does_not_expose_backend_portuguese_descriptions(self) -> None:
        progress = self.javascript.split("function showExecutionEvent", 1)[1].split(
            "function setInstallationStatus", 1
        )[0]
        self.assertIn("i18n.t('installing')", progress)
        self.assertNotIn("payload.name", progress)
        self.assertNotIn("payload.message", progress)
        for key in ("installAuthorizing", "installStarted", "installing", "installFailed", "installCompleted"):
            self.assertGreaterEqual(self.i18n.count(f"{key}:"), 3)

    def test_validation_and_reboot_messages_follow_selected_locale(self) -> None:
        validation = self.javascript.split("function validate()", 1)[1].split(
            "function suggestedUsername", 1
        )[0]
        self.assertNotIn("obrigatório", validation)
        self.assertNotIn("inválido", validation)
        self.assertIn("errors.map(key=>i18n.t(key))", validation)
        for key in (
            "fullNameRequired",
            "invalidUsername",
            "invalidHostname",
            "passwordTooShort",
            "passwordMismatch",
            "unsupportedLocale",
            "unsupportedTimezone",
            "unsupportedKeyboard",
            "rebooting",
            "rebootFailed",
        ):
            self.assertGreaterEqual(self.i18n.count(f"{key}:"), 3)

        restart = self.javascript.split("async function restartSystem()", 1)[1].split(
            "next.addEventListener", 1
        )[0]
        self.assertIn("i18n.t('rebooting')", restart)
        self.assertIn("i18n.t('rebootLabel')", restart)
        self.assertIn("i18n.t('rebootFailed')", restart)
        self.assertNotIn("Não foi possível", restart)

    def test_dynamic_storage_and_plan_text_uses_catalogs(self) -> None:
        for key in (
            "diskLiveMedia",
            "diskRaidMember",
            "diskLvmMember",
            "diskWillErase",
            "diskAvailable",
            "espReuse",
            "espCreate",
            "planErased",
            "erasedPartition",
            "unknownFilesystem",
            "mountedAt",
            "calculatingPlan",
            "confirmErase",
            "storageDiscoveryFailed",
            "planFailed",
        ):
            self.assertGreaterEqual(self.i18n.count(f"{key}:"), 3)
            self.assertIn(f"i18n.t('{key}'", self.javascript)

        self.assertNotIn('class="disk-plan-error">${error}', self.javascript)
        self.assertIn("if(selectedPlan) renderPlan(selectedPlan)", self.javascript)
        self.assertIn("function localizedErasedItems()", self.javascript)
        self.assertNotIn("plan.destructive_summary.erased", self.javascript)
        self.assertNotIn("plan.warnings.map", self.javascript)

    def test_keyboard_cards_do_not_expose_portuguese_variant_descriptions(self) -> None:
        renderer = self.javascript.split("function renderKeyboardCards", 1)[1].split(
            "const transportLabel", 1
        )[0]
        self.assertIn("i18n.t(`keyboardGroup.", renderer)
        self.assertNotIn("<small>${variant}", renderer)
        for key in ("language", "europe", "latinAmerica", "nordic", "cyrillic", "middleEast", "asia"):
            self.assertGreaterEqual(self.i18n.count(f"{key}:'"), 3)

    def test_accessible_names_follow_the_selected_locale(self) -> None:
        self.assertIn("catalogs[current].attributes", self.i18n)
        self.assertIn("element.setAttribute(name,value)", self.i18n)
        for selector in (".rail|aria-label", ".brand-logo|alt", ".timezone-map|aria-label", ".final-art img|alt"):
            self.assertEqual(self.i18n.count(f"'{selector}'"), 3)

    def test_language_flag_is_inline_with_language_name(self) -> None:
        self.assertIn(
            '<strong><span class="language-flag" aria-hidden="true">${flag}</span>${name}</strong>',
            self.javascript,
        )
        self.assertNotIn('class="choice-flag"', self.javascript)

    def test_timezone_map_pins_track_supported_backend_zones(self) -> None:
        self.assertIn('class="timezone-map"', self.html)
        self.assertIn('href="assets/world-map-noborders.svg"', self.html)
        self.assertIn("timezones=await invoke('list_timezones')", self.javascript)
        self.assertIn("#timezone-marker", self.javascript)
        self.assertIn("function projectTimezone(latitude,longitude)", self.javascript)
        self.assertIn("const robinsonX=", self.javascript)
        self.assertIn("const mapCentralMeridian=11.25", self.javascript)
        self.assertIn("const mapLatitudeCompression=.95623", self.javascript)
        self.assertNotIn('<select id="region">', self.html)
        self.assertIn('<select id="timezone">', self.html)
        self.assertIn('id="map-zoom-in"', self.html)
        self.assertIn('id="map-zoom-out"', self.html)
        self.assertIn("const mapZoomLevels=[100,125,150,200]", self.javascript)
        self.assertIn("setMapZoom(mapZoomIndex+1)", self.javascript)
        self.assertIn("setMapZoom(mapZoomIndex-1)", self.javascript)
        self.assertIn("mapCanvas.addEventListener('pointermove'", self.javascript)
        self.assertIn("mapCanvas.setPointerCapture(event.pointerId)", self.javascript)
        self.assertRegex(self.css, r"\.marker-label\{[^}]*opacity:0")
        self.assertIn('#timezone-marker:hover .marker-label', self.css)


if __name__ == "__main__":
    unittest.main()
