//! Declarative, dry-run install plan: turns a [`StorageSnapshot`] plus a
//! user's guided choice into an [`InstallPlan`], or a list of reasons the
//! choice is blocked. `PlanBuilder::build` never touches the system — that
//! is what makes it safe to call from the unprivileged frontend and what
//! satisfies issue #39's "dry-run não executa operações privilegiadas".
//!
//! Executing a plan (`mdadm --create`, `vgcreate`, `mkfs.btrfs`, ...) is the
//! privileged service's job (issues #37/#40), not this module's.

use std::path::PathBuf;

use serde::{Deserialize, Serialize};

use super::device::{DeviceRole, Disk, RaidLevel, StorageSnapshot};

/// Below this, a whole-disk/array/VG is not offered as an install target.
/// No size requirement is documented anywhere in the project yet (grepped
/// `PROMPT-LYRA-OS.md`, the historical storage reference, and
/// `docs/installer-architecture.md`
/// — none set one); 20 GiB is a conservative placeholder for a Btrfs+Plasma
/// desktop root and should be revisited once #49 (performance/size budget)
/// lands.
pub const MINIMUM_ROOT_SIZE_BYTES: u64 = 20 * 1024 * 1024 * 1024;

pub const ESP_RECOMMENDED_SIZE_BYTES: u64 = 300 * 1024 * 1024;
pub const ESP_MINIMUM_SIZE_BYTES: u64 = 32 * 1024 * 1024;

/// Wire-format version for [`InstallPlan`]. Any structural or semantic change
/// that an older privileged service could misinterpret must increment this
/// value. The service rejects unknown versions before running an operation.
pub const INSTALL_PLAN_SCHEMA_VERSION: u32 = 3;

/// Fixed size used by the guided "swap em disco" choice. Keeping the size
/// in the typed plan makes the destructive layout explicit and lets the
/// builder reserve the space before approving the installation.
pub const DISK_SWAP_SIZE_BYTES: u64 = 8 * 1024 * 1024 * 1024;

// --- Btrfs layout used by Lyra's native installer ---

/// Filesystem-wide Btrfs policy. Btrfs does not implement `compress` or
/// `nodatacow` independently per subvolume, so every mount and fstab entry
/// must agree. Zstd's current default is level 3; spelling it out keeps the
/// release policy stable if the upstream default changes.
pub const BTRFS_MOUNT_OPTIONS: &str = "compress=zstd:3";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SubvolumePlan {
    pub mount_point: PathBuf,
    pub subvolume: String,
    /// Mark the empty subvolume root with `chattr +C` before deployment so
    /// new database/VM files inherit NOCOW without changing filesystem-wide
    /// mount options.
    pub nodatacow: bool,
}

fn subvol(mount_point: &str, subvolume: &str, nodatacow: bool) -> SubvolumePlan {
    SubvolumePlan {
        mount_point: PathBuf::from(mount_point),
        subvolume: subvolume.to_string(),
        nodatacow,
    }
}

