#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1
: "${PI_CODING_AGENT_ROOT:?Set PI_CODING_AGENT_ROOT to the installed Pi package root}"
python3 - <<'PY'
import ast, json, pathlib, re, sys
sys.path.insert(0, 'scripts')
from composition import compose, check_lock
root = pathlib.Path.cwd()
for path in root.rglob('*'):
    if '.git' in path.parts or '__pycache__' in path.parts or not path.is_file():
        continue
    if path.suffix == '.json':
        json.loads(path.read_text())
    if path.suffix == '.py':
        ast.parse(path.read_text(), filename=str(path))
    if path.name in ('auth.json', '.env') or path.suffix in ('.log', '.jsonl', '.key', '.pem'):
        raise SystemExit(f'forbidden runtime/credential file: {path.relative_to(root)}')
    if path.suffix in ('.json', '.md', '.ts', '.py', '.sh', '.mjs'):
        text = path.read_text()
        patterns = [r'AKIA[0-9A-Z]{16}', r'-----BEGIN (?:RSA|OPENSSH|EC|DSA) PRIVATE KEY-----',
                    r'(?i)(?:api[_-]?key|password|secret)\s*[:=]\s*[a-z0-9_-]{24,}']
        if any(re.search(pattern, text) for pattern in patterns):
            raise SystemExit(f'possible credential: {path.relative_to(root)}')
c, _ = compose(root)
check_lock(c, root / 'config/dependencies')
assert c['entries']['packages']['pi-subagents']['shared']
assert c['entries']['packages']['pi-lens']['shared']
assert 'fleetView' not in json.dumps(c['entries']['settings'])
assert 'asyncWidget' not in json.dumps(c['entries']['settings'])
assert json.loads((root / 'config/settings.json').read_text())['theme'] == 'hyper-term-white'
for skill in (root / 'config/skills').glob('*/SKILL.md'):
    text = skill.read_text()
    assert re.search(r'^name: [a-z0-9]+(?:-[a-z0-9]+)*$', text, re.M), skill
    assert re.search(r'^description: \S.+$', text, re.M), skill
    for reference in re.findall(r'\]\(([^)]+)\)', text):
        if not reference.startswith(('http:', 'https:', '#')):
            assert (skill.parent / reference).exists(), (skill, reference)
print('JSON, Python syntax, source hygiene, skill references, shared ownership and lock binding: passed')
PY
bash -n scripts/verify.sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
node extensions/web-search/tests/renderers.test.mjs
node --test tests/*.test.mjs
if [[ -z "${PI_CANDIDATE_DEPENDENCIES:-}" ]]; then
  printf '%s\n' 'Pinned dependency renderer check skipped: set PI_CANDIDATE_DEPENDENCIES for the publication gate.'
fi
printf '%s\n' 'Verification passed. No live activation or reload was performed.'
