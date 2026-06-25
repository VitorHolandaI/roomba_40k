#!/usr/bin/env bash
# Run pyquality on source directories only (excluding tests).
set -euo pipefail
trap 'rm -f _dummy_*.py' EXIT

paths=(roomba web media cli main.py)

for path in "${paths[@]}"; do
  if [ -e "$path" ]; then
    uv run python quick_python_analisys/pyquality.py "$path" -t B
  fi
done
