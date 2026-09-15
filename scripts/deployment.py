"""Frozen generations and conservative three-way deployment, separate from sources."""
from __future__ import annotations

import base64
import fcntl
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from subagent_inventory import assert_subagent_inventory
from composition import (Refusal, anchored, binding, check_lock, compose, dependency_manifest, digest,
                         encoded, files, read_json, relative, require, validate)


MISSING = object()
# Pi and its plugins create these after activation. They are never read, captured,
# adopted or removed; a name outside this reviewed allowlist still refuses.
RUNTIME_NAMES = {'auth.json', 'trust.json', 'sessions', 'cache', 'logs', 'models-cache',
                 'models-store.json', 'subagent-artifacts', 'subagent-runs', 'tasks',
                 'pi-improver', 'missions', 'plans', 'powerline-footer', 'web-search-cache',
                 'history.json', 'run-history.jsonl', 'package-state.json'}


def canonical_path(path):
    path = Path(path).absolute()
    require('..' not in path.parts, 'parent traversal is not allowed in deployment paths')
    for parent in (path, *path.parents):
        require(not parent.is_symlink(), f'linked destination ancestor: {parent}')
    return path.resolve()


def external(path, roots):
    path = canonical_path(path)
    for root in roots:
        root = canonical_path(root)
        require(not path.is_relative_to(root) and not root.is_relative_to(path), 'deployment/state must be outside and disjoint from source roots')
    return path


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def npm_supports_allow_remote():
    """Probe the installed npm once; npm 12+ gates URL (remote) dependencies behind
    --allow-remote, while older npm rejects the flag as unknown. Version-neutral."""
    global _NPM_ALLOW_REMOTE
    if _NPM_ALLOW_REMOTE is None:
        env = {'PATH': os.environ['PATH'], 'HOME': tempfile.mkdtemp(prefix='pi-npm-')}
        probe = subprocess.run(['npm', 'install', '--help'], capture_output=True, text=True, env=env)
        _NPM_ALLOW_REMOTE = probe.returncode == 0 and re.search(r'--allow-remote\b', probe.stdout) is not None
    return _NPM_ALLOW_REMOTE


_NPM_ALLOW_REMOTE = None


def npm_run(target, args):
    # No user npmrc, credentials, lifecycle scripts, global writes, or Pi auto-install.
    extra = []
    if npm_supports_allow_remote():
        # Newer npm blocks URL dependencies by default. The pinned archive is a
        # direct (root) dependency, so root is the tightest sufficient value.
        extra = ['--allow-remote', 'root']
    with tempfile.TemporaryDirectory(prefix='pi-npm-') as tmp:
        env = {'PATH': os.environ['PATH'], 'HOME': tmp,
               'npm_config_cache': tmp + '/cache', 'npm_config_userconfig': tmp + '/user.npmrc',
               'npm_config_globalconfig': tmp + '/global.npmrc', 'npm_config_update_notifier': 'false'}
        # Preserve normal transport/CA policy, but never npm auth or user npmrc.
        for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'http_proxy',
                     'https_proxy', 'all_proxy', 'no_proxy', 'NODE_EXTRA_CA_CERTS',
                     'SSL_CERT_FILE', 'SSL_CERT_DIR'):
            if name in os.environ:
                env[name] = os.environ[name]
        subprocess.run(['npm', *args, *extra, '--prefix', str(target), '--ignore-scripts',
                        '--legacy-peer-deps', '--no-audit', '--no-fund'], check=True, env=env, stdout=sys.stderr)


def make_lock(composed, output):
    output = external(output, composed['roots'].values())
    output.mkdir(parents=True, exist_ok=False)
    write(output / 'package.json', encoded(dependency_manifest(composed)))
    npm_run(output, ['install', '--package-lock-only'])
    write(output / 'binding.json', encoded(binding(composed)))
    check_lock(composed, output)


def unpack_archive(archive, output):
    with urllib.request.urlopen(archive['url'], timeout=60) as response:
        require(response.url.startswith('https://'), 'archive redirected outside HTTPS')
        data = response.read(50_000_001)
    require(len(data) <= 50_000_000 and digest(data) == archive['sha256'], 'archive size/integrity mismatch')
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        members = tar.getmembers()
        roots = {m.name.split('/')[0] for m in members}
        require(len(roots) == 1, 'archive must have one top directory')
        for member in members:
            relative(member.name.rstrip('/'))
            require(member.isfile() or member.isdir(), 'archive links/special files refused')
        tar.extractall(output, filter='data')
    return anchored(output / next(iter(roots)), archive['path'])


