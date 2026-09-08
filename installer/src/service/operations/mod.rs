//! Real [`PrivilegedOperation`] implementations for issue #40: partition
//! the target disk, format ESP + Btrfs, create and mount the subvolume
//! layout from `storage::plan::default_subvolumes`, write `/etc/fstab`.
//!
//! Only covers "whole disk, [`VolumeLayer::Direct`]" today —
//! [`plan_to_operations`] returns [`OperationError::NotImplemented`] for
//! RAID/LVM raw targets rather than silently doing nothing; #41/#42 (and a
//! RAID/LVM follow-up here) fill those in.

use std::fs;
use std::path::{Path, PathBuf};

use crate::storage::{
    BTRFS_MOUNT_OPTIONS, EspPlan, FilesystemPlan, InstallPlan, RawTarget, StorageSnapshot,
    SubvolumePlan, SwapPlan, VolumeLayer,
};

use super::executor::Executor;
use super::operation::{ArgvCommand, OperationError, PrivilegedOperation};

mod deploy;
#[cfg(test)]
mod mount_cleanup_tests;

/// Where the target filesystem tree ends up mounted during install — tmpfs,
/// ephemeral, same convention as the live squashfs's own `/run/overlay/live`.
pub const TARGET_ROOT: &str = "/run/lyra-installer/target";
const STAGING_ROOT: &str = "/run/lyra-installer/staging";

pub fn plan_to_operations(
    plan: &InstallPlan,
    snapshot: &StorageSnapshot,
) -> Result<Vec<Box<dyn PrivilegedOperation>>, OperationError> {
    let disk = match &plan.raw_target {
        Some(RawTarget::Disk(path)) => path.clone(),
        Some(RawTarget::NewRaid { .. }) => {
            return Err(OperationError::NotImplemented(
                "RAID novo como alvo bruto".to_string(),
            ));
        }
        Some(RawTarget::ExistingRaid { .. }) => {
            return Err(OperationError::NotImplemented(
                "RAID existente como alvo bruto".to_string(),
            ));
        }
        None => {
            return Err(OperationError::NotImplemented(
                "volume group existente como alvo direto".to_string(),
            ));
        }
    };
    match &plan.volume_layer {
        VolumeLayer::Direct => {}
        VolumeLayer::NewVolumeGroup { .. } => {
            return Err(OperationError::NotImplemented(
                "criar volume group LVM".to_string(),
            ));
        }
        VolumeLayer::ExistingVolumeGroup { .. } => {
            return Err(OperationError::NotImplemented(
                "volume group LVM existente".to_string(),
            ));
        }
    }

    let FilesystemPlan::Btrfs { subvolumes } = &plan.root_filesystem;

    let target_root = PathBuf::from(TARGET_ROOT);
    let staging = PathBuf::from(STAGING_ROOT);

    let esp_size_bytes = match &plan.esp {
        EspPlan::Create { size_bytes } => Some(*size_bytes),
        EspPlan::Reuse { .. } => None,
    };
    let swap_size_bytes = match &plan.swap {
        SwapPlan::Partition { size_bytes } => Some(*size_bytes),
        SwapPlan::None | SwapPlan::Zram => None,
    };
    let root_partition_number =
        1 + u32::from(esp_size_bytes.is_some()) + u32::from(swap_size_bytes.is_some());
    let root_partition = partition_path(&disk, root_partition_number);
    let esp_partition = match &plan.esp {
        EspPlan::Create { .. } => partition_path(&disk, 1),
        EspPlan::Reuse { path } => path.clone(),
    };

    let existing_partitions: Vec<PathBuf> = snapshot
        .disks
        .iter()
        .find(|d| d.path == disk)
        .map(|d| d.partitions.iter().map(|p| p.path.clone()).collect())
        .unwrap_or_default();

    let mut operations: Vec<Box<dyn PrivilegedOperation>> = Vec::new();
    if let Some(release) = ReleaseDisk::for_target(&disk, snapshot) {
        operations.push(Box::new(release));
    }
    operations.push(Box::new(CreatePartitionTable {
        disk: disk.clone(),
        existing_partitions,
        esp_size_bytes,
        swap_size_bytes,
    }));

    if matches!(plan.esp, EspPlan::Create { .. }) {
        operations.push(Box::new(FormatEsp {
            partition: esp_partition.clone(),
        }));
    }

    let swap_partition = swap_size_bytes.map(|_| {
        let number = 1 + u32::from(esp_size_bytes.is_some());
        partition_path(&disk, number)
    });
    if let Some(partition) = &swap_partition {
        operations.push(Box::new(FormatSwap {
            partition: partition.clone(),
        }));
    }

    operations.push(Box::new(FormatBtrfsRoot {
        partition: root_partition.clone(),
    }));
    operations.push(Box::new(CreateSubvolumes {
        partition: root_partition.clone(),
        staging: staging.clone(),
        subvolumes: subvolumes.clone(),
    }));

    // Shallowest mount points first. `fs::create_dir_all` in each
    // MountSubvolume::perform makes plain mkdir-before-mount work
    // regardless of order, but unmounting doesn't: the engine's undo stack
    // unwinds in reverse, so mounting parents before children here is what
    // makes reverse order unmount children before their parents. Mounting
    // a parent over an already-mounted child's path would leave that child
    // mount orphaned - `umount` on the parent fails with "target is busy"
    // while a child mount still exists under it.
    let mut ordered_subvolumes = subvolumes.clone();
    ordered_subvolumes.sort_by_key(|subvolume| subvolume.mount_point.components().count());
    for subvolume in ordered_subvolumes {
        operations.push(Box::new(MountSubvolume {
            target_root: target_root.clone(),
            mount_point: subvolume.mount_point.clone(),
            subvolume: subvolume.subvolume.clone(),
            partition: root_partition.clone(),
        }));
    }

    operations.push(Box::new(MountEsp {
        target_root: target_root.clone(),
        partition: esp_partition.clone(),
    }));
    operations.push(Box::new(WriteFstab {
        target_root,
        root_partition,
        esp_partition,
        swap_partition,
        subvolumes: subvolumes.clone(),
    }));

    Ok(operations)
}

