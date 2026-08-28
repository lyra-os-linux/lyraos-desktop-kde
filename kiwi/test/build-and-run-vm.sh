#!/usr/bin/env bash
#
# Build the Lyra OS ISO with kiwi-ng, replace any previous test VM with a fresh
# install-target disk, and boot it in QEMU/KVM. Run this directly (not via `sudo`) --
# it escalates only the kiwi-ng build step itself, so QEMU still runs as
# your own user (needed for KVM access and the GTK display window).
#
# Usage:
#   ./build-and-run-vm.sh                 rebuild, then boot live with a fresh install disk
#   ./build-and-run-vm.sh --build-only    rebuild and validate the ISO without touching the VM
#   ./build-and-run-vm.sh --skip-build    boot the existing ISO with a fresh install disk
#   ./build-and-run-vm.sh --boot-installed
#                                        boot the installed disk without attaching an ISO
#   ./build-and-run-vm.sh --fresh-disk    accepted for compatibility; fresh is always enforced
#   ./build-and-run-vm.sh --published-installer
#                                        use the installer RPM from OBS instead of local sources
#   ./build-and-run-vm.sh --secure-boot   use OVMF with Secure Boot and Microsoft keys
#   ./build-and-run-vm.sh --help          show every option and environment override
#
# Every run rebuilds the KIWI tree from a clean slate by default. The current
# ISO is kept until the replacement is ready and then archived under
# iso/archive. A VM run stops a previous QEMU instance started by this helper,
# if one still exists, and recreates the VM disk and OVMF state only after the
# replacement ISO has passed validation. The ISO is first in the boot order
# only once; reboot inside the same QEMU session after installation to validate
# the installed disk.
#
# All output is logged (with timestamps) below a private per-user directory
# in /var/tmp, in addition to your terminal. The work tree must stay outside
# the KIWI description checkout: KIWI exposes that checkout in its build root,
# so nesting the output below it can recursively leak host paths into the ISO.
# Set LYRA_TEST_WORK_DIR to use another persistent location outside the repo.

set -euo pipefail
PATH="/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
export PATH

if [ "$(id -u)" -eq 0 ]; then
  echo "Don't run this script itself with sudo - it escalates only the" >&2
  echo "kiwi-ng build step internally. Running the whole thing as root" >&2
  echo "makes QEMU inherit root too, which usually can't open a window" >&2
  echo "on your desktop session. Run: ./$(basename "$0") [flags]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
KIWI_DESC="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$KIWI_DESC")"
INSTALLER_DIR="$REPO_ROOT/installer"
PACKAGE_SIGNING_KEYRING="$KIWI_DESC/keys/obs-package-signing-keyring.asc"
CURRENT_UID="$(id -u)"
# Keep enough memory for the live Plasma session and the Rust installer while
# installer regressions are being isolated.
RAM_MB="${LYRA_VM_RAM_MB:-8192}"
SMP="${LYRA_VM_CPUS:-4}"
RELEASE_TOOL="$REPO_ROOT/scripts/release.py"
ISO_SECURITY_AUDIT="$REPO_ROOT/scripts/audit-release-iso.py"

SKIP_BUILD=0
BUILD_ONLY=0
BOOT_INSTALLED=0
SECURE_BOOT=0
USE_LOCAL_INSTALLER=1
PRIVILEGE_TOOL="${LYRA_PRIVILEGE_TOOL:-sudo}"

run_privileged() {
  case "$PRIVILEGE_TOOL" in
    sudo) sudo "$@" ;;
    pkexec) pkexec "$@" ;;
    *) echo "LYRA_PRIVILEGE_TOOL must be sudo or pkexec" >&2; return 2 ;;
  esac
}

usage() {
  cat <<'EOF'
Uso: ./kiwi/test/build-and-run-vm.sh [opções]

Sem opções, valida e constrói a ISO, cria uma VM descartável nova e a inicia.

Opções:
  --build-only   constrói e valida a ISO sem encerrar ou alterar a VM existente
  --skip-build    reutiliza a ISO já construída
  --boot-installed
                  inicia o disco já instalado sem anexar ISO e sem recriar
                  disco ou estado UEFI
  --fresh-disk    compatibilidade; disco/NVRAM novos são sempre obrigatórios
  --published-installer
                  usa somente o RPM publicado no OBS (obrigatório para release)
  --secure-boot   usa OVMF Secure Boot com chaves Microsoft
  -h, --help      mostra esta ajuda

Recursos podem ser ajustados sem editar o script:
  LYRA_VM_DISK_SIZE=32G  tamanho do disco de instalação (padrão: 24G)
  LYRA_VM_RAM_MB=8192    memória da VM em MiB (padrão: 8192)
  LYRA_VM_CPUS=4         CPUs virtuais (padrão: 4)
  LYRA_TEST_WORK_DIR=... diretório persistente de build, ISO, VM e logs

Cada execução que inicia QEMU encerra a VM anterior e apaga seu disco e estado
UEFI somente depois de uma ISO válida estar disponível. Depois da instalação,
reinicie dentro da mesma janela do QEMU para testar o primeiro boot pelo disco
instalado. --build-only não requer QEMU, KVM, OVMF nem sessão gráfica.

Por padrão, um novo build compila e injeta o binário do instalador deste
workspace; o Lyra Welcome sempre usa o RPM publicado no OBS, já que vive em
repositório próprio. --skip-build apenas reinicia a ISO já existente e não
recompila.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --build-only) BUILD_ONLY=1; shift ;;
    --skip-build) SKIP_BUILD=1; shift ;;
    --boot-installed) BOOT_INSTALLED=1; shift ;;
    --fresh-disk) shift ;;
    --published-installer) USE_LOCAL_INSTALLER=0; shift ;;
    --secure-boot) SECURE_BOOT=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 1 ;;
  esac
done

# Keep the large KIWI tree, ISO and VM disk on the persistent filesystem.
# On many systems /tmp is a small RAM-backed tmpfs and cannot hold a full
# image build plus an expanding qcow2 installation disk.
WORK_DIR="${LYRA_TEST_WORK_DIR:-/var/tmp/lyraos-desktop-test-$CURRENT_UID}"
BUILD_DIR="$WORK_DIR/build"
BUILD_DESCRIPTION_DIR="$WORK_DIR/description"
ISO_DIR="$WORK_DIR/iso"
ISO_ARCHIVE_DIR="$ISO_DIR/archive"
VM_DIR="$WORK_DIR/vm"
DISK_IMG="$VM_DIR/lyra-os-install.qcow2"
DISK_SIZE="${LYRA_VM_DISK_SIZE:-24G}"
OVMF_VARS_STANDARD="$VM_DIR/ovmf-vars.bin"
OVMF_VARS_SECURE="$VM_DIR/ovmf-secure-vars.bin"
VM_PID_FILE="$VM_DIR/qemu.pid"
VM_MONITOR_SOCKET="$VM_DIR/qemu-monitor.sock"
LOG="$WORK_DIR/lyra-os-test.log"

