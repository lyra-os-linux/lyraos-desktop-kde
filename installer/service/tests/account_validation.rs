//! Exercise the actual JSON service entry point without a frontend or disk.
use std::io::Write;
use std::process::{Command, Stdio};

use lyra_installer_core::InstallConfig;
use lyra_installer_core::service::{ExecutionEvent, ExecutionRequest};
use lyra_installer_core::storage::{
    DestructiveSummary, EspPlan, FilesystemPlan, GuidedChoice, InstallPlan, SwapChoice, SwapPlan,
    VolumeLayer,
};

fn request() -> ExecutionRequest {
    ExecutionRequest {
        choice: GuidedChoice {
            raw_target: None,
            volume_layer: VolumeLayer::Direct,
            swap: SwapChoice::Zram,
        },
        // No device and an unsupported schema: even if validation regresses,
        // this fixture cannot translate into disk operations on the test host.
        plan: InstallPlan {
            schema_version: 0,
            raw_target: None,
            volume_layer: VolumeLayer::Direct,
            esp: EspPlan::Create { size_bytes: 0 },
            swap: SwapPlan::Zram,
            root_filesystem: FilesystemPlan::default(),
            destructive_summary: DestructiveSummary::default(),
            warnings: Vec::new(),
        },
        config: InstallConfig {
            full_name: "Lyra User".into(),
            username: "lyra".into(),
            password: "valid-password".into(),
            ..InstallConfig::default()
        },
    }
}

#[test]
fn direct_service_calls_reject_invalid_accounts_before_environment_or_storage_checks() {
    for (field, value, expected) in [
        (
            "password",
            "valid-pass\nroot:other-pass".into(),
            "validation.invalidPassword",
        ),
        (
            "password",
            "valid-pass\r\nroot:other-pass".into(),
            "validation.invalidPassword",
        ),
        (
            "password",
            "valid-pass\0suffix".into(),
            "validation.invalidPassword",
        ),
        ("password", "é".repeat(4093), "validation.passwordTooLong"),
        ("password", "🔑".repeat(4), "validation.passwordTooShort"),
        (
            "full_name",
            "Name:extra-field".into(),
            "validation.invalidFullName",
        ),
        (
            "full_name",
            "Name\nextra-record".into(),
            "validation.invalidFullName",
        ),
        (
            "full_name",
            "Name\0truncated".into(),
            "validation.invalidFullName",
        ),
        (
            "full_name",
            "a".repeat(131072),
            "validation.invalidFullName",
        ),
        ("username", "root".into(), "validation.invalidUsername"),
    ] {
        let mut request = request();
        match field {
            "password" => request.config.password = value,
            "full_name" => request.config.full_name = value,
            "username" => request.config.username = value,
            _ => unreachable!(),
        }
        let mut child = Command::new(env!("CARGO_BIN_EXE_lyra-installer-service"))
            .env_clear()
            .env("PATH", "")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        let mut stdin = child.stdin.take().unwrap();
        serde_json::to_writer(&mut stdin, &request).unwrap();
        stdin.write_all(b"\n").unwrap();
        drop(stdin);
        let output = child.wait_with_output().unwrap();
        assert_eq!(output.status.code(), Some(1));
        assert!(
            output.stderr.is_empty(),
            "diagnostics must not contain account data"
        );
        let events: Vec<ExecutionEvent> = String::from_utf8(output.stdout)
            .unwrap()
            .lines()
            .map(|line| serde_json::from_str(line).unwrap())
            .collect();
        assert_eq!(
            events,
            vec![ExecutionEvent::Failed {
                step: "validação da configuração".into(),
                message: expected.into(),
            }]
        );
    }
}
