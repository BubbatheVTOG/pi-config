#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
AGENT_DIR="${PI_CODING_AGENT_DIR:-$HOME/.pi/agent}"

if ! command -v pi >/dev/null 2>&1; then
  echo "pi is not installed or not on PATH." >&2
  echo "Install the Pi CLI first, then rerun ./bootstrap.sh." >&2
  exit 1
fi

mkdir -p "$AGENT_DIR" "$AGENT_DIR/extensions" "$AGENT_DIR/skills" "$AGENT_DIR/themes"

# Install pinned packages first. pi writes package entries to settings; the
# saved settings are copied afterward so the backup remains authoritative.
while IFS= read -r package || [[ -n "$package" ]]; do
  [[ -z "$package" || "$package" == \#* ]] && continue
  pi install "$package"
done < "$ROOT/config/packages.txt"

cp "$ROOT/config/settings.json" "$AGENT_DIR/settings.json"
cp "$ROOT/config/models.json" "$AGENT_DIR/models.json"
cp "$ROOT/config/AGENTS.md" "$AGENT_DIR/AGENTS.md"
cp "$ROOT/config/pi-vcc-config.json" "$AGENT_DIR/pi-vcc-config.json"
cp "$ROOT/config/tasks-config.json" "$AGENT_DIR/tasks-config.json"

rm -rf "$AGENT_DIR/themes"/*
cp -a "$ROOT/config/themes/." "$AGENT_DIR/themes/"

rm -rf "$AGENT_DIR/skills/plan" "$AGENT_DIR/skills/self-optimize"
mkdir -p "$AGENT_DIR/skills/plan" "$AGENT_DIR/skills/self-optimize"
cp "$ROOT/config/skills/plan/SKILL.md" "$AGENT_DIR/skills/plan/SKILL.md"
cp "$ROOT/config/skills/self-optimize/SKILL.md" "$AGENT_DIR/skills/self-optimize/SKILL.md"

rm -rf "$AGENT_DIR/extensions/web-search"
cp -a "$ROOT/extensions/web-search" "$AGENT_DIR/extensions/web-search"
cp "$ROOT/extensions/pi-splash.ts" "$AGENT_DIR/extensions/pi-splash.ts"

mkdir -p "$AGENT_DIR/extensions/pi-tool-display"
cp "$ROOT/extensions/pi-tool-display/config.json" "$AGENT_DIR/extensions/pi-tool-display/config.json"

cat <<'NOTICE'

Pi configuration restored without credentials or logs.

Required external setup may include:
  - VLLM_API_KEY environment variable
  - SearXNG at http://127.0.0.1:8080 for web-search
  - optional agent-voice and SIGINT/dotfiles repositories
  - optional Herdr integration

Run /reload inside Pi after bootstrap.
NOTICE