if [ "$BUILD_ONLY" -eq 1 ] && [ "$SKIP_BUILD" -eq 1 ]; then
  echo "--build-only cannot be combined with --skip-build" >&2
  exit 1
fi
if [ "$BOOT_INSTALLED" -eq 1 ] &&
   { [ "$BUILD_ONLY" -eq 1 ] || [ "$SKIP_BUILD" -eq 1 ]; }; then
  echo "--boot-installed cannot be combined with --build-only or --skip-build" >&2
  exit 1
fi
if [ "$BUILD_ONLY" -eq 1 ] && [ "$SECURE_BOOT" -eq 1 ]; then
  echo "--secure-boot requires a VM run and cannot be combined with --build-only" >&2
  exit 1
fi

case "$RAM_MB" in
  ''|*[!0-9]*) echo "LYRA_VM_RAM_MB must be a positive integer" >&2; exit 1 ;;
esac
case "$SMP" in
  ''|*[!0-9]*) echo "LYRA_VM_CPUS must be a positive integer" >&2; exit 1 ;;
esac
if [ "$RAM_MB" -eq 0 ] || [ "$SMP" -eq 0 ]; then
  echo "LYRA_VM_RAM_MB and LYRA_VM_CPUS must be greater than zero" >&2
  exit 1
fi

# The build runs partly through sudo. Keep every root-written path below a
# directory owned by this user and inaccessible to other local users.
if [ -L "$WORK_DIR" ]; then
  echo "Refusing symbolic-link work directory: $WORK_DIR" >&2
  exit 1
fi
if [ -e "$WORK_DIR" ] && [ "$(stat -c '%u' "$WORK_DIR")" -ne "$CURRENT_UID" ]; then
  echo "Work directory is not owned by the current user: $WORK_DIR" >&2
  exit 1
fi
mkdir -p -m 0700 "$WORK_DIR"
chmod 0700 "$WORK_DIR"

case "$(readlink -f "$WORK_DIR")/" in
  "$(readlink -f "$REPO_ROOT")/"*)
    echo "Work directory must be outside the repository: $WORK_DIR" >&2
    exit 1
    ;;
esac

validate_live_rootfs_homes() {
  local extracted_root="$1"
  local unexpected_home

  if [ ! -d "$extracted_root/home/liveuser" ]; then
    echo "!!! live rootfs does not contain /home/liveuser" >&2
    return 1
  fi
  unexpected_home="$(
    find "$extracted_root/home" -mindepth 1 -maxdepth 1 \
      ! -name liveuser -print -quit
  )"
  if [ -n "$unexpected_home" ]; then
    echo "!!! live rootfs contains an unexpected home: $unexpected_home" >&2
    echo "!!! refusing an ISO that may contain host build data" >&2
    return 1
  fi
}

audit_live_rootfs() {
  local iso="$1"
  local extracted_root="$2"
  local report="$3"

  if ! "$ISO_SECURITY_AUDIT" "$iso" --rootfs "$extracted_root" --output "$report"; then
    echo "!!! live rootfs failed the build-host data security audit" >&2
    echo "!!! evidence: $report" >&2
    return 1
  fi
}

# Timestamp every line, tee to log file and terminal.
exec > >(while IFS= read -r line; do printf '%s %s\n' "$(date '+%H:%M:%S')" "$line"; done | tee -a "$LOG") 2>&1

echo "=== $(date -Iseconds) run start (args: $*) ==="
echo "--- using KIWI description: $KIWI_DESC ---"

mkdir -p "$ISO_DIR"

stop_previous_vm() {
  if [ ! -f "$VM_PID_FILE" ]; then
    return
  fi

  PREVIOUS_VM_PID="$(head -n 1 "$VM_PID_FILE" 2>/dev/null || true)"
  case "$PREVIOUS_VM_PID" in
    ''|*[!0-9]*) return ;;
  esac
  if ! kill -0 "$PREVIOUS_VM_PID" 2>/dev/null; then
    return
  fi

  PREVIOUS_VM_CMDLINE="$(tr '\0' '\n' < "/proc/$PREVIOUS_VM_PID/cmdline" 2>/dev/null || true)"
  if ! grep -F 'qemu-system-x86_64' <<<"$PREVIOUS_VM_CMDLINE" >/dev/null ||
     ! grep -F "$DISK_IMG" <<<"$PREVIOUS_VM_CMDLINE" >/dev/null; then
    echo "!!! refusing to stop PID $PREVIOUS_VM_PID: it is not this Lyra VM" >&2
    exit 1
  fi

  echo "--- stopping previous Lyra VM (PID $PREVIOUS_VM_PID) ---"
  kill "$PREVIOUS_VM_PID"
  for _ in {1..50}; do
    if ! kill -0 "$PREVIOUS_VM_PID" 2>/dev/null; then
      return
    fi
    sleep 0.1
  done
  echo "--- previous VM did not stop; forcing termination ---"
  kill -KILL "$PREVIOUS_VM_PID"
}

if [ ! -x "$RELEASE_TOOL" ]; then
  echo "release metadata tool is missing or not executable: $RELEASE_TOOL" >&2
  exit 1
fi
"$RELEASE_TOOL" check
EXPECTED_ISO_NAME="$("$RELEASE_TOOL" field iso_filename)"
BUILD_SOURCE_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD)"
BUILD_SOURCE_EPOCH="$(git -C "$REPO_ROOT" show -s --format=%ct "$BUILD_SOURCE_COMMIT")"
GIT_STATUS_FILE="$WORK_DIR/source-status.txt"
git -C "$REPO_ROOT" status --porcelain --untracked-files=normal >"$GIT_STATUS_FILE"
if [ -s "$GIT_STATUS_FILE" ]; then
  BUILD_SOURCE_DIRTY=1
else
  BUILD_SOURCE_DIRTY=0
fi
IMAGE_BUILT_AT="$(date -u -d "@$BUILD_SOURCE_EPOCH" +%Y-%m-%dT%H:%M:%SZ)"

