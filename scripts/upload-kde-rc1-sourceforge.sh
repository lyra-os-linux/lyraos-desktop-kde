#!/usr/bin/env bash
# Validate and publish the signed KDE 16.1 RC 1 bundle to SourceForge.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
export LYRA_EXPECTED_VERSION="16.1-rc.1"
export LYRA_RELEASE_LABEL="KDE RC 1"
export LYRA_RELEASE_SLUG="rc1"
export LYRA_RELEASE_EDITION="kde"
export LYRA_RELEASE_LAYOUT="release-first"
export LYRA_ISSUE_REPOSITORY="lyra-os-linux/lyraos-desktop-kde"
export LYRA_BLOCKER_LABEL=""
export LYRA_COMMAND_NAME="$0"
exec "$SCRIPT_DIR/upload-desktop-alpha6-sourceforge.sh" "$@"