/// Full sequence for one execution: partitioning (this module) + rootfs
/// deployment (`deploy`, issue #41) + a final `sync`. Kept apart from
/// `plan_to_operations` so #40's own tests can still check the
/// partitioning-only sequence without the identity data `deploy` needs.
pub fn build(
    request: &super::ExecutionRequest,
    snapshot: &StorageSnapshot,
) -> Result<Vec<Box<dyn PrivilegedOperation>>, OperationError> {
    let mut operations = plan_to_operations(&request.plan, snapshot)?;
    operations.extend(deploy::deployment_operations(
        &request.config,
        &request.plan.swap,
    ));
    operations.push(Box::new(SyncAndFinish));
    Ok(operations)
}

/// `/dev/sda` + 1 -> `/dev/sda1`; `/dev/nvme0n1` + 1 -> `/dev/nvme0n1p1` —
/// standard Linux partition naming (a `p` separator only when the disk name
/// itself ends in a digit).
fn partition_path(disk: &Path, number: u32) -> PathBuf {
    let name = disk
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or_default();
    let separator = if name.ends_with(|c: char| c.is_ascii_digit()) {
        "p"
    } else {
        ""
    };
    disk.with_file_name(format!("{name}{separator}{number}"))
}

fn path_str(path: &Path) -> String {
    path.to_string_lossy().into_owned()
}

fn join_under(root: &Path, mount_point: &Path) -> PathBuf {
    if mount_point == Path::new("/") {
        root.to_path_buf()
    } else {
        root.join(mount_point.strip_prefix("/").unwrap_or(mount_point))
    }
}

/// Releases whatever the kernel still holds open on a whole-disk install
/// target that arrived with partitions already in use — mounted
/// filesystems, active swap, or an LVM volume group with a physical volume
/// on this disk. The disk-selection flow accepts such "occupied" disks and
/// wipes them (see `PlanBuilder::eligible_disk`), but `wipefs`/`sgdisk` fail
/// with "device or resource busy" unless whatever is using the disk is
/// released first, so this runs immediately before `CreatePartitionTable`.
struct ReleaseDisk {
    disk: PathBuf,
    /// Deepest mount points first, so a parent is never unmounted while a
    /// child mount underneath it is still active.
    mountpoints: Vec<PathBuf>,
    swap_partitions: Vec<PathBuf>,
    /// Volume groups with a PV on this disk — deactivated before `umount`
    /// would be pointless, since the dm devices they back keep the
    /// underlying partition open even once nothing is mounted on it.
    volume_groups: Vec<String>,
}

impl ReleaseDisk {
    /// `None` when the target disk is unknown to `snapshot` or has nothing
    /// mounted/swapped-on/LVM-active to release — the common case, where
    /// inserting a no-op step into the plan would just be noise in the UI.
    fn for_target(disk: &Path, snapshot: &StorageSnapshot) -> Option<Self> {
        let target = snapshot.disks.iter().find(|d| d.path == disk)?;

        let mut mountpoints: Vec<PathBuf> = target
            .partitions
            .iter()
            .flat_map(|partition| partition.mountpoints.iter().cloned())
            .collect();
        mountpoints.sort_by_key(|m| std::cmp::Reverse(m.components().count()));

        let swap_partitions: Vec<PathBuf> = target
            .partitions
            .iter()
            .filter(|partition| {
                partition
                    .filesystem
                    .as_deref()
                    .is_some_and(|fs| fs.eq_ignore_ascii_case("swap"))
            })
            .map(|partition| partition.path.clone())
            .collect();

        let volume_groups: Vec<String> = snapshot
            .volume_groups
            .iter()
            .filter(|vg| {
                vg.physical_volumes
                    .iter()
                    .any(|pv| target.partitions.iter().any(|p| &p.path == pv))
            })
            .map(|vg| vg.name.clone())
            .collect();

        if mountpoints.is_empty() && swap_partitions.is_empty() && volume_groups.is_empty() {
            return None;
        }
        Some(ReleaseDisk {
            disk: disk.to_path_buf(),
            mountpoints,
            swap_partitions,
            volume_groups,
        })
    }
}

impl PrivilegedOperation for ReleaseDisk {
    fn describe(&self) -> String {
        format!("liberar partições em uso em {}", self.disk.display())
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        for swap_partition in &self.swap_partitions {
            executor.run(&ArgvCommand {
                binary: "swapoff".to_string(),
                args: vec![path_str(swap_partition)],
            })?;
        }
        for mountpoint in &self.mountpoints {
            executor.run(&ArgvCommand {
                binary: "umount".to_string(),
                args: vec!["-R".to_string(), path_str(mountpoint)],
            })?;
        }
        // Deactivate *after* unmounting/swapoff: a mount point or swap
        // partition living on a logical volume of this VG would otherwise
        // still be held open, and `vgchange -an` would fail the same way
        // `wipefs` did.
        for vg in &self.volume_groups {
            executor.run(&ArgvCommand {
                binary: "vgchange".to_string(),
                args: vec!["-an".to_string(), vg.clone()],
            })?;
        }
        Ok(())
    }
}

struct CreatePartitionTable {
    disk: PathBuf,
    /// Partitions that existed on this disk before the install. `wipefs -a`
    /// on the *disk* device only reaches signatures libblkid probes there
    /// (GPT/MBR), never a filesystem/LVM/RAID member signature living inside
    /// one of its partitions, and `sgdisk --zap-all` only destroys the
    /// partition table, not partition contents. Left alone, a stale
    /// `LVM2_member` label survives on disk; if a newly created partition
    /// later lands on those same bytes, udev's `lvm2-pvscan@.service`
    /// rediscovers it and reactivates the old volume group against the new
    /// partition mid-install, so the next `mkfs`/`mkswap` fails with
    /// "device or resource busy" (confirmed against a real disk that
    /// previously held an LVM-based openSUSE install). Wiping every old
    /// partition individually, before the table itself is touched, removes
    /// those signatures while their device nodes are still addressable.
    existing_partitions: Vec<PathBuf>,
    /// `None` when the plan reuses an existing ESP elsewhere — #39's
    /// eligibility rules already guarantee this disk has no partitions of
    /// its own in that case, so only the root partition is created here.
    esp_size_bytes: Option<u64>,
    swap_size_bytes: Option<u64>,
}