if [ "$SECURE_BOOT" -eq 1 ]; then
  OVMF_CODE="/usr/share/qemu/ovmf-x86_64-smm-ms-code.bin"
  OVMF_VARS_TEMPLATE="/usr/share/qemu/ovmf-x86_64-smm-ms-vars.bin"
  OVMF_VARS="$OVMF_VARS_SECURE"
  MACHINE="q35,accel=kvm,smm=on"
else
  OVMF_CODE="/usr/share/qemu/ovmf-x86_64-4m-code.bin"
  OVMF_VARS_TEMPLATE="/usr/share/qemu/ovmf-x86_64-4m-vars.bin"
  OVMF_VARS="$OVMF_VARS_STANDARD"
  MACHINE="q35,accel=kvm"
fi

if [ "$BOOT_INSTALLED" -eq 1 ]; then
  if ! command -v qemu-system-x86_64 >/dev/null 2>&1; then
    echo "required command not found: qemu-system-x86_64" >&2
    exit 1
  fi
  if [ ! -r "$OVMF_CODE" ]; then
    echo "OVMF firmware code is missing or unreadable: $OVMF_CODE" >&2
    exit 1
  fi
  if [ ! -f "$DISK_IMG" ] || [ ! -r "$DISK_IMG" ] || [ -L "$DISK_IMG" ]; then
    echo "installed VM disk is missing, unreadable, or a symbolic link:" >&2
    echo "  $DISK_IMG" >&2
    echo "Run a normal installation before using --boot-installed." >&2
    exit 1
  fi
  if [ ! -f "$OVMF_VARS" ] || [ ! -r "$OVMF_VARS" ] || [ -L "$OVMF_VARS" ]; then
    echo "installed VM UEFI state is missing, unreadable, or a symbolic link:" >&2
    echo "  $OVMF_VARS" >&2
    echo "Use the same Secure Boot mode used during installation." >&2
    exit 1
  fi
  if [ ! -r /dev/kvm ] || [ ! -w /dev/kvm ]; then
    echo "KVM is unavailable to the current user (/dev/kvm is not readable/writable)." >&2
    exit 1
  fi
  if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    echo "No graphical display found (DISPLAY and WAYLAND_DISPLAY are unset)." >&2
    exit 1
  fi

  mkdir -p "$VM_DIR"
  stop_previous_vm
  rm -f "$VM_PID_FILE" "$VM_MONITOR_SOCKET"

  INSTALLED_QEMU_ARGS=(
    -name lyra-os-test
    -pidfile "$VM_PID_FILE"
    -monitor "unix:$VM_MONITOR_SOCKET,server=on,wait=off"
    -machine "$MACHINE"
    -cpu host
    -smp "$SMP"
    -m "$RAM_MB"
    -drive if=pflash,format=raw,readonly=on,file="$OVMF_CODE"
    -drive if=pflash,format=raw,file="$OVMF_VARS"
    -drive if=virtio,format=qcow2,file="$DISK_IMG"
    -device virtio-net-pci,netdev=net0
    -netdev user,id=net0
    -vga virtio
    -display gtk
    -boot order=c,menu=on
  )
  if [ "$SECURE_BOOT" -eq 1 ]; then
    INSTALLED_QEMU_ARGS+=(-global driver=cfi.pflash01,property=secure,value=on)
  fi

  echo "--- booting installed disk without attaching an ISO ---"
  echo "--- preserving VM disk and UEFI state ---"
  echo "--- launching: qemu-system-x86_64 ${INSTALLED_QEMU_ARGS[*]} ---"
  if qemu-system-x86_64 "${INSTALLED_QEMU_ARGS[@]}"; then
    INSTALLED_QEMU_STATUS=0
  else
    INSTALLED_QEMU_STATUS=$?
  fi
  rm -f "$VM_PID_FILE"
  echo "=== qemu exited with status $INSTALLED_QEMU_STATUS ==="
  exit "$INSTALLED_QEMU_STATUS"
fi

if [ "$SKIP_BUILD" -eq 0 ]; then
  for command in kiwi-ng ldconfig ldd lsinitrd strings "$PRIVILEGE_TOOL" xorriso unsquashfs; do
    if ! command -v "$command" >/dev/null 2>&1; then
      echo "required build command not found: $command" >&2
      exit 1
    fi
  done
  if [ "$USE_LOCAL_INSTALLER" -eq 1 ]; then
    for command in cargo install sha256sum; do
      if ! command -v "$command" >/dev/null 2>&1; then
        echo "required local workspace command not found: $command" >&2
        exit 1
      fi
    done
  fi
  if [ ! -r "$PACKAGE_SIGNING_KEYRING" ]; then
    echo "required RPM package signing keyring is missing: $PACKAGE_SIGNING_KEYRING" >&2
    exit 1
  fi
fi

# KIWI's package bootstrap runs privileged scriptlets in a chroot.  A real
# Alpha 6 build temporarily left the host loader cache pointing at the image
# root: desktop processes then failed to resolve libz.so.1 and localsearch
# spawned a failing extractor every second until the session became
# unresponsive.  Keep this guard in the supported helper instead of relying
# on every caller to remember a post-build ldconfig.
LOADER_GUARD_PID=""
LOADER_GUARD_PARENT_PID=""
LOADER_SENTINEL=/usr/bin/zypper

host_loader_is_healthy() {
  ldd "$LOADER_SENTINEL" 2>&1 | grep -F 'libz.so.1 =>' >/dev/null &&
    ! ldd "$LOADER_SENTINEL" 2>&1 | grep -F 'not found' >/dev/null
}

repair_host_loader_cache() {
  if host_loader_is_healthy; then
    return 0
  fi
  echo "!!! host loader cache became inconsistent; regenerating it with ldconfig"
  if [ "$PRIVILEGE_TOOL" = sudo ]; then
    sudo -n ldconfig
  else
    pkexec /usr/sbin/ldconfig
  fi
  if ! host_loader_is_healthy; then
    echo "!!! host loader cache is still inconsistent after ldconfig" >&2
    return 1
  fi
  echo "--- host loader cache recovered ---"
}

stop_loader_guard() {
  if [ -n "$LOADER_GUARD_PID" ]; then
    kill "$LOADER_GUARD_PID" 2>/dev/null || true
    wait "$LOADER_GUARD_PID" 2>/dev/null || true
    LOADER_GUARD_PID=""
  fi
  repair_host_loader_cache
}

