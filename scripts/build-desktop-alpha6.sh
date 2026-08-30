#!/usr/bin/env bash
# Build and qualify the unsigned Lyra OS Desktop Alpha 6 publication bundle.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
WORK_DIR="${LYRA_TEST_WORK_DIR:-/var/tmp/lyraos-desktop-test-$(id -u)}"
BUILD_DIR="$WORK_DIR/build"
ARTIFACT_DIR="$WORK_DIR/iso"
EVIDENCE_DIR=""
ARTIFACTS_ONLY=0
EXPECTED_VERSION="${LYRA_EXPECTED_VERSION:-1.0-alpha.6}"
RELEASE_LABEL="${LYRA_RELEASE_LABEL:-Desktop Alpha 6}"
COMMAND_NAME="${LYRA_COMMAND_NAME:-$0}"

usage() {
  cat <<EOF
Uso: $COMMAND_NAME [--artifacts-only] [--evidence-dir DIRETÓRIO]

Sem opções, valida o OBS e constrói uma candidata limpa usando o RPM
publicado do instalador (o Welcome já vem sempre do RPM publicado).
--artifacts-only reutiliza a ISO atual.
Quando --evidence-dir é informado, o manifesto final exige todas as evidências
aplicáveis ao estágio declarado em release.toml.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --artifacts-only) ARTIFACTS_ONLY=1 ;;
    --evidence-dir) shift; EVIDENCE_DIR="${1:-}" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERRO: opção desconhecida: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
if [ -n "$EVIDENCE_DIR" ]; then
  EVIDENCE_DIR="$(readlink -f "$EVIDENCE_DIR")"
fi

cd "$REPO_ROOT"
./scripts/release.py check
./scripts/image-build.py validate

VERSION="$(./scripts/release.py field version_id)"
ISO_NAME="$(./scripts/release.py field iso_filename)"
PREFIX="${ISO_NAME%.iso}"
[ "$VERSION" = "$EXPECTED_VERSION" ] || {
  echo "ERRO: release.toml não aponta para $EXPECTED_VERSION." >&2
  exit 1
}
[ -z "$(git status --porcelain --untracked-files=normal)" ] || {
  echo "ERRO: a candidata exige uma árvore de código limpa." >&2
  exit 1
}

mkdir -p "$WORK_DIR/evidence"
./scripts/obs-release.py health \
  --output "$WORK_DIR/evidence/obs-repositories-result.json"

if [ "$ARTIFACTS_ONLY" -eq 0 ]; then
  sudo -v
  ./kiwi/test/build-and-run-vm.sh --build-only \
    --published-installer
fi

ISO="$ARTIFACT_DIR/$ISO_NAME"
BUILD_MANIFEST="$ISO.manifest.json"
PACKAGES_SOURCE="$BUILD_DIR/$PREFIX.packages"
VERIFIED_SOURCE="$BUILD_DIR/$PREFIX.verified"
for file in "$ISO" "$BUILD_MANIFEST" "$PACKAGES_SOURCE" "$VERIFIED_SOURCE"; do
  [ -s "$file" ] || { echo "ERRO: artefato ausente: $file" >&2; exit 1; }
done

COMMIT="$(python3 - "$BUILD_MANIFEST" "$EXPECTED_VERSION" <<'PY'
import json
import pathlib
import re
import sys

document = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
expected_version = sys.argv[2]
commit = document.get("source", {}).get("commit", "")
if document.get("version") != expected_version:
    raise SystemExit("ERRO: versão inesperada no manifesto do build")
if document.get("source", {}).get("dirty") is not False:
    raise SystemExit("ERRO: o build não veio de uma árvore limpa")
if not re.fullmatch(r"[0-9a-f]{40}", commit):
    raise SystemExit("ERRO: commit inválido no manifesto do build")
print(commit)
PY
)"
HEAD_COMMIT="$(git rev-parse HEAD)"
[ "$COMMIT" = "$HEAD_COMMIT" ] || {
  echo "ERRO: a ISO veio de $COMMIT, mas o HEAD atual é $HEAD_COMMIT." >&2
  exit 1
}
[ -z "$(git status --porcelain --untracked-files=normal)" ] || {
  echo "ERRO: o bundle final exige uma árvore de código limpa." >&2
  exit 1
}

install -m 0644 "$PACKAGES_SOURCE" "$ARTIFACT_DIR/$PREFIX.packages"
install -m 0644 "$VERIFIED_SOURCE" "$ARTIFACT_DIR/$PREFIX.verified"
./scripts/release-artifacts.py generate \
  --iso "$ISO" \
  --packages "$ARTIFACT_DIR/$PREFIX.packages" \
  --verified "$ARTIFACT_DIR/$PREFIX.verified" \
  --output-dir "$ARTIFACT_DIR" \
  --commit "$COMMIT"
install -m 0644 \
  "$REPO_ROOT/docs/releases/lyra-os-desktop-$EXPECTED_VERSION.md" \
  "$ARTIFACT_DIR/README.md"
(cd "$ARTIFACT_DIR" && sha256sum -c "$PREFIX.iso.sha256")

if [ -n "$EVIDENCE_DIR" ]; then
  # The stage-aware policy always includes the established baseline:
  # obs-repositories, live-session, installer, first-boot, uefi-secure-boot,
  # rollback and hardware-matrix. Alpha 8+ additions come from the same
  # versioned policy rather than a second shell list that could drift.
  TEST_ARGS=()
  while IFS= read -r name; do
    file="$EVIDENCE_DIR/$name-result.json"
    [ -s "$file" ] || { echo "ERRO: evidência ausente: $file" >&2; exit 1; }
    TEST_ARGS+=(--test-result "$name=$file")
  done < <(./scripts/image-build.py required-test-results)
  ./scripts/image-build.py artifact-manifest "$ARTIFACT_DIR" \
    --output "$ARTIFACT_DIR/$PREFIX.evidence.json" "${TEST_ARGS[@]}"
  echo "Bundle $RELEASE_LABEL qualificado em: $ARTIFACT_DIR"
else
  echo "Artefatos da candidata prontos em: $ARTIFACT_DIR"
  echo "Execute novamente com --artifacts-only --evidence-dir após concluir o gate."
fi

echo "$RELEASE_LABEL usa SHA-256 sem assinatura GPG destacada conforme a ADR 0005."