impl PrivilegedOperation for CreatePartitionTable {
    fn describe(&self) -> String {
        format!("criar tabela de partições em {}", self.disk.display())
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        let disk = path_str(&self.disk);
        for partition in &self.existing_partitions {
            executor.run(&ArgvCommand {
                binary: "wipefs".to_string(),
                args: vec!["-a".to_string(), path_str(partition)],
            })?;
        }
        executor.run(&ArgvCommand {
            binary: "wipefs".to_string(),
            args: vec!["-a".to_string(), disk.clone()],
        })?;
        executor.run(&ArgvCommand {
            binary: "sgdisk".to_string(),
            args: vec!["--zap-all".to_string(), disk.clone()],
        })?;

        let mut next_partition = 1u32;
        if let Some(esp_size_bytes) = self.esp_size_bytes {
            let esp_mib = esp_size_bytes / (1024 * 1024);
            executor.run(&ArgvCommand {
                binary: "sgdisk".to_string(),
                args: vec![
                    format!("-n{next_partition}:0:+{esp_mib}M"),
                    format!("-t{next_partition}:ef00"),
                    disk.clone(),
                ],
            })?;
            next_partition += 1;
        }
        if let Some(swap_size_bytes) = self.swap_size_bytes {
            let swap_mib = swap_size_bytes / (1024 * 1024);
            executor.run(&ArgvCommand {
                binary: "sgdisk".to_string(),
                args: vec![
                    format!("-n{next_partition}:0:+{swap_mib}M"),
                    format!("-t{next_partition}:8200"),
                    disk.clone(),
                ],
            })?;
            next_partition += 1;
        }
        executor.run(&ArgvCommand {
            binary: "sgdisk".to_string(),
            args: vec![
                format!("-n{next_partition}:0:0"),
                format!("-t{next_partition}:8300"),
                disk,
            ],
        })?;
        Ok(())
    }
}

struct FormatEsp {
    partition: PathBuf,
}

impl PrivilegedOperation for FormatEsp {
    fn describe(&self) -> String {
        format!("formatar ESP em {}", self.partition.display())
    }
    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        executor.run(&ArgvCommand {
            binary: "mkfs.vfat".to_string(),
            args: vec!["-F32".to_string(), path_str(&self.partition)],
        })?;
        Ok(())
    }
}

struct FormatBtrfsRoot {
    partition: PathBuf,
}

struct FormatSwap {
    partition: PathBuf,
}

impl PrivilegedOperation for FormatSwap {
    fn describe(&self) -> String {
        format!("formatar swap em {}", self.partition.display())
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        executor.run(&ArgvCommand {
            binary: "mkswap".to_string(),
            args: vec![path_str(&self.partition)],
        })?;
        Ok(())
    }
}

impl PrivilegedOperation for FormatBtrfsRoot {
    fn describe(&self) -> String {
        format!("formatar Btrfs em {}", self.partition.display())
    }
    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        executor.run(&ArgvCommand {
            binary: "mkfs.btrfs".to_string(),
            args: vec!["-f".to_string(), path_str(&self.partition)],
        })?;
        Ok(())
    }
}

/// Mounts the raw (subvolid=5) top-level Btrfs tree at a throwaway staging
/// path just long enough to create every subvolume from the plan, then
/// unmounts it. The real, final mounts (one per subvolume, at its real
/// target path) happen afterwards via [`MountSubvolume`].
struct CreateSubvolumes {
    partition: PathBuf,
    staging: PathBuf,
    subvolumes: Vec<SubvolumePlan>,
}

impl PrivilegedOperation for CreateSubvolumes {
    fn describe(&self) -> String {
        "criar subvolumes Btrfs".to_string()
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        fs::create_dir_all(&self.staging).map_err(io_error)?;
        executor.run(&ArgvCommand {
            binary: "mount".to_string(),
            args: vec![path_str(&self.partition), path_str(&self.staging)],
        })?;

        // The engine records only successful operations for unwind. Every
        // fallible step after this mount must therefore stay inside this
        // closure, so an early return still reaches the matching unmount.
        let creation = (|| -> Result<(), OperationError> {
            for subvolume in &self.subvolumes {
                let leaf = self
                    .staging
                    .join(subvolume.subvolume.trim_start_matches('/'));
                if let Some(parent) = leaf.parent() {
                    fs::create_dir_all(parent).map_err(io_error)?;
                }
                executor.run(&ArgvCommand {
                    binary: "btrfs".to_string(),
                    args: vec![
                        "subvolume".to_string(),
                        "create".to_string(),
                        path_str(&leaf),
                    ],
                })?;
                if subvolume.nodatacow {
                    executor.run(&ArgvCommand {
                        binary: "chattr".to_string(),
                        args: vec!["+C".to_string(), path_str(&leaf)],
                    })?;
                }
            }

            Ok(())
        })();

        let cleanup = executor
            .run(&ArgvCommand {
                binary: "umount".to_string(),
                args: vec![path_str(&self.staging)],
            })
            .map(|_| ())
            .map_err(OperationError::from);
        match (creation, cleanup) {
            (Err(operation), Err(cleanup)) => Err(OperationError::Cleanup {
                operation: Box::new(operation),
                cleanup: Box::new(cleanup),
            }),
            (Err(error), Ok(())) | (Ok(()), Err(error)) => Err(error),
            (Ok(()), Ok(())) => Ok(()),
        }
    }
}

