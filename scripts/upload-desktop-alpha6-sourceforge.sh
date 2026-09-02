#!/usr/bin/env bash
# Validate and publish the qualified Desktop Alpha 6 bundle to SourceForge.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
WORK_DIR="${LYRA_TEST_WORK_DIR:-/var/tmp/lyraos-desktop-test-$(id -u)}"
ARTIFACT_DIR="$WORK_DIR/iso"
EXPECTED_VERSION="${LYRA_EXPECTED_VERSION:-1.0-alpha.6}"
RELEASE_LABEL="${LYRA_RELEASE_LABEL:-Desktop Alpha 6}"
RELEASE_SLUG="${LYRA_RELEASE_SLUG:-alpha6}"
COMMAND_NAME="${LYRA_COMMAND_NAME:-$0}"
RELEASE_SERIES="$("$REPO_ROOT/scripts/release.py" field product_version)"
REMOTE="rodrigobritosoa@frs.sourceforge.net:/home/frs/project/lyra/releases/$RELEASE_SERIES/desktop/$RELEASE_SLUG/"
DOWNLOAD_URL="https://downloads.sourceforge.net/project/lyra/releases/$RELEASE_SERIES/desktop/$RELEASE_SLUG"
CHECK_ONLY=0
DECISION_FILE=""

usage() {
  echo "Uso: $COMMAND_NAME [--check-only] --decision-file ARQUIVO.json" >&2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check-only) CHECK_ONLY=1 ;;
    --decision-file) shift; DECISION_FILE="${1:-}" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERRO: opção desconhecida: $1" >&2; usage; exit 2 ;;
  esac
  shift
done
[ -n "$DECISION_FILE" ] || {
  echo "ERRO: registro formal de GO ausente." >&2
  usage
  exit 2
}
DECISION_FILE="$(readlink -f "$DECISION_FILE")"
[ -s "$DECISION_FILE" ] || {
  echo "ERRO: registro de GO ausente: $DECISION_FILE" >&2
  exit 1
}

cd "$REPO_ROOT"
VERSION="$(./scripts/release.py field version_id)"
ISO_NAME="$(./scripts/release.py field iso_filename)"
[ "$VERSION" = "$EXPECTED_VERSION" ] || {
  echo "ERRO: release.toml não aponta para $EXPECTED_VERSION." >&2
  exit 1
}
PREFIX="${ISO_NAME%.iso}"
FILES=(
  README.md
  "$PREFIX.cdx.json"
  "$PREFIX.evidence.json"
  "$PREFIX.iso"
  "$PREFIX.iso.manifest.json"
  "$PREFIX.iso.sha256"
  "$PREFIX.packages"
  "$PREFIX.report"
  "$PREFIX.spdx.json"
  "$PREFIX.verified"
)
for file in "${FILES[@]}"; do
  [ -s "$ARTIFACT_DIR/$file" ] || {
    echo "ERRO: artefato ausente: $ARTIFACT_DIR/$file" >&2
    exit 1
  }
done

cd "$ARTIFACT_DIR"
sha256sum -c "$PREFIX.iso.sha256"
# Baseline: obs-repositories, live-session, installer, first-boot,
# uefi-secure-boot, rollback and hardware-matrix. Stage-aware additions are
# read from the same policy used to create the evidence manifest.
mapfile -t REQUIRED_EVIDENCE < <("$REPO_ROOT/scripts/image-build.py" required-test-results)
python3 - "$PREFIX.evidence.json" "$DECISION_FILE" "$PREFIX" "${REQUIRED_EVIDENCE[@]}" <<'PY'
import datetime
import json
import pathlib
import re
import sys

evidence = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
decision = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
prefix = sys.argv[3]
required = set(sys.argv[4:])
if not required:
    raise SystemExit("ERRO: política não informou evidências obrigatórias")
if evidence.get("source", {}).get("dirty") is not False:
    raise SystemExit("ERRO: manifesto final originado de árvore suja")
if set(evidence.get("test_results", {})) != required:
    raise SystemExit("ERRO: manifesto final não contém todas as evidências")
