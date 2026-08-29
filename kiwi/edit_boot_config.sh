#!/bin/bash
# KIWI calls this hook outside the chroot, from the final image root, after it
# has generated the live ISO bootloader configuration and before packing the
# squashfs. Its first argument names the ISO media tree; the second is the boot
# partition id. The live /boot layout remains untouched here.

set -euo pipefail

case "${1:-}" in
  iso:*) ;;
  *) echo "Unexpected KIWI boot filesystem: ${1:-missing}" >&2; exit 1 ;;
esac
if [ "${2:-}" != "1" ]; then
  echo "Unexpected KIWI boot partition id: ${2:-missing}" >&2
  exit 1
fi

GRUB_DEFAULTS=etc/default/grub
if [ ! -f "$GRUB_DEFAULTS" ]; then
  echo "Missing GRUB defaults: /$GRUB_DEFAULTS" >&2
  exit 1
fi

# The installed system uses GRUB's default appearance. Remove theme paths
# inherited from a desktop-specific package or KIWI's live boot layout.
sed -i '/^[[:space:]]*GRUB_THEME=/d' "$GRUB_DEFAULTS"