struct MountSubvolume {
    target_root: PathBuf,
    mount_point: PathBuf,
    subvolume: String,
    partition: PathBuf,
}

impl PrivilegedOperation for MountSubvolume {
    fn describe(&self) -> String {
        format!(
            "montar {} em {}",
            self.subvolume,
            self.mount_point.display()
        )
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        let dest = join_under(&self.target_root, &self.mount_point);
        fs::create_dir_all(&dest).map_err(io_error)?;
        let options = format!("subvol={},{BTRFS_MOUNT_OPTIONS}", self.subvolume);
        executor.run(&ArgvCommand {
            binary: "mount".to_string(),
            args: vec![
                "-o".to_string(),
                options,
                path_str(&self.partition),
                path_str(&dest),
            ],
        })?;
        Ok(())
    }

    fn undo(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        let dest = join_under(&self.target_root, &self.mount_point);
        executor.run(&ArgvCommand {
            binary: "umount".to_string(),
            args: vec![path_str(&dest)],
        })?;
        Ok(())
    }
}

struct MountEsp {
    target_root: PathBuf,
    partition: PathBuf,
}

impl MountEsp {
    fn dest(&self) -> PathBuf {
        self.target_root.join("boot/efi")
    }
}

impl PrivilegedOperation for MountEsp {
    fn describe(&self) -> String {
        "montar ESP em /boot/efi".to_string()
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        let dest = self.dest();
        fs::create_dir_all(&dest).map_err(io_error)?;
        executor.run(&ArgvCommand {
            binary: "mount".to_string(),
            args: vec![
                "-o".to_string(),
                "defaults,umask=0077".to_string(),
                path_str(&self.partition),
                path_str(&dest),
            ],
        })?;
        Ok(())
    }

    fn undo(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        executor.run(&ArgvCommand {
            binary: "umount".to_string(),
            args: vec![path_str(&self.dest())],
        })?;
        Ok(())
    }
}

struct WriteFstab {
    target_root: PathBuf,
    root_partition: PathBuf,
    esp_partition: PathBuf,
    swap_partition: Option<PathBuf>,
    subvolumes: Vec<SubvolumePlan>,
}

impl PrivilegedOperation for WriteFstab {
    fn describe(&self) -> String {
        "gerar /etc/fstab".to_string()
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        let root_uuid = executor.run(&ArgvCommand {
            binary: "blkid".to_string(),
            args: vec![
                "-s".to_string(),
                "UUID".to_string(),
                "-o".to_string(),
                "value".to_string(),
                path_str(&self.root_partition),
            ],
        })?;
        let esp_uuid = executor.run(&ArgvCommand {
            binary: "blkid".to_string(),
            args: vec![
                "-s".to_string(),
                "UUID".to_string(),
                "-o".to_string(),
                "value".to_string(),
                path_str(&self.esp_partition),
            ],
        })?;

        let mut content = String::from("# Gerado pelo Lyra Installer\n");
        for subvolume in &self.subvolumes {
            content.push_str(&format!(
                "UUID={root_uuid} {} btrfs subvol={},{BTRFS_MOUNT_OPTIONS} 0 0\n",
                subvolume.mount_point.display(),
                subvolume.subvolume,
            ));
        }
        content.push_str(&format!(
            "UUID={esp_uuid} /boot/efi vfat defaults,umask=0077 0 2\n"
        ));
        if let Some(swap_partition) = &self.swap_partition {
            let swap_uuid = executor.run(&ArgvCommand {
                binary: "blkid".to_string(),
                args: vec![
                    "-s".to_string(),
                    "UUID".to_string(),
                    "-o".to_string(),
                    "value".to_string(),
                    path_str(swap_partition),
                ],
            })?;
            content.push_str(&format!("UUID={swap_uuid} none swap defaults 0 0\n"));
        }

        let etc = self.target_root.join("etc");
        fs::create_dir_all(&etc).map_err(io_error)?;
        fs::write(etc.join("fstab"), content).map_err(io_error)?;
        Ok(())
    }
}

struct SyncAndFinish;

impl PrivilegedOperation for SyncAndFinish {
    fn describe(&self) -> String {
        "sincronizar dispositivos".to_string()
    }
    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        executor.run(&ArgvCommand {
            binary: "sync".to_string(),
            args: Vec::new(),
        })?;
        Ok(())
    }
}

fn io_error(error: std::io::Error) -> OperationError {
    OperationError::Io(error.to_string())
}

#[cfg(test)]
mod tests {
    use std::cell::RefCell;
    use std::sync::atomic::{AtomicU64, Ordering};

    use super::*;
    use crate::storage::{
        DeviceRole, Disk, GuidedChoice, LogicalVolumePlan, PlanBuilder, RaidArray, RaidLevel,
        SizePolicy, StorageSnapshot, Transport, VolumeGroup,
    };

    /// Records every command it's asked to run and returns a distinct fake
    /// UUID per partition for `blkid` calls, so `WriteFstab` output can be
    /// checked without a real filesystem to query.
    struct FakeExecutor {
        calls: RefCell<Vec<String>>,
    }

    impl FakeExecutor {
        fn new() -> Self {
            Self {
                calls: RefCell::new(Vec::new()),
            }
        }
        fn calls(&self) -> Vec<String> {
            self.calls.borrow().clone()
        }
    }

    impl Executor for FakeExecutor {
        fn run(
            &self,
            command: &ArgvCommand,
        ) -> Result<String, crate::service::executor::ExecutorError> {
            self.calls
                .borrow_mut()
                .push(format!("{} {}", command.binary, command.args.join(" ")));
            if command.binary == "blkid" {
                let partition = command.args.last().cloned().unwrap_or_default();
                Ok(format!("UUID-FOR-{partition}"))
            } else {
                Ok(String::new())
            }
        }

