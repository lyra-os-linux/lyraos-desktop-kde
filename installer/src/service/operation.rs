//! The allow-listed shape every privileged action must take. Nothing here
//! runs a shell or interpolates a string into one: every process spawn goes
//! through [`ArgvCommand`], checked against [`ALLOWED_BINARIES`] before
//! [`super::executor::RealExecutor`] ever spawns it. Direct file I/O (e.g.
//! writing `/etc/fstab`) doesn't need that gate — the service process is
//! already root, and the allow-list exists to bound *process spawning*
//! with plan-derived data, not to forbid the trusted process from writing
//! a file with content it generated itself.

use std::fmt;

use super::executor::{Executor, ExecutorError};

/// One process invocation: `Command::new(binary).args(args)`, never
/// `sh -c "..."`. Kept separate from [`PrivilegedOperation`] so tests can
/// build one directly without needing a real operation type to exist.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ArgvCommand {
    pub binary: String,
    pub args: Vec<String>,
}

/// Every binary a privileged operation is ever allowed to run. Adding to
/// this list is a deliberate, reviewable act — it's the actual security
/// boundary, not the polkit prompt (which only gates *launching* the
/// service at all).
pub const ALLOWED_BINARIES: &[&str] = &[
    "sgdisk",
    "wipefs",
    "mkfs.btrfs",
    "mkfs.vfat",
    "mkswap",
    "blkid",
    "mdadm",
    "vgcreate",
    "lvcreate",
    "vgchange",
    "mount",
    "umount",
    "swapoff",
    "btrfs",
    "chattr",
    "sync",
    "unsquashfs",
    "useradd",
    "userdel",
    "chpasswd",
    // Repairs ownership of the target user's home after useradd copies the
    // live image skeleton. Arguments use numeric IDs read from target passwd.
    "chown",
    "chroot",
    "systemctl",
    "hwclock",
    "grub2-mkconfig",
    "shim-install",
    "snapper",
    // Removes the live-only installer package from the target RPM database.
    // Deleting only its files would let a later package update restore the
    // privileged service and polkit rule on the installed system.
    "rpm",
    // Compiles /etc/dconf/db/local.d/* into the binary dconf database
    // WriteKeyboard just wrote — no arguments beyond the fixed "update".
    "dconf",
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum OperationError {
    Executor(ExecutorError),
    /// The plan asks for a target shape this translator doesn't implement
    /// yet (e.g. a RAID or LVM raw target) — surfaced explicitly rather
    /// than silently doing nothing.
    NotImplemented(String),
    Io(String),
    /// A step failed and its internal compensation failed too. Keep the
    /// original failure first without hiding that resources may remain held.
    Cleanup {
        operation: Box<OperationError>,
        cleanup: Box<OperationError>,
    },
}

impl From<ExecutorError> for OperationError {
    fn from(error: ExecutorError) -> Self {
        OperationError::Executor(error)
    }
}

impl fmt::Display for OperationError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            OperationError::Executor(error) => write!(f, "{error}"),
            OperationError::NotImplemented(reason) => write!(f, "não implementado: {reason}"),
            OperationError::Io(reason) => write!(f, "erro de E/S: {reason}"),
            OperationError::Cleanup { operation, cleanup } => {
                write!(f, "{operation}; falha na limpeza: {cleanup}")
            }
        }
    }
}

/// A single privileged step. An operation may run zero or more commands
/// through the given [`Executor`] and/or write files directly; it decides
/// its own internal sequencing (e.g. `WriteFstab` runs `blkid` to read a
/// UUID, then writes the file).
pub trait PrivilegedOperation {
    /// Human-readable description surfaced in `ExecutionEvent::Step`.
    fn describe(&self) -> String;
    /// Compensate partial work internally before returning an error: the
    /// engine calls `undo` only for operations that completed successfully.
    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError>;
    /// Best-effort compensating action, run in reverse order over every
    /// operation that already succeeded — always, whether the run as a
    /// whole ends in success, cancellation or failure (mount operations'
    /// `undo` is the matching `umount`, so this is also how the target
    /// ends up cleanly unmounted after a *successful* run). `Ok(())` when
    /// there's nothing meaningful to undo.
    fn undo(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        let _ = executor;
        Ok(())
    }
}
