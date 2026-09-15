#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
AGENT_DIR="${PI_CODING_AGENT_DIR:-$HOME/.pi/agent}"

if ! command -v pi >/dev/null 2>&1; then
  echo "pi is not installed or not on PATH." >&2
  echo "Install the Pi CLI first, then rerun ./bootstrap.sh." >&2
  exit 1
fi

mkdir -p "$AGENT_DIR" "$AGENT_DIR/extensions" "$AGENT_DIR/npm"

link_path() {
  local source=$1
  local destination=$2
  rm -rf "$destination"
  mkdir -p "$(dirname -- "$destination")"
  ln -s "$source" "$destination"
}

# Install pinned packages first. pi writes package entries to settings; the
# repository-owned symlinks are installed afterward so the backup is the
# single source of truth.
while IFS= read -r package || [[ -n "$package" ]]; do
  [[ -z "$package" || "$package" == \#* ]] && continue
  pi install "$package"
done <"$ROOT/config/packages.txt"

link_path "$ROOT/config/settings.json" "$AGENT_DIR/settings.json"
link_path "$ROOT/config/models.json" "$AGENT_DIR/models.json"
link_path "$ROOT/config/AGENTS.md" "$AGENT_DIR/AGENTS.md"
link_path "$ROOT/config/pi-vcc-config.json" "$AGENT_DIR/pi-vcc-config.json"
link_path "$ROOT/config/tasks-config.json" "$AGENT_DIR/tasks-config.json"
link_path "$ROOT/config/npm-package.json" "$AGENT_DIR/npm/package.json"
link_path "$ROOT/config/npm-package-lock.json" "$AGENT_DIR/npm/package-lock.json"
THEME_REPO="$HOME/git/OpenCodeHyperTermTheme/pi/themes"
if [[ -d "$THEME_REPO" ]]; then
  link_path "$THEME_REPO" "$AGENT_DIR/themes"
else
  echo "OpenCodeHyperTermTheme not found; using pi-config theme snapshot." >&2
  link_path "$ROOT/config/themes" "$AGENT_DIR/themes"
fi
link_path "$ROOT/config/skills" "$AGENT_DIR/skills"
link_path "$ROOT/extensions/web-search" "$AGENT_DIR/extensions/web-search"
link_path "$ROOT/extensions/pi-splash.ts" "$AGENT_DIR/extensions/pi-splash.ts"
link_path "$ROOT/extensions/pi-tool-display/config.json" "$AGENT_DIR/extensions/pi-tool-display/config.json"

cat <<'NOTICE'

Pi configuration restored without credentials or logs.

Required external setup may include:
  - VLLM_API_KEY environment variable
  - SearXNG at http://127.0.0.1:8080 for web-search
  - optional agent-voice and SIGINT/dotfiles repositories
  - optional Herdr integration

Run /reload inside Pi after bootstrap.
NOTICE