        fn run_with_stdin(
            &self,
            command: &ArgvCommand,
            stdin: &str,
        ) -> Result<String, crate::service::executor::ExecutorError> {
            self.calls.borrow_mut().push(format!(
                "{} {} <stdin: {stdin}>",
                command.binary,
                command.args.join(" ")
            ));
            Ok(String::new())
        }
    }

    /// Self-cleaning writable directory under `/tmp` — real operations do
    /// real `fs::create_dir_all`/`fs::write`, so tests need somewhere
    /// writable by a non-root user, unlike the real `/run/lyra-installer`.
    pub(super) struct TempRoot(pub(super) PathBuf);

    impl TempRoot {
        pub(super) fn new(label: &str) -> Self {
            static COUNTER: AtomicU64 = AtomicU64::new(0);
            let n = COUNTER.fetch_add(1, Ordering::SeqCst);
            let path = std::env::temp_dir().join(format!(
                "lyra-installer-test-{label}-{}-{n}",
                std::process::id()
            ));
            fs::create_dir_all(&path).expect("temp dir should be creatable");
            TempRoot(path)
        }
    }

    impl Drop for TempRoot {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn disk(kname: &str, size_bytes: u64) -> Disk {
        Disk {
            path: PathBuf::from(format!("/dev/{kname}")),
            kname: kname.to_string(),
            size_bytes,
            transport: Transport::Sata,
            vendor: None,
            model: None,
            removable: false,
            is_live_media: false,
            role: DeviceRole::Free,
            partitions: Vec::new(),
        }
    }

    const LARGE: u64 = 40 * 1024 * 1024 * 1024;

    pub(super) fn whole_disk_plan_with_new_esp() -> (InstallPlan, StorageSnapshot) {
        let snapshot = StorageSnapshot {
            uefi: true,
            disks: vec![disk("sda", LARGE)],
            raid_arrays: Vec::new(),
            volume_groups: Vec::new(),
            logical_volumes: Vec::new(),
        };
        let choice = GuidedChoice {
            raw_target: Some(RawTarget::Disk(PathBuf::from("/dev/sda"))),
            volume_layer: VolumeLayer::Direct,
            swap: crate::storage::SwapChoice::Zram,
        };
        let plan = PlanBuilder::new(&snapshot)
            .build(&choice)
            .expect("fixture plan should be valid");
        (plan, snapshot)
    }

    fn whole_disk_plan_with_swap_partition() -> (InstallPlan, StorageSnapshot) {
        let (mut plan, snapshot) = whole_disk_plan_with_new_esp();
        plan.swap = SwapPlan::Partition {
            size_bytes: crate::storage::DISK_SWAP_SIZE_BYTES,
        };
        (plan, snapshot)
    }

    #[test]
    fn whole_disk_with_new_esp_produces_operations_in_mount_safe_order() {
        let (plan, snapshot) = whole_disk_plan_with_new_esp();
        let operations =
            plan_to_operations(&plan, &snapshot).expect("direct whole-disk plan should translate");

        let describe: Vec<String> = operations.iter().map(|op| op.describe()).collect();
        assert_eq!(describe[0], "criar tabela de partições em /dev/sda");
        assert_eq!(describe[1], "formatar ESP em /dev/sda1");
        assert_eq!(describe[2], "formatar Btrfs em /dev/sda2");
        assert_eq!(describe[3], "criar subvolumes Btrfs");
        // plan_to_operations covers only partitioning; SyncAndFinish is
        // appended later by `build`, alongside deployment (#41).
        assert_eq!(describe.last().unwrap(), "gerar /etc/fstab");
        assert_eq!(describe[describe.len() - 2], "montar ESP em /boot/efi");

        // 21 default subvolumes (see storage::plan::default_subvolumes).
        let mount_count = describe
            .iter()
            .filter(|d| d.starts_with("montar /@"))
            .count();
        assert_eq!(mount_count, 21);

        let index_of = |needle: &str| describe.iter().position(|d| d == needle).unwrap();
        // Ancestors must be mounted before descendants, or reverse-order
        // unmount on rollback would try to unmount a parent while a child
        // mount still exists under it.
        assert!(index_of("montar /@ em /") < index_of("montar /@/home em /home"));
        assert!(
            index_of("montar /@/var/lib/machines em /var/lib/machines")
                < index_of("montar /@/var/lib/libvirt/images em /var/lib/libvirt/images")
        );
    }

    #[test]
    fn build_assembles_partitioning_then_deployment_then_a_final_sync() {
        let (plan, snapshot) = whole_disk_plan_with_new_esp();
        let request = super::super::ExecutionRequest {
            choice: GuidedChoice {
                raw_target: Some(RawTarget::Disk(PathBuf::from("/dev/sda"))),
                volume_layer: VolumeLayer::Direct,
                swap: crate::storage::SwapChoice::Zram,
            },
            plan,
            config: crate::InstallConfig::default(),
        };

        let operations = build(&request, &snapshot).expect("request should translate");
        let describe: Vec<String> = operations.iter().map(|op| op.describe()).collect();

        // Partitioning ends with the fstab write (see the test above);
        // deployment starts right after with the rootfs extraction; the
        // whole thing ends with the sync that plan_to_operations no longer
        // includes on its own.
        let fstab_index = describe
            .iter()
            .position(|d| d == "gerar /etc/fstab")
            .unwrap();
        assert_eq!(describe[fstab_index + 1], "extrair rootfs da sessão live");
        assert_eq!(describe.last().unwrap(), "sincronizar dispositivos");
        assert!(describe.iter().any(|d| d == "gerar initramfs (dracut)"));
    }

    #[test]
    fn create_partition_table_argv_matches_expected_sgdisk_invocations_when_creating_an_esp() {
        let (plan, snapshot) = whole_disk_plan_with_new_esp();
        let operations = plan_to_operations(&plan, &snapshot).unwrap();
        let executor = FakeExecutor::new();

        operations[0]
            .perform(&executor)
            .expect("partition table creation should succeed");

        assert_eq!(
            executor.calls(),
            vec![
                "wipefs -a /dev/sda",
                "sgdisk --zap-all /dev/sda",
                "sgdisk -n1:0:+300M -t1:ef00 /dev/sda",
                "sgdisk -n2:0:0 -t2:8300 /dev/sda",
            ]
        );
    }