/// The 20 subvolumes from `mount.conf`, in the same order.
pub fn default_subvolumes() -> Vec<SubvolumePlan> {
    vec![
        subvol("/", "/@", false),
        subvol("/home", "/@/home", false),
        subvol("/opt", "/@/opt", false),
        subvol("/srv", "/@/srv", false),
        subvol("/tmp", "/@/tmp", false),
        subvol("/usr/local", "/@/usr/local", false),
        subvol("/var/cache", "/@/var/cache", false),
        subvol("/var/crash", "/@/var/crash", false),
        subvol("/var/lib/machines", "/@/var/lib/machines", false),
        subvol("/var/lib/mailman", "/@/var/lib/mailman", false),
        subvol("/var/lib/named", "/@/var/lib/named", false),
        subvol("/var/log", "/@/var/log", false),
        subvol("/var/opt", "/@/var/opt", false),
        subvol("/var/spool", "/@/var/spool", false),
        subvol("/var/tmp", "/@/var/tmp", false),
        subvol("/boot/grub2/i386-pc", "/@/boot/grub2/i386-pc", false),
        subvol("/boot/grub2/x86_64-efi", "/@/boot/grub2/x86_64-efi", false),
        subvol("/var/lib/libvirt/images", "/@/var/lib/libvirt/images", true),
        subvol("/var/lib/mariadb", "/@/var/lib/mariadb", true),
        subvol("/var/lib/mysql", "/@/var/lib/mysql", true),
        subvol("/var/lib/pgsql", "/@/var/lib/pgsql", true),
    ]
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum FilesystemPlan {
    Btrfs { subvolumes: Vec<SubvolumePlan> },
}

impl Default for FilesystemPlan {
    fn default() -> Self {
        FilesystemPlan::Btrfs {
            subvolumes: default_subvolumes(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum EspPlan {
    Create {
        size_bytes: u64,
    },
    /// An existing ESP is reused, never reformatted implicitly (per #39's
    /// acceptance criteria).
    Reuse {
        path: PathBuf,
    },
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
pub enum SwapChoice {
    None,
    Disk,
    #[default]
    Zram,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum SwapPlan {
    None,
    Partition { size_bytes: u64 },
    Zram,
}

// --- Target shape: raw block target, optionally with LVM on top -----------

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum RawTarget {
    Disk(PathBuf),
    NewRaid {
        level: RaidLevel,
        members: Vec<PathBuf>,
        name: String,
    },
    ExistingRaid {
        array: PathBuf,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SizePolicy {
    FillRemaining,
    Fixed(u64),
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LogicalVolumePlan {
    pub name: String,
    pub mount_point: PathBuf,
    pub size: SizePolicy,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum VolumeLayer {
    /// Root filesystem sits directly on the raw target's root partition —
    /// no LVM involved.
    Direct,
    NewVolumeGroup {
        name: String,
        logical_volumes: Vec<LogicalVolumePlan>,
    },
    ExistingVolumeGroup {
        name: String,
        logical_volumes: Vec<LogicalVolumePlan>,
    },
}

/// What the guided wizard collected from the user, before validation.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GuidedChoice {
    /// `None` only when `volume_layer` is `ExistingVolumeGroup` — the target
    /// *is* the volume group, there is no raw disk/array to prepare first.
    pub raw_target: Option<RawTarget>,
    pub volume_layer: VolumeLayer,
    #[serde(default)]
    pub swap: SwapChoice,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct DestructiveSummary {
    /// Human-readable description of data that will be erased, one entry
    /// per affected device (e.g. "sda1: ext4, montado em /mnt/dados (120 GiB)").
    pub erased: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct InstallPlan {
    pub schema_version: u32,
    pub raw_target: Option<RawTarget>,
    pub volume_layer: VolumeLayer,
    pub esp: EspPlan,
    pub swap: SwapPlan,
    pub root_filesystem: FilesystemPlan,
    pub destructive_summary: DestructiveSummary,
    pub warnings: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PlanError(pub Vec<String>);

pub struct PlanBuilder<'a> {
    snapshot: &'a StorageSnapshot,
}

impl<'a> PlanBuilder<'a> {
    pub fn new(snapshot: &'a StorageSnapshot) -> Self {
        Self { snapshot }
    }

    /// Pure function: validates `choice` against `snapshot` and produces a
    /// declarative plan, or every reason it's blocked. No I/O happens here.
    pub fn build(&self, choice: &GuidedChoice) -> Result<InstallPlan, PlanError> {
        let mut errors = Vec::new();
        let mut warnings = Vec::new();
        let mut erased = Vec::new();
        let mut available_bytes: Option<u64> = None;

        match &choice.raw_target {
            Some(RawTarget::Disk(path)) => match self.eligible_disk(path) {
                Ok(disk) => {
                    available_bytes = Some(disk.size_bytes);
                    describe_disk_erasure(disk, &mut erased);
                }
                Err(reason) => errors.push(reason),
            },
            Some(RawTarget::NewRaid {
                level,
                members,
                name,
            }) => {
                if members.len() < level.minimum_members() {
                    errors.push(format!(
                        "{name}: {level:?} exige ao menos {} discos, {} informados",
                        level.minimum_members(),
                        members.len()
                    ));
                }
                let mut member_sizes = Vec::new();
                for member in members {
                    match self.eligible_disk(member) {
                        Ok(disk) => {
                            member_sizes.push(disk.size_bytes);
                            describe_disk_erasure(disk, &mut erased);
                        }
                        Err(reason) => errors.push(reason),
                    }
                }
                if !member_sizes.is_empty() {
                    available_bytes = Some(raid_capacity(*level, &member_sizes));
                }
            }
            Some(RawTarget::ExistingRaid { array }) => match self.eligible_raid_array(array) {
                Ok(raid) => available_bytes = Some(raid.size_bytes),
                Err(reason) => errors.push(reason),
            },
            None => {
                if !matches!(choice.volume_layer, VolumeLayer::ExistingVolumeGroup { .. }) {
                    errors.push(
                        "nenhum destino selecionado: informe um disco, array RAID ou volume group"
                            .to_string(),
                    );
                }
            }
        }

        // A whole-disk install always recreates the target disk's partition
        // table.  Do not reuse an ESP that lives on that disk: its path will
        // be destroyed by sgdisk before the new layout is created.
        let target_disk = match &choice.raw_target {
            Some(RawTarget::Disk(path)) => Some(path.as_path()),
            _ => None,
        };
        let esp = match self.existing_esp(target_disk) {
            Some(path) => EspPlan::Reuse { path },
            None => EspPlan::Create {
                size_bytes: ESP_RECOMMENDED_SIZE_BYTES,
            },
        };
        if matches!(esp, EspPlan::Create { .. }) {
            warnings.push("nenhuma ESP existente encontrada — uma nova será criada".to_string());
        }

        let swap = match choice.swap {
            SwapChoice::None => SwapPlan::None,
            SwapChoice::Disk => SwapPlan::Partition {
                size_bytes: DISK_SWAP_SIZE_BYTES,
            },
            SwapChoice::Zram => SwapPlan::Zram,
        };
        let reserved_bytes = match esp {
            EspPlan::Create { size_bytes } => size_bytes,
            EspPlan::Reuse { .. } => 0,
        } + match swap {
            SwapPlan::Partition { size_bytes } => size_bytes,
            SwapPlan::None | SwapPlan::Zram => 0,
        };
        let root_available_bytes =
            available_bytes.map(|bytes| bytes.saturating_sub(reserved_bytes));

        let root_mount_present;
        match &choice.volume_layer {
            VolumeLayer::Direct => {
                root_mount_present = true;
            }
            VolumeLayer::NewVolumeGroup {
                name,
                logical_volumes,
            } => {
                root_mount_present = has_root_mount(logical_volumes);
                if let Err(reason) =
                    validate_logical_volumes(name, logical_volumes, root_available_bytes)
                {
                    errors.push(reason);
                }
            }
            VolumeLayer::ExistingVolumeGroup {
                name,
                logical_volumes,
            } => {
                root_mount_present = has_root_mount(logical_volumes);
                match self.eligible_volume_group(name) {
                    Ok(vg) => {
                        if let Err(reason) =
                            validate_logical_volumes(name, logical_volumes, Some(vg.free_bytes))
                        {
                            errors.push(reason);
                        }
                    }
                    Err(reason) => errors.push(reason),
                }
            }
        }
        if !root_mount_present {
            errors.push(
                "o layout de volumes precisa incluir uma logical volume montada em /".to_string(),
            );
        }

        if let Some(bytes) = root_available_bytes
            && bytes < MINIMUM_ROOT_SIZE_BYTES
        {
            errors.push(format!(
                "espaço insuficiente para a raiz: {bytes} bytes após ESP/swap, mínimo {MINIMUM_ROOT_SIZE_BYTES} bytes"
            ));
        }

        if !errors.is_empty() {
            return Err(PlanError(errors));
        }

        Ok(InstallPlan {
            schema_version: INSTALL_PLAN_SCHEMA_VERSION,
            raw_target: choice.raw_target.clone(),
            volume_layer: choice.volume_layer.clone(),
            esp,
            swap,
            root_filesystem: FilesystemPlan::default(),
            destructive_summary: DestructiveSummary { erased },
            warnings,
        })
    }

    fn eligible_disk(&self, path: &PathBuf) -> Result<&Disk, String> {
        let disk = self
            .snapshot
            .disks
            .iter()
            .find(|d| &d.path == path)
            .ok_or_else(|| format!("{}: disco não encontrado", path.display()))?;

        if disk.is_live_media {
            return Err(format!(
                "{}: é a mídia de instalação (live) e nunca pode ser um destino",
                path.display()
            ));
        }
        match disk.role {
            DeviceRole::Free => Ok(disk),
            DeviceRole::RaidMember => {
                Err(format!("{}: já é membro de um array RAID", path.display()))
            }
            DeviceRole::LvmPhysicalVolume => Err(format!(
                "{}: já é um physical volume LVM em uso",
                path.display()
            )),
            // A whole-disk guided install is explicitly destructive. Existing
            // partitions are reported in the plan summary and wiped by the
            // partitioning operations after the user confirms installation.
            DeviceRole::Unsupported => Ok(disk),
        }
    }

    fn eligible_raid_array(&self, path: &PathBuf) -> Result<&super::device::RaidArray, String> {
        let raid = self
            .snapshot
            .raid_arrays
            .iter()
            .find(|r| &r.path == path)
            .ok_or_else(|| format!("{}: array RAID não encontrado", path.display()))?;
        if raid.degraded {
            return Err(format!(
                "{}: array RAID degradado não é um destino suportado",
                path.display()
            ));
        }
        Ok(raid)
    }

    fn eligible_volume_group(&self, name: &str) -> Result<&super::device::VolumeGroup, String> {
        self.snapshot
            .volume_groups
            .iter()
            .find(|vg| vg.name == name)
            .ok_or_else(|| format!("{name}: volume group não encontrado"))
    }

    /// UEFI-only per `config.xml`'s `firmware="uefi"`, so ESP detection is
    /// simply "an existing vfat/EFI-typed partition" — reused verbatim,
    /// never reformatted (matches `partition.conf`'s ESP override).
    fn existing_esp(&self, excluded_disk: Option<&std::path::Path>) -> Option<PathBuf> {
        self.snapshot.disks.iter().find_map(|disk| {
            if excluded_disk.is_some_and(|excluded| excluded == disk.path.as_path()) {
                return None;
            }
            disk.partitions
                .iter()
                .find(|p| {
                    p.mountpoints
                        .iter()
                        .any(|m| m == std::path::Path::new("/boot/efi"))
                })
                .map(|p| p.path.clone())
        })
    }
}

fn describe_disk_erasure(disk: &Disk, erased: &mut Vec<String>) {
    if disk.partitions.is_empty() {
        return;
    }
    for partition in &disk.partitions {
        let fs = partition.filesystem.as_deref().unwrap_or("desconhecido");
        let mount = partition
            .mountpoints
            .first()
            .map(|m| format!(", montado em {}", m.display()))
            .unwrap_or_default();
        erased.push(format!(
            "{}: {fs}{mount} ({} bytes)",
            partition.path.display(),
            partition.size_bytes
        ));
    }
}

fn has_root_mount(logical_volumes: &[LogicalVolumePlan]) -> bool {
    logical_volumes
        .iter()
        .any(|lv| lv.mount_point.as_path() == std::path::Path::new("/"))
}

fn validate_logical_volumes(
    vg_name: &str,
    logical_volumes: &[LogicalVolumePlan],
    available_bytes: Option<u64>,
) -> Result<(), String> {
    if logical_volumes.is_empty() {
        return Err(format!("{vg_name}: nenhuma logical volume definida"));
    }
    let Some(available) = available_bytes else {
        return Ok(());
    };
    let fixed: u64 = logical_volumes
        .iter()
        .filter_map(|lv| match lv.size {
            SizePolicy::Fixed(bytes) => Some(bytes),
            SizePolicy::FillRemaining => None,
        })
        .sum();
    if fixed > available {
        return Err(format!(
            "{vg_name}: logical volumes somam {fixed} bytes, disponível {available} bytes"
        ));
    }
    Ok(())
}

/// Usable capacity for a freshly created array — conservative, mirrors
/// mdadm's own formulas assuming equally sized members.
fn raid_capacity(level: RaidLevel, member_sizes: &[u64]) -> u64 {
    let smallest = member_sizes.iter().copied().min().unwrap_or(0);
    let count = member_sizes.len() as u64;
    match level {
        RaidLevel::Raid0 => smallest * count,
        RaidLevel::Raid1 => smallest,
        RaidLevel::Raid5 => smallest * count.saturating_sub(1),
        RaidLevel::Raid6 => smallest * count.saturating_sub(2),
        RaidLevel::Raid10 => smallest * (count / 2),
    }
}
