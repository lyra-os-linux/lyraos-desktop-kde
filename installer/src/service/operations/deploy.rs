//! Rootfs deployment and target configuration (issue #41): extract the live
//! squashfs into the mounted target from #40, then configure the installed
//! system. The initial behavior was audited against the former installer
//! path and is now owned directly by Lyra rather than depending on it.
//!
//! Most steps use `--root`/`-R` flags (`useradd`, `userdel`, `chpasswd`,
//! `systemctl`) or plain file I/O against paths under the target, avoiding
//! a chroot entirely. Only `dracut` genuinely needs one — it inspects the
//! target's own `/lib/modules` — so [`BindMount`] + [`RunDracut`] are the
//! only operations here that touch `chroot`.

use std::fs;
use std::io::Read;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};

use crate::InstallConfig;
use crate::storage::SwapPlan;

use super::{ArgvCommand, Executor, OperationError, PrivilegedOperation, io_error, path_str};

const LIVE_SQUASHFS: &str = "/run/overlay/live/LiveOS/squashfs.img";
const LIVE_NM_CONNECTIONS: &str = "/etc/NetworkManager/system-connections";

/// Repos whose priority KIWI sets to 1/2/3 (`kiwi/config.xml`) only so the
/// image build picks Lyra's own package forks — must drop back down once
/// installed, or a personal OBS project would keep outranking official
/// Leap packages on every future `zypper dup`.
const LYRA_REPO_ALIASES: &[&str] = &["repo-lyra", "repo-vega", "repo-fina"];
const INSTALLED_THIRD_PARTY_PRIORITY: u8 = 90;

/// Files that only make sense in the autologin live session.
const LIVE_ONLY_ARTIFACTS: &[&str] = &[
    "etc/sddm.conf.d/10-lyra-live.conf",
    "etc/sddm.conf",
    "etc/pam.d/common-auth-lyra-live",
    "etc/pam.d/sddm",
    "etc/pam.d/sddm-autologin",
    "etc/xdg/autostart/lyra-installer-autostart.desktop",
    "etc/xdg/autostart/lyra-plasma-initialize.desktop",
    "usr/libexec/lyra-live-plasma-start",
    "usr/libexec/lyra-live-sddm-autologin-retry",
    "usr/lib/systemd/system/lyra-live-autologin-retry.service",
    "usr/bin/lyra-live-smoke",
    // liveuser's passwordless sudo (kiwi/config.sh) - must never survive
    // onto the installed system, which gets its own sudo user with a real
    // password.
    "etc/sudoers.d/00-liveuser-nopasswd",
];

/// Essential services enabled in the installed system.
const ENABLED_SERVICES: &[&str] = &[
    "NetworkManager.service",
    "firewalld.service",
    "sddm.service",
    "cups.service",
];

pub fn deployment_operations(
    config: &InstallConfig,
    swap: &SwapPlan,
) -> Vec<Box<dyn PrivilegedOperation>> {
    let target_root = PathBuf::from(super::TARGET_ROOT);

    vec![
        Box::new(ExtractRootfs {
            target_root: target_root.clone(),
        }),
        Box::new(ConfigureSwap {
            target_root: target_root.clone(),
            swap: swap.clone(),
        }),
        Box::new(WriteMachineId {
            target_root: target_root.clone(),
        }),
        // Real settings.conf order is locale (timezone) -> keyboard ->
        // localecfg, not locale-then-keyboard with WriteLocale standing in
        // for localecfg - see WriteTimezone's doc comment.
        Box::new(WriteTimezone {
            target_root: target_root.clone(),
            timezone: config.timezone.clone(),
        }),
        Box::new(WriteKeyboard {
            target_root: target_root.clone(),
            keyboard_layout: config.keyboard_layout.clone(),
        }),
        Box::new(WriteLocale {
            target_root: target_root.clone(),
            locale: config.locale.clone(),
        }),
        Box::new(WriteHostname {
            target_root: target_root.clone(),
            hostname: config.hostname.clone(),
        }),
        Box::new(CreateUser {
            target_root: target_root.clone(),
            full_name: config.full_name.clone(),
            username: config.username.clone(),
            password: config.password.clone(),
        }),
        Box::new(WriteSudoers {
            target_root: target_root.clone(),
        }),
        Box::new(BindMount {
            source: PathBuf::from("/proc"),
            dest: target_root.join("proc"),
        }),
        Box::new(BindMount {
            source: PathBuf::from("/sys"),
            dest: target_root.join("sys"),
        }),
        Box::new(BindMount {
            source: PathBuf::from("/dev"),
            dest: target_root.join("dev"),
        }),
        Box::new(MountVirtualFs {
            fstype: "tmpfs",
            dest: target_root.join("run"),
        }),
        Box::new(BindMount {
            source: PathBuf::from("/run/udev"),
            dest: target_root.join("run/udev"),
        }),
        Box::new(MountVirtualFs {
            fstype: "efivarfs",
            dest: target_root.join("sys/firmware/efi/efivars"),
        }),
        Box::new(RunDracut {
            target_root: target_root.clone(),
        }),
        Box::new(RemoveLiveUser {
            target_root: target_root.clone(),
        }),
        Box::new(LowerLyraRepoPriorities {
            target_root: target_root.clone(),
        }),
        Box::new(DisableRepositoryPackageRetention {
            target_root: target_root.clone(),
        }),
        Box::new(RemoveLiveOnlyArtifacts {
            target_root: target_root.clone(),
        }),
        Box::new(CopyNetworkConfig {
            target_root: target_root.clone(),
            source_dir: PathBuf::from(LIVE_NM_CONNECTIONS),
            username: config.username.clone(),
        }),
        Box::new(SetHardwareClock {
            target_root: target_root.clone(),
        }),
        Box::new(EnableServices {
            target_root: target_root.clone(),
        }),
        // GRUB/Snapper come last, mirroring settings.conf's real order
        // (grubcfg -> uefibootloader -> snapshotcfg run right before
        // umount, after installcleanup/networkcfg/hwclock/services-systemd
        // above) - the first snapshot below must be taken after liveuser
        // and live-only artifacts are already gone, or it would capture
        // them. /proc, /sys, /dev are still bind-mounted from RunDracut
        // above (the engine only unwinds at the very end of the whole
        // run), so every chrooted step here reuses that same chroot.
        Box::new(WriteGrubDefaults {
            target_root: target_root.clone(),
        }),
        Box::new(GenerateGrubConfig {
            target_root: target_root.clone(),
        }),
        Box::new(InstallShimAndGrub {
            target_root: target_root.clone(),
        }),
        Box::new(PrepareBtrfsRollback {
            target_root: target_root.clone(),
        }),
        Box::new(SnapperCreateConfig {
            target_root: target_root.clone(),
        }),
        Box::new(MountSnapshotsSubvolume {
            target_root: target_root.clone(),
        }),
        Box::new(RegenerateInitramfsWithFstab {
            target_root: target_root.clone(),
        }),
        // The first rollback snapshot must not retain the live-only installer
        // package, especially its privileged service and polkit rule.
        Box::new(RemoveTransitionalInstallerArtifacts {
            target_root: target_root.clone(),
        }),
        Box::new(SnapperCreateFirstSnapshot {
            target_root: target_root.clone(),
        }),
        Box::new(GenerateGrubConfig { target_root }),
    ]
}

struct ConfigureSwap {
    target_root: PathBuf,
    swap: SwapPlan,
}

impl PrivilegedOperation for ConfigureSwap {
    fn describe(&self) -> String {
        match self.swap {
            SwapPlan::None => "desativar swap e ZRAM".to_string(),
            SwapPlan::Partition { .. } => "configurar swap em disco".to_string(),
            SwapPlan::Zram => "configurar ZRAM".to_string(),
        }
    }

    fn perform(&self, _executor: &dyn Executor) -> Result<(), OperationError> {
        let config = self.target_root.join("etc/systemd/zram-generator.conf");
        match self.swap {
            SwapPlan::Zram => {
                let parent = config.parent().expect("zram config always has a parent");
                fs::create_dir_all(parent).map_err(io_error)?;
                fs::write(
                    config,
                    "[zram0]\nzram-size = min(ram / 2, 8192)\ncompression-algorithm = zstd\n",
                )
                .map_err(io_error)?;
            }
            SwapPlan::None | SwapPlan::Partition { .. } => {
                if config.exists() {
                    fs::remove_file(config).map_err(io_error)?;
                }
            }
        }
        Ok(())
    }
}

fn random_bytes(n: usize) -> Result<Vec<u8>, OperationError> {
    let mut file = fs::File::open("/dev/urandom").map_err(io_error)?;
    let mut buf = vec![0u8; n];
    file.read_exact(&mut buf).map_err(io_error)?;
    Ok(buf)
}

fn random_hex(n: usize) -> Result<String, OperationError> {
    Ok(random_bytes(n)?
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}

struct ExtractRootfs {
    target_root: PathBuf,
}

impl PrivilegedOperation for ExtractRootfs {
    fn describe(&self) -> String {
        "extrair rootfs da sessão live".to_string()
    }
    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        executor.run(&ArgvCommand {
            binary: "unsquashfs".to_string(),
            args: vec![
                "-f".to_string(),
                "-d".to_string(),
                path_str(&self.target_root),
                LIVE_SQUASHFS.to_string(),
            ],
        })?;
        repair_root_permissions(&self.target_root)?;
        Ok(())
    }
}

/// Ports `unpackfs/main.py`'s `repair_root_permissions` exactly: squashfs
/// has a known, real quirk of leaving the extracted root at mode 777
/// (confirmed by the real module's own docstring, not guessed); anything
/// else is left untouched. Couldn't reproduce 777 with a hand-built test
/// squashfs against this machine's `unsquashfs` (got the expected 755), so
/// this may be a version- or build-flag-specific trigger this session
/// didn't hit — ported anyway since the fix is cheap, narrowly scoped
/// (only acts on exactly 777), and mirrors a real, deliberate upstream
/// workaround rather than a guess.
fn repair_root_permissions(target_root: &Path) -> Result<(), OperationError> {
    let metadata = fs::metadata(target_root).map_err(io_error)?;
    let mode = metadata.permissions().mode() & 0o777;
    if mode == 0o777 {
        fs::set_permissions(target_root, fs::Permissions::from_mode(0o755)).map_err(io_error)?;
    }
    Ok(())
}

/// Mirrors `machineid.conf`'s active keys: `systemd-style: uuid`,
/// `dbus-symlink: true`, `entropy-copy: false` (always generate fresh
/// entropy, never copy the live session's).
struct WriteMachineId {
    target_root: PathBuf,
}

impl PrivilegedOperation for WriteMachineId {
    fn describe(&self) -> String {
        "gerar machine-id".to_string()
    }