start_loader_guard() {
  # Acquire credentials in the foreground so recovery never blocks on an
  # invisible password prompt in the background watcher.
  if [ "$PRIVILEGE_TOOL" = sudo ]; then
    sudo -v
  else
    pkexec /usr/bin/true
  fi
  repair_host_loader_cache
  LOADER_GUARD_PARENT_PID="$BASHPID"
  (
    refresh_count=0
    while sleep 2; do
      refresh_count=$((refresh_count + 1))
      if [ "$PRIVILEGE_TOOL" = sudo ] && [ "$refresh_count" -ge 30 ]; then
        if ! sudo -n -v; then
          echo "!!! loader guard could not renew its sudo credential; aborting build" >&2
          kill -TERM "$LOADER_GUARD_PARENT_PID"
          exit 1
        fi
        refresh_count=0
      fi
      if ! repair_host_loader_cache; then
        echo "!!! loader guard could not recover the host; aborting build" >&2
        kill -TERM "$LOADER_GUARD_PARENT_PID"
        exit 1
      fi
    done
  ) &
  LOADER_GUARD_PID=$!
}

ISO_PATH=""

if [ "$SKIP_BUILD" -eq 1 ]; then
  ISO_CANDIDATES=()
  mapfile -d '' -t ISO_CANDIDATES < <(
    find "$ISO_DIR" -maxdepth 1 -type f -name '*.iso' -print0 2>/dev/null
  )
  if [ "${#ISO_CANDIDATES[@]}" -gt 1 ]; then
    echo "!!! multiple ISO files found in $ISO_DIR; refusing an ambiguous boot:" >&2
    printf '  %s\n' "${ISO_CANDIDATES[@]}" >&2
    exit 1
  elif [ "${#ISO_CANDIDATES[@]}" -eq 1 ]; then
    ISO_PATH="${ISO_CANDIDATES[0]}"
    if [ "$(basename "$ISO_PATH")" != "$EXPECTED_ISO_NAME" ]; then
      echo "!!! cached ISO does not match release.toml:" >&2
      echo "  expected: $EXPECTED_ISO_NAME" >&2
      echo "  found:    $(basename "$ISO_PATH")" >&2
      exit 1
    fi
  fi
fi

