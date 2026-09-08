//! Privileged backend for the Lyra Installer. Launched via
//! `pkexec /usr/libexec/lyra-installer-service` by the Tauri frontend for
//! the duration of plan execution only — never the whole UI (see
//! `docs/installer-architecture.md`).
//!
//! Protocol: one JSON `ExecutionRequest` line on stdin, then one JSON
//! `ExecutionEvent` line per event on stdout. An optional
//! `ExecutionControl::Cancel` line may follow on the same stdin stream.

use std::io::{self, BufRead, Write};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

use lyra_installer_core::service::{
    ExecutionControl, ExecutionEvent, ExecutionOutcome, ExecutionRequest, RealExecutor, build,
    execute, missing_allowed_binaries,
};
use lyra_installer_core::storage::{DiscoveryBackend, SystemDiscoveryBackend};

fn main() {
    let mut reader = io::BufReader::new(io::stdin());

    let mut first_line = String::new();
    if reader.read_line(&mut first_line).unwrap_or(0) == 0 {
        eprintln!("lyra-installer-service: nenhuma requisição recebida no stdin");
        std::process::exit(2);
    }

    let request: ExecutionRequest = match serde_json::from_str(first_line.trim()) {
        Ok(request) => request,
        Err(error) => {
            eprintln!("lyra-installer-service: requisição inválida: {error}");
            std::process::exit(2);
        }
    };

    // Treat direct service clients exactly like the UI. Reject account
    // protocol delimiters before discovery, planning or any disk operation.
    if let Err(errors) = request.config.validate() {
        emit(ExecutionEvent::Failed {
            step: "validação da configuração".to_string(),
            message: errors.join(", "),
        });
        std::process::exit(1);
    }

    // Package/image regressions must be caught before storage discovery and,
    // critically, before wipefs/sgdisk can touch the selected disk.
    let missing_binaries = missing_allowed_binaries();
    if !missing_binaries.is_empty() {
        emit(ExecutionEvent::Failed {
            step: "pré-verificação do ambiente".to_string(),
            message: format!(
                "comandos obrigatórios ausentes: {}",
                missing_binaries.join(", ")
            ),
        });
        std::process::exit(1);
    }

    let cancel_requested = Arc::new(AtomicBool::new(false));
    spawn_control_reader(reader, Arc::clone(&cancel_requested));

    let snapshot = match SystemDiscoveryBackend.snapshot() {
        Ok(snapshot) => snapshot,
        Err(error) => {
            emit(ExecutionEvent::Failed {
                step: "descoberta".to_string(),
                message: error.to_string(),
            });
            std::process::exit(1);
        }
    };

    let operations = match build(&request, &snapshot) {
        Ok(operations) => operations,
        Err(error) => {
            emit(ExecutionEvent::Failed {
                step: "tradução do plano".to_string(),
                message: error.to_string(),
            });
            std::process::exit(1);
        }
    };
    let outcome = execute(
        &request,
        &snapshot,
        &operations,
        &RealExecutor,
        &cancel_requested,
        emit,
    );

    std::process::exit(match outcome {
        ExecutionOutcome::Completed => 0,
        ExecutionOutcome::Cancelled | ExecutionOutcome::Failed => 1,
    });
}

/// Keeps reading stdin after the initial request line, looking for a
/// cancellation request. Runs for the lifetime of the process; the parent
/// closing stdin simply ends the loop.
fn spawn_control_reader(mut reader: io::BufReader<io::Stdin>, cancel_requested: Arc<AtomicBool>) {
    std::thread::spawn(move || {
        let mut line = String::new();
        while reader.read_line(&mut line).unwrap_or(0) > 0 {
            if let Ok(ExecutionControl::Cancel) = serde_json::from_str(line.trim()) {
                cancel_requested.store(true, Ordering::SeqCst);
            }
            line.clear();
        }
    });
}

fn emit(event: ExecutionEvent) {
    let json = serde_json::to_string(&event).expect("ExecutionEvent always serializes");
    println!("{json}");
    let _ = io::stdout().flush();
}
