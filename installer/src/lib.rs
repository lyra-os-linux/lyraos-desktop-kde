//! Domain model shared by the installer UI and privileged backend.

pub mod service;
pub mod storage;

use serde::{Deserialize, Serialize};

/// Values collected by the unprivileged graphical wizard.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct InstallConfig {
    pub locale: String,
    /// IANA zone name, e.g. `America/Sao_Paulo` — one of `ui/index.html`'s
    /// `#timezone` options. The wizard sends this typed value to the
    /// privileged service only after summary validation and destructive
    /// confirmation.
    pub timezone: String,
    /// One of `ui/app.js`'s `keyboardLayouts` ids (e.g. `br-abnt2`,
    /// `us-intl`, `dvorak`) — see [`KEYBOARD_LAYOUTS`] for how each maps to
    /// a real XKB layout/variant.
    pub keyboard_layout: String,
    pub hostname: String,
    pub full_name: String,
    pub username: String,
    pub password: String,
}

/// Wizard keyboard-picker id -> real XKB `(layout, variant)`, verified
/// against a real system's own `/usr/share/X11/xkb/rules/base.lst` (via
/// `localectl list-x11-keymap-layouts`/`-variants`), not guessed from
/// familiar-looking codes. `None` means the base layout needs no variant
/// suffix (e.g. `br` alone already is ABNT2; `ch` alone already is
/// German-Swiss QWERTZ — neither has a `-abnt2`/`-de` variant on real
/// xkeyboard-config).
///
/// Two ids don't back the language their UI label promises, on purpose,
/// not by oversight:
/// - `ua` (Ukrainian) — the wizard used to call this `uk`, but XKB has no
///   `uk` layout at all (`gb` already owns British English); real code is
///   `ua`. `ui/app.js` was fixed to match.
/// - `la` ("Latina"/classical Latin in the UI) is deliberately **not**
///   backed by XKB's actual `la` code, which is Lao (Laos) — a completely
///   unrelated language. Classical Latin has no dedicated XKB layout
///   anywhere upstream and needs nothing beyond the base Latin alphabet,
///   so this maps to `us` instead of the wrong language.
///
/// Several non-Latin entries (`ja`/`ko`/`zh-pinyin`/`th`/`ar`/`fa`/`he`)
/// only get raw XKB key-level typing this way, not full input-method
/// conversion (Pinyin→Hanzi, Kana→Kanji, …) — that needs `ibus` engine
/// packages (e.g. `ibus-libpinyin`), and `kiwi/config.xml` doesn't install
/// any yet. Full input-method support is an image-content concern rather
/// than an XKB layout setting and remains outside this installer module.
pub const KEYBOARD_LAYOUTS: &[(&str, &str, Option<&str>)] = &[
    ("br-abnt2", "br", None),
    ("br", "br", None),
    ("pt", "pt", None),
    ("us", "us", None),
    ("us-intl", "us", Some("intl")),
    ("gb", "gb", None),
    ("ca", "ca", Some("multix")),
    ("ie", "ie", None),
    ("es", "es", None),
    ("latam", "latam", None),
    ("fr", "fr", None),
    ("be", "be", None),
    ("de", "de", None),
    ("ch-de", "ch", None),
    ("it", "it", None),
    ("nl", "nl", None),
    ("se", "se", None),
    ("no", "no", None),
    ("dk", "dk", None),
    ("fi", "fi", None),
    ("is", "is", None),
    ("pl", "pl", None),
    ("cz", "cz", None),
    ("sk", "sk", None),
    ("hu", "hu", None),
    ("ro", "ro", None),
    ("tr", "tr", None),
    ("ru", "ru", None),
    ("ua", "ua", None),
    ("bg", "bg", Some("phonetic")),
    ("el", "gr", None),
    ("he", "il", None),
    ("ar", "ara", None),
    ("fa", "ir", None),
    ("ja", "jp", None),
    ("ko", "kr", None),
    ("zh-pinyin", "cn", None),
    ("th", "th", None),
    ("in", "in", Some("eng")),
    ("pk", "pk", None),
    ("la", "us", None),
    ("dvorak", "us", Some("dvorak")),
    ("colemak", "us", Some("colemak")),
];

impl Default for InstallConfig {
    fn default() -> Self {
        Self {
            locale: "en_US.UTF-8".into(),
            timezone: "America/Sao_Paulo".into(),
            keyboard_layout: "br-abnt2".into(),
            hostname: "lyra-os".into(),
            full_name: String::new(),
            username: String::new(),
            password: String::new(),
        }
    }
}

