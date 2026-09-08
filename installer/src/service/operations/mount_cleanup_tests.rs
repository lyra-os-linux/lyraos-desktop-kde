use std::cell::RefCell;
use std::sync::atomic::{AtomicBool, Ordering};

use super::tests::{TempRoot, whole_disk_plan_with_new_esp};
use super::*;
use crate::service::engine::{ExecutionOutcome, execute};
use crate::service::executor::{ExecutorError, RealExecutor};
use crate::service::{ExecutionEvent, ExecutionRequest};
use crate::storage::{GuidedChoice, SwapChoice};

struct FaultExecutor<'a> {
    calls: RefCell<Vec<ArgvCommand>>,
    fail_at: Vec<usize>,
    real: bool,
    cancel: Option<&'a AtomicBool>,
}

impl FaultExecutor<'_> {
    fn new(fail_at: Vec<usize>, real: bool) -> Self {
        Self {
            calls: RefCell::new(Vec::new()),
            fail_at,
            real,
            cancel: None,
        }
    }
}

impl Executor for FaultExecutor<'_> {
    fn run(&self, command: &ArgvCommand) -> Result<String, ExecutorError> {
        let index = self.calls.borrow().len();
        self.calls.borrow_mut().push(command.clone());
        if index == 1 {
            if let Some(cancel) = self.cancel {
                cancel.store(true, Ordering::SeqCst);
            }
        }
        if self.fail_at.contains(&index) {
            return Err(ExecutorError::NonZeroExit {
                binary: command.binary.clone(),
                code: Some(73),
                stderr: format!("injected failure {index}"),
            });
        }
        if self.real {
            RealExecutor.run(command)
        } else {
            Ok(String::new())
        }
    }

    fn run_with_stdin(&self, _: &ArgvCommand, _: &str) -> Result<String, ExecutorError> {
        panic!("subvolume preparation must not use stdin");
    }
}

fn operation(staging: &Path, partition: &Path) -> CreateSubvolumes {
    let (plan, _) = whole_disk_plan_with_new_esp();
    let FilesystemPlan::Btrfs { subvolumes } = plan.root_filesystem;
    CreateSubvolumes {
        staging: staging.into(),
        partition: partition.into(),
        subvolumes,
    }
}

fn creation_commands(op: &CreateSubvolumes) -> usize {
    op.subvolumes
        .iter()
        .map(|s| 1 + usize::from(s.nodatacow))
        .sum()
}

fn assert_unmount(executor: &FaultExecutor<'_>, staging: &Path) {
    let calls = executor.calls.borrow();
    assert_eq!(
        calls.last().unwrap(),
        &ArgvCommand {
            binary: "umount".into(),
            args: vec![path_str(staging)],
        }
    );
    assert_eq!(calls.iter().filter(|c| c.binary == "umount").count(), 1);
}

#[test]
fn every_subvolume_and_chattr_failure_unmounts_and_preserves_original_error() {
    let staging = TempRoot::new("subvol-faults");
    let op = operation(&staging.0, Path::new("/dev/test-only"));
    for index in 1..=creation_commands(&op) {
        let executor = FaultExecutor::new(vec![index], false);
        let error = op.perform(&executor).unwrap_err();
        assert!(matches!(error, OperationError::Executor(_)));
        assert!(
            error
                .to_string()
                .contains(&format!("injected failure {index}"))
        );
        assert_unmount(&executor, &staging.0);
        assert_eq!(executor.calls.borrow().len(), index + 2);
    }
}

#[test]
fn parent_directory_failure_after_mount_also_unmounts() {
    let staging = TempRoot::new("subvol-parent");
    fs::write(staging.0.join("blocked"), "not a directory").unwrap();
    let mut op = operation(&staging.0, Path::new("/dev/test-only"));
    op.subvolumes[0].subvolume = "/blocked/child".into();
    let executor = FaultExecutor::new(vec![], false);
    assert!(matches!(op.perform(&executor), Err(OperationError::Io(_))));
    assert_unmount(&executor, &staging.0);
    assert_eq!(executor.calls.borrow().len(), 2);
}

#[test]
fn mount_failure_does_not_unmount_a_mount_it_did_not_acquire() {
    let staging = TempRoot::new("subvol-mount");
    let op = operation(&staging.0, Path::new("/dev/test-only"));
    let executor = FaultExecutor::new(vec![0], false);
    assert!(op.perform(&executor).is_err());
    assert_eq!(executor.calls.borrow().len(), 1);
}

#[test]
fn creation_and_unmount_errors_are_both_reported_in_order() {
    let staging = TempRoot::new("subvol-dual");
    let op = operation(&staging.0, Path::new("/dev/test-only"));
    let executor = FaultExecutor::new(vec![1, 2], false);
    let error = op.perform(&executor).unwrap_err();
    assert!(matches!(error, OperationError::Cleanup { .. }));
    let message = error.to_string();
    assert!(message.find("btrfs").unwrap() < message.find("umount").unwrap());
    assert!(message.contains("injected failure 1"));
    assert!(message.contains("injected failure 2"));
    assert_unmount(&executor, &staging.0);
}

