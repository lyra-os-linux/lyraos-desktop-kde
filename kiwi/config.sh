#!/bin/bash
#
# Lyra OS - Odisseia (desktop)
# KIWI config.sh: runs chrooted into the image after packages are installed.

set -euo pipefail

test -f /.kconfig && . /.kconfig
test -f /.profile && . /.profile

echo "Configuring image: [$kiwi_iname]..."

RELEASE_METADATA=/usr/lib/lyra-os/release
if [ ! -r "$RELEASE_METADATA" ]; then
    echo "Missing generated release metadata: $RELEASE_METADATA" >&2
    exit 1
fi
# shellcheck source=/dev/null
. "$RELEASE_METADATA"

if [ "$kiwi_iversion" != "$LYRA_VERSION_ID" ]; then
    echo "KIWI version $kiwi_iversion does not match $LYRA_VERSION_ID" >&2
    exit 1
fi

BUILD_SOURCE_METADATA=/usr/lib/lyra-os/build-source
if [ -r "$BUILD_SOURCE_METADATA" ]; then
    # OBS receives this generated file with the exported KIWI description.
    # Local builds keep using the environment fallbacks below.
    # shellcheck source=/dev/null
    . "$BUILD_SOURCE_METADATA"
fi

LYRA_BUILD_SOURCE_COMMIT="${LYRA_BUILD_SOURCE_COMMIT:-unknown}"
LYRA_BUILD_SOURCE_EPOCH="${LYRA_BUILD_SOURCE_EPOCH:-unknown}"
LYRA_IMAGE_BUILT_AT="${LYRA_IMAGE_BUILT_AT:-unknown}"
LYRA_BUILD_SOURCE_DIRTY="${LYRA_BUILD_SOURCE_DIRTY:-unknown}"
if ! [[ "$LYRA_BUILD_SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]]; then
    LYRA_BUILD_SOURCE_COMMIT=unknown
fi
if [[ "$LYRA_BUILD_SOURCE_DIRTY" != 0 && "$LYRA_BUILD_SOURCE_DIRTY" != 1 ]]; then
    LYRA_BUILD_SOURCE_DIRTY=unknown
fi
if ! [[ "$LYRA_BUILD_SOURCE_EPOCH" =~ ^[0-9]+$ ]]; then
    LYRA_BUILD_SOURCE_EPOCH=unknown
fi
cat > /usr/lib/lyra-os/build-info <<EOF
# Generated during the KIWI build; do not edit.
LYRA_SOURCE_COMMIT="$LYRA_BUILD_SOURCE_COMMIT"
LYRA_SOURCE_DIRTY="$LYRA_BUILD_SOURCE_DIRTY"
LYRA_SOURCE_EPOCH="$LYRA_BUILD_SOURCE_EPOCH"
LYRA_IMAGE_BUILT_AT="$LYRA_IMAGE_BUILT_AT"
EOF

# Leap's filesystem package does not own /etc/mtab, and a KIWI-built root can
# therefore leave the path absent.  Snapper still opens /etc/mtab while
# detecting the filesystem for `create-config`; point it at the kernel's live
# mount table, as on a normally installed system.  The relative target keeps
# the link valid both in the live image and in the installer's target root.
ln -sfn ../proc/self/mounts /etc/mtab

# Networking / firewall - Leap defaults, enabled explicitly for the live boot
suseInsertService NetworkManager
suseInsertService firewalld
suseInsertService lyra-live-autologin-retry

# Plasma display manager
baseUpdateSysConfig /etc/sysconfig/displaymanager DISPLAYMANAGER sddm
# Leap's display-manager-legacy.service reads DISPLAYMANAGER above. Enabling
# sddm.service directly conflicts with the distribution-managed alias.

# bluez is present but its service isn't enabled by default - without
# this, Bluetooth stays off even with the adapter and driver both
# working (confirmed on a real installed image: hardware/kernel side
# was fine, bluetooth.service just didn't exist as an enabled unit).
suseInsertService bluetooth

# Live-session autologin as liveuser. This is a live-boot convenience
# only; the installed system's login/account model is set up by the
# Lyra Installer (root disabled, sudo user), not here.
# SDDM's PAM account check rejects the locked password created by KIWI's
# user declaration even for autologin, so leave this live-only account with
# an empty password. The installer never copies the live account.
passwd -d liveuser
install -Dm0644 /dev/null /usr/lib/lyra-os/liveuser-passwordless
mkdir -p /etc/sddm.conf.d
cat > /etc/sddm.conf.d/10-lyra-live.conf <<EOF
[Autologin]
User=liveuser
Session=plasmawayland.desktop
Relogin=false
EOF
cat > /etc/sddm.conf <<EOF
[Autologin]
User=liveuser
Session=plasmawayland.desktop
Relogin=false

[Theme]
Current=breeze
EOF

# The distribution's common-auth intentionally rejects empty passwords. The
# live account is the sole exception: allow its deliberately empty password
# at SDDM, while leaving every other PAM consumer on the Leap defaults.
# Also omit pam_nologin from the live autologin service: SDDM can attempt its
# one-shot login while systemd is still completing the boot transition.
# All three overrides are removed from the installed target by the installer.
mkdir -p /etc/pam.d
sed 's/pam_unix\.so[[:space:]]\+try_first_pass/pam_unix.so nullok try_first_pass/' \
    /usr/lib/pam.d/common-auth > /etc/pam.d/common-auth-lyra-live
sed 's/substack[[:space:]]\+common-auth/substack       common-auth-lyra-live/' \
    /usr/lib/pam.d/sddm > /etc/pam.d/sddm
sed '/pam_nologin\.so/d' /usr/lib/pam.d/sddm-autologin \
    > /etc/pam.d/sddm-autologin
chmod 0644 \
    /etc/pam.d/common-auth-lyra-live \
    /etc/pam.d/sddm \
    /etc/pam.d/sddm-autologin

# Passwordless sudo for the live session only. liveuser's password is
# locked ("!" in config.xml), so without this it cannot authenticate to
# sudo at all - this is what lets a live-session terminal actually run
# admin commands (e.g. cfdisk to inspect a disk before installing). The
# Rust installer removes this file during deployment (LIVE_ONLY_ARTIFACTS
# in deploy.rs); it must never reach an installed system, which gets its
# own sudo user with a real password instead.
cat > /etc/sudoers.d/00-liveuser-nopasswd <<EOF
liveuser ALL=(ALL) NOPASSWD: ALL
EOF
chmod 0440 /etc/sudoers.d/00-liveuser-nopasswd
visudo -cf /etc/sudoers.d/00-liveuser-nopasswd

# zram-generator activates its own systemd generator at boot from
# /etc/systemd/zram-generator.conf - no service to enable here.

# Flathub is shipped as a versioned remote definition in root/. Keeping
# its URL and signing key in the source prevents a network fetch during
# the build.
if [ ! -r /etc/flatpak/remotes.d/flathub.flatpakrepo ]; then
    echo "Missing versioned Flathub remote definition" >&2
    exit 1
fi

# Fish plugin set, resolved once here instead of on every machine's first
# terminal. Fisher has no RPM upstream and pulls its plugins from GitHub,
# so doing this at first login would mean every new installation hitting
# the network - and an installation done offline would simply never get
# the plugins. Seeding /etc/skel moves that cost to this build: useradd
# -m copies it into every account the installer creates afterwards, and
# conf.d/lyra-fish-bootstrap.fish then finds the marker and stays quiet.
#
# This is the one step in the build that needs the network. Lyra builds
# its images locally (image-build.toml pins OBS to "packages-only"), so
# that is available here; the failure is fatal on purpose, because an ISO
# that silently ships without the plugins is a regression nobody notices
# until it is installed.
LYRA_FISH_SKEL=/etc/skel
if ! HOME="$LYRA_FISH_SKEL" \
     XDG_CONFIG_HOME="$LYRA_FISH_SKEL/.config" \
     XDG_STATE_HOME="$LYRA_FISH_SKEL/.local/state" \
     LYRA_FISH_SEED=1 \
     fish --command fish_setup_lyra_plugins; then
    echo "Failed to seed the Lyra fish plugin set into $LYRA_FISH_SKEL" >&2
    exit 1
fi

# Never carry a build-time z/zoxide data path into accounts copied from
# /etc/skel. The universal-variable file is loaded before normal Fish
# config snippets and can otherwise retain /root from the privileged
# image build, causing a permission error on every new terminal.
LYRA_FISH_VARIABLES="$LYRA_FISH_SKEL/.config/fish/fish_variables"
if [ -f "$LYRA_FISH_VARIABLES" ]; then
    sed -i \
        -e '\|SETUVAR Z_DATA:/root/|d' \
        -e '\|SETUVAR Z_DATA_DIR:/root/|d' \
        "$LYRA_FISH_VARIABLES"
fi

# fish_plugins is Fisher's manifest; fish_prompt.fish only exists if hydro
# actually activated. Checking both turns a half-finished seed into a
# build failure rather than a surprise on the installed system.
for lyra_fish_artifact in fish_plugins functions/fish_prompt.fish; do
    if [ ! -e "$LYRA_FISH_SKEL/.config/fish/$lyra_fish_artifact" ]; then
        echo "Incomplete fish seed: missing $lyra_fish_artifact" >&2
        exit 1
    fi
done

# liveuser's home was created by KIWI from the pre-seed /etc/skel (its
# useradd -m runs before this script), so the live session needs an
# explicit copy to match what an installed account gets.
if [ ! -d /home/liveuser ]; then
    echo "liveuser home is missing; cannot seed the live session" >&2
    exit 1
fi
install -d -m 0755 /home/liveuser/.config /home/liveuser/.local/state
cp -a "$LYRA_FISH_SKEL/.config/fish" /home/liveuser/.config/
cp -a "$LYRA_FISH_SKEL/.local/state/lyra-fish-productivity" \
    /home/liveuser/.local/state/
chown -R liveuser:"$(id -gn liveuser)" /home/liveuser/.config /home/liveuser/.local

# Product identity (PROMPT-LYRA-OS.md: "Lyra OS", not "Lyra Linux" or
# "Lyra Enterprise Linux" - those are historical/discontinued names).
# ID_LIKE keeps openSUSE/SUSE tooling that branches on it (package
# managers, some installers) working correctly; everything user-visible
# says Lyra OS. Overwrites whatever openSUSE-release just installed.
#
# Deliberately no HOME_URL/BUG_REPORT_URL/LOGO here: there's no
# confirmed project website, issue tracker, or a matching icon name
# shipped by lyra-os-icons to point them at - adding guessed
# URLs/icon names felt worse than leaving these optional fields out.
cat > /etc/os-release <<EOF
NAME="Lyra OS"
PRETTY_NAME="$LYRA_PRETTY_NAME"
ID=lyra-os
ID_LIKE="opensuse suse"
VERSION="$LYRA_VERSION_NAME"
VERSION_ID="$LYRA_VERSION_ID"
VERSION_CODENAME="$LYRA_CODENAME_ID"
BUILD_ID="$LYRA_VERSION_ID"
IMAGE_ID="$LYRA_IMAGE_NAME"
IMAGE_VERSION="$LYRA_VERSION_ID"
CPE_NAME="cpe:/o:rodrigosbrito:lyra_os:$LYRA_VERSION_ID"
EOF

exit 0