    #[test]
    fn disk_swap_gets_its_own_partition_and_is_formatted() {
        let (plan, snapshot) = whole_disk_plan_with_swap_partition();
        let operations = plan_to_operations(&plan, &snapshot).unwrap();
        let executor = FakeExecutor::new();

        operations[0].perform(&executor).unwrap();
        assert_eq!(
            executor.calls(),
            vec![
                "wipefs -a /dev/sda",
                "sgdisk --zap-all /dev/sda",
                "sgdisk -n1:0:+300M -t1:ef00 /dev/sda",
                "sgdisk -n2:0:+8192M -t2:8200 /dev/sda",
                "sgdisk -n3:0:0 -t3:8300 /dev/sda",
            ]
        );
        assert_eq!(operations[2].describe(), "formatar swap em /dev/sda2");
        operations[2].perform(&executor).unwrap();
        assert_eq!(executor.calls().last().unwrap(), "mkswap /dev/sda2");
        assert!(
            operations
                .iter()
                .any(|op| op.describe() == "formatar Btrfs em /dev/sda3")
        );
    }

    #[test]
    fn esp_reuse_never_formats_or_creates_an_esp_partition() {
        let mut esp_disk = disk("sda", LARGE);
        esp_disk.partitions.push(crate::storage::Partition {
            path: PathBuf::from("/dev/sda1"),
            number: 1,
            size_bytes: 300 * 1024 * 1024,
            filesystem: Some("vfat".to_string()),
            mountpoints: vec![PathBuf::from("/boot/efi")],
            part_type: Some("esp".to_string()),
            uuid: None,
        });
        let target_disk = disk("sdb", LARGE);
        let snapshot = StorageSnapshot {
            uefi: true,
            disks: vec![esp_disk, target_disk],
            raid_arrays: Vec::new(),
            volume_groups: Vec::new(),
            logical_volumes: Vec::new(),
        };
        let choice = GuidedChoice {
            raw_target: Some(RawTarget::Disk(PathBuf::from("/dev/sdb"))),
            volume_layer: VolumeLayer::Direct,
            swap: crate::storage::SwapChoice::Zram,
        };
        let plan = PlanBuilder::new(&snapshot)
            .build(&choice)
            .expect("fixture plan should be valid");

        let operations = plan_to_operations(&plan, &snapshot).expect("plan should translate");
        assert!(
            !operations
                .iter()
                .any(|op| op.describe().contains("formatar ESP")),
            "reusing an existing ESP must never format it"
        );

        let executor = FakeExecutor::new();
        operations[0].perform(&executor).unwrap();
        assert_eq!(
            executor.calls(),
            vec![
                "wipefs -a /dev/sdb",
                "sgdisk --zap-all /dev/sdb",
                "sgdisk -n1:0:0 -t1:8300 /dev/sdb"
            ],
            "the target disk gets only a root partition; the existing ESP on the other disk is untouched"
        );
    }

    #[test]
    fn occupied_disk_is_released_before_being_wiped() {
        let mut occupied = disk("sda", LARGE);
        occupied.role = DeviceRole::Unsupported;
        occupied.partitions.push(crate::storage::Partition {
            path: PathBuf::from("/dev/sda1"),
            number: 1,
            size_bytes: 300 * 1024 * 1024,
            filesystem: Some("ext4".to_string()),
            mountpoints: vec![PathBuf::from("/mnt/dados")],
            part_type: None,
            uuid: None,
        });
        occupied.partitions.push(crate::storage::Partition {
            path: PathBuf::from("/dev/sda2"),
            number: 2,
            size_bytes: 2 * 1024 * 1024 * 1024,
            filesystem: Some("swap".to_string()),
            mountpoints: Vec::new(),
            part_type: None,
            uuid: None,
        });
        let snapshot = StorageSnapshot {
            uefi: true,
            disks: vec![occupied],
            raid_arrays: Vec::new(),
            volume_groups: Vec::new(),
            logical_volumes: Vec::new(),
        };
        let choice = GuidedChoice {
            raw_target: Some(RawTarget::Disk(PathBuf::from("/dev/sda"))),
            volume_layer: VolumeLayer::Direct,
            swap: crate::storage::SwapChoice::Zram,
        };
        let plan = PlanBuilder::new(&snapshot)
            .build(&choice)
            .expect("whole-disk install should accept an occupied disk");

        let operations = plan_to_operations(&plan, &snapshot).expect("plan should translate");
        assert_eq!(
            operations[0].describe(),
            "liberar partições em uso em /dev/sda",
            "the disk must be released before CreatePartitionTable runs wipefs/sgdisk"
        );

        let executor = FakeExecutor::new();
        operations[0].perform(&executor).unwrap();
        assert_eq!(
            executor.calls(),
            vec!["swapoff /dev/sda2", "umount -R /mnt/dados"]
        );

        assert_eq!(
            operations[1].describe(),
            "criar tabela de partições em /dev/sda"
        );
    }

