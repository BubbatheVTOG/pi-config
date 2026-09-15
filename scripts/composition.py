"""Explicit, feature-owned Pi configuration composition. No Pi process is started."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

KINDS = ('packages', 'resources', 'settings', 'providers', 'models', 'instructions')
RESOURCE_TYPES = ('extensions', 'skills', 'prompts', 'themes', 'data', 'copy', 'seed')


class Refusal(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Refusal(message)


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode()


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else encoded(value)).hexdigest()


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f'duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs)


def keys(value, required, optional=()):
    require(isinstance(value, dict), 'expected object')
    require(set(required) <= value.keys(), f'missing keys: {set(required) - value.keys()}')
    require(value.keys() <= set(required) | set(optional), f'unknown keys: {value.keys() - set(required) - set(optional)}')


def relative(value):
    require(isinstance(value, str) and value and '\\' not in value, 'expected relative POSIX path')
    p = PurePosixPath(value)
    require(not p.is_absolute() and all(x not in ('', '.', '..') for x in value.split('/')), f'unsafe path: {value}')
    require(not any(c in value for c in '\n\r\0'), 'control character in path')
    return value


def anchored(root, name):
    relative(name)
    path = root / name
    for p in (path, *path.parents):
        if p == root:
            break
        require(not p.is_symlink(), f'symlink source/path refused: {p}')
    require(path.resolve().is_relative_to(root.resolve()), f'path escapes root: {name}')
    return path


def files(path):
    require(path.exists() and not path.is_symlink(), f'missing/linked source: {path}')
    candidates = sorted(path.rglob('*')) if path.is_dir() else [path]
    for p in candidates:
        require(not p.is_symlink(), f'symlink source refused: {p}')
        require(p.is_file() or p.is_dir(), f'special source refused: {p}')
    return [p for p in candidates if p.is_file()]


def pointer_get(value, pointer):
    if not pointer:
        return value
    require(pointer.startswith('/'), 'JSON pointer must start with /')
    for key in pointer[1:].split('/'):
        key = key.replace('~1', '/').replace('~0', '~')
        require(isinstance(value, dict) and key in value, f'unknown source pointer: {pointer}')
        value = value[key]
    return value


def pointer_set(value, pointer, item):
    require(pointer.startswith('/') and pointer != '/', 'setting ID must be a JSON pointer')
    parts = [s.replace('~1', '/').replace('~0', '~') for s in pointer[1:].split('/')]
    for part in parts[:-1]:
        value = value.setdefault(part, {})
        require(isinstance(value, dict), f'overlapping settings: {pointer}')
    require(parts[-1] not in value, f'overlapping settings: {pointer}')
    value[parts[-1]] = copy.deepcopy(item)


def source_commit(root, clean=False):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()
    require(Path(git('rev-parse', '--show-toplevel')).resolve() == root, 'manifest root must be repository root')
    if clean:
        require(not git('status', '--porcelain', '--untracked-files=all'), f'dirty source repository: {root}')
    return git('rev-parse', 'HEAD')


def load_core(root):
    manifest = read_json(root / 'manifest.json')
    keys(manifest, ('schema', 'features', 'entries'))
    require(manifest['schema'] == 1, 'unsupported manifest schema')
    keys(manifest['entries'], KINDS)
    return manifest


def materialize(entry, root, inputs):
    keys(entry, ('feature', 'owner'), ('value', 'source', 'pointer', 'shared', 'claims', 'requires'))
    require(('value' in entry) != ('source' in entry), 'entry needs exactly one of value/source')
    require(isinstance(entry['feature'], str) and isinstance(entry['owner'], str), 'feature/owner must be strings')
    require(isinstance(entry.get('shared', False), bool), 'shared must be boolean')
    for field in ('claims', 'requires'):
        require(isinstance(entry.get(field, []), list) and all(isinstance(x, str) for x in entry.get(field, [])), f'{field} must be strings')
    result = copy.deepcopy(entry)
    if 'source' in entry:
        path = anchored(root, entry['source'])
        inputs[entry['source']] = digest(path.read_bytes())
        result['value'] = pointer_get(read_json(path), entry.get('pointer', '')) if path.suffix == '.json' else path.read_text()
        del result['source']
        result.pop('pointer', None)
    return result


def validate(manifest):
    features, entries = manifest['features'], manifest['entries']
    require(isinstance(features, dict), 'features must be keyed by ID')
    for name, feature in features.items():
        require(re.fullmatch(r'[a-z0-9][a-z0-9-]*', name), 'invalid feature ID')
        keys(feature, ('description',))
    claims = {}
    for kind, records in entries.items():
        require(isinstance(records, dict), f'{kind} must be keyed by identity')
        for name, entry in records.items():
            require(entry['feature'] in features, f'unknown/excluded feature: {entry["feature"]}')
            require(set(entry.get('requires', [])) <= features.keys(), f'dangling feature reference: {kind}/{name}')
            for claim in entry.get('claims', []):
                require(claim not in claims, f'duplicate capability: {claim}')
                claims[claim] = f'{kind}/{name}'
            value = entry['value']
            if kind == 'packages':
                require(re.fullmatch(r'(?:@[a-z0-9._-]+/)?[a-z0-9._-]+', name), 'package ID must be npm package identity')
                keys(value, ('spec',), ('filters',))
                spec = value['spec']
                require(isinstance(spec, str) and (re.fullmatch(r'\d+\.\d+\.\d+(?:-[\w.-]+)?', spec) or re.fullmatch(r'https://[^\s?#]+/[0-9a-f]{40}', spec)), f'unpinned/non-HTTPS package: {name}')
                keys(value.get('filters', {}), (), ('extensions', 'skills', 'prompts', 'themes'))
                for patterns in value.get('filters', {}).values():
                    require(isinstance(patterns, list), 'package filters must be arrays')
                    for pattern in patterns:
                        relative(pattern.lstrip('!+-').removeprefix('./'))
            elif kind == 'resources':
                relative(name)
                keys(value, ('type',), ('source', 'archive'))
                require(value['type'] in RESOURCE_TYPES, 'unknown resource type')
                require(('source' in value) != ('archive' in value), 'resource needs source or archive')
                if 'source' in value:
                    relative(value['source'])
                else:
                    a = value['archive']
                    keys(a, ('url', 'sha256', 'path'))
                    require(re.fullmatch(r'https://[^\s?#]+/[0-9a-f]{40}', a['url']), 'archive URL must pin a commit over HTTPS')
                    require(re.fullmatch(r'[0-9a-f]{64}', a['sha256']), 'archive needs sha256')
                    relative(a['path'])
                if value['type'] in ('copy', 'seed'):
                    require(name not in ('settings.json', 'models.json', 'AGENTS.md', 'auth.json', 'trust.json'), 'reserved singleton path')
                    require(not name.startswith(('managed/', 'skills/', 'themes/', 'prompts/')), 'copy would enter immutable discovery tree')
                    require(name.endswith('.json') and not name.endswith('/package.json'), 'only JSON plugin config copies/seeds are supported')
            elif kind == 'providers':
                require(isinstance(value, dict) and 'models' not in value, 'models must be declared by ID, not provider arrays')
            elif kind == 'models':
                provider, sep, model = name.partition('/')
                require(sep and provider in entries['providers'], f'unknown model provider: {name}')
                require(value.get('id') == model, f'model ID mismatch: {name}')
            elif kind == 'instructions':
                require(isinstance(value, str), 'instruction section must be text')
    settings = {}
    for key, entry in entries['settings'].items():
        require(isinstance(key, str) and key.startswith('/') and key.count('/') >= 1, 'settings need JSON pointer IDs')
        require(key.split('/')[1] not in ('packages', 'extensions', 'skills', 'themes', 'prompts'), 'resources must use resource/package declarations')
        pointer_set(settings, key, entry['value'])
    provider, model = settings.get('defaultProvider'), settings.get('defaultModel')
    if provider or model:
        require(f'{provider}/{model}' in entries['models'], 'default provider/model must be explicitly declared')
    overrides = settings.get('subagents', {}).get('agentOverrides', {})
    for override in [settings.get('subagents', {}), *overrides.values()]:
        for field in ('model', 'defaultModel'):
            ref = override.get(field)
            require(not ref or ref == 'inherit' or ref in entries['models'], f'undeclared subagent model: {ref}')
    return settings, claims


def compose(core, overlay=None, clean=False):
    core = Path(core).resolve()
    raw = load_core(core)
    result = copy.deepcopy(raw)
    origins, inputs = {}, {'manifest.json': digest((core / 'manifest.json').read_bytes())}
    for kind in KINDS:
        for name, entry in raw['entries'][kind].items():
            result['entries'][kind][name] = materialize(entry, core, inputs)
            origins[kind, name] = core
    # Bind the dependency lock to all core source inputs, including resource trees and composer.
    for entry in result['entries']['resources'].values():
        if 'source' in entry['value']:
            path = anchored(core, entry['value']['source'])
            for p in files(path):
                inputs[str(p.relative_to(core))] = digest(p.read_bytes())
    for p in sorted((core / 'scripts').glob('*')):
        if p.suffix in ('.py', '.mjs', '.sh'):
            inputs[str(p.relative_to(core))] = digest(p.read_bytes())
    core_digest = digest(inputs)
    commits = {'core': source_commit(core, clean)}
    excluded = []
    overlay_inputs = {}
    if overlay:
        overlay = Path(overlay).resolve()
        raw_overlay = read_json(overlay / 'overlay.json')
        keys(raw_overlay, ('schema', 'coreDigest', 'features', 'operations'))
        require(raw_overlay['schema'] == 1 and raw_overlay['coreDigest'] == core_digest, 'overlay core input digest drift')
        commits['overlay'] = source_commit(overlay, clean)
        overlay_inputs['overlay.json'] = digest((overlay / 'overlay.json').read_bytes())
        for name, feature in raw_overlay['features'].items():
            require(name not in result['features'], f'conflicting feature: {name}')
            result['features'][name] = feature
        for operation in raw_overlay['operations']:
            op = operation.get('op')
            if op == 'exclude':
                keys(operation, ('op', 'feature'))
                feature = operation['feature']
                require(feature in result['features'], f'unknown/excluded feature: {feature}')
                excluded.append(feature)
                del result['features'][feature]
                for records in result['entries'].values():
                    for name in list(records):
                        if records[name]['feature'] == feature:
                            del records[name]
                continue
            require(op in ('add', 'replace', 'remove'), f'unknown operation: {op}')
            keys(operation, ('op', 'kind', 'id'), ('expect', 'entry'))
            kind, name = operation['kind'], operation['id']
            require(kind in KINDS, 'unknown entry kind')
            records = result['entries'][kind]
            if op == 'add':
                require(name not in records and 'expect' not in operation, f'add conflict: {kind}/{name}')
            else:
                require(name in records and operation.get('expect') == digest(records[name]), f'owner/value drift: {kind}/{name}')
                require(not records[name].get('shared'), f'shared setting/package belongs in core: {kind}/{name}')
            if op == 'remove':
                require('entry' not in operation, 'remove cannot supply an entry')
                del records[name]
            else:
                require('entry' in operation, 'missing entry')
                records[name] = materialize(operation['entry'], overlay, overlay_inputs)
                origins[kind, name] = overlay
    # Exclude/add or overlapping pointer spelling must not bypass shared ownership.
    for kind in KINDS:
        for name, original in raw['entries'][kind].items():
            if not original.get('shared'):
                continue
            original_value = materialize(original, core, {})
            if name in result['entries'][kind]:
                require(result['entries'][kind][name] == original_value, f'shared setting/package belongs in core: {kind}/{name}')
            if kind == 'settings':
                for candidate in result['entries'][kind]:
                    require(candidate == name or not (candidate.startswith(name + '/') or name.startswith(candidate + '/')),
                            f'overlapping shared setting: {candidate}')
    validate(result)
    for name, entry in result['entries']['resources'].items():
        if 'source' in entry['value'] and origins['resources', name] != core:
            root = origins['resources', name]
            for p in files(anchored(root, entry['value']['source'])):
                overlay_inputs[str(p.relative_to(root))] = digest(p.read_bytes())
    result['coreDigest'] = core_digest
    result['inputDigest'] = digest({'core': inputs, 'overlay': overlay_inputs})
    result['commits'] = commits
    result['roots'] = {'core': str(core), **({'overlay': str(overlay)} if overlay else {})}
    result['sourceFiles'] = {str(core): inputs, **({str(overlay): overlay_inputs} if overlay else {})}
    result['excluded'] = excluded
    return result, origins


def dependency_manifest(composed):
    return {'name': 'pi-composed-dependencies', 'private': True, 'dependencies': {
        name: entry['value']['spec'] for name, entry in sorted(composed['entries']['packages'].items())}}


def binding(composed):
    return {'schema': 1, 'coreDigest': composed['coreDigest'], 'inputDigest': composed['inputDigest'],
            'dependenciesDigest': digest(dependency_manifest(composed)), 'scripts': 'ignore', 'peerPolicy': 'host-provided'}


def check_lock(composed, lock):
    require(read_json(lock / 'binding.json') == binding(composed), 'dependency lock binding drift; regenerate the combined union lock')
    require(read_json(lock / 'package.json') == dependency_manifest(composed), 'dependency manifest drift')
    data = read_json(lock / 'package-lock.json')
    require(data['lockfileVersion'] == 3, 'expected npm lockfileVersion 3')
    require(data['packages']['']['dependencies'] == dependency_manifest(composed)['dependencies'], 'lock root dependencies drift')
    for path, package in data['packages'].items():
        if not path:
            continue
        require(path.startswith('node_modules/') and package.get('resolved', '').startswith('https://') and package.get('integrity'), f'unlocked/non-HTTPS dependency: {path}')
        require(not package.get('link'), 'linked dependencies are not allowed')
    return data
