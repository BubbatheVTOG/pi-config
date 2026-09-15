#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

command -v jq >/dev/null || { echo "missing jq" >&2; exit 1; }

jq empty config/settings.json
jq empty config/models.json
jq empty config/pi-vcc-config.json
jq empty config/tasks-config.json
jq empty extensions/pi-tool-display/config.json

if find . -type f \( \
  -name '*.log' -o -name 'auth.json' -o -name '.env' -o -name '.env.*' \
  -o -name '*.key' -o -name '*.pem' -o -name '*credentials*' -o -name '*token*' \
\) -not -path './.git/*' -print -quit | grep -q .; then
  echo "forbidden log/credential-like file found" >&2
  exit 1
fi

patterns=(
  'AKIA[0-9A-Z]{16}'
  '-----BEGIN (RSA|OPENSSH|EC|DSA) PRIVATE KEY-----'
  'api[_-]?key[[:space:]]*[:=][[:space:]]*[A-Za-z0-9_-]{20,}'
  '(token|secret|password)[[:space:]]*[:=][[:space:]]*[A-Za-z0-9_-]{20,}'
)
for pattern in "${patterns[@]}"; do
  if rg -n --hidden --glob '!.git/**' -- "$pattern" .; then
    echo "possible credential pattern found" >&2
    exit 1
  fi
done

if ! rg -q 'VLLM_API_KEY' config/models.json; then
  echo "models.json no longer uses the expected environment-variable credential reference" >&2
  exit 1
fi

if [[ -n "${PI_CODING_AGENT_ROOT:-}" && -f extensions/web-search/tests/renderers.test.mjs ]] && command -v node >/dev/null; then
  PI_CODING_AGENT_ROOT="$PI_CODING_AGENT_ROOT" node extensions/web-search/tests/renderers.test.mjs
else
  echo "web-search renderer harness skipped (set PI_CODING_AGENT_ROOT to run it)"
fi

echo "pi-config verification passed: no logs, credentials, or forbidden runtime state found"