    fn perform(&self, _executor: &dyn Executor) -> Result<(), OperationError> {
        let id = random_hex(16)?;
        let etc = self.target_root.join("etc");
        fs::create_dir_all(&etc).map_err(io_error)?;
        fs::write(etc.join("machine-id"), format!("{id}\n")).map_err(io_error)?;

        let dbus_dir = self.target_root.join("var/lib/dbus");
        fs::create_dir_all(&dbus_dir).map_err(io_error)?;
        let dbus_link = dbus_dir.join("machine-id");
        let _ = fs::remove_file(&dbus_link);
        std::os::unix::fs::symlink("../../../etc/machine-id", &dbus_link).map_err(io_error)?;

        for seed_dir in ["var/lib/urandom", "var/lib/systemd"] {
            let dir = self.target_root.join(seed_dir);
            fs::create_dir_all(&dir).map_err(io_error)?;
            fs::write(dir.join("random-seed"), random_bytes(512)?).map_err(io_error)?;
        }
        Ok(())
    }
}

/// Writes the timezone selected on the Region page using Leap's canonical
/// `/etc/localtime`, `/etc/timezone`, and `/usr/share/zoneinfo` paths.
struct WriteTimezone {
    target_root: PathBuf,
    timezone: String,
}

impl PrivilegedOperation for WriteTimezone {
    fn describe(&self) -> String {
        format!("configurar fuso horário ({})", self.timezone)
    }

    fn perform(&self, _executor: &dyn Executor) -> Result<(), OperationError> {
        let etc = self.target_root.join("etc");
        fs::create_dir_all(&etc).map_err(io_error)?;

        let localtime = etc.join("localtime");
        let _ = fs::remove_file(&localtime);
        std::os::unix::fs::symlink(
            format!("../usr/share/zoneinfo/{}", self.timezone),
            &localtime,
        )
        .map_err(io_error)?;

        fs::write(etc.join("timezone"), format!("{}\n", self.timezone)).map_err(io_error)?;
        Ok(())
    }
}

/// Mirrors `localecfg`'s real `main.py`: writes `/etc/locale.conf` (every
/// `LC_*` category set to the same value as `LANG`, matching its
/// no-selection-made fallback shape) and `/etc/default/locale` only if
/// `/etc/default` exists. Leap has no `/etc/locale.gen`, so the module's
/// `locale-gen` branch never actually runs on this image either — nothing
/// to reproduce there.
struct WriteLocale {
    target_root: PathBuf,
    locale: String,
}

const LOCALE_CATEGORIES: &[&str] = &[
    "LANG",
    "LC_NUMERIC",
    "LC_TIME",
    "LC_MONETARY",
    "LC_PAPER",
    "LC_NAME",
    "LC_ADDRESS",
    "LC_TELEPHONE",
    "LC_MEASUREMENT",
    "LC_IDENTIFICATION",
];

impl PrivilegedOperation for WriteLocale {
    fn describe(&self) -> String {
        format!("configurar locale ({})", self.locale)
    }

    fn perform(&self, _executor: &dyn Executor) -> Result<(), OperationError> {
        let mut content = String::new();
        for key in LOCALE_CATEGORIES {
            content.push_str(&format!("{key}={}\n", self.locale));
        }

        let etc = self.target_root.join("etc");
        fs::create_dir_all(&etc).map_err(io_error)?;
        fs::write(etc.join("locale.conf"), &content).map_err(io_error)?;

        let default_dir = etc.join("default");
        if default_dir.is_dir() {
            fs::write(default_dir.join("locale"), &content).map_err(io_error)?;
        }
        Ok(())
    }
}

/// Writes the target's keyboard layout two ways, deliberately not the way
/// the previous, locale-inferred placeholder did:
///
/// - `/etc/vconsole.conf` `KEYMAP=` — still just best-effort (console
///   keymap names are a different namespace from XKB, `kbd` package, not
///   `xkeyboard-config`; the resolved XKB layout id is reused verbatim
///   since it happens to also be a valid console keymap for most of
///   [`KEYBOARD_LAYOUTS`]'s Latin-script entries), covers TTY access only
///   (Ctrl+Alt+F3), unrelated to the desktop session.
/// Plasma reads the system XKB defaults written to `/etc/default/keyboard`.
/// The setting remains a default and users can change it in System Settings.
struct WriteKeyboard {
    target_root: PathBuf,
    keyboard_layout: String,
}

impl PrivilegedOperation for WriteKeyboard {
    fn describe(&self) -> String {
        "configurar layout de teclado".to_string()
    }

    fn perform(&self, _executor: &dyn Executor) -> Result<(), OperationError> {
        let (_, xkb_layout, xkb_variant) = crate::KEYBOARD_LAYOUTS
            .iter()
            .find(|(id, ..)| *id == self.keyboard_layout)
            .ok_or_else(|| {
                OperationError::Io(format!(
                    "layout de teclado desconhecido: {}",
                    self.keyboard_layout
                ))
            })?;

        let etc = self.target_root.join("etc");
        fs::create_dir_all(&etc).map_err(io_error)?;
        fs::write(etc.join("vconsole.conf"), format!("KEYMAP={xkb_layout}\n")).map_err(io_error)?;

        // Real module also writes /etc/default/keyboard, only when
        // /etc/default already exists (confirmed via strings: its own
        // failure message says "existing /etc/default directory", same
        // conditional WriteLocale already mirrors for /etc/default/locale)
        // - not dead code here: /usr/bin/setupcon (present on this image)
        // reads exactly this file. XKBMODEL="pc105" is the module's own
        // literal default (also found via strings), used for every layout
        // since there's no model picker in the wizard.
        if etc.join("default").is_dir() {
            let variant = xkb_variant.unwrap_or("");
            fs::write(
                etc.join("default/keyboard"),
                format!(
                    "XKBMODEL=\"pc105\"\nXKBLAYOUT=\"{xkb_layout}\"\nXKBVARIANT=\"{variant}\"\nXKBOPTIONS=\"\"\nBACKSPACE=\"guess\"\n"
                ),
            )
            .map_err(io_error)?;
        }

        Ok(())
    }
}

struct WriteHostname {
    target_root: PathBuf,
    hostname: String,
}

impl PrivilegedOperation for WriteHostname {
    fn describe(&self) -> String {
        format!("configurar hostname ({})", self.hostname)
    }

    fn perform(&self, _executor: &dyn Executor) -> Result<(), OperationError> {
        let etc = self.target_root.join("etc");
        fs::create_dir_all(&etc).map_err(io_error)?;
        fs::write(etc.join("hostname"), format!("{}\n", self.hostname)).map_err(io_error)?;

        let hosts_path = etc.join("hosts");
        let mut content = fs::read_to_string(&hosts_path).unwrap_or_default();
        content.push_str(&format!("127.0.1.1\t{}\n", self.hostname));
        fs::write(&hosts_path, content).map_err(io_error)?;
        Ok(())
    }
}

/// `-R`/`-c`/`-G`/`-s` mirror `users.conf`'s real `defaultGroups` list —
/// `users`, `lp`, `video`, `network`, `storage`, `wheel`, `audio` — and
/// `/usr/bin/fish` shell. `users` and `wheel` carry `must_exist` in that config;
/// the other groups are optional and must be filtered against the extracted
/// target's `/etc/group`. Leap 16 no longer creates `network` or `storage`,
/// and passing either blindly to one `useradd -G` makes the entire account
/// creation fail with exit code 6. The password crosses via
/// `chpasswd`'s stdin (`run_with_stdin`), never argv. Root is never touched
/// here — it's already locked in the extracted squashfs (`setRootPassword:
/// false`'s real-world equivalent is simply that no step anywhere sets a
/// root password).
const USER_SUPPLEMENTARY_GROUPS: &[&str] = &[
    "users", "lp", "video", "network", "storage", "wheel", "audio",
];
const REQUIRED_USER_GROUPS: &[&str] = &["users", "wheel"];
const DEFAULT_DESKTOP_SHELL: &str = "/usr/bin/fish";

fn available_user_groups(target_root: &Path) -> Result<String, OperationError> {
    let group_path = target_root.join("etc/group");
    let group_file = fs::read_to_string(&group_path).map_err(io_error)?;
    let available: Vec<&str> = group_file
        .lines()
        .filter_map(|line| line.split_once(':').map(|(name, _)| name))
        .collect();

    let missing_required: Vec<&str> = REQUIRED_USER_GROUPS
        .iter()
        .copied()
        .filter(|group| !available.contains(group))
        .collect();
    if !missing_required.is_empty() {
        return Err(OperationError::Io(format!(
            "grupos obrigatórios ausentes em {}: {}",
            group_path.display(),
            missing_required.join(", ")
        )));
    }

    Ok(USER_SUPPLEMENTARY_GROUPS
        .iter()
        .copied()
        .filter(|group| available.contains(group))
        .collect::<Vec<_>>()
        .join(","))
}

fn target_user_ids(target_root: &Path, username: &str) -> Result<(u32, u32), OperationError> {
    let passwd_path = target_root.join("etc/passwd");
    let passwd = fs::read_to_string(&passwd_path).map_err(io_error)?;
    let expected_home = format!("/home/{username}");

    for line in passwd.lines() {
        let fields: Vec<&str> = line.split(':').collect();
        if fields.first() != Some(&username) {
            continue;
        }
        if fields.len() != 7 || fields[5] != expected_home {
            return Err(OperationError::Io(format!(
                "entrada inválida para {username} em {}",
                passwd_path.display()
            )));
        }
        let uid = fields[2].parse::<u32>().map_err(|_| {
            OperationError::Io(format!(
                "UID inválido para {username} em {}",
                passwd_path.display()
            ))
        })?;
        let gid = fields[3].parse::<u32>().map_err(|_| {
            OperationError::Io(format!(
                "GID inválido para {username} em {}",
                passwd_path.display()
            ))
        })?;
        return Ok((uid, gid));
    }

    Err(OperationError::Io(format!(
        "usuário {username} ausente em {} após useradd",
        passwd_path.display()
    )))
}

struct CreateUser {
    target_root: PathBuf,
    full_name: String,
    username: String,
    password: String,
}