    #[test]
    fn occupied_disk_with_active_lvm_deactivates_the_volume_group_before_being_wiped() {
        let mut occupied = disk("nvme0n1", LARGE);
        occupied.role = DeviceRole::Unsupported;
        occupied.partitions.push(crate::storage::Partition {
            path: PathBuf::from("/dev/nvme0n1p1"),
            number: 1,
            size_bytes: 512 * 1024 * 1024,
            filesystem: Some("vfat".to_string()),
            mountpoints: Vec::new(),
            part_type: None,
            uuid: None,
        });
        occupied.partitions.push(crate::storage::Partition {
            path: PathBuf::from("/dev/nvme0n1p2"),
            number: 2,
            size_bytes: LARGE,
            filesystem: Some("LVM2_member".to_string()),
            mountpoints: Vec::new(),
            part_type: None,
            uuid: None,
        });
        let snapshot = StorageSnapshot {
            uefi: true,
            disks: vec![occupied],
            raid_arrays: Vec::new(),
            volume_groups: vec![VolumeGroup {
                name: "system".to_string(),
                physical_volumes: vec![PathBuf::from("/dev/nvme0n1p2")],
                size_bytes: LARGE,
                free_bytes: 0,
            }],
            logical_volumes: Vec::new(),
        };
        let choice = GuidedChoice {
            raw_target: Some(RawTarget::Disk(PathBuf::from("/dev/nvme0n1"))),
            volume_layer: VolumeLayer::Direct,
            swap: crate::storage::SwapChoice::Zram,
        };
        let plan = PlanBuilder::new(&snapshot)
            .build(&choice)
            .expect("whole-disk install should accept a disk occupied by an LVM PV");

        let operations = plan_to_operations(&plan, &snapshot).expect("plan should translate");
        assert_eq!(
            operations[0].describe(),
            "liberar partições em uso em /dev/nvme0n1"
        );

        let executor = FakeExecutor::new();
        operations[0].perform(&executor).unwrap();
        assert_eq!(
            executor.calls(),
            vec!["vgchange -an system"],
            "an LVM PV on the target disk has nothing mounted or swapped on \
             directly, but the VG it backs must still be deactivated or \
             wipefs sees the partition as busy"
        );

        assert_eq!(
            operations[1].describe(),
            "criar tabela de partições em /dev/nvme0n1"
        );
        operations[1].perform(&executor).unwrap();
        assert_eq!(
            executor.calls()[1..],
            vec![
                "wipefs -a /dev/nvme0n1p1",
                "wipefs -a /dev/nvme0n1p2",
                "wipefs -a /dev/nvme0n1",
                "sgdisk --zap-all /dev/nvme0n1",
                "sgdisk -n1:0:+300M -t1:ef00 /dev/nvme0n1",
                "sgdisk -n2:0:0 -t2:8300 /dev/nvme0n1",
            ],
            "the old LVM2_member signature on nvme0n1p2 lives inside the \
             partition and survives `wipefs`/`sgdisk` run only against the \
             disk; deactivating the volume group isn't enough — without an \
             explicit wipe of the old partition, its stale signature can \
             resurface under lvm2-pvscan once a new partition lands on the \
             same bytes and the next mkfs sees the device as busy"
        );
    }

    #[test]
    fn free_disk_gets_no_release_step() {
        let (plan, snapshot) = whole_disk_plan_with_new_esp();
        let operations = plan_to_operations(&plan, &snapshot).expect("plan should translate");
        assert_eq!(
            operations[0].describe(),
            "criar tabela de partições em /dev/sda",
            "a disk with nothing mounted or swapped-on needs no release step"
        );
    }

    #[test]
    fn raid_and_lvm_raw_targets_are_rejected_explicitly_not_silently_skipped() {
        let raid_snapshot = StorageSnapshot {
            uefi: true,
            disks: Vec::new(),
            raid_arrays: vec![RaidArray {
                path: PathBuf::from("/dev/md0"),
                level: RaidLevel::Raid1,
                members: vec![PathBuf::from("/dev/sda"), PathBuf::from("/dev/sdb")],
                degraded: false,
                size_bytes: LARGE,
            }],
            volume_groups: Vec::new(),
            logical_volumes: Vec::new(),
        };
        let raid_choice = GuidedChoice {
            raw_target: Some(RawTarget::ExistingRaid {
                array: PathBuf::from("/dev/md0"),
            }),
            volume_layer: VolumeLayer::Direct,
            swap: crate::storage::SwapChoice::Zram,
        };
        let raid_plan = PlanBuilder::new(&raid_snapshot)
            .build(&raid_choice)
            .expect("valid raid plan");
        assert!(matches!(
            plan_to_operations(&raid_plan, &raid_snapshot),
            Err(OperationError::NotImplemented(_))
        ));

        let vg_snapshot = StorageSnapshot {
            uefi: true,
            disks: Vec::new(),
            raid_arrays: Vec::new(),
            volume_groups: vec![VolumeGroup {
                name: "vg-lyra".to_string(),
                physical_volumes: vec![PathBuf::from("/dev/sda1")],
                size_bytes: LARGE,
                free_bytes: LARGE,
            }],
            logical_volumes: Vec::new(),
        };
        let vg_choice = GuidedChoice {
            raw_target: None,
            volume_layer: VolumeLayer::ExistingVolumeGroup {
                name: "vg-lyra".to_string(),
                logical_volumes: vec![LogicalVolumePlan {
                    name: "root".to_string(),
                    mount_point: PathBuf::from("/"),
                    size: SizePolicy::FillRemaining,
                }],
            },
            swap: crate::storage::SwapChoice::Zram,
        };
        let vg_plan = PlanBuilder::new(&vg_snapshot)
            .build(&vg_choice)
            .expect("valid vg plan");
        assert!(matches!(
            plan_to_operations(&vg_plan, &vg_snapshot),
            Err(OperationError::NotImplemented(_))
        ));
    }

    #[test]
    fn mount_subvolume_creates_the_target_directory_and_uses_compress_by_default() {
        let temp = TempRoot::new("mount-subvolume");
        let op = MountSubvolume {
            target_root: temp.0.clone(),
            mount_point: PathBuf::from("/home"),
            subvolume: "/@/home".to_string(),
            partition: PathBuf::from("/dev/sda2"),
        };
        let executor = FakeExecutor::new();

        op.perform(&executor).expect("mount should succeed");
        assert!(temp.0.join("home").is_dir());
        assert_eq!(
            executor.calls(),
            vec![
                "mount -o subvol=/@/home,compress=zstd:3 /dev/sda2 ".to_string()
                    + &temp.0.join("home").to_string_lossy()
            ]
        );

        op.undo(&executor).expect("undo should succeed");
        assert_eq!(
            executor.calls().last().unwrap(),
            &("umount ".to_string() + &temp.0.join("home").to_string_lossy())
        );
    }

