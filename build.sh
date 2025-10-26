#!/usr/bin/env bash
set -euo pipefail

APP_NAME="${APP_NAME:-TrackNote}"
VENV=".venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

# Require Python 3.13.x
$PYTHON_BIN - <<'PYVER'
import sys
major, minor = sys.version_info[:2]
assert major == 3 and minor == 13, f"Python 3.13.x required, got {sys.version}"
print(f"Using Python {sys.version.split()[0]}")
PYVER

$PYTHON_BIN -m venv "$VENV"
source "$VENV/bin/activate"
python -m pip install --upgrade pip wheel
python -m pip install -r requirements.txt

rm -rf build dist TrackNote.spec
VERSION="$(tr -d '\r\n' < VERSION)"

# PyInstaller options (each item is a separate array element)
OPTS=(
  --noconfirm
  --clean
  --onedir
  --windowed
  --name "$APP_NAME"
  --add-data "config_template.json:."
  --add-data "VERSION:."
)

# macOS target arch: arm64 (avoid universal/fat)
if [[ "$(uname -s)" == "Darwin" ]]; then
  OPTS+=( --target-arch "${TARGET_ARCH:-arm64}" )
fi

pyinstaller "${OPTS[@]}" app.py
echo "Built dist/$APP_NAME"
