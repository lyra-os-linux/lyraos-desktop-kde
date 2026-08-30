#!/usr/bin/env bash
# Build and qualify the unsigned Lyra OS Desktop Alpha 8 publication bundle.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
export LYRA_EXPECTED_VERSION="1.0-alpha.8"
export LYRA_RELEASE_LABEL="Desktop Alpha 8"
export LYRA_COMMAND_NAME="$0"
exec "$SCRIPT_DIR/build-desktop-alpha6.sh" "$@"