if [ "$SKIP_BUILD" -eq 0 ]; then
  echo "--- wiping the previous build dir; preserving the current ISO ---"
  run_privileged rm -rf "$BUILD_DIR"
  ISO_PATH=""

  echo "--- staging clean KIWI description ---"
  rm -rf "$BUILD_DESCRIPTION_DIR"
  mkdir -p "$BUILD_DESCRIPTION_DIR"
  cp \
    "$KIWI_DESC/config.xml" \
    "$KIWI_DESC/config.sh" \
    "$KIWI_DESC/edit_boot_config.sh" \
    "$BUILD_DESCRIPTION_DIR/"
  cp -a "$KIWI_DESC/root" "$BUILD_DESCRIPTION_DIR/root"
  cp -a "$KIWI_DESC/keys" "$BUILD_DESCRIPTION_DIR/keys"
  find "$BUILD_DESCRIPTION_DIR/root" -type d -name __pycache__ -prune -exec rm -rf -- {} +
  find "$BUILD_DESCRIPTION_DIR/root" -type f -name '*.pyc' -delete

  BUILD_DESCRIPTION="$BUILD_DESCRIPTION_DIR"
  LOCAL_INSTALLER_GUI_SHA256=""
  LOCAL_INSTALLER_SERVICE_SHA256=""
  if [ "$USE_LOCAL_INSTALLER" -eq 1 ]; then
    echo "--- compiling current Lyra Installer workspace ---"
    cargo build \
      --manifest-path "$INSTALLER_DIR/Cargo.toml" \
      --workspace \
      --release \
      --locked

    echo "--- adding local installer binaries to staged KIWI description ---"

    install -Dm0755 "$INSTALLER_DIR/target/release/lyra-installer" \
      "$BUILD_DESCRIPTION_DIR/root/usr/bin/lyra-installer"
    install -Dm0755 "$INSTALLER_DIR/target/release/lyra-installer-service" \
      "$BUILD_DESCRIPTION_DIR/root/usr/libexec/lyra-installer-service"
    install -Dm0644 "$INSTALLER_DIR/packaging/io.lyra.Installer.policy" \
      "$BUILD_DESCRIPTION_DIR/root/usr/share/polkit-1/actions/io.lyra.Installer.policy"
    install -Dm0644 "$INSTALLER_DIR/packaging/01-lyra-installer-service.rules" \
      "$BUILD_DESCRIPTION_DIR/root/etc/polkit-1/rules.d/01-lyra-installer-service.rules"

    INSTALLER_BUILD_SOURCE="$BUILD_DESCRIPTION_DIR/root/usr/share/lyra-installer/build-source.txt"
    install -d "$(dirname "$INSTALLER_BUILD_SOURCE")"
    {
      printf 'commit=%s\n' "$BUILD_SOURCE_COMMIT"
      printf 'dirty=%s\n' "$BUILD_SOURCE_DIRTY"
      printf 'cargo_lock_sha256=%s\n' \
        "$(sha256sum "$INSTALLER_DIR/Cargo.lock" | awk '{print $1}')"
      printf 'source=local-worktree\n'
    } >"$INSTALLER_BUILD_SOURCE"
    install -Dm0644 /dev/null \
      "$BUILD_DESCRIPTION_DIR/root/usr/lib/lyra-os/local-installer-build"
    printf 'commit=%s\ndirty=%s\n' "$BUILD_SOURCE_COMMIT" "$BUILD_SOURCE_DIRTY" \
      >"$BUILD_DESCRIPTION_DIR/root/usr/lib/lyra-os/local-installer-build"

    LOCAL_INSTALLER_GUI_SHA256="$(sha256sum "$INSTALLER_DIR/target/release/lyra-installer" | awk '{print $1}')"
    LOCAL_INSTALLER_SERVICE_SHA256="$(sha256sum "$INSTALLER_DIR/target/release/lyra-installer-service" | awk '{print $1}')"
    BUILD_DESCRIPTION="$BUILD_DESCRIPTION_DIR"
    echo "--- DEVELOPMENT IMAGE: local installer override is not releasable ---"
  else
    echo "--- using published Lyra Installer RPM from OBS ---"
  fi


  echo "--- building ISO with kiwi-ng (will prompt for sudo password) ---"
  start_loader_guard
  trap 'stop_loader_guard' EXIT
  trap 'stop_loader_guard; exit 130' INT TERM
  if run_privileged kiwi-ng \
      --setenv="LYRA_BUILD_SOURCE_COMMIT=$BUILD_SOURCE_COMMIT" \
      --setenv="LYRA_BUILD_SOURCE_DIRTY=$BUILD_SOURCE_DIRTY" \
      --setenv="LYRA_BUILD_SOURCE_EPOCH=$BUILD_SOURCE_EPOCH" \
      --setenv="LYRA_IMAGE_BUILT_AT=$IMAGE_BUILT_AT" \
      system build \
      --signing-key "$PACKAGE_SIGNING_KEYRING" \
      --description "$BUILD_DESCRIPTION" \
      --target-dir "$BUILD_DIR"; then
    BUILD_STATUS=0
  else
    BUILD_STATUS=$?
    stop_loader_guard
    trap - EXIT INT TERM
    echo "!!! kiwi-ng build failed with exit code $BUILD_STATUS, see log above"
    exit "$BUILD_STATUS"
  fi
  stop_loader_guard
  trap - EXIT INT TERM

  IMAGE_MTAB="$BUILD_DIR/build/image-root/etc/mtab"
  if [ ! -L "$IMAGE_MTAB" ] || [ "$(readlink "$IMAGE_MTAB")" != "../proc/self/mounts" ]; then
    echo "!!! built image has no valid /etc/mtab -> ../proc/self/mounts symlink" >&2
    echo "!!! Snapper cannot detect the installed root filesystem without it" >&2
    exit 1
  fi

  IMAGE_OS_RELEASE="$BUILD_DIR/build/image-root/etc/os-release"
  if ! grep -Fx "VERSION_ID=\"$("$RELEASE_TOOL" field version_id)\"" \
      "$IMAGE_OS_RELEASE" >/dev/null; then
    echo "!!! built image /etc/os-release does not match release.toml" >&2
    exit 1
  fi
  if ! grep -Fx "LYRA_SOURCE_COMMIT=\"$BUILD_SOURCE_COMMIT\"" \
      "$BUILD_DIR/build/image-root/usr/lib/lyra-os/build-info" >/dev/null; then
    echo "!!! built image does not identify source commit $BUILD_SOURCE_COMMIT" >&2
    exit 1
  fi

  IMAGE_SDDM_LIVE_CONFIG="$BUILD_DIR/build/image-root/etc/sddm.conf.d/10-lyra-live.conf"
  IMAGE_SDDM_MAIN_CONFIG="$BUILD_DIR/build/image-root/etc/sddm.conf"
  IMAGE_PLASMA_SESSION="$BUILD_DIR/build/image-root/usr/share/wayland-sessions/plasmawayland.desktop"
  IMAGE_XORG="$BUILD_DIR/build/image-root/usr/bin/Xorg"
  IMAGE_XORG_LIBINPUT="$BUILD_DIR/build/image-root/usr/lib64/xorg/modules/input/libinput_drv.so"
  IMAGE_DBUS_RUN_SESSION="$BUILD_DIR/build/image-root/usr/bin/dbus-run-session"
  IMAGE_LIVEUSER_PASSWORDLESS="$BUILD_DIR/build/image-root/usr/lib/lyra-os/liveuser-passwordless"
  IMAGE_SDDM_PAM="$BUILD_DIR/build/image-root/etc/pam.d/sddm"
  IMAGE_SDDM_AUTOLOGIN_PAM="$BUILD_DIR/build/image-root/etc/pam.d/sddm-autologin"
  IMAGE_LIVE_COMMON_AUTH="$BUILD_DIR/build/image-root/etc/pam.d/common-auth-lyra-live"
  if ! grep -Fx 'User=liveuser' "$IMAGE_SDDM_LIVE_CONFIG" >/dev/null ||
     ! grep -Fx 'Session=plasmawayland.desktop' "$IMAGE_SDDM_LIVE_CONFIG" >/dev/null ||
     ! grep -Fx 'User=liveuser' "$IMAGE_SDDM_MAIN_CONFIG" >/dev/null ||
     ! grep -Fx 'Session=plasmawayland.desktop' "$IMAGE_SDDM_MAIN_CONFIG" >/dev/null ||
     [ ! -s "$IMAGE_PLASMA_SESSION" ] ||
     [ ! -x "$IMAGE_XORG" ] ||
     [ ! -s "$IMAGE_XORG_LIBINPUT" ] ||
     [ ! -x "$IMAGE_DBUS_RUN_SESSION" ] ||
     [ ! -f "$IMAGE_LIVEUSER_PASSWORDLESS" ] ||
     ! grep -F 'common-auth-lyra-live' "$IMAGE_SDDM_PAM" >/dev/null ||
     ! grep -E 'pam_unix\.so[[:space:]]+nullok' "$IMAGE_LIVE_COMMON_AUTH" >/dev/null ||
     grep -F 'pam_nologin.so' "$IMAGE_SDDM_AUTOLOGIN_PAM" >/dev/null; then
    echo "!!! built image has no valid SDDM/Plasma Wayland autologin chain" >&2
    exit 1
  fi
  echo "--- validated SDDM autologin and Plasma Wayland session ---"

  IMAGE_WALLPAPER_DIR="$BUILD_DIR/build/image-root/usr/share/backgrounds/lyra"
  if [ ! -s "$IMAGE_WALLPAPER_DIR/2702-dawn.png" ]; then
    echo "!!! built image is missing the default Lyra OS - Dawn wallpaper asset:" >&2
    echo "  $IMAGE_WALLPAPER_DIR/2702-dawn.png" >&2
    exit 1
  fi
  echo "--- validated Lyra OS - Dawn wallpaper asset ---"

  IMAGE_INSTALLER_GUI="$BUILD_DIR/build/image-root/usr/bin/lyra-installer"
  IMAGE_INSTALLER_LOCK="$BUILD_DIR/build/image-root/usr/bin/lyra-install-lock"
  IMAGE_INSTALLER_SERVICE="$BUILD_DIR/build/image-root/usr/libexec/lyra-installer-service"
  IMAGE_HARDWARE_MATRIX="$BUILD_DIR/build/image-root/usr/bin/lyra-hardware-matrix"
  IMAGE_LIVE_SMOKE="$BUILD_DIR/build/image-root/usr/bin/lyra-live-smoke"
  IMAGE_SYSTEM_SMOKE="$BUILD_DIR/build/image-root/usr/bin/lyra-system-smoke"
  IMAGE_UPDATE_SMOKE="$BUILD_DIR/build/image-root/usr/bin/lyra-update-smoke"
  IMAGE_INSTALLER_AUTOSTART="$BUILD_DIR/build/image-root/etc/xdg/autostart/lyra-installer-autostart.desktop"
  IMAGE_PLASMA_INITIALIZE_AUTOSTART="$BUILD_DIR/build/image-root/etc/xdg/autostart/lyra-plasma-initialize.desktop"
  IMAGE_LIVE_PLASMA_START="$BUILD_DIR/build/image-root/usr/libexec/lyra-live-plasma-start"
  IMAGE_INSTALLER_LAUNCHER="$BUILD_DIR/build/image-root/usr/share/applications/org.lyraos.LyraInstaller.desktop"
  IMAGE_INSTALLER_ICON="$BUILD_DIR/build/image-root/usr/share/icons/hicolor/256x256/apps/org.lyraos.LyraInstaller.png"
  for INSTALLER_EXECUTABLE in \
      "$IMAGE_INSTALLER_GUI" \
      "$IMAGE_INSTALLER_LOCK" \
      "$IMAGE_INSTALLER_SERVICE" \
      "$IMAGE_LIVE_PLASMA_START" \
      "$IMAGE_HARDWARE_MATRIX" \
      "$IMAGE_LIVE_SMOKE" \
      "$IMAGE_SYSTEM_SMOKE" \
      "$IMAGE_UPDATE_SMOKE"; do
    if [ ! -x "$INSTALLER_EXECUTABLE" ]; then
      echo "!!! built image is missing an executable installer component:" >&2
      echo "  $INSTALLER_EXECUTABLE" >&2
      exit 1
    fi
  done
  # Validate the actual packaged service, not merely the local source tree.
  # Alpha 6 once embedded a green but stale OBS RPM from before the Fish
  # migration; installations succeeded and silently created Bash users.
  # Optimized Rust/LLVM builds may split the literal `/usr/bin/fish` into
  # adjacent ELF string fragments (for example `bin/fish` and `/usr/bin`).
  # Check the stable suffix in the actual packaged ELF instead of requiring
  # one contiguous `strings` record, while still rejecting the old Bash
  # implementation.
  if ! grep -a -F 'bin/fish' "$IMAGE_INSTALLER_SERVICE" >/dev/null ||
     grep -a -F '.bashrc' "$IMAGE_INSTALLER_SERVICE" >/dev/null; then
    echo "!!! packaged Lyra Installer does not enforce the desktop Fish policy" >&2
    echo "!!! refusing an ISO with a stale or incompatible installer RPM" >&2
    if [ -f "$BUILD_DIR/build/image-root/usr/share/lyra-installer/build-source.txt" ]; then
      echo "!!! packaged installer source identity:" >&2
      sed 's/^/  /' \
        "$BUILD_DIR/build/image-root/usr/share/lyra-installer/build-source.txt" >&2
    fi
    exit 1
  fi
  if [ "$USE_LOCAL_INSTALLER" -eq 1 ]; then
    IMAGE_INSTALLER_GUI_SHA256="$(sha256sum "$IMAGE_INSTALLER_GUI" | awk '{print $1}')"
    IMAGE_INSTALLER_SERVICE_SHA256="$(sha256sum "$IMAGE_INSTALLER_SERVICE" | awk '{print $1}')"
    if [ "$IMAGE_INSTALLER_GUI_SHA256" != "$LOCAL_INSTALLER_GUI_SHA256" ] ||
       [ "$IMAGE_INSTALLER_SERVICE_SHA256" != "$LOCAL_INSTALLER_SERVICE_SHA256" ]; then
      echo "!!! built image did not preserve the current local installer binaries" >&2
      exit 1
    fi
    if [ ! -f "$BUILD_DIR/build/image-root/usr/lib/lyra-os/local-installer-build" ]; then
      echo "!!! built development image lost local installer provenance" >&2
      exit 1
    fi
  fi
  if [ ! -f "$IMAGE_INSTALLER_AUTOSTART" ] ||
     ! grep -Fx 'TryExec=/usr/bin/lyra-installer' "$IMAGE_INSTALLER_AUTOSTART" >/dev/null ||
     ! grep -Fx 'Exec=/usr/bin/lyra-install-lock /usr/bin/lyra-installer' \
        "$IMAGE_INSTALLER_AUTOSTART" >/dev/null ||
     ! grep -Fx 'Exec=/usr/libexec/lyra-live-plasma-start' \
        "$IMAGE_PLASMA_INITIALIZE_AUTOSTART" >/dev/null ||
     ! grep -F 'kscreen-doctor -o' "$IMAGE_LIVE_PLASMA_START" >/dev/null ||
     ! grep -F 'lookandfeeltool -a org.kde.breeze.desktop --resetLayout' \
        "$IMAGE_LIVE_PLASMA_START" >/dev/null ||
     ! grep -Fx 'StartupWMClass=lyra-installer' \
        "$IMAGE_INSTALLER_AUTOSTART" >/dev/null; then
    echo "!!! built image has no valid Plasma autostart for Lyra Installer" >&2
    exit 1
  fi
  if [ ! -f "$IMAGE_INSTALLER_LAUNCHER" ] || [ ! -s "$IMAGE_INSTALLER_ICON" ]; then
    echo "!!! built image is missing the Lyra Installer launcher or icon" >&2
    exit 1
  fi
  if ! grep -Fx 'TryExec=/usr/bin/lyra-installer' "$IMAGE_INSTALLER_LAUNCHER" >/dev/null ||
     ! grep -Fx 'Exec=/usr/bin/lyra-install-lock /usr/bin/lyra-installer' \
        "$IMAGE_INSTALLER_LAUNCHER" >/dev/null ||
     ! grep -Fx 'Icon=org.lyraos.LyraInstaller' "$IMAGE_INSTALLER_LAUNCHER" >/dev/null ||
     ! grep -Fx 'StartupWMClass=lyra-installer' \
        "$IMAGE_INSTALLER_LAUNCHER" >/dev/null; then
    echo "!!! built image has an inconsistent Lyra Installer desktop identity" >&2
    exit 1
  fi
  if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate "$IMAGE_INSTALLER_AUTOSTART" "$IMAGE_INSTALLER_LAUNCHER"
  fi
  echo "--- validated Lyra Installer executable and Plasma autostart chain ---"

  BUILT_ISO="$(run_privileged find "$BUILD_DIR" -maxdepth 1 -type f -name '*.iso' -print -quit)"
  if [ -z "$BUILT_ISO" ]; then
    echo "!!! kiwi-ng reported success but no .iso found under $BUILD_DIR"
    exit 1
  fi
  if [ "$(basename "$BUILT_ISO")" != "$EXPECTED_ISO_NAME" ]; then
    echo "!!! KIWI generated an unexpected ISO name:" >&2
    echo "  expected: $EXPECTED_ISO_NAME" >&2
    echo "  found:    $(basename "$BUILT_ISO")" >&2
    exit 1
  fi

  ISO_GRUB_CFG="$WORK_DIR/iso-grub.cfg"
  ISO_INITRD="$WORK_DIR/iso-initrd"
  ISO_SQUASHFS="$WORK_DIR/iso-squashfs.img"
  SQUASHFS_VERIFY_DIR="$WORK_DIR/squashfs-verify"
  rm -f "$ISO_GRUB_CFG" "$ISO_INITRD" "$ISO_SQUASHFS"
  chmod -R u+rwX "$SQUASHFS_VERIFY_DIR" 2>/dev/null || true
  rm -rf "$SQUASHFS_VERIFY_DIR"
  xorriso -osirrox on -indev "$BUILT_ISO" \
    -extract /boot/grub2/grub.cfg "$ISO_GRUB_CFG" >/dev/null 2>&1
  xorriso -osirrox on -indev "$BUILT_ISO" \
    -extract /boot/x86_64/loader/initrd "$ISO_INITRD" >/dev/null 2>&1
  xorriso -osirrox on -indev "$BUILT_ISO" \
    -extract /LiveOS/squashfs.img "$ISO_SQUASHFS" >/dev/null 2>&1

  if grep -Eq '^[[:space:]]*linux .* (quiet|splash)( |$)' "$ISO_GRUB_CFG"; then
    echo "!!! live GRUB entry unexpectedly hides boot diagnostics with quiet/splash" >&2
    exit 1
  fi
  if lsinitrd -m "$ISO_INITRD" | grep -Fx 'plymouth' >/dev/null; then
    echo "!!! Plymouth was included in the generic live initrd" >&2
    echo "!!! this regresses boot by pulling the complete DRM/firmware set" >&2
    exit 1
  fi
  echo "--- validated live initrd without Plymouth ($(du -h "$ISO_INITRD" | cut -f1)) ---"

  # Reading metadata is insufficient: the Alpha 3 installer exposed an ISO
  # whose SquashFS superblock was valid but one XZ-compressed data block was
  # corrupt. Fully extract every inode before the image can replace the last
  # known test ISO. This intentionally costs time and temporary disk space;
  # an installer image whose rootfs cannot be read end-to-end is unusable.
  echo "--- validating every compressed block in the live SquashFS ---"
  # Validate serially: parallel XZ readers have produced intermittent data
  # errors on otherwise identical large live images on constrained hosts.
  if ! unsquashfs -processors 1 -no-xattrs -no-exit-code -f \
      -d "$SQUASHFS_VERIFY_DIR" "$ISO_SQUASHFS" >/dev/null; then
    echo "!!! generated ISO contains an unreadable/corrupt live SquashFS" >&2
    echo "!!! refusing to promote or boot: $BUILT_ISO" >&2
    chmod -R u+rwX "$SQUASHFS_VERIFY_DIR" 2>/dev/null || true
    rm -rf "$SQUASHFS_VERIFY_DIR"
    exit 1
  fi
  if ! validate_live_rootfs_homes "$SQUASHFS_VERIFY_DIR"; then
    chmod -R u+rwX "$SQUASHFS_VERIFY_DIR" 2>/dev/null || true
    rm -rf "$SQUASHFS_VERIFY_DIR"
    exit 1
  fi
  if ! audit_live_rootfs \
      "$BUILT_ISO" "$SQUASHFS_VERIFY_DIR" "$WORK_DIR/generated-iso-security-audit.json"; then
    chmod -R u+rwX "$SQUASHFS_VERIFY_DIR" 2>/dev/null || true
    rm -rf "$SQUASHFS_VERIFY_DIR"
    exit 1
  fi
  chmod -R u+rwX "$SQUASHFS_VERIFY_DIR" 2>/dev/null || true
  rm -rf "$SQUASHFS_VERIFY_DIR"
  echo "--- validated live SquashFS by full extraction ---"

  ISO_NAME="$(basename "$BUILT_ISO")"
  ISO_PATH="$ISO_DIR/$ISO_NAME"
  ISO_STAGED="$ISO_DIR/.$ISO_NAME.new"
  rm -f "$ISO_STAGED"
  echo "--- staging $BUILT_ISO -> $ISO_STAGED ---"
  # The KIWI result is world-readable and ISO_DIR belongs to the invoking
  # user. Keep artifact promotion unprivileged so a completed build cannot
  # stall behind a second desktop authorization prompt.
  cp "$BUILT_ISO" "$ISO_STAGED"

  EXISTING_ISOS=()
  mapfile -d '' -t EXISTING_ISOS < <(
    find "$ISO_DIR" -maxdepth 1 -type f -name '*.iso' -print0 2>/dev/null
  )
  for EXISTING_ISO in "${EXISTING_ISOS[@]}"; do
    mkdir -p "$ISO_ARCHIVE_DIR"
    ARCHIVE_STAMP="$(date '+%Y%m%d-%H%M%S')"
    EXISTING_NAME="$(basename "$EXISTING_ISO")"
    ARCHIVED_ISO="$ISO_ARCHIVE_DIR/${EXISTING_NAME%.iso}-$ARCHIVE_STAMP.iso"
    if [ -e "$ARCHIVED_ISO" ]; then
      ARCHIVED_ISO="$ISO_ARCHIVE_DIR/${EXISTING_NAME%.iso}-$ARCHIVE_STAMP-$$.iso"
    fi
    echo "--- archiving previous ISO -> $ARCHIVED_ISO ---"
    mv "$EXISTING_ISO" "$ARCHIVED_ISO"
    if [ -f "$EXISTING_ISO.manifest.json" ]; then
      mv "$EXISTING_ISO.manifest.json" "$ARCHIVED_ISO.manifest.json"
    fi
  done

  echo "--- promoting new ISO -> $ISO_PATH ---"
  mv -f "$ISO_STAGED" "$ISO_PATH"
  echo "--- writing build traceability manifest ---"
  "$RELEASE_TOOL" build-manifest --iso "$ISO_PATH"