impl InstallConfig {
    /// Validate user-controlled values before they cross the privilege boundary.
    pub fn validate(&self) -> Result<(), Vec<&'static str>> {
        let mut errors = Vec::new();

        if !matches!(
            self.locale.as_str(),
            "pt_BR.UTF-8" | "en_US.UTF-8" | "es_ES.UTF-8"
        ) {
            errors.push("validation.unsupportedLocale");
        }
        let timezone_path = std::path::Path::new("/usr/share/zoneinfo").join(&self.timezone);
        let valid_timezone_name = self.timezone == "UTC"
            || (self.timezone.contains('/')
                && self.timezone.split('/').all(|part| {
                    !part.is_empty()
                        && part != "."
                        && part != ".."
                        && part.bytes().all(|byte| {
                            byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'+')
                        })
                }));
        if !valid_timezone_name || !timezone_path.is_file() {
            errors.push("validation.unsupportedTimezone");
        }
        if !KEYBOARD_LAYOUTS
            .iter()
            .any(|(id, ..)| *id == self.keyboard_layout)
        {
            errors.push("validation.unsupportedKeyboard");
        }
        if !valid_hostname(&self.hostname) {
            errors.push("validation.invalidHostname");
        }
        errors.extend(validate_account(
            &self.full_name,
            &self.username,
            &self.password,
        ));

        if errors.is_empty() {
            Ok(())
        } else {
            Err(errors)
        }
    }
}

// Linux permits at most 32 pages per argv string, including its NUL. The
// supported x86_64 image uses 4 KiB pages. chpasswd (shadow/glibc) reads each
// username:password\n record into BUFSIZ=8192, including the final NUL.
const MAX_ACCOUNT_COMMENT_BYTES: usize = 128 * 1024 - 1;
const MAX_CHPASSWD_RECORD_BYTES: usize = 8191;

pub(crate) fn validate_account(
    full_name: &str,
    username: &str,
    password: &str,
) -> Vec<&'static str> {
    let mut errors = Vec::new();
    if full_name.trim().is_empty() {
        errors.push("validation.fullNameRequired");
    } else if full_name.len() > MAX_ACCOUNT_COMMENT_BYTES
        || full_name
            .bytes()
            .any(|byte| matches!(byte, 0 | b':' | b'\n'))
    {
        // useradd -c rejects ':' and LF; exec cannot carry an embedded NUL.
        errors.push("validation.invalidFullName");
    }
    if !valid_username(username) {
        errors.push("validation.invalidUsername");
    }
    if password.chars().count() < 8 {
        errors.push("validation.passwordTooShort");
    }
    if password.bytes().any(|byte| matches!(byte, 0 | b'\n')) {
        // LF starts another account record. NUL truncates C/PAM strings.
        // Colons, spaces and Unicode are password data, not delimiters here.
        errors.push("validation.invalidPassword");
    }
    if username
        .len()
        .saturating_add(password.len())
        .saturating_add(2)
        > MAX_CHPASSWD_RECORD_BYTES
    {
        errors.push("validation.passwordTooLong");
    }
    errors
}

fn valid_hostname(value: &str) -> bool {
    let bytes = value.as_bytes();
    !bytes.is_empty()
        && bytes.len() <= 63
        && bytes.first().is_some_and(u8::is_ascii_alphanumeric)
        && bytes.last().is_some_and(u8::is_ascii_alphanumeric)
        && bytes
            .iter()
            .all(|byte| byte.is_ascii_alphanumeric() || *byte == b'-')
}

