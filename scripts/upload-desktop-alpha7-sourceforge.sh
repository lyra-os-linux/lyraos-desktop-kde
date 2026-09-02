#!/usr/bin/env bash
# Validate and publish the qualified Desktop Alpha 7 bundle to SourceForge.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
export LYRA_EXPECTED_VERSION="1.1-alpha.7"
export LYRA_RELEASE_LABEL="Desktop Alpha 7"
export LYRA_RELEASE_SLUG="alpha7"
export LYRA_COMMAND_NAME="$0"
exec "$SCRIPT_DIR/upload-desktop-alpha6-sourceforge.sh" "$@"