else
  echo "--- skipping build, reusing existing ISO ---"
fi

if [ -z "$ISO_PATH" ] || [ ! -f "$ISO_PATH" ]; then
  echo "!!! no ISO available (build skipped and none found in $ISO_DIR)"
  exit 1
fi

if [ "$SKIP_BUILD" -eq 1 ]; then
  for command in xorriso unsquashfs; do
    if ! command -v "$command" >/dev/null 2>&1; then
      echo "required ISO validation command not found: $command" >&2
      exit 1
    fi
  done
  ISO_SQUASHFS="$WORK_DIR/iso-squashfs.img"
  SQUASHFS_VERIFY_DIR="$WORK_DIR/squashfs-verify"
  rm -f "$ISO_SQUASHFS"
  chmod -R u+rwX "$SQUASHFS_VERIFY_DIR" 2>/dev/null || true
  rm -rf "$SQUASHFS_VERIFY_DIR"
  xorriso -osirrox on -indev "$ISO_PATH" \
    -extract /LiveOS/squashfs.img "$ISO_SQUASHFS" >/dev/null 2>&1
  echo "--- validating every compressed block in the reused live SquashFS ---"
  if ! unsquashfs -processors 1 -no-xattrs -no-exit-code -f \
      -d "$SQUASHFS_VERIFY_DIR" "$ISO_SQUASHFS" >/dev/null; then
    echo "!!! existing ISO contains an unreadable/corrupt live SquashFS" >&2
    echo "!!! refusing to boot with --skip-build: $ISO_PATH" >&2
    chmod -R u+rwX "$SQUASHFS_VERIFY_DIR" 2>/dev/null || true
    rm -rf "$SQUASHFS_VERIFY_DIR"
    exit 1
  fi
  if ! validate_live_rootfs_homes "$SQUASHFS_VERIFY_DIR"; then
    chmod -R u+rwX "$SQUASHFS_VERIFY_DIR" 2>/dev/null || true
    rm -rf "$SQUASHFS_VERIFY_DIR"
    exit 1
  fi
  if ! audit_live_rootfs \
      "$ISO_PATH" "$SQUASHFS_VERIFY_DIR" "$WORK_DIR/reused-iso-security-audit.json"; then
    chmod -R u+rwX "$SQUASHFS_VERIFY_DIR" 2>/dev/null || true
    rm -rf "$SQUASHFS_VERIFY_DIR"
    exit 1
  fi
  chmod -R u+rwX "$SQUASHFS_VERIFY_DIR" 2>/dev/null || true
  rm -rf "$SQUASHFS_VERIFY_DIR"
  echo "--- validated reused live SquashFS by full extraction ---"