def tree_inventory(root):
    inventory = {}
    for p in sorted(root.rglob('*')):
        name = str(p.relative_to(root))
        if p.is_symlink():
            require(p.resolve().is_relative_to(root.resolve()), f'snapshot symlink escapes: {name}')
            inventory[name] = {'link': os.readlink(p)}
        elif p.is_file():
            require(p.stat().st_nlink == 1, f'hardlinked snapshot file: {name}')
            inventory[name] = {'sha256': digest(p.read_bytes()), 'executable': bool(p.stat().st_mode & 0o111)}
        else:
            require(p.is_dir(), f'special snapshot file: {name}')
    return inventory


def verify_generation(path):
    path = canonical_path(path)
    require((path / 'generation.json').is_file() and not (path / 'generation.json').is_symlink(), 'missing/linked generation receipt')
    receipt = read_json(path / 'generation.json')
    inventory = tree_inventory(path)
    inventory.pop('generation.json')
    require(inventory == receipt['inventory'], 'frozen generation has changed')
    require(str(path.resolve()) == receipt['path'], 'generation moved; absolute package paths are anchored')
    return receipt


def resource_inventory(output):
    pi_root = os.environ.get('PI_CODING_AGENT_ROOT')
    require(pi_root, 'PI_CODING_AGENT_ROOT is required for version-bound filesystem discovery preflight')
    assert pi_root is not None
    script = Path(__file__).parent / 'resource-inventory.mjs'
    with tempfile.TemporaryDirectory(prefix='pi-inventory-') as tmp:
        env = {'PATH': os.environ['PATH'], 'HOME': tmp, 'PI_OFFLINE': '1', 'PI_CODING_AGENT_DIR': tmp + '/agent'}
        result = subprocess.check_output(['node', str(script), str(output), pi_root], cwd=tmp, env=env)
    import json
    try:
        return json.loads(result)
    except ValueError as error:
        raise Refusal(f'inventory output is not valid JSON: {error}') from error


def prepare(composed, origins, output, lock):
    output = external(output, composed['roots'].values())
    check_lock(composed, lock)
    output.mkdir(parents=True, exist_ok=False)
    deps = output / 'dependencies'
    deps.mkdir()
    for name in ('package.json', 'package-lock.json', 'binding.json'):
        shutil.copyfile(lock / name, deps / name)
    npm_run(deps, ['ci'])
    settings, claims = validate(composed)
    settings['packages'] = []
    for name, entry in composed['entries']['packages'].items():
        package = deps / 'node_modules' / name
        require((package / 'package.json').is_file(), f'missing dependency: {name}')
        package_json = read_json(package / 'package.json')
        require(package_json['name'] == name, 'installed package identity mismatch')
        spec = entry['value']['spec']
        if not spec.startswith('https://'):
            require(package_json['version'] == spec, f'installed version mismatch: {name}')
        # Preserve Pi object filters exactly; only replace the source with its generation-local path.
        settings['packages'].append({'source': str(package), **entry['value'].get('filters', {})})
    modes = {'settings.json': 'copy', 'models.json': 'copy', 'AGENTS.md': 'copy'}
    for name, entry in composed['entries']['resources'].items():
        value = entry['value']
        kind = value['type']
        with tempfile.TemporaryDirectory(prefix='pi-resource-') as tmp:
            source = (anchored(origins['resources', name], value['source']) if 'source' in value
                      else unpack_archive(value['archive'], Path(tmp)))
            source_files = files(source)  # no links, devices, sockets or missing resources
            if 'source' in value:
                root = origins['resources', name]
                expected_files = composed['sourceFiles'][str(root)]
                for p in source_files:
                    require(digest(p.read_bytes()) == expected_files[str(p.relative_to(root))], 'source changed during generation')
            if kind in ('copy', 'seed'):
                require(source.is_file(), 'writable resource must be one JSON file')
                read_json(source)
                write(output / 'defaults' / name, source.read_bytes())
                modes[name] = kind
            else:
                target = output / 'stow' / 'agent' / 'managed' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    shutil.copytree(source, target)
                else:
                    shutil.copy2(source, target)
                if 'source' in value:
                    root = origins['resources', name]
                    expected_files = composed['sourceFiles'][str(root)]
                    for p in source_files:
                        copied = target / p.relative_to(source) if source.is_dir() else target
                        require(digest(copied.read_bytes()) == expected_files[str(p.relative_to(root))], 'source changed while copying')
                if kind != 'data':
                    settings.setdefault(kind, []).append(str(target))
    models = {'providers': {name: entry['value'].copy() for name, entry in composed['entries']['providers'].items()}}
    for name, entry in composed['entries']['models'].items():
        provider = name.split('/', 1)[0]
        models['providers'][provider].setdefault('models', []).append(entry['value'])
    instructions = '\n\n'.join(entry['value'].strip() for entry in composed['entries']['instructions'].values()) + '\n'
    write(output / 'defaults' / 'settings.json', encoded(settings))
    write(output / 'defaults' / 'models.json', encoded(models))
    write(output / 'defaults' / 'AGENTS.md', instructions.encode())
    (output / 'stow' / 'agent').mkdir(parents=True, exist_ok=True)
    discovered = resource_inventory(output)
    current, _ = compose(composed['roots']['core'], composed['roots'].get('overlay'), clean=True)
    require(current['inputDigest'] == composed['inputDigest'] and current['commits'] == composed['commits'], 'source changed during generation')
    receipt = {'schema': 1, 'path': str(output), 'coreDigest': composed['coreDigest'],
               'inputDigest': composed['inputDigest'], 'commits': composed['commits'],
               'roots': sorted({str(root) for root in origins.values()}), 'modes': modes,
               'features': sorted(composed['features']), 'excluded': composed['excluded'], 'claims': claims,
               'resources': discovered,
               'inventory': tree_inventory(output)}
    write(output / 'generation.json', encoded(receipt))
    # Read-only is an accident guard, not a sandbox against the same OS user.
    for p in output.rglob('*'):
        if not p.is_symlink():
            p.chmod((0o555 if p.is_dir() or p.stat().st_mode & 0o111 else 0o444))
    output.chmod(0o555)
    return verify_generation(output)


