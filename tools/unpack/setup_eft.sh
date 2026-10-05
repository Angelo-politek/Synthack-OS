#!/usr/bin/env bash
# Clona e compila elektron-firmware-tool in third_party/ (git-ignored).
# Da eseguire in WSL o Linux:  bash tools/unpack/setup_eft.sh
#
# Il commit e' fissato: tutti usano la stessa versione del tool e un suo
# aggiornamento diventa una modifica esplicita (e revisionabile) di questo file.
set -euo pipefail

EFT_REPO="https://github.com/mischa85/elektron-firmware-tool"
EFT_COMMIT="a5bce9a6af644386d900924082993a805e812874"   # 2026-09-08

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="$ROOT/third_party/elektron-firmware-tool"

if [ ! -d "$DEST/.git" ]; then
    mkdir -p "$ROOT/third_party"
    git clone --quiet "$EFT_REPO" "$DEST"
fi

git -C "$DEST" fetch --quiet origin
git -C "$DEST" -c advice.detachedHead=false checkout --quiet "$EFT_COMMIT"
make -C "$DEST" --no-print-directory

echo "elektron-firmware-tool pronto @ ${EFT_COMMIT:0:7}: $DEST/elektron-firmware-tool"