impl PrivilegedOperation for CreateUser {
    fn describe(&self) -> String {
        format!("criar usuário {}", self.username)
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        let home = self.target_root.join("home").join(&self.username);
        if home.exists() {
            return Err(OperationError::Io(format!(
                "home já existe antes de useradd: {}",
                home.display()
            )));
        }
        let supplementary_groups = available_user_groups(&self.target_root)?;
        executor.run(&ArgvCommand {
            binary: "useradd".to_string(),
            args: vec![
                "-R".to_string(),
                path_str(&self.target_root),
                "-m".to_string(),
                "-c".to_string(),
                self.full_name.clone(),
                "-G".to_string(),
                supplementary_groups,
                "-s".to_string(),
                DEFAULT_DESKTOP_SHELL.to_string(),
                self.username.clone(),
            ],
        })?;

        executor.run_with_stdin(
            &ArgvCommand {
                binary: "chpasswd".to_string(),
                args: vec!["-R".to_string(), path_str(&self.target_root)],
            },
            &format!("{}:{}\n", self.username, self.password),
        )?;

        // Do not rely only on useradd -R -m for the final ownership invariant.
        // A real Alpha 6 image leaked the host build path into /home; for a
        // matching username useradd adopted that root-owned directory. The
        // pre-existing-home guard above rejects that collision, while this
        // final repair covers skeleton content. Resolve IDs from the target
        // passwd database (never host NSS) and do not dereference symlinks.
        let (uid, gid) = target_user_ids(&self.target_root, &self.username)?;
        executor.run(&ArgvCommand {
            binary: "chown".to_string(),
            args: vec![
                "--recursive".to_string(),
                "--no-dereference".to_string(),
                format!("{uid}:{gid}"),
                path_str(&home),
            ],
        })?;
        Ok(())
    }
}

struct WriteSudoers {
    target_root: PathBuf,
}

impl PrivilegedOperation for WriteSudoers {
    fn describe(&self) -> String {
        "conceder sudo ao grupo wheel".to_string()
    }

    fn perform(&self, _executor: &dyn Executor) -> Result<(), OperationError> {
        let dir = self.target_root.join("etc/sudoers.d");
        fs::create_dir_all(&dir).map_err(io_error)?;
        let path = dir.join("10-installer");
        // openSUSE's stock /etc/sudoers ships "Defaults targetpw" active,
        // which makes sudo prompt for the *target* user's password (root)
        // instead of the invoking user's - the opposite of what "root
        // disabled, sudo user created at install" promises. `@includedir
        // /etc/sudoers.d` comes after that line in the stock file, so this
        // override here is what actually takes effect.
        fs::write(&path, "Defaults !targetpw\n%wheel ALL=(ALL) ALL\n").map_err(io_error)?;
        fs::set_permissions(&path, fs::Permissions::from_mode(0o440)).map_err(io_error)?;
        Ok(())
    }
}

struct BindMount {
    source: PathBuf,
    dest: PathBuf,
}

impl PrivilegedOperation for BindMount {
    fn describe(&self) -> String {
        format!(
            "bind-mount {} em {}",
            self.source.display(),
            self.dest.display()
        )
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        fs::create_dir_all(&self.dest).map_err(io_error)?;
        executor.run(&ArgvCommand {
            binary: "mount".to_string(),
            args: vec![
                "--bind".to_string(),
                path_str(&self.source),
                path_str(&self.dest),
            ],
        })?;
        Ok(())
    }

    fn undo(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        executor.run(&ArgvCommand {
            binary: "umount".to_string(),
            args: vec![path_str(&self.dest)],
        })?;
        Ok(())
    }
}

/// Mounts a virtual filesystem whose device name is conventionally the same
/// as its type (`tmpfs`, `efivarfs`) — matches `mount.conf`'s
/// `extraMounts` entries for `/run` and `/sys/firmware/efi/efivars`.
///
/// The `efivarfs` one closes a real gap (issue #44's parity audit): a plain
/// `mount --bind /sys <target>/sys` (the [`BindMount`] just above) does
/// *not* carry over `/sys/firmware/efi/efivars` — that's a separate mount
/// already sitting inside `/sys` on the live host, and non-recursive bind
/// mounts only capture the directory entries visible at the bind source at
/// mount time, not filesystems mounted inside it (that needs `--rbind`,
/// which this deliberately isn't, matching every other bind mount in this
/// file). `mount.conf`'s own comment says exactly why this matters:
/// "grub/shim need it to create the UEFI NVRAM entry from inside the
/// target system" — without it, `efibootmgr` (called internally by
/// [`InstallShimAndGrub`]'s `shim-install`) has no UEFI variable store to
/// write to inside the chroot, so the real NVRAM boot entry silently never
/// gets created even though `shim-install` itself reports success (it
/// still writes the removable-media fallback path unconditionally, which
/// is why this wasn't caught by a successful-looking install). Mounted
/// unconditionally here, not behind a UEFI check, because this codebase has
/// no BIOS/legacy path anywhere else either (GPT/ESP-only partitioning,
/// `firmware="uefi"` in `kiwi/config.xml`).
struct MountVirtualFs {
    fstype: &'static str,
    dest: PathBuf,
}

impl PrivilegedOperation for MountVirtualFs {
    fn describe(&self) -> String {
        format!("montar {} em {}", self.fstype, self.dest.display())
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        fs::create_dir_all(&self.dest).map_err(io_error)?;
        executor.run(&ArgvCommand {
            binary: "mount".to_string(),
            args: vec![
                "-t".to_string(),
                self.fstype.to_string(),
                self.fstype.to_string(),
                path_str(&self.dest),
            ],
        })?;
        Ok(())
    }

    fn undo(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        executor.run(&ArgvCommand {
            binary: "umount".to_string(),
            args: vec![path_str(&self.dest)],
        })?;
        Ok(())
    }
}

/// Runs plain `dracut -f`, preserving the correct kernel-versioned default
/// instead of inheriting an installer-specific output filename.
struct RunDracut {
    target_root: PathBuf,
}

impl PrivilegedOperation for RunDracut {
    fn describe(&self) -> String {
        "gerar initramfs (dracut)".to_string()
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        executor.run(&ArgvCommand {
            binary: "chroot".to_string(),
            args: vec![
                path_str(&self.target_root),
                "dracut".to_string(),
                "-f".to_string(),
            ],
        })?;
        Ok(())
    }
}

struct RemoveLiveUser {
    target_root: PathBuf,
}

impl PrivilegedOperation for RemoveLiveUser {
    fn describe(&self) -> String {
        "remover conta liveuser".to_string()
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        executor.run(&ArgvCommand {
            binary: "userdel".to_string(),
            args: vec![
                "-R".to_string(),
                path_str(&self.target_root),
                "--force".to_string(),
                "--remove".to_string(),
                "liveuser".to_string(),
            ],
        })?;
        Ok(())
    }
}

struct LowerLyraRepoPriorities {
    target_root: PathBuf,
}

impl PrivilegedOperation for LowerLyraRepoPriorities {
    fn describe(&self) -> String {
        "reduzir prioridade dos repositórios Lyra".to_string()
    }

    fn perform(&self, _executor: &dyn Executor) -> Result<(), OperationError> {
        let repos_dir = self.target_root.join("etc/zypp/repos.d");
        for alias in LYRA_REPO_ALIASES {
            let path = repos_dir.join(format!("{alias}.repo"));
            if !path.is_file() {
                continue;
            }
            let content = fs::read_to_string(&path).map_err(io_error)?;
            let rewritten: String = content
                .lines()
                .map(|line| {
                    if line.trim_start().starts_with("priority=") {
                        format!("priority={INSTALLED_THIRD_PARTY_PRIORITY}")
                    } else {
                        line.to_string()
                    }
                })
                .collect::<Vec<_>>()
                .join("\n");
            fs::write(&path, rewritten + "\n").map_err(io_error)?;
        }
        Ok(())
    }
}

struct DisableRepositoryPackageRetention {
    target_root: PathBuf,
}

impl PrivilegedOperation for DisableRepositoryPackageRetention {
    fn describe(&self) -> String {
        "desativar retenção de pacotes dos repositórios".to_string()
    }

    fn perform(&self, _executor: &dyn Executor) -> Result<(), OperationError> {
        let repos_dir = self.target_root.join("etc/zypp/repos.d");
        if !repos_dir.is_dir() {
            return Ok(());
        }
        for entry in fs::read_dir(repos_dir).map_err(io_error)? {
            let path = entry.map_err(io_error)?.path();
            if path.extension().and_then(|extension| extension.to_str()) != Some("repo") {
                continue;
            }
            let content = fs::read_to_string(&path).map_err(io_error)?;
            let mut found = false;
            let mut lines = content
                .lines()
                .map(|line| {
                    if line.trim_start().starts_with("keeppackages=") {
                        found = true;
                        "keeppackages=0".to_string()
                    } else {
                        line.to_string()
                    }
                })
                .collect::<Vec<_>>();
            if !found {
                lines.push("keeppackages=0".to_string());
            }
            fs::write(path, lines.join("\n") + "\n").map_err(io_error)?;
        }
        Ok(())
    }
}

struct RemoveLiveOnlyArtifacts {
    target_root: PathBuf,
}

impl PrivilegedOperation for RemoveLiveOnlyArtifacts {
    fn describe(&self) -> String {
        "remover artefatos exclusivos da sessão live".to_string()
    }

    fn perform(&self, _executor: &dyn Executor) -> Result<(), OperationError> {
        for artifact in LIVE_ONLY_ARTIFACTS {
            // Best-effort: a missing file here just means there was nothing
            // to clean up.
            let _ = fs::remove_file(self.target_root.join(artifact));
        }
        Ok(())
    }
}

/// Line-for-line translation of `networkcfg/main.py`'s real logic: copy
/// each live NetworkManager keyfile connection except `LTSP` or one that
/// already exists on the target, rewriting the live user's saved
/// `permissions=user:...:;` line to the newly-created account.
struct CopyNetworkConfig {
    target_root: PathBuf,
    /// Always `LIVE_NM_CONNECTIONS` in production; a field (not the
    /// constant used directly) so tests can point it at a fixture
    /// directory instead of the real live session's `/etc`.
    source_dir: PathBuf,
    username: String,
}

impl PrivilegedOperation for CopyNetworkConfig {
    fn describe(&self) -> String {
        "copiar perfis de rede da sessão live".to_string()
    }

    fn perform(&self, _executor: &dyn Executor) -> Result<(), OperationError> {
        if !self.source_dir.is_dir() {
            return Ok(());
        }
        let dest_dir = self
            .target_root
            .join("etc/NetworkManager/system-connections");
        fs::create_dir_all(&dest_dir).map_err(io_error)?;

        let live_marker = "permissions=user:liveuser:;";
        let target_marker = format!("permissions=user:{}:;", self.username);

        for entry in fs::read_dir(&self.source_dir).map_err(io_error)? {
            let entry = entry.map_err(io_error)?;
            let file_name = entry.file_name();
            if file_name.to_string_lossy() == "LTSP" {
                continue;
            }
            let dest_path = dest_dir.join(&file_name);
            if dest_path.exists() {
                continue;
            }

            let content = fs::read_to_string(entry.path()).map_err(io_error)?;
            let rewritten: String = content
                .lines()
                .map(|line| {
                    if line.contains(live_marker) {
                        target_marker.as_str()
                    } else {
                        line
                    }
                })
                .collect::<Vec<_>>()
                .join("\n");
            fs::write(&dest_path, rewritten + "\n").map_err(io_error)?;
        }
        Ok(())
    }
}

