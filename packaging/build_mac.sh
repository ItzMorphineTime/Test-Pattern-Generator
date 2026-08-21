#!/usr/bin/env bash
# Build the macOS single-file executable (and .app bundle).
# Run this ON macOS (PyInstaller cannot cross-compile from Windows/Linux).
# Usage from the repo root:  bash packaging/build_mac.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Installing build dependencies..."
python3 -m pip install --upgrade pyinstaller
python3 -m pip install -e .

echo "Running PyInstaller..."
python3 -m PyInstaller packaging/projgen.spec --clean --noconfirm

BIN="$ROOT/dist/ProjectionTestPatternGenerator"
APP="$ROOT/dist/ProjectionTestPatternGenerator.app"
if [[ -f "$BIN" ]]; then
  echo "Built single-file binary: $BIN ($(du -h "$BIN" | cut -f1))"
fi
if [[ -d "$APP" ]]; then
  echo "Built app bundle:        $APP"
  echo "Tip: to run an unsigned app, right-click it and choose Open the first time,"
  echo "     or clear the quarantine flag:  xattr -dr com.apple.quarantine \"$APP\""
fi