fn valid_username(value: &str) -> bool {
    let mut chars = value.chars();
    chars.next().is_some_and(|first| first.is_ascii_lowercase())
        && value.len() <= 32
        && value != "root"
        && chars.all(|character| {
            character.is_ascii_lowercase()
                || character.is_ascii_digit()
                || character == '-'
                || character == '_'
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_config() -> InstallConfig {
        InstallConfig {
            full_name: "Lyra User".into(),
            username: "lyra".into(),
            password: "harmonia-2026".into(),
            ..InstallConfig::default()
        }
    }

    #[test]
    fn defaults_follow_product_specification() {
        let config = InstallConfig::default();
        assert_eq!(config.locale, "en_US.UTF-8");
        assert_eq!(config.timezone, "America/Sao_Paulo");
        assert_eq!(config.keyboard_layout, "br-abnt2");
        assert_eq!(config.hostname, "lyra-os");
    }

    #[test]
    fn accepts_an_iana_timezone_from_the_system_database() {
        let mut config = valid_config();
        config.timezone = "Europe/Lisbon".into();
        assert!(config.validate().is_ok());
    }

    #[test]
    fn rejects_an_unsupported_locale() {
        let mut config = valid_config();
        config.locale = "de_DE.UTF-8".into();
        let errors = config.validate().unwrap_err();
        assert!(errors.contains(&"validation.unsupportedLocale"));
    }

    #[test]
    fn rejects_a_timezone_path_traversal() {
        let mut config = valid_config();
        config.timezone = "America/../../etc/passwd".into();
        let errors = config.validate().unwrap_err();
        assert!(errors.contains(&"validation.unsupportedTimezone"));
    }

    #[test]
    fn rejects_a_keyboard_layout_outside_the_wizards_option_list() {
        let mut config = valid_config();
        config.keyboard_layout = "dvorak-de-nonexistent".into();
        let errors = config.validate().unwrap_err();
        assert!(errors.contains(&"validation.unsupportedKeyboard"));
    }

    #[test]
    fn every_keyboard_layout_id_is_unique() {
        let mut ids: Vec<&str> = KEYBOARD_LAYOUTS.iter().map(|(id, ..)| *id).collect();
        let before = ids.len();
        ids.sort_unstable();
        ids.dedup();
        assert_eq!(ids.len(), before, "duplicate id in KEYBOARD_LAYOUTS");
    }

    #[test]
    fn accepts_a_complete_configuration() {
        assert_eq!(valid_config().validate(), Ok(()));
    }

    #[test]
    fn account_protocol_rejects_extra_records_and_c_string_truncation() {
        for password in [
            "valid-pass\nroot:other-pass",
            "valid-pass\r\nroot:other-pass",
            "valid-pass\0suffix",
        ] {
            let mut config = valid_config();
            config.password = password.into();
            assert!(
                config
                    .validate()
                    .unwrap_err()
                    .contains(&"validation.invalidPassword")
            );
        }
        for name in ["Name:extra-field", "Name\nextra-record", "Name\0truncated"] {
            let mut config = valid_config();
            config.full_name = name.into();
            assert!(
                config
                    .validate()
                    .unwrap_err()
                    .contains(&"validation.invalidFullName")
            );
        }
    }

    #[test]
    fn account_protocol_preserves_valid_password_data_and_unicode_names() {
        let mut config = valid_config();
        config.full_name = "María D’Ávila, 李".into();
        for password in [
            "  pass:word  ",
            "quotes'\"\\$word",
            "é🔑senha-segura",
            "password\rdata",
            "password\u{2028}data",
        ] {
            config.password = password.into();
            assert_eq!(config.validate(), Ok(()));
        }
    }

    #[test]
    fn account_text_limits_count_encoded_bytes_and_the_complete_chpasswd_record() {
        let mut config = valid_config();
        let available = MAX_CHPASSWD_RECORD_BYTES - config.username.len() - 2;
        config.password = "a".repeat(available);
        assert_eq!(config.validate(), Ok(()));
        config.password.push('a');
        assert!(
            config
                .validate()
                .unwrap_err()
                .contains(&"validation.passwordTooLong")
        );
        config.password = "é".repeat(available / 2 + 1);
        assert!(
            config
                .validate()
                .unwrap_err()
                .contains(&"validation.passwordTooLong")
        );
        config.password = "valid-password".into();
        config.full_name = "a".repeat(MAX_ACCOUNT_COMMENT_BYTES);
        assert_eq!(config.validate(), Ok(()));
        config.full_name.push('a');
        assert!(
            config
                .validate()
                .unwrap_err()
                .contains(&"validation.invalidFullName")
        );
    }

    #[test]
    fn rejects_root_and_shell_metacharacters() {
        let mut config = valid_config();
        config.username = "root".into();
        config.hostname = "lyra; reboot".into();

        let errors = config.validate().unwrap_err();
        assert!(errors.contains(&"validation.invalidUsername"));
        assert!(errors.contains(&"validation.invalidHostname"));
    }

    #[test]
    fn rejects_incomplete_identity() {
        let errors = InstallConfig::default().validate().unwrap_err();
        assert!(errors.contains(&"validation.fullNameRequired"));
        assert!(errors.contains(&"validation.invalidUsername"));
        assert!(errors.contains(&"validation.passwordTooShort"));
    }
}