    #[test]
    fn every_subvolume_mount_uses_the_same_filesystem_wide_policy() {
        let temp = TempRoot::new("mount-subvolume-policy");
        let op = MountSubvolume {
            target_root: temp.0.clone(),
            mount_point: PathBuf::from("/var/lib/mariadb"),
            subvolume: "/@/var/lib/mariadb".to_string(),
            partition: PathBuf::from("/dev/sda2"),
        };
        let executor = FakeExecutor::new();

        op.perform(&executor).expect("mount should succeed");
        let call = executor.calls().into_iter().next().unwrap();
        assert!(call.contains("compress=zstd:3"));
        assert!(!call.contains("nodatacow"));
    }

    #[test]
    fn mount_subvolume_at_root_mounts_directly_onto_target_root() {
        let temp = TempRoot::new("mount-subvolume-root");
        let op = MountSubvolume {
            target_root: temp.0.clone(),
            mount_point: PathBuf::from("/"),
            subvolume: "/@".to_string(),
            partition: PathBuf::from("/dev/sda2"),
        };
        let executor = FakeExecutor::new();

        op.perform(&executor).expect("mount should succeed");
        let call = executor.calls().into_iter().next().unwrap();
        assert!(call.ends_with(&temp.0.to_string_lossy().into_owned()));
    }

    #[test]
    fn mount_esp_creates_boot_efi_and_uses_expected_options() {
        let temp = TempRoot::new("mount-esp");
        let op = MountEsp {
            target_root: temp.0.clone(),
            partition: PathBuf::from("/dev/sda1"),
        };
        let executor = FakeExecutor::new();

        op.perform(&executor).expect("mount should succeed");
        assert!(temp.0.join("boot/efi").is_dir());
        assert_eq!(
            executor.calls(),
            vec![format!(
                "mount -o defaults,umask=0077 /dev/sda1 {}",
                temp.0.join("boot/efi").display()
            )]
        );
    }

    #[test]
    fn write_fstab_uses_real_uuids_and_matching_mount_options() {
        let temp = TempRoot::new("write-fstab");
        let subvolumes = vec![
            SubvolumePlan {
                mount_point: PathBuf::from("/"),
                subvolume: "/@".to_string(),
                nodatacow: false,
            },
            SubvolumePlan {
                mount_point: PathBuf::from("/var/lib/mariadb"),
                subvolume: "/@/var/lib/mariadb".to_string(),
                nodatacow: true,
            },
        ];
        let op = WriteFstab {
            target_root: temp.0.clone(),
            root_partition: PathBuf::from("/dev/sda2"),
            esp_partition: PathBuf::from("/dev/sda1"),
            swap_partition: None,
            subvolumes,
        };
        let executor = FakeExecutor::new();

        op.perform(&executor)
            .expect("fstab generation should succeed");

        let content =
            fs::read_to_string(temp.0.join("etc/fstab")).expect("fstab should have been written");
        assert!(content.contains("UUID-FOR-/dev/sda2 / btrfs subvol=/@,compress=zstd:3 0 0"));
        assert!(content.contains(
            "UUID-FOR-/dev/sda2 /var/lib/mariadb btrfs subvol=/@/var/lib/mariadb,compress=zstd:3 0 0"
        ));
        assert!(content.contains("UUID-FOR-/dev/sda1 /boot/efi vfat defaults,umask=0077 0 2"));
    }

    #[test]
    fn write_fstab_includes_the_selected_disk_swap() {
        let temp = TempRoot::new("write-fstab-swap");
        let op = WriteFstab {
            target_root: temp.0.clone(),
            root_partition: PathBuf::from("/dev/sda3"),
            esp_partition: PathBuf::from("/dev/sda1"),
            swap_partition: Some(PathBuf::from("/dev/sda2")),
            subvolumes: vec![SubvolumePlan {
                mount_point: PathBuf::from("/"),
                subvolume: "/@".to_string(),
                nodatacow: false,
            }],
        };

        op.perform(&FakeExecutor::new()).unwrap();
        let content = fs::read_to_string(temp.0.join("etc/fstab")).unwrap();
        assert!(content.contains("UUID=UUID-FOR-/dev/sda2 none swap defaults 0 0"));
    }

    #[test]
    fn create_subvolumes_mounts_staging_creates_each_subvolume_and_unmounts() {
        let staging = TempRoot::new("create-subvolumes-staging");
        let subvolumes = vec![
            SubvolumePlan {
                mount_point: PathBuf::from("/"),
                subvolume: "/@".to_string(),
                nodatacow: false,
            },
            SubvolumePlan {
                mount_point: PathBuf::from("/var/lib/machines"),
                subvolume: "/@/var/lib/machines".to_string(),
                nodatacow: true,
            },
        ];
        let op = CreateSubvolumes {
            partition: PathBuf::from("/dev/sda2"),
            staging: staging.0.clone(),
            subvolumes,
        };
        let executor = FakeExecutor::new();

        op.perform(&executor)
            .expect("subvolume creation should succeed");

        assert_eq!(
            executor.calls(),
            vec![
                format!("mount /dev/sda2 {}", staging.0.display()),
                format!("btrfs subvolume create {}", staging.0.join("@").display()),
                format!(
                    "btrfs subvolume create {}",
                    staging.0.join("@/var/lib/machines").display()
                ),
                format!(
                    "chattr +C {}",
                    staging.0.join("@/var/lib/machines").display()
                ),
                format!("umount {}", staging.0.display()),
            ]
        );
        // The parent directory for the nested subvolume must exist as a
        // plain directory even though "@/var/lib" was never itself created
        // as a subvolume.
        assert!(staging.0.join("@/var/lib").is_dir());
    }
}