if any(item.get("status") != "passed" for item in evidence["test_results"].values()):
    raise SystemExit("ERRO: há evidência obrigatória não aprovada")
iso = evidence.get("artifacts", {}).get("iso", {})
expected = {
    "decision": "GO",
    "source_commit": evidence.get("source", {}).get("commit"),
    "iso_filename": iso.get("filename"),
    "iso_sha256": iso.get("sha256"),
    "evidence_manifest": f"{prefix}.evidence.json",
}
if decision.get("schema") != 1 or any(decision.get(key) != value for key, value in expected.items()):
    raise SystemExit("ERRO: registro de GO não corresponde exatamente ao candidato")
if not isinstance(decision.get("coordinator"), str) or not decision["coordinator"].strip():
    raise SystemExit("ERRO: registro de GO sem coordenador")
if not re.fullmatch(r"[0-9a-f]{40}", decision.get("source_commit", "")):
    raise SystemExit("ERRO: commit inválido no registro de GO")
if not re.fullmatch(r"[0-9a-f]{64}", decision.get("iso_sha256", "")):
    raise SystemExit("ERRO: SHA-256 inválido no registro de GO")
try:
    decided_at = datetime.datetime.fromisoformat(
        decision.get("decided_at_utc", "").replace("Z", "+00:00")
    )
except ValueError as error:
    raise SystemExit("ERRO: horário UTC inválido no registro de GO") from error
if decided_at.utcoffset() != datetime.timedelta(0):
    raise SystemExit("ERRO: decisão deve registrar horário UTC")
for field in ("accepted_p2_p3", "residual_risks"):
    values = decision.get(field)
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise SystemExit(f"ERRO: registro de GO sem lista válida: {field}")
PY

OPEN_BLOCKERS="$(gh issue list --state open --label desktop --limit 200 \
  --json number,title --jq '.[] | select(.title | test("\\[P[01]\\]"; "i")) | "#\\(.number) \\(.title)"')"
[ -z "$OPEN_BLOCKERS" ] || {
  echo "ERRO: há P0/P1 Desktop aberta; publicação bloqueada:" >&2
  echo "$OPEN_BLOCKERS" >&2
  exit 1
}

install -m 0644 "$DECISION_FILE" "$ARTIFACT_DIR/$PREFIX.release-decision.json"
FILES+=("$PREFIX.release-decision.json")
if [ "$CHECK_ONLY" -eq 1 ]; then
  echo "Bundle $RELEASE_LABEL válido; nenhum arquivo foi enviado."
  exit 0
fi

KNOWN_HOSTS="$REPO_ROOT/kiwi/.kiwi/sourceforge-known-hosts"
mkdir -p "$(dirname "$KNOWN_HOSTS")"
printf '%s\n' \
  'frs.sourceforge.net ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOQD35Ujalhh+JJkPvMckDlhu4dS7WH6NsOJ15iGCJLC' \
  >"$KNOWN_HOSTS"
chmod 0600 "$KNOWN_HOSTS"
rsync -avP --partial \
  -e "ssh -o UserKnownHostsFile=$KNOWN_HOSTS -o StrictHostKeyChecking=yes" \
  "${FILES[@]}" "$REMOTE"

DOWNLOAD_DIR="$(mktemp -d "/tmp/lyra-desktop-$RELEASE_SLUG-download.XXXXXX")"
trap 'rm -rf -- "$DOWNLOAD_DIR"' EXIT
curl --fail --location --retry 5 \
  --output "$DOWNLOAD_DIR/$PREFIX.iso.sha256" \
  "$DOWNLOAD_URL/$PREFIX.iso.sha256"
curl --fail --location --retry 5 \
  --output "$DOWNLOAD_DIR/$PREFIX.iso" \
  "$DOWNLOAD_URL/$PREFIX.iso"
(cd "$DOWNLOAD_DIR" && sha256sum -c "$PREFIX.iso.sha256")
echo "Publicação $RELEASE_LABEL verificada após novo download."