/// `--adjfile` targets the install's own `/etc/adjtime` without needing a
/// chroot (the real `hwclock/main.py` runs chrooted via
/// `target_env_call`, but writes the same file either way). Always UTC —
/// `hwclock`'s real module has no local-time branch at all.
///
/// The RTC-then-ISA retry and the "never fails the job" ending are both
/// ported from that real `main.py`, not invented here: it tries plain
/// `hwclock --systohc --utc` first, and only on a non-zero exit retries with
/// `--directisa` (relevant on older hardware/some VMs where the RTC method
/// doesn't work); if *both* fail, the module still just logs and returns
/// `None` rather than aborting the install (issue #44's parity audit — the
/// single, non-retried, error-propagating call this replaced was a real gap
/// against that behaviour).
struct SetHardwareClock {
    target_root: PathBuf,
}

impl PrivilegedOperation for SetHardwareClock {
    fn describe(&self) -> String {
        "sincronizar relógio de hardware (UTC)".to_string()
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        let adjfile_flag = format!(
            "--adjfile={}",
            path_str(&self.target_root.join("etc/adjtime"))
        );

        let rtc = executor.run(&ArgvCommand {
            binary: "hwclock".to_string(),
            args: vec![
                "--systohc".to_string(),
                "--utc".to_string(),
                adjfile_flag.clone(),
            ],
        });
        if rtc.is_ok() {
            return Ok(());
        }

        let _ = executor.run(&ArgvCommand {
            binary: "hwclock".to_string(),
            args: vec![
                "--systohc".to_string(),
                "--utc".to_string(),
                "--directisa".to_string(),
                adjfile_flag,
            ],
        });
        Ok(())
    }
}

struct EnableServices {
    target_root: PathBuf,
}

impl PrivilegedOperation for EnableServices {
    fn describe(&self) -> String {
        "habilitar serviços do sistema".to_string()
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        let mut args = vec![
            format!("--root={}", path_str(&self.target_root)),
            "enable".to_string(),
        ];
        args.extend(ENABLED_SERVICES.iter().map(|service| service.to_string()));
        executor.run(&ArgvCommand {
            binary: "systemctl".to_string(),
            args,
        })?;
        Ok(())
    }
}

// --- GRUB, shim (Secure Boot) and Snapper rollback (issue #42) ------------
//
// Mirrors settings.conf's real grubcfg -> uefibootloader -> snapshotcfg
// sequence, read from the actually-installed modules (grubcfg's main.py,
// /usr/sbin/shim-install from the shim package, and
// lyra-configure-btrfs-rollback) rather than guessed. All chrooted steps
// reuse the /proc,/sys,/dev bind mounts RunDracut set up above - the
// engine only unwinds them at the very end of the whole run.

/// Real `grubcfg` merges into an existing `/etc/default/grub` rather than
/// overwriting it (`overwrite: false`, file already shipped by the `grub2`
/// package), uncommenting/replacing managed keys in place and appending
/// any that aren't already present. Deliberately does NOT reproduce a real
/// bug in that module: it separately auto-detects `plymouth` in the target
/// and appends `"splash"` again on top of an already-`"splash"`-containing
/// `kernel_params`, producing `'quiet splash splash'`. This writes the
/// correct value once.
const GRUB_DEFAULT_KEYS: &[(&str, &str)] = &[
    ("GRUB_TIMEOUT", "5"),
    ("GRUB_DEFAULT", "saved"),
    ("GRUB_DISABLE_SUBMENU", "true"),
    ("GRUB_TERMINAL_OUTPUT", "gfxterm"),
    ("GRUB_DISABLE_RECOVERY", "true"),
    ("SUSE_BTRFS_SNAPSHOT_BOOTING", "true"),
    ("GRUB_CMDLINE_LINUX_DEFAULT", "\"quiet splash\""),
    ("GRUB_DISTRIBUTOR", "\"Lyra OS\""),
    ("GRUB_THEME", "\"/usr/share/grub/themes/Lyra-OS/theme.txt\""),
];

const GRUB_THEME_PATH: &str = "/usr/share/grub/themes/Lyra-OS/theme.txt";

struct WriteGrubDefaults {
    target_root: PathBuf,
}

impl PrivilegedOperation for WriteGrubDefaults {
    fn describe(&self) -> String {
        "configurar /etc/default/grub".to_string()
    }

    fn perform(&self, _executor: &dyn Executor) -> Result<(), OperationError> {
        let theme = self
            .target_root
            .join(GRUB_THEME_PATH.trim_start_matches('/'));
        if !theme.is_file() {
            return Err(OperationError::Io(format!(
                "tema do GRUB ausente no target: {GRUB_THEME_PATH}"
            )));
        }
        let path = self.target_root.join("etc/default/grub");
        let existing = fs::read_to_string(&path).unwrap_or_default();
        let mut remaining: Vec<(&str, &str)> = GRUB_DEFAULT_KEYS.to_vec();
        let mut lines: Vec<String> = Vec::new();

        for line in existing.lines() {
            if line.contains('=') {
                let key = line
                    .trim_start()
                    .trim_start_matches('#')
                    .trim_start()
                    .split('=')
                    .next()
                    .unwrap_or("")
                    .trim();
                if let Some(pos) = remaining.iter().position(|(k, _)| *k == key) {
                    let (k, v) = remaining.remove(pos);
                    lines.push(format!("{k}={v}"));
                    continue;
                }
            }
            lines.push(line.to_string());
        }
        for (k, v) in remaining {
            lines.push(format!("{k}={v}"));
        }

        let mut content = lines.join("\n");
        content.push('\n');
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(io_error)?;
        }
        fs::write(&path, content).map_err(io_error)?;
        Ok(())
    }
}

struct GenerateGrubConfig {
    target_root: PathBuf,
}

impl PrivilegedOperation for GenerateGrubConfig {
    fn describe(&self) -> String {
        "gerar configuração do GRUB".to_string()
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        executor.run(&ArgvCommand {
            binary: "chroot".to_string(),
            args: vec![
                path_str(&self.target_root),
                "grub2-mkconfig".to_string(),
                "-o".to_string(),
                "/boot/grub2/grub.cfg".to_string(),
            ],
        })?;
        Ok(())
    }
}

/// Native Leap `shim-install`. The script from package `shim` writes the
/// fallback `/boot/efi/EFI/boot/bootx64.efi` itself whenever that path is
/// missing or belongs to another distro's CA, and creates the NVRAM boot
/// entry via `efibootmgr` internally - none of that needs reimplementing
/// here; the installer invokes the distribution-native tool directly.
struct InstallShimAndGrub {
    target_root: PathBuf,
}

impl PrivilegedOperation for InstallShimAndGrub {
    fn describe(&self) -> String {
        "instalar shim e GRUB (Secure Boot)".to_string()
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        executor.run(&ArgvCommand {
            binary: "chroot".to_string(),
            args: vec![
                path_str(&self.target_root),
                "shim-install".to_string(),
                "--efi-directory=/boot/efi".to_string(),
                "--config-file=/boot/grub2/grub.cfg".to_string(),
            ],
        })?;
        Ok(())
    }
}

/// Ports `lyra-configure-btrfs-rollback prepare-root`'s awk logic directly
/// rather than shelling out to the bash script. `btrfs subvolume
/// set-default` doesn't need a chroot: it's a plain path argument, and
/// `target_root` is already visible to this process without entering it.
struct PrepareBtrfsRollback {
    target_root: PathBuf,
}

impl PrivilegedOperation for PrepareBtrfsRollback {
    fn describe(&self) -> String {
        "definir /@ como subvolume padrão".to_string()
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        executor.run(&ArgvCommand {
            binary: "btrfs".to_string(),
            args: vec![
                "subvolume".to_string(),
                "set-default".to_string(),
                path_str(&self.target_root),
            ],
        })?;

        let fstab_path = self.target_root.join("etc/fstab");
        let content = fs::read_to_string(&fstab_path).map_err(io_error)?;
        let rewritten = strip_root_subvol_option(&content)?;
        fs::write(&fstab_path, rewritten).map_err(io_error)?;
        Ok(())
    }
}

/// `snapper create-config` writes to `/etc/snapper/configs/` relative to
/// whatever root *it* sees — unlike `useradd`/`systemctl`, it has no
/// `--root` equivalent, so this genuinely needs the chroot (otherwise it
/// would configure the live session's own `/etc`, not the target's).
struct SnapperCreateConfig {
    target_root: PathBuf,
}

impl PrivilegedOperation for SnapperCreateConfig {
    fn describe(&self) -> String {
        "criar configuração do Snapper".to_string()
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        executor.run(&ArgvCommand {
            binary: "chroot".to_string(),
            args: vec![
                path_str(&self.target_root),
                "snapper".to_string(),
                "--no-dbus".to_string(),
                "-c".to_string(),
                "root".to_string(),
                "create-config".to_string(),
                "/".to_string(),
            ],
        })?;
        Ok(())
    }
}

/// Ports `mount-snapshots`'s awk logic. `/.snapshots` must already exist
/// (created by `SnapperCreateConfig` just before this) - checked via
/// `btrfs subvolume show`, output discarded, same as the original script.
struct MountSnapshotsSubvolume {
    target_root: PathBuf,
}

impl PrivilegedOperation for MountSnapshotsSubvolume {
    fn describe(&self) -> String {
        "adicionar /.snapshots ao fstab".to_string()
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        executor.run(&ArgvCommand {
            binary: "btrfs".to_string(),
            args: vec![
                "subvolume".to_string(),
                "show".to_string(),
                path_str(&self.target_root.join(".snapshots")),
            ],
        })?;

        let fstab_path = self.target_root.join("etc/fstab");
        let content = fs::read_to_string(&fstab_path).map_err(io_error)?;
        let rewritten = add_snapshots_line(&content)?;
        fs::write(&fstab_path, rewritten).map_err(io_error)?;
        Ok(())
    }
}

/// Separate from #41's `RunDracut` (`dracut -f`): the real sequence runs
/// dracut *again* here specifically so the initramfs picks up the fstab
/// with `subvol=/@` already stripped by `PrepareBtrfsRollback`.
struct RegenerateInitramfsWithFstab {
    target_root: PathBuf,
}

impl PrivilegedOperation for RegenerateInitramfsWithFstab {
    fn describe(&self) -> String {
        "regenerar initramfs com fstab atualizado".to_string()
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        executor.run(&ArgvCommand {
            binary: "chroot".to_string(),
            args: vec![
                path_str(&self.target_root),
                "dracut".to_string(),
                "--force".to_string(),
                "--fstab".to_string(),
            ],
        })?;
        Ok(())
    }
}

