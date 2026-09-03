#!/usr/bin/env bash
# Validate and upload the qualified KDE Alpha 7 bundle to SourceForge.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
export LYRA_EXPECTED_VERSION="1.1-alpha.7"
export LYRA_RELEASE_LABEL="KDE Alpha 7"
export LYRA_RELEASE_SLUG="alpha7"
export LYRA_RELEASE_EDITION="kde"
export LYRA_RELEASE_LAYOUT="release-first"
export LYRA_VERIFY_DOWNLOAD="0"
export LYRA_REQUIRE_DECISION="0"
export LYRA_CHECK_OPEN_BLOCKERS="0"
export LYRA_COMMAND_NAME="$0"
exec "$SCRIPT_DIR/upload-desktop-alpha6-sourceforge.sh" "$@"