fi

echo "--- ISO ready: $ISO_PATH ($(du -h "$ISO_PATH" | cut -f1)) ---"

if [ "$BUILD_ONLY" -eq 1 ]; then
  echo "=== build-only complete; existing VM disk and UEFI state were not changed ==="
  exit 0
fi

# Check VM runtime requirements only after the ISO has passed its complete
# integrity validation, but still before touching the previous VM state. This
# lets --skip-build diagnose a corrupt cache even on a shell without KVM or a
# graphical session.
for command in qemu-img qemu-system-x86_64; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "required command not found: $command" >&2
    exit 1
  fi
done
if [ ! -r "$OVMF_CODE" ] || [ ! -r "$OVMF_VARS_TEMPLATE" ]; then
  echo "OVMF firmware files not found or unreadable:" >&2
  echo "  $OVMF_CODE" >&2
  echo "  $OVMF_VARS_TEMPLATE" >&2
  exit 1
fi
if [ ! -r /dev/kvm ] || [ ! -w /dev/kvm ]; then
  echo "KVM is unavailable to the current user (/dev/kvm is not readable/writable)." >&2
  echo "Check that the KVM module is loaded and log in again after joining the kvm group." >&2
  exit 1
fi
if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
  echo "No graphical display found (DISPLAY and WAYLAND_DISPLAY are unset)." >&2
  exit 1