def merge(old, current, new, path=''):
    if current == old:
        return new
    if new == old or current == new:
        return current
    if all(isinstance(x, dict) for x in (old, current, new)):
        known_keys(old, current, new, path)
        result = {}
        for key in sorted(old.keys() | current.keys() | new.keys()):
            value = merge(old.get(key, MISSING), current.get(key, MISSING), new.get(key, MISSING), path + '/' + key)
            if value is not MISSING:
                result[key] = value
        return result
    raise Refusal(f'local/generated conflict: {path}; reconcile in the owning source or preserve local edits explicitly')


def known_keys(old, current, new, path):
    if not isinstance(current, dict):
        return
    allowed = {**(old if isinstance(old, dict) else {}), **(new if isinstance(new, dict) else {})}
    if path == 'settings.json' and 'lastChangelogVersion' in current:
        version = current['lastChangelogVersion']
        require(isinstance(version, str) and len(version) <= 64
                and re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?', version), 'invalid local changelog metadata')
        allowed['lastChangelogVersion'] = version
    require(current.keys() <= allowed.keys(), f'unknown local JSON keys: {path}')
    for key, value in current.items():
        known_keys(old.get(key, MISSING) if isinstance(old, dict) else MISSING, value,
                   new.get(key, MISSING) if isinstance(new, dict) else MISSING, path + '/' + key)


def reconcile(old, current, new, name):
    if name.endswith('.json') and all(x is not MISSING for x in (old, current, new)):
        import json
        try:
            values = [json.loads(x) for x in (old, current, new)]
        except ValueError as error:
            raise Refusal(f'invalid JSON in three-way inputs for {name}: {error}') from error
        known_keys(*values, path=name)
        merged = merge(*values, path=name)
        if merged == values[1]:
            return current
        if merged == values[2]:
            return new
        return encoded(merged)
    return merge(old, current, new, name)


def effective_config(name, data, desired, models):
    if data is MISSING or desired is MISSING or not name.endswith('.json'):
        return
    import json
    try:
        current, generated = json.loads(data), json.loads(desired)
    except ValueError as error:
        raise Refusal(f'invalid JSON in settings inputs for {name}: {error}') from error
    if name == 'settings.json':
        for kind in ('packages', 'extensions', 'skills', 'prompts', 'themes'):
            require(current.get(kind) == generated.get(kind), f'unmanaged local resource settings: {kind}')
        available = {f'{provider}/{model["id"]}' for provider, value in models['providers'].items()
                     for model in value.get('models', [])}
        ref = f'{current.get("defaultProvider")}/{current.get("defaultModel")}'
        require(ref == 'None/None' or ref in available, 'local default model is outside effective inventory')
        subagents = current.get('subagents', {})
        for override in [subagents, *subagents.get('agentOverrides', {}).values()]:
            for field in ('model', 'defaultModel'):
                ref = override.get(field)
                require(not ref or ref == 'inherit' or ref in available, 'local subagent model is outside effective inventory')
    if 'registerToolOverrides' in generated:
        require(current.get('registerToolOverrides') == generated['registerToolOverrides'], 'local renderer ownership drift; promote through explicit composition')
    if 'customToolOverrides' in generated:
        require(current.get('customToolOverrides') == generated['customToolOverrides'], 'local custom renderer ownership drift')


def fingerprint(path):
    if path.is_symlink():
        return {'link': os.readlink(path)}
    if not path.exists():
        return None
    require(path.is_file() and path.stat().st_nlink == 1, f'nonlocal writable singleton: {path}')
    return {'sha256': digest(path.read_bytes()), 'mode': path.stat().st_mode}


def ambient(home, project):
    # No project resources are adopted. Recheck on every deployment/diff. This does
    # not police future CLI -e/--skill flags or dynamic plugin registrations.
    candidates = [home / '.agents', home / '.pi' / 'agent' / 'skills']
    for directory in (project, *project.parents):
        candidates += [directory / '.agents']
        pi = directory / '.pi'
        candidates += [pi / 'agents', pi / 'chains', pi / 'subagent', directory / 'AGENTS.override.md']
        candidates += [pi / n for n in ('settings.json', 'extensions', 'skills', 'prompts', 'themes', 'SYSTEM.md', 'APPEND_SYSTEM.md')]
    return sorted(set(candidates))


def assert_inventory(agent, home, project, old, new):
    managed = set(old.get('links', {})) | set(old.get('baseline', {})) | set(new['modes'])
    for p in ambient(home, project):
        if p == agent / 'skills':
            continue
        require(not p.exists() and not p.is_symlink(), f'unmanaged ambient resource: {p}')
    if not agent.exists():
        return
    def walk(directory):
        for p in directory.iterdir():
            name = str(p.relative_to(agent))
            if name in RUNTIME_NAMES:
                continue  # never inspect auth, transcripts, local state or credentials
            if name in managed:
                continue
            if p.is_dir() and not p.is_symlink() and any(n.startswith(name + '/') for n in managed):
                walk(p)
            else:
                raise Refusal(f'unmanaged target resource: {name}')
    walk(agent)


def deployment_plan(generation, agent, state, home, project):
    generation, agent, state, home, project = map(canonical_path, (generation, agent, state, home, project))
    new = verify_generation(generation)
    for path in (agent, state):
        external(path, [Path(p) for p in new['roots']] + [generation])
    require(not agent.is_relative_to(state) and not state.is_relative_to(agent), 'state must be outside target')
    require(not (state / 'transaction.json').exists(), 'interrupted deployment journal exists; owner recovery required')
    if state.exists():
        for p in state.iterdir():
            require(p.name in ('receipt.json', 'deploy.lock') and p.is_file() and not p.is_symlink()
                    and p.stat().st_nlink == 1, f'unknown/linked deployment state: {p.name}')
    old = read_json(state / 'receipt.json') if (state / 'receipt.json').exists() else {}
    require(not old or old['agent'] == str(agent), 'receipt belongs to another target')
    if old:
        verify_generation(Path(old['generation']))
    assert_inventory(agent, home, project, old, new)
    links = {str(p.relative_to(generation / 'stow' / 'agent')): str(p)
             for p in files(generation / 'stow' / 'agent')}
    for name, target in old.get('links', {}).items():
        p = agent / name
        require(p.is_symlink() and p.resolve() == Path(target), f'managed link drift: {name}')
    for name in links:
        relative(name)
        for p in (agent / name, *(agent / name).parents):
            if p == agent:
                break
            rel = str(p.relative_to(agent))
            if rel in old.get('links', {}):
                break
            require(not p.is_symlink(), f'linked target ancestor: {rel}')
            require(not p.exists() or p.is_dir(), f'unowned target collision: {rel}')
    defaults, changes, before = {}, {}, {}
    effective_settings = read_json(generation / 'defaults/settings.json')
    modes = new['modes'].copy()
    for name, mode in old.get('modes', {}).items():
        if mode == 'seed':
            modes.setdefault(name, mode)
    for name in sorted(set(old.get('baseline', {})) | set(modes)):
        p = anchored(agent, name)
        before[name] = fingerprint(p)
        previous = base64.b64decode(old['baseline'][name]) if name in old.get('baseline', {}) else MISSING
        desired = (generation / 'defaults' / name).read_bytes() if name in new['modes'] else MISSING
        current = p.read_bytes() if p.exists() else MISSING
        if modes.get(name) == 'seed' or old.get('modes', {}).get(name) == 'seed':
            result = current if current is not MISSING else desired
        else:
            require(previous is not MISSING or current is MISSING, f'unowned singleton: {name}')
            result = reconcile(previous, current, desired, name)
        effective_config(name, result, desired, read_json(generation / 'defaults' / 'models.json'))
        if name == 'settings.json' and result is not MISSING:
            import json
            assert isinstance(result, bytes)
            try:
                effective_settings = json.loads(result)
            except ValueError as error:
                raise Refusal(f'reconciled settings are not valid JSON: {error}') from error
        if desired is not MISSING:
            assert isinstance(desired, bytes)
            defaults[name] = base64.b64encode(desired).decode()
        elif modes.get(name) == 'seed' and previous is not MISSING:
            # Retired seed ownership remains local; never recreate or delete it.
            assert isinstance(previous, bytes)
            defaults[name] = base64.b64encode(previous).decode()
        if result != current:
            changes[name] = result
    discovery = assert_subagent_inventory(agent, home, project, new, effective_settings)
    receipt = {'schema': 1, 'generation': str(generation), 'agent': str(agent),
               'baseline': defaults, 'links': links, 'modes': modes, 'discovery': discovery}
    return new, old, receipt, changes, before


def report_plan(plan):
    _, old, receipt, changes, before = plan
    return {'generation': receipt['generation'],
            'write': [p for p, value in changes.items() if value is not MISSING],
            'remove': [p for p, value in changes.items() if value is MISSING],
            'preserveLocal': [p for p in before if p not in changes],
            'linkCount': len(receipt['links']), 'previousGeneration': old.get('generation')}


def deploy(generation, agent, state, home, project, expected):
    # An explicit diff digest is required; concurrent writers are detected again
    # before mutation. The lock coordinates deployments, not arbitrary Pi writes.
    # Validate locations before even creating the state directory/lock.
    generation, agent, state, home, project = map(canonical_path, (generation, agent, state, home, project))
    initial = deployment_plan(generation, agent, state, home, project)
    require(plan_digest(initial) == expected, 'deployment diff drift; review a fresh diff')
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(not (state / 'deploy.lock').is_symlink(), 'linked deployment lock refused')
    with (state / 'deploy.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan = deployment_plan(generation, agent, state, home, project)
        new, old, receipt, changes, before = plan
        require(plan_digest(plan) == expected, 'deployment diff drift; review a fresh diff')
        write(state / 'transaction.json', encoded({'oldReceipt': old, 'plannedReceipt': receipt, 'before': before}))
        agent.mkdir(parents=True, exist_ok=True)
        # All unknowns/conflicts checked before the first target mutation.
        for name, fp in before.items():
            require(fingerprint(agent / name) == fp, f'concurrent singleton drift: {name}')
        if old.get('generation') and old.get('links'):
            subprocess.run(['stow', '--no-folding', '--dir', old['generation'] + '/stow',
                            '--target', str(agent), '--delete', 'agent'], check=True)
        subprocess.run(['stow', '--no-folding', '--dir', str(generation / 'stow'),
                        '--target', str(agent), '--stow', 'agent'], check=True)
        for name, data in changes.items():
            p = agent / name
            require(fingerprint(p) == before[name], f'concurrent singleton drift: {name}')
            if data is MISSING:
                p.unlink()
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(prefix='.pi-copy-', dir=p.parent)
                try:
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    require(fingerprint(p) == before[name], f'concurrent singleton drift: {name}')
                    os.replace(tmp, p)
                finally:
                    if os.path.exists(tmp):
                        os.unlink(tmp)
        write(state / 'receipt.next', encoded(receipt))
        os.replace(state / 'receipt.next', state / 'receipt.json')
        (state / 'transaction.json').unlink()
    return report_plan(plan)


def plan_digest(plan):
    _, old, receipt, changes, before = plan
    return digest({'old': old, 'new': receipt, 'before': before,
                   'changes': {k: None if v is MISSING else digest(v) for k, v in changes.items()}})