struct MustNotRun;
impl PrivilegedOperation for MustNotRun {
    fn describe(&self) -> String {
        "must not run".into()
    }
    fn perform(&self, _: &dyn Executor) -> Result<(), OperationError> {
        panic!("engine continued after failure/cancellation");
    }
}

fn engine_run(
    op: CreateSubvolumes,
    executor: &FaultExecutor<'_>,
    cancel: &AtomicBool,
) -> (ExecutionOutcome, Vec<ExecutionEvent>) {
    let (plan, snapshot) = whole_disk_plan_with_new_esp();
    let request = ExecutionRequest {
        choice: GuidedChoice {
            raw_target: plan.raw_target.clone(),
            volume_layer: VolumeLayer::Direct,
            swap: SwapChoice::Zram,
        },
        plan,
        config: crate::InstallConfig {
            full_name: "VM Test".into(),
            username: "lyra".into(),
            password: "public-test-only".into(),
            timezone: "UTC".into(),
            ..Default::default()
        },
    };
    let operations: Vec<Box<dyn PrivilegedOperation>> = vec![Box::new(op), Box::new(MustNotRun)];
    let mut events = Vec::new();
    let outcome = execute(
        &request,
        &snapshot,
        &operations,
        executor,
        cancel,
        |event| events.push(event),
    );
    (outcome, events)
}

#[test]
fn unmount_failure_stops_engine_even_after_successful_creation() {
    let staging = TempRoot::new("subvol-unmount");
    let op = operation(&staging.0, Path::new("/dev/test-only"));
    let executor = FaultExecutor::new(vec![creation_commands(&op) + 1], false);
    let (outcome, events) = engine_run(op, &executor, &AtomicBool::new(false));
    assert_eq!(outcome, ExecutionOutcome::Failed);
    assert!(events.iter().any(
        |e| matches!(e, ExecutionEvent::Failed { message, .. } if message.contains("umount"))
    ));
    assert_unmount(&executor, &staging.0);
}

#[test]
fn cancellation_during_creation_reaches_checkpoint_with_staging_unmounted() {
    let staging = TempRoot::new("subvol-cancel");
    let cancel = AtomicBool::new(false);
    let mut executor = FaultExecutor::new(vec![], false);
    executor.cancel = Some(&cancel);
    let (outcome, _) = engine_run(
        operation(&staging.0, Path::new("/dev/test-only")),
        &executor,
        &cancel,
    );
    assert_eq!(outcome, ExecutionOutcome::Cancelled);
    assert_unmount(&executor, &staging.0);
}

fn assert_no_mount(staging: &Path) {
    let mounts = fs::read_to_string("/proc/self/mountinfo").unwrap();
    assert!(
        !mounts
            .lines()
            .any(|line| line.split_whitespace().nth(4) == staging.to_str()),
        "staging mount leaked: {mounts}"
    );
}

#[test]
#[ignore = "requires the disposable QEMU guest from scripts/check-installer-mount-vm.py"]
fn native_mount_cleanup_vm() {
    assert!(
        fs::read_to_string("/proc/cmdline")
            .unwrap()
            .split_whitespace()
            .any(|s| s == "lyra.mount-cleanup-test=1"),
        "disposable guest required"
    );
    assert_eq!(
        fs::read_to_string("/sys/class/block/vda/serial")
            .unwrap()
            .trim(),
        "lyra-mount-test-only"
    );
    let partition = Path::new("/dev/vda");
    let staging = TempRoot::new("native-subvol");
    let format = || {
        RealExecutor
            .run(&ArgvCommand {
                binary: "mkfs.btrfs".into(),
                args: vec!["-f".into(), path_str(partition)],
            })
            .unwrap()
    };
    let count = creation_commands(&operation(&staging.0, partition));
    for index in 1..=count {
        assert_no_mount(&staging.0);
        format();
        let executor = FaultExecutor::new(vec![index], true);
        let (outcome, events) = engine_run(
            operation(&staging.0, partition),
            &executor,
            &AtomicBool::new(false),
        );
        assert_eq!(outcome, ExecutionOutcome::Failed);
        assert!(events.iter().any(|e| matches!(e, ExecutionEvent::Failed { message, .. } if message.contains(&format!("injected failure {index}")))), "case {index}: {events:?}");
        assert_unmount(&executor, &staging.0);
        assert_no_mount(&staging.0);
    }
    format();
    let cancel = AtomicBool::new(false);
    let mut executor = FaultExecutor::new(vec![], true);
    executor.cancel = Some(&cancel);
    assert_eq!(
        engine_run(operation(&staging.0, partition), &executor, &cancel).0,
        ExecutionOutcome::Cancelled
    );
    assert_no_mount(&staging.0);
    // The ordinary whole-disk retry reformats before recreating subvolumes.
    format();
    operation(&staging.0, partition)
        .perform(&RealExecutor)
        .unwrap();
    assert_no_mount(&staging.0);
    println!("LYRA_MOUNT_VM_PASS faults={count} cancellation=1 retry=1");
}