/// `--read-only` is load-bearing, not cosmetic: `grub2-snapper-plugin`
/// skips writable snapshots when building the GRUB rollback submenu. Runs
/// after #41's liveuser/live-artifact cleanup (earlier in
/// `deployment_operations`), so this snapshot is clean by construction —
/// no extra filtering logic needed here.
struct SnapperCreateFirstSnapshot {
    target_root: PathBuf,
}

impl PrivilegedOperation for SnapperCreateFirstSnapshot {
    fn describe(&self) -> String {
        "criar primeiro snapshot somente leitura".to_string()
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        executor.run(&ArgvCommand {
            binary: "chroot".to_string(),
            args: vec![
                path_str(&self.target_root),
                "snapper".to_string(),
                "--no-dbus".to_string(),
                "-c".to_string(),
                "root".to_string(),
                "create".to_string(),
                "--read-only".to_string(),
                "--type".to_string(),
                "single".to_string(),
                "--cleanup-algorithm".to_string(),
                "number".to_string(),
                "--description".to_string(),
                "first root filesystem".to_string(),
                "--userdata".to_string(),
                "important=yes".to_string(),
            ],
        })?;
        Ok(())
    }
}

/// The installer belongs only to the live environment. Remove its GUI,
/// service, launcher and authorization policy before the first snapshot so
/// the installed system has no reusable installation privilege.
const LYRA_INSTALLER_ARTIFACTS: &[&str] = &[
    "usr/bin/lyra-install-lock",
    "usr/bin/lyra-installer",
    "usr/libexec/lyra-installer-service",
    "usr/share/applications/org.lyraos.LyraInstaller.desktop",
    "usr/share/polkit-1/actions/io.lyra.Installer.policy",
    "etc/polkit-1/rules.d/01-lyra-installer-service.rules",
    // Development images add this outside the RPM payload.
    "usr/lib/lyra-os/local-installer-build",
];

struct RemoveTransitionalInstallerArtifacts {
    target_root: PathBuf,
}

impl PrivilegedOperation for RemoveTransitionalInstallerArtifacts {
    fn describe(&self) -> String {
        "remover artefatos transitórios do instalador".to_string()
    }

    fn perform(&self, executor: &dyn Executor) -> Result<(), OperationError> {
        executor.run(&ArgvCommand {
            binary: "rpm".to_string(),
            args: vec![
                "--root".to_string(),
                path_str(&self.target_root),
                "--erase".to_string(),
                "--noscripts".to_string(),
                "lyra-installer".to_string(),
            ],
        })?;

        // Keep this cleanup explicit for development-image overlays and for
        // defense in depth if the RPM payload changes. The RPM erase above is
        // still mandatory so the package database cannot restore these files
        // during a later update.
        let _ = fs::remove_file(
            self.target_root
                .join("usr/libexec/lyra-configure-btrfs-rollback"),
        );
        for artifact in LYRA_INSTALLER_ARTIFACTS {
            let _ = fs::remove_file(self.target_root.join(artifact));
        }
        Ok(())
    }
}

/// Ports `lyra-configure-btrfs-rollback prepare-root`'s awk program:
/// strips only `subvol=`/`subvolid=` from the root Btrfs entry's options,
/// keeping every other option and every other line untouched. Errors
/// (mirroring the original's `exit 42`) if there isn't exactly one root
/// Btrfs line.
fn strip_root_subvol_option(fstab: &str) -> Result<String, OperationError> {
    let mut found = 0;
    let mut lines = Vec::new();

    for line in fstab.lines() {
        let trimmed = line.trim_start();
        let fields: Vec<&str> = line.split_whitespace().collect();
        if trimmed.starts_with('#') || fields.len() < 4 {
            lines.push(line.to_string());
            continue;
        }
        if fields[1] == "/" && fields[2] == "btrfs" {
            found += 1;
            let options: Vec<&str> = fields[3]
                .split(',')
                .filter(|opt| !opt.starts_with("subvol=") && !opt.starts_with("subvolid="))
                .collect();
            let options = if options.is_empty() {
                "defaults".to_string()
            } else {
                options.join(",")
            };
            let dump = fields.get(4).copied().unwrap_or("0");
            let pass = fields.get(5).copied().unwrap_or("0");
            lines.push(format!(
                "{} {} {} {} {} {}",
                fields[0], fields[1], fields[2], options, dump, pass
            ));
        } else {
            lines.push(line.to_string());
        }
    }

    if found != 1 {
        return Err(OperationError::Io(format!(
            "esperava exatamente 1 linha raiz Btrfs no fstab, encontrei {found}"
        )));
    }

    let mut content = lines.join("\n");
    content.push('\n');
    Ok(content)
}

/// Ports `mount-snapshots`'s awk program: drops any existing `/.snapshots`
/// line (at most one tolerated, mirroring the original) and appends a
/// fresh one using the root entry's own source device and options plus
/// `subvol=/@/.snapshots`.
fn add_snapshots_line(fstab: &str) -> Result<String, OperationError> {
    let mut root_count = 0;
    let mut snapshots_count = 0;
    let mut source = String::new();
    let mut options = String::new();
    let mut lines = Vec::new();

    for line in fstab.lines() {
        let trimmed = line.trim_start();
        let fields: Vec<&str> = line.split_whitespace().collect();
        if trimmed.starts_with('#') || fields.len() < 4 {
            lines.push(line.to_string());
            continue;
        }
        if fields[1] == "/.snapshots" {
            snapshots_count += 1;
            continue;
        }
        if fields[1] == "/" && fields[2] == "btrfs" {
            root_count += 1;
            source = fields[0].to_string();
            options = fields[3].to_string();
        }
        lines.push(line.to_string());
    }

    if root_count != 1 || snapshots_count > 1 {
        return Err(OperationError::Io(format!(
            "fstab inconsistente: {root_count} linha(s) raiz Btrfs, {snapshots_count} linha(s) /.snapshots"
        )));
    }
    if options.is_empty() || options == "-" {
        options = "defaults".to_string();
    }

    lines.push(format!(
        "{source} /.snapshots btrfs {options},subvol=/@/.snapshots 0 0"
    ));
    let mut content = lines.join("\n");
    content.push('\n');
    Ok(content)
}

#[cfg(test)]
mod tests {
    use std::cell::RefCell;
    use std::sync::atomic::{AtomicU64, Ordering};

    use super::*;
    use crate::service::executor::ExecutorError;

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
        fn run(&self, command: &ArgvCommand) -> Result<String, ExecutorError> {
            self.calls
                .borrow_mut()
                .push(format!("{} {}", command.binary, command.args.join(" ")));
            Ok(String::new())
        }