fi

mkdir -p "$VM_DIR"
stop_previous_vm
echo "--- deleting previous VM disk and UEFI state ---"
rm -f "$DISK_IMG" "$OVMF_VARS_STANDARD" "$OVMF_VARS_SECURE" "$VM_PID_FILE" "$VM_MONITOR_SOCKET"

echo "--- creating install-target disk: $DISK_IMG ($DISK_SIZE) ---"
qemu-img create -f qcow2 "$DISK_IMG" "$DISK_SIZE"

if [ ! -f "$OVMF_VARS" ]; then
  echo "--- seeding OVMF UEFI vars ---"
  cp "$OVMF_VARS_TEMPLATE" "$OVMF_VARS"
fi

if [ "$SECURE_BOOT" -eq 1 ]; then
  echo "--- Secure Boot enabled (OVMF with Microsoft keys) ---"
else
  echo "--- Secure Boot disabled (standard OVMF UEFI) ---"
fi

QEMU_ARGS=(
  -name lyra-os-test
  -pidfile "$VM_PID_FILE"
  -monitor "unix:$VM_MONITOR_SOCKET,server=on,wait=off"
  -machine "$MACHINE"
  -cpu host
  -smp "$SMP"
  -m "$RAM_MB"
  -drive if=pflash,format=raw,readonly=on,file="$OVMF_CODE"
  -drive if=pflash,format=raw,file="$OVMF_VARS"
  -drive if=virtio,format=qcow2,file="$DISK_IMG"
  -device virtio-net-pci,netdev=net0
  -netdev user,id=net0
  -vga virtio
  -display gtk
)

if [ "$SECURE_BOOT" -eq 1 ]; then
  QEMU_ARGS+=(-global driver=cfi.pflash01,property=secure,value=on)
fi

echo "--- booting live ISO once; subsequent reboot uses the installed disk ---"
QEMU_ARGS+=(-cdrom "$ISO_PATH")
QEMU_ARGS+=(-boot order=c,once=d,menu=on)

echo "--- launching: qemu-system-x86_64 ${QEMU_ARGS[*]} ---"
if qemu-system-x86_64 "${QEMU_ARGS[@]}"; then
  QEMU_STATUS=0
else
  QEMU_STATUS=$?
fi
rm -f "$VM_PID_FILE"
echo "=== qemu exited with status $QEMU_STATUS ==="
exit "$QEMU_STATUS"
