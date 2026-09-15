#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if (($# == 0)); then
  printf '%s\n' 'Safe bootstrap requires an explicit command; nothing was changed.' \
    'Read docs/composition.md. Start with: ./bootstrap.sh compose' \
    'prepare creates a frozen candidate; deploy needs a reviewed diff digest.'
  exit 0
fi
export PYTHONDONTWRITEBYTECODE=1
exec python3 "$ROOT/scripts/pi-config.py" "$@"