        fn run_with_stdin(
            &self,
            command: &ArgvCommand,
            stdin: &str,
        ) -> Result<String, ExecutorError> {
            self.calls.borrow_mut().push(format!(
                "{} {} <stdin: {stdin}>",
                command.binary,
                command.args.join(" ")
            ));
            Ok(String::new())
        }
    }

    struct TempRoot(PathBuf);

    impl TempRoot {
        fn new(label: &str) -> Self {
            static COUNTER: AtomicU64 = AtomicU64::new(0);
            let n = COUNTER.fetch_add(1, Ordering::SeqCst);
            let path = std::env::temp_dir().join(format!(
                "lyra-installer-deploy-test-{label}-{}-{n}",
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

    fn write_group_fixture(root: &Path, groups: &[&str]) {
        let etc = root.join("etc");
        fs::create_dir_all(&etc).unwrap();
        let content = groups
            .iter()
            .enumerate()
            .map(|(index, group)| format!("{group}:x:{}:\n", 100 + index))
            .collect::<String>();
        fs::write(etc.join("group"), content).unwrap();
    }

    fn write_passwd_fixture(root: &Path, username: &str, uid: u32, gid: u32) {
        let etc = root.join("etc");
        fs::create_dir_all(&etc).unwrap();
        fs::write(
            etc.join("passwd"),
            format!("{username}:x:{uid}:{gid}:Lyra User:/home/{username}:/usr/bin/fish\n"),
        )
        .unwrap();
    }

    #[test]
    fn extract_rootfs_runs_unsquashfs_with_force_and_the_live_squashfs_source() {
        // A real directory: FakeExecutor doesn't actually run unsquashfs, but
        // repair_root_permissions still stats target_root for real afterwards,
        // same as it would against unsquashfs's own freshly-extracted target.
        let temp = TempRoot::new("extract-rootfs");
        let op = ExtractRootfs {
            target_root: temp.0.clone(),
        };
        let executor = FakeExecutor::new();
        op.perform(&executor).unwrap();
        assert_eq!(
            executor.calls(),
            vec![format!(
                "unsquashfs -f -d {} /run/overlay/live/LiveOS/squashfs.img",
                temp.0.display()
            )]
        );
    }

    #[test]
    fn repair_root_permissions_fixes_exactly_777_and_leaves_other_modes_alone() {
        let temp = TempRoot::new("repair-permissions-777");
        fs::set_permissions(&temp.0, fs::Permissions::from_mode(0o777)).unwrap();
        repair_root_permissions(&temp.0).unwrap();
        assert_eq!(
            fs::metadata(&temp.0).unwrap().permissions().mode() & 0o777,
            0o755
        );

        let temp2 = TempRoot::new("repair-permissions-700");
        fs::set_permissions(&temp2.0, fs::Permissions::from_mode(0o700)).unwrap();
        repair_root_permissions(&temp2.0).unwrap();
        assert_eq!(
            fs::metadata(&temp2.0).unwrap().permissions().mode() & 0o777,
            0o700,
            "only exactly 777 should ever be touched"
        );
    }

    #[test]
    fn write_machine_id_writes_id_symlink_and_entropy_seeds() {
        let temp = TempRoot::new("machine-id");
        let op = WriteMachineId {
            target_root: temp.0.clone(),
        };
        op.perform(&FakeExecutor::new()).unwrap();

        let id = fs::read_to_string(temp.0.join("etc/machine-id")).unwrap();
        assert_eq!(
            id.trim().len(),
            32,
            "machine-id should be a 32-char hex UUID"
        );
        assert!(id.trim().chars().all(|c| c.is_ascii_hexdigit()));

        let link = temp.0.join("var/lib/dbus/machine-id");
        assert!(link.symlink_metadata().unwrap().file_type().is_symlink());
        assert_eq!(
            fs::read_link(&link).unwrap(),
            PathBuf::from("../../../etc/machine-id")
        );

        for seed_dir in ["var/lib/urandom", "var/lib/systemd"] {
            let seed = fs::read(temp.0.join(seed_dir).join("random-seed")).unwrap();
            assert_eq!(seed.len(), 512);
        }
    }

    #[test]
    fn write_locale_sets_every_category_and_writes_default_locale_only_if_the_dir_exists() {
        let temp = TempRoot::new("locale-no-default-dir");
        let op = WriteLocale {
            target_root: temp.0.clone(),
            locale: "pt_BR.UTF-8".to_string(),
        };
        op.perform(&FakeExecutor::new()).unwrap();

        let content = fs::read_to_string(temp.0.join("etc/locale.conf")).unwrap();
        for category in LOCALE_CATEGORIES {
            assert!(content.contains(&format!("{category}=pt_BR.UTF-8")));
        }
        assert!(!temp.0.join("etc/default/locale").exists());

        // Now with an existing /etc/default directory.
        let temp2 = TempRoot::new("locale-with-default-dir");
        fs::create_dir_all(temp2.0.join("etc/default")).unwrap();
        let op2 = WriteLocale {
            target_root: temp2.0.clone(),
            locale: "en_US.UTF-8".to_string(),
        };
        op2.perform(&FakeExecutor::new()).unwrap();
        assert!(
            fs::read_to_string(temp2.0.join("etc/default/locale"))
                .unwrap()
                .contains("LANG=en_US.UTF-8")
        );
    }

    #[test]
    fn write_timezone_symlinks_localtime_and_writes_timezone_file() {
        let temp = TempRoot::new("timezone");
        let op = WriteTimezone {
            target_root: temp.0.clone(),
            timezone: "America/Sao_Paulo".to_string(),
        };
        op.perform(&FakeExecutor::new()).unwrap();

        let localtime = temp.0.join("etc/localtime");
        assert!(
            localtime
                .symlink_metadata()
                .unwrap()
                .file_type()
                .is_symlink()
        );
        assert_eq!(
            fs::read_link(&localtime).unwrap(),
            PathBuf::from("../usr/share/zoneinfo/America/Sao_Paulo")
        );
        assert_eq!(
            fs::read_to_string(temp.0.join("etc/timezone")).unwrap(),
            "America/Sao_Paulo\n"
        );
    }

    #[test]
    fn write_keyboard_writes_vconsole_without_desktop_specific_state() {
        let temp = TempRoot::new("keyboard-brazil");
        let op = WriteKeyboard {
            target_root: temp.0.clone(),
            keyboard_layout: "br-abnt2".to_string(),
        };
        let executor = FakeExecutor::new();
        op.perform(&executor).unwrap();

        assert_eq!(
            fs::read_to_string(temp.0.join("etc/vconsole.conf")).unwrap(),
            "KEYMAP=br\n"
        );
        assert!(executor.calls().is_empty());
        assert!(
            !temp.0.join("etc/default/keyboard").exists(),
            "no /etc/default dir here, nothing to write into"
        );
    }

    #[test]
    fn write_keyboard_writes_etc_default_keyboard_only_if_the_dir_exists() {
        let temp = TempRoot::new("keyboard-defaults-dir");
        fs::create_dir_all(temp.0.join("etc/default")).unwrap();
        let op = WriteKeyboard {
            target_root: temp.0.clone(),
            keyboard_layout: "us-intl".to_string(),
        };
        op.perform(&FakeExecutor::new()).unwrap();

        let content = fs::read_to_string(temp.0.join("etc/default/keyboard")).unwrap();
        assert!(content.contains("XKBMODEL=\"pc105\""));
        assert!(content.contains("XKBLAYOUT=\"us\""));
        assert!(content.contains("XKBVARIANT=\"intl\""));
        assert!(content.contains("BACKSPACE=\"guess\""));
    }

    #[test]
    fn write_keyboard_rejects_an_unknown_layout_id() {
        let op = WriteKeyboard {
            target_root: PathBuf::from("/run/lyra-installer/target"),
            keyboard_layout: "does-not-exist".to_string(),
        };
        let error = op.perform(&FakeExecutor::new()).unwrap_err();
        assert!(matches!(error, OperationError::Io(_)));
    }

    #[test]
    fn write_hostname_writes_hostname_file_and_hosts_entry() {
        let temp = TempRoot::new("hostname");
        let op = WriteHostname {
            target_root: temp.0.clone(),
            hostname: "lyra-os".to_string(),
        };
        op.perform(&FakeExecutor::new()).unwrap();
        assert_eq!(
            fs::read_to_string(temp.0.join("etc/hostname")).unwrap(),
            "lyra-os\n"
        );
        assert!(
            fs::read_to_string(temp.0.join("etc/hosts"))
                .unwrap()
                .contains("127.0.1.1\tlyra-os")
        );
    }

    #[test]
    fn create_user_sends_the_password_via_stdin_never_as_an_argument() {
        let temp = TempRoot::new("create-user");
        write_group_fixture(&temp.0, USER_SUPPLEMENTARY_GROUPS);
        write_passwd_fixture(&temp.0, "lyra", 1000, 100);
        let op = CreateUser {
            target_root: temp.0.clone(),
            full_name: "Lyra User".to_string(),
            username: "lyra".to_string(),
            password: "harmonia-2026".to_string(),
        };
        let executor = FakeExecutor::new();
        op.perform(&executor).unwrap();

        let calls = executor.calls();
        assert!(calls[0].starts_with("useradd -R"));
        assert!(calls[0].contains("-s /usr/bin/fish lyra"));
        assert!(
            !calls[0].contains("harmonia-2026"),
            "password must never appear in argv"
        );
        assert!(
            calls[0].contains("-G users,lp,video,network,storage,wheel,audio"),
            "must match users.conf's real defaultGroups list, not just wheel: {}",
            calls[0]
        );
        assert_eq!(
            calls[1],
            format!(
                "chpasswd -R {} <stdin: lyra:harmonia-2026\n>",
                temp.0.display()
            )
        );
        assert_eq!(
            calls[2],
            format!(
                "chown --recursive --no-dereference 1000:100 {}/home/lyra",
                temp.0.display()
            ),
            "the installed account must own its complete home and skeleton"
        );
    }

    #[test]
    fn create_user_skips_optional_groups_absent_from_the_target() {
        let temp = TempRoot::new("create-user-optional-groups");
        write_group_fixture(&temp.0, &["users", "lp", "video", "wheel", "audio"]);
        write_passwd_fixture(&temp.0, "lyra", 1000, 100);
        let op = CreateUser {
            target_root: temp.0.clone(),
            full_name: "Lyra User".to_string(),
            username: "lyra".to_string(),
            password: "harmonia-2026".to_string(),
        };
        let executor = FakeExecutor::new();
        op.perform(&executor).unwrap();

        assert!(
            executor.calls()[0].contains("-G users,lp,video,wheel,audio"),
            "network and storage must be omitted when Leap does not provide them"
        );
    }

    #[test]
    fn create_user_rejects_a_home_that_existed_before_useradd() {
        let temp = TempRoot::new("create-user-existing-home");
        write_group_fixture(&temp.0, USER_SUPPLEMENTARY_GROUPS);
        fs::create_dir_all(temp.0.join("home/lyra/Git")).unwrap();
        let op = CreateUser {
            target_root: temp.0.clone(),
            full_name: "Lyra User".to_string(),
            username: "lyra".to_string(),
            password: "harmonia-2026".to_string(),
        };
        let executor = FakeExecutor::new();

        let error = op.perform(&executor).unwrap_err();

        assert!(error.to_string().contains("home já existe antes de useradd"));
        assert!(executor.calls().is_empty());
    }

    #[test]
    fn create_user_rejects_a_target_without_required_groups_before_useradd() {
        let temp = TempRoot::new("create-user-required-groups");
        write_group_fixture(&temp.0, &["users", "lp", "video", "audio"]);
        let op = CreateUser {
            target_root: temp.0.clone(),
            full_name: "Lyra User".to_string(),
            username: "lyra".to_string(),
            password: "harmonia-2026".to_string(),
        };
        let executor = FakeExecutor::new();
        let error = op.perform(&executor).unwrap_err();

        assert!(error.to_string().contains("grupos obrigatórios ausentes"));
        assert!(error.to_string().contains("wheel"));
        assert!(executor.calls().is_empty());
    }

    #[test]
    fn write_sudoers_grants_wheel_with_restrictive_permissions() {
        let temp = TempRoot::new("sudoers");
        let op = WriteSudoers {
            target_root: temp.0.clone(),
        };
        op.perform(&FakeExecutor::new()).unwrap();

        let path = temp.0.join("etc/sudoers.d/10-installer");
        assert_eq!(
            fs::read_to_string(&path).unwrap(),
            "Defaults !targetpw\n%wheel ALL=(ALL) ALL\n"
        );
        let mode = fs::metadata(&path).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode, 0o440);
    }

    #[test]
    fn mount_virtual_fs_uses_matching_device_and_type_then_unmounts_on_undo() {
        let temp = TempRoot::new("mount-virtual-fs");
        let dest = temp.0.join("sys/firmware/efi/efivars");
        let op = MountVirtualFs {
            fstype: "efivarfs",
            dest: dest.clone(),
        };
        let executor = FakeExecutor::new();
        op.perform(&executor).unwrap();
        assert!(dest.is_dir());
        assert_eq!(
            executor.calls(),
            vec![format!("mount -t efivarfs efivarfs {}", dest.display())]
        );

        op.undo(&executor).unwrap();
        assert_eq!(
            executor.calls().last().unwrap(),
            &format!("umount {}", dest.display())
        );
    }

    #[test]
    fn bind_mount_creates_destination_and_mounts_then_unmounts_on_undo() {
        let temp = TempRoot::new("bind-mount");
        let dest = temp.0.join("proc");
        let op = BindMount {
            source: PathBuf::from("/proc"),
            dest: dest.clone(),
        };
        let executor = FakeExecutor::new();
        op.perform(&executor).unwrap();
        assert!(dest.is_dir());
        assert_eq!(
            executor.calls(),
            vec![format!("mount --bind /proc {}", dest.display())]
        );

        op.undo(&executor).unwrap();
        assert_eq!(
            executor.calls().last().unwrap(),
            &format!("umount {}", dest.display())
        );
    }

    #[test]
    fn run_dracut_chroots_and_runs_the_corrected_command() {
        let op = RunDracut {
            target_root: PathBuf::from("/run/lyra-installer/target"),
        };
        let executor = FakeExecutor::new();
        op.perform(&executor).unwrap();
        // No "initramfsName" garbage - see the module doc comment on RunDracut.
        assert_eq!(
            executor.calls(),
            vec!["chroot /run/lyra-installer/target dracut -f"]
        );
    }

    #[test]
    fn remove_live_user_argv_is_exact() {
        let op = RemoveLiveUser {
            target_root: PathBuf::from("/run/lyra-installer/target"),
        };
        let executor = FakeExecutor::new();
        op.perform(&executor).unwrap();
        assert_eq!(
            executor.calls(),
            vec!["userdel -R /run/lyra-installer/target --force --remove liveuser"]
        );
    }

    #[test]
    fn lower_lyra_repo_priorities_only_touches_the_priority_line() {
        let temp = TempRoot::new("repo-priorities");
        let repos_dir = temp.0.join("etc/zypp/repos.d");
        fs::create_dir_all(&repos_dir).unwrap();
        fs::write(
            repos_dir.join("repo-lyra.repo"),
            "[repo-lyra]\nname=Lyra\nenabled=1\npriority=1\nautorefresh=1\n",
        )
        .unwrap();
        fs::write(
            repos_dir.join("repo-oss.repo"),
            "[repo-oss]\nname=OSS\npriority=20\n",
        )
        .unwrap();

        let op = LowerLyraRepoPriorities {
            target_root: temp.0.clone(),
        };
        op.perform(&FakeExecutor::new()).unwrap();

        let lyra = fs::read_to_string(repos_dir.join("repo-lyra.repo")).unwrap();
        assert!(lyra.contains("priority=90"));
        assert!(lyra.contains("name=Lyra"));
        assert!(lyra.contains("autorefresh=1"));
        // Untouched: not one of the three Lyra aliases.
        assert!(
            fs::read_to_string(repos_dir.join("repo-oss.repo"))
                .unwrap()
                .contains("priority=20")
        );
    }

    #[test]
    fn disables_package_retention_for_every_installed_repository() {
        let temp = TempRoot::new("repo-package-retention");
        let repos_dir = temp.0.join("etc/zypp/repos.d");
        fs::create_dir_all(&repos_dir).unwrap();
        fs::write(
            repos_dir.join("repo-oss.repo"),
            "[repo-oss]\nenabled=1\nautorefresh=1\nkeeppackages=1\n",
        )
        .unwrap();
        fs::write(
            repos_dir.join("repo-lyra.repo"),
            "[repo-lyra]\nenabled=1\nautorefresh=1\n",
        )
        .unwrap();

        let op = DisableRepositoryPackageRetention {
            target_root: temp.0.clone(),
        };
        op.perform(&FakeExecutor::new()).unwrap();

        for alias in ["repo-oss", "repo-lyra"] {
            let content = fs::read_to_string(repos_dir.join(format!("{alias}.repo"))).unwrap();
            assert!(content.contains("autorefresh=1"));
            assert_eq!(content.matches("keeppackages=0").count(), 1);
            assert!(!content.contains("keeppackages=1"));
        }
    }

    #[test]
    fn remove_live_only_artifacts_is_best_effort_when_files_are_missing() {
        let temp = TempRoot::new("remove-artifacts-missing");
        let op = RemoveLiveOnlyArtifacts {
            target_root: temp.0.clone(),
        };
        // None of LIVE_ONLY_ARTIFACTS exist under this fresh temp root.
        op.perform(&FakeExecutor::new())
            .expect("missing files must not be an error");
    }

    #[test]
    fn remove_live_only_artifacts_removes_files_that_exist() {
        let temp = TempRoot::new("remove-artifacts-present");
        let paths = LIVE_ONLY_ARTIFACTS
            .iter()
            .map(|artifact| temp.0.join(artifact))
            .collect::<Vec<_>>();
        for path in &paths {
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, "fixture\n").unwrap();
        }

        let op = RemoveLiveOnlyArtifacts {
            target_root: temp.0.clone(),
        };
        op.perform(&FakeExecutor::new()).unwrap();
        assert!(paths.iter().all(|path| !path.exists()));
    }

    #[test]
    fn copy_network_config_skips_ltsp_and_existing_and_rewrites_permissions() {
        let source = TempRoot::new("nm-source");
        fs::write(
            source.0.join("home-wifi.nmconnection"),
            "[connection]\npermissions=user:liveuser:;\nid=home\n",
        )
        .unwrap();
        fs::write(source.0.join("LTSP"), "should be skipped\n").unwrap();

        let target = TempRoot::new("nm-target");
        let existing_dest = target.0.join("etc/NetworkManager/system-connections");
        fs::create_dir_all(&existing_dest).unwrap();
        fs::write(
            existing_dest.join("already-there.nmconnection"),
            "id=already-there\n",
        )
        .unwrap();
        fs::write(
            source.0.join("already-there.nmconnection"),
            "id=should-not-overwrite\n",
        )
        .unwrap();

        let op = CopyNetworkConfig {
            target_root: target.0.clone(),
            source_dir: source.0.clone(),
            username: "lyra".to_string(),
        };
        op.perform(&FakeExecutor::new()).unwrap();

        let copied = fs::read_to_string(existing_dest.join("home-wifi.nmconnection")).unwrap();
        assert!(copied.contains("permissions=user:lyra:;"));
        assert!(!copied.contains("liveuser"));
        assert!(!existing_dest.join("LTSP").exists());
        assert_eq!(
            fs::read_to_string(existing_dest.join("already-there.nmconnection")).unwrap(),
            "id=already-there\n",
            "an existing target file must never be overwritten"
        );
    }

    #[test]
    fn set_hardware_clock_uses_the_target_adjfile_and_utc() {
        let op = SetHardwareClock {
            target_root: PathBuf::from("/run/lyra-installer/target"),
        };
        let executor = FakeExecutor::new();
        op.perform(&executor).unwrap();
        assert_eq!(
            executor.calls(),
            vec!["hwclock --systohc --utc --adjfile=/run/lyra-installer/target/etc/adjtime"]
        );
    }

    /// Fails every `hwclock` call unless `--directisa` is present, so tests
    /// can exercise the RTC-then-ISA retry without a real broken RTC.
    struct RtcBrokenExecutor {
        calls: RefCell<Vec<String>>,
    }

    impl RtcBrokenExecutor {
        fn new() -> Self {
            Self {
                calls: RefCell::new(Vec::new()),
            }
        }
        fn calls(&self) -> Vec<String> {
            self.calls.borrow().clone()
        }
    }

    impl Executor for RtcBrokenExecutor {
        fn run(&self, command: &ArgvCommand) -> Result<String, ExecutorError> {
            self.calls
                .borrow_mut()
                .push(format!("{} {}", command.binary, command.args.join(" ")));
            if command.args.contains(&"--directisa".to_string()) {
                Ok(String::new())
            } else {
                Err(ExecutorError::NonZeroExit {
                    binary: command.binary.clone(),
                    code: Some(1),
                    stderr: String::new(),
                })
            }
        }

        fn run_with_stdin(
            &self,
            _command: &ArgvCommand,
            _stdin: &str,
        ) -> Result<String, ExecutorError> {
            unreachable!("hwclock never uses stdin")
        }
    }

    #[test]
    fn set_hardware_clock_retries_with_isa_bus_when_rtc_method_fails() {
        let op = SetHardwareClock {
            target_root: PathBuf::from("/run/lyra-installer/target"),
        };
        let executor = RtcBrokenExecutor::new();
        op.perform(&executor)
            .expect("must not fail even though the RTC attempt did");
        assert_eq!(
            executor.calls(),
            vec![
                "hwclock --systohc --utc --adjfile=/run/lyra-installer/target/etc/adjtime",
                "hwclock --systohc --utc --directisa --adjfile=/run/lyra-installer/target/etc/adjtime",
            ]
        );
    }

    /// Always fails, RTC or ISA — mirrors the real module's "BIOS or Kernel
    /// BUG" case, which still just logs rather than aborting the install.
    struct AlwaysFailingExecutor;

    impl Executor for AlwaysFailingExecutor {
        fn run(&self, command: &ArgvCommand) -> Result<String, ExecutorError> {
            Err(ExecutorError::NonZeroExit {
                binary: command.binary.clone(),
                code: Some(1),
                stderr: String::new(),
            })
        }

        fn run_with_stdin(
            &self,
            _command: &ArgvCommand,
            _stdin: &str,
        ) -> Result<String, ExecutorError> {
            unreachable!("hwclock never uses stdin")
        }
    }

    #[test]
    fn set_hardware_clock_never_fails_the_job_even_if_both_methods_fail() {
        let op = SetHardwareClock {
            target_root: PathBuf::from("/run/lyra-installer/target"),
        };
        op.perform(&AlwaysFailingExecutor)
            .expect("real hwclock module logs and returns None, never aborts");
    }

    #[test]
    fn enable_services_targets_the_right_root_and_unit_list() {
        let op = EnableServices {
            target_root: PathBuf::from("/run/lyra-installer/target"),
        };
        let executor = FakeExecutor::new();
        op.perform(&executor).unwrap();
        assert_eq!(
            executor.calls(),
            vec![
                "systemctl --root=/run/lyra-installer/target enable NetworkManager.service firewalld.service sddm.service cups.service"
            ]
        );
    }

    #[test]
    fn write_grub_defaults_uncomments_replaces_and_appends_missing_keys() {
        let temp = TempRoot::new("grub-defaults");
        let grub_dir = temp.0.join("etc/default");
        fs::create_dir_all(&grub_dir).unwrap();
        let theme = temp.0.join("usr/share/grub/themes/Lyra-OS/theme.txt");
        fs::create_dir_all(theme.parent().unwrap()).unwrap();
        fs::write(&theme, "desktop-image: background.png\n").unwrap();
        fs::write(
            grub_dir.join("grub"),
            "GRUB_TIMEOUT=10\n#GRUB_DISABLE_RECOVERY=false\nGRUB_ENABLE_CRYPTODISK=n\nGRUB_THEME=/boot/grub2/themes/Lyra-OS/theme.txt\n",
        )
        .unwrap();

        let op = WriteGrubDefaults {
            target_root: temp.0.clone(),
        };
        op.perform(&FakeExecutor::new()).unwrap();

        let content = fs::read_to_string(grub_dir.join("grub")).unwrap();
        assert!(
            content.contains("GRUB_TIMEOUT=5"),
            "existing key should be replaced, not duplicated"
        );
        assert!(!content.contains("GRUB_TIMEOUT=10"));
        assert!(
            content.contains("GRUB_DISABLE_RECOVERY=true"),
            "commented key should be uncommented and replaced"
        );
        assert!(!content.contains("#GRUB_DISABLE_RECOVERY"));
        assert!(
            content.contains("GRUB_ENABLE_CRYPTODISK=n"),
            "unmanaged key must be left untouched"
        );
        assert!(
            content.contains("GRUB_DEFAULT=saved"),
            "missing managed key should be appended"
        );
        assert!(content.contains("GRUB_THEME=\"/usr/share/grub/themes/Lyra-OS/theme.txt\""));
        assert!(!content.contains("GRUB_THEME=/boot/grub2/themes"));
        // The real grubcfg module's plymouth auto-detect bug would produce
        // "quiet splash splash" - confirm we never do that.
        assert_eq!(content.matches("splash").count(), 1);
    }

    #[test]
    fn write_grub_defaults_rejects_a_missing_packaged_theme() {
        let temp = TempRoot::new("grub-theme-missing");
        let op = WriteGrubDefaults {
            target_root: temp.0.clone(),
        };

        let error = op.perform(&FakeExecutor::new()).unwrap_err();
        assert!(error.to_string().contains(GRUB_THEME_PATH));
        assert!(!temp.0.join("etc/default/grub").exists());
    }

    #[test]
    fn generate_grub_config_chroots_and_writes_the_right_output_path() {
        let op = GenerateGrubConfig {
            target_root: PathBuf::from("/run/lyra-installer/target"),
        };
        let executor = FakeExecutor::new();
        op.perform(&executor).unwrap();
        assert_eq!(
            executor.calls(),
            vec!["chroot /run/lyra-installer/target grub2-mkconfig -o /boot/grub2/grub.cfg"]
        );
    }

    #[test]
    fn install_shim_and_grub_argv_is_exact() {
        let op = InstallShimAndGrub {
            target_root: PathBuf::from("/run/lyra-installer/target"),
        };
        let executor = FakeExecutor::new();
        op.perform(&executor).unwrap();
        assert_eq!(
            executor.calls(),
            vec![
                "chroot /run/lyra-installer/target shim-install --efi-directory=/boot/efi --config-file=/boot/grub2/grub.cfg"
            ]
        );
    }

    #[test]
    fn prepare_btrfs_rollback_sets_default_subvolume_and_strips_fstab_options() {
        let temp = TempRoot::new("prepare-rollback");
        let etc = temp.0.join("etc");
        fs::create_dir_all(&etc).unwrap();
        fs::write(
            etc.join("fstab"),
            "UUID=1111 / btrfs subvol=/@,compress=zstd 0 0\n\
             UUID=2222 /boot/efi vfat defaults,umask=0077 0 2\n",
        )
        .unwrap();

        let op = PrepareBtrfsRollback {
            target_root: temp.0.clone(),
        };
        let executor = FakeExecutor::new();
        op.perform(&executor).unwrap();

        assert_eq!(
            executor.calls(),
            vec![format!("btrfs subvolume set-default {}", temp.0.display())]
        );
        let fstab = fs::read_to_string(etc.join("fstab")).unwrap();
        assert!(fstab.contains("UUID=1111 / btrfs compress=zstd 0 0"));
        assert!(!fstab.contains("subvol=/@"));
        assert!(
            fstab.contains("UUID=2222 /boot/efi vfat defaults,umask=0077 0 2"),
            "other lines untouched"
        );
    }

    #[test]
    fn mount_snapshots_subvolume_checks_and_appends_the_snapshots_line() {
        let temp = TempRoot::new("mount-snapshots");
        let etc = temp.0.join("etc");
        fs::create_dir_all(&etc).unwrap();
        fs::create_dir_all(temp.0.join(".snapshots")).unwrap();
        fs::write(etc.join("fstab"), "UUID=1111 / btrfs compress=zstd 0 0\n").unwrap();

        let op = MountSnapshotsSubvolume {
            target_root: temp.0.clone(),
        };
        let executor = FakeExecutor::new();
        op.perform(&executor).unwrap();

        assert_eq!(
            executor.calls(),
            vec![format!(
                "btrfs subvolume show {}",
                temp.0.join(".snapshots").display()
            )]
        );
        let fstab = fs::read_to_string(etc.join("fstab")).unwrap();
        assert!(
            fstab.contains("UUID=1111 /.snapshots btrfs compress=zstd,subvol=/@/.snapshots 0 0")
        );
    }

    #[test]
    fn regenerate_initramfs_with_fstab_uses_force_and_fstab_flags() {
        let op = RegenerateInitramfsWithFstab {
            target_root: PathBuf::from("/run/lyra-installer/target"),
        };
        let executor = FakeExecutor::new();
        op.perform(&executor).unwrap();
        assert_eq!(
            executor.calls(),
            vec!["chroot /run/lyra-installer/target dracut --force --fstab"]
        );
    }

    #[test]
    fn snapper_create_config_and_first_snapshot_argv_is_exact() {
        let config_op = SnapperCreateConfig {
            target_root: PathBuf::from("/run/lyra-installer/target"),
        };
        let executor = FakeExecutor::new();
        config_op.perform(&executor).unwrap();
        assert_eq!(
            executor.calls(),
            vec!["chroot /run/lyra-installer/target snapper --no-dbus -c root create-config /"]
        );

        let snapshot_op = SnapperCreateFirstSnapshot {
            target_root: PathBuf::from("/run/lyra-installer/target"),
        };
        let executor2 = FakeExecutor::new();
        snapshot_op.perform(&executor2).unwrap();
        assert_eq!(
            executor2.calls(),
            vec![
                "chroot /run/lyra-installer/target snapper --no-dbus -c root create --read-only --type single --cleanup-algorithm number --description first root filesystem --userdata important=yes"
            ]
        );
    }

    #[test]
    fn remove_transitional_installer_artifacts_erases_the_rpm() {
        let temp = TempRoot::new("remove-transitional");

        let op = RemoveTransitionalInstallerArtifacts {
            target_root: temp.0.clone(),
        };
        let executor = FakeExecutor::new();
        op.perform(&executor).unwrap();
        assert_eq!(
            executor.calls(),
            vec![format!(
                "rpm --root {} --erase --noscripts lyra-installer",
                temp.0.display()
            )]
        );
    }

    #[test]
    fn remove_transitional_installer_artifacts_removes_its_own_files_too() {
        let temp = TempRoot::new("remove-transitional-self");
        for artifact in LYRA_INSTALLER_ARTIFACTS {
            let path = temp.0.join(artifact);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(&path, "placeholder").unwrap();
        }

        let op = RemoveTransitionalInstallerArtifacts {
            target_root: temp.0.clone(),
        };
        op.perform(&FakeExecutor::new()).unwrap();

        for artifact in LYRA_INSTALLER_ARTIFACTS {
            assert!(
                !temp.0.join(artifact).exists(),
                "{artifact} should have been removed"
            );
        }
    }

    #[test]
    fn strip_root_subvol_option_rejects_a_fstab_without_exactly_one_root_line() {
        let error =
            strip_root_subvol_option("UUID=1111 /home btrfs subvol=/@/home 0 0\n").unwrap_err();
        assert!(matches!(error, OperationError::Io(_)));
    }

    #[test]
    fn add_snapshots_line_rejects_more_than_one_existing_snapshots_line() {
        let fstab = "UUID=1111 / btrfs compress=zstd 0 0\n\
                     UUID=1111 /.snapshots btrfs compress=zstd,subvol=/@/.snapshots 0 0\n\
                     UUID=1111 /.snapshots btrfs compress=zstd,subvol=/@/.snapshots 0 0\n";
        let error = add_snapshots_line(fstab).unwrap_err();
        assert!(matches!(error, OperationError::Io(_)));
    }

    #[test]
    fn configure_swap_writes_zram_or_removes_it_for_other_choices() {
        let temp = TempRoot::new("configure-swap");
        let config_path = temp.0.join("etc/systemd/zram-generator.conf");
        let executor = FakeExecutor::new();

        ConfigureSwap {
            target_root: temp.0.clone(),
            swap: SwapPlan::Zram,
        }
        .perform(&executor)
        .unwrap();
        let zram = fs::read_to_string(&config_path).unwrap();
        assert!(zram.contains("zram-size = min(ram / 2, 8192)"));
        assert!(zram.contains("compression-algorithm = zstd"));

        ConfigureSwap {
            target_root: temp.0.clone(),
            swap: SwapPlan::Partition {
                size_bytes: crate::storage::DISK_SWAP_SIZE_BYTES,
            },
        }
        .perform(&executor)
        .unwrap();
        assert!(!config_path.exists());

        fs::create_dir_all(config_path.parent().unwrap()).unwrap();
        fs::write(&config_path, "stale").unwrap();
        ConfigureSwap {
            target_root: temp.0.clone(),
            swap: SwapPlan::None,
        }
        .perform(&executor)
        .unwrap();
        assert!(!config_path.exists());
    }

    #[test]
    fn deployment_operations_orders_timezone_before_keyboard_before_locale() {
        let config = InstallConfig::default();
        let describe: Vec<String> = deployment_operations(&config, &SwapPlan::Zram)
            .iter()
            .map(|op| op.describe())
            .collect();

        let timezone_index = describe
            .iter()
            .position(|d| d.starts_with("configurar fuso horário"))
            .unwrap();
        let keyboard_index = describe
            .iter()
            .position(|d| d == "configurar layout de teclado")
            .unwrap();
        let locale_index = describe
            .iter()
            .position(|d| d.starts_with("configurar locale"))
            .unwrap();
        assert!(
            timezone_index < keyboard_index,
            "real settings.conf runs locale (timezone) before keyboard"
        );
        assert!(
            keyboard_index < locale_index,
            "real settings.conf runs keyboard before localecfg"
        );
    }

    #[test]
    fn deployment_operations_snapshots_only_after_all_live_cleanup() {
        let config = InstallConfig::default();
        let describe: Vec<String> = deployment_operations(&config, &SwapPlan::Zram)
            .iter()
            .map(|op| op.describe())
            .collect();

        let cleanup_index = describe
            .iter()
            .position(|d| d == "remover conta liveuser")
            .unwrap();
        let first_snapshot_index = describe
            .iter()
            .position(|d| d == "criar primeiro snapshot somente leitura")
            .unwrap();
        let installer_cleanup_index = describe
            .iter()
            .position(|d| d == "remover artefatos transitórios do instalador")
            .unwrap();
        assert!(
            cleanup_index < first_snapshot_index,
            "the first snapshot must be taken after liveuser cleanup, or it would capture it"
        );
        assert!(
            installer_cleanup_index < first_snapshot_index,
            "the first snapshot must not retain the installer RPM, privileged service or polkit rule"
        );

        // grub2-mkconfig runs twice: once before shim-install, once again
        // after the first snapshot exists (so it shows up in the rollback
        // submenu).
        let grub_indexes: Vec<usize> = describe
            .iter()
            .enumerate()
            .filter(|(_, d)| *d == "gerar configuração do GRUB")
            .map(|(i, _)| i)
            .collect();
        assert_eq!(grub_indexes.len(), 2);
        assert!(grub_indexes[1] > first_snapshot_index);

        assert_eq!(describe.last().unwrap(), "gerar configuração do GRUB");
    }
}
