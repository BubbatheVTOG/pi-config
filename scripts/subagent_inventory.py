"""Fail-closed definition inventory for the reviewed pi-subagents 0.68 discovery inputs.

Inspect metadata and candidate filenames, not prompts or executable plugin factories.
Real pinned discovery is exercised independently by the regression tests.
"""
import os
from pathlib import Path
import subprocess

from composition import Refusal, read_json, require

PRUNED = {'.git', 'node_modules', '.pi', 'sync-backups'}


def global_npm_root(home, project):
    if os.environ.get('PI_OFFLINE', '').lower() in ('1', 'true', 'yes'):
        return None
    try:
        result = subprocess.check_output(['npm', 'root', '-g'], cwd=project,
            env={**os.environ, 'HOME': str(home)}, stderr=subprocess.DEVNULL, text=True, timeout=5)
        lines = result.strip().splitlines()
        require(len(lines) == 1 and Path(lines[0]).is_absolute(), 'ambiguous global npm root')
        root = Path(lines[0]).resolve(strict=True)
        require(root.is_dir(), 'global npm root is not a directory')
        return root
    except (OSError, subprocess.SubprocessError) as error:
        raise Refusal('cannot establish global npm discovery root; activation refused') from error


def assert_subagent_inventory(agent, home, project, generation, effective_settings=None):
    owned = {str((Path(generation['path']) / name).resolve()) for name in generation['inventory']}
    seen_packages, seen_dirs = set(), set()

    def present(path):
        # A broken link is uncertainty, not an absent resource.
        require(not path.is_symlink() or path.exists(), f'unresolved discovery link: {path}')
        return path.exists()

    def definitions(root, kind):
        if not present(root):
            return
        require(root.is_dir(), f'uncertain {kind} discovery directory: {root}')
        def visit(directory):
            identity = (directory.resolve(), kind)
            if identity in seen_dirs:
                return
            seen_dirs.add(identity)
            for p in sorted(directory.iterdir()):
                present(p)
                if p.is_dir():
                    if p.name not in PRUNED and not any((p / n).exists() for n in ('.git', '.pi', '.agents')):
                        visit(p)
                elif p.is_file():
                    candidate = (p.name.endswith(('.chain.md', '.chain.json')) if kind == 'chain'
                                 else p.suffix == '.md' and not p.name.endswith('.chain.md'))
                    if candidate:
                        require(str(p.resolve()) in owned, f'unmanaged subagent {kind} definition: {p}')
                else:
                    raise Refusal(f'uncertain discovery resource: {p}')
        visit(root)

    def package(root):
        root = root.resolve()
        if root in seen_packages:
            return
        seen_packages.add(root)
        metadata = root / 'package.json'
        if not present(metadata):
            return
        value = read_json(metadata)
        require(isinstance(value, dict), f'uncertain package discovery metadata: {metadata}')
        sections = [value.get('pi-subagents')]
        pi = value.get('pi')
        if pi is not None:
            require(isinstance(pi, dict), f'uncertain Pi package metadata: {metadata}')
            sections.append(pi.get('subagents'))
        for section in sections:
            if section is None:
                continue
            require(isinstance(section, dict), f'uncertain subagent package metadata: {metadata}')
            for key, kind in (('agents', 'agent'), ('chains', 'chain')):
                paths = section.get(key, [])
                require(isinstance(paths, list) and all(isinstance(p, str) and p.strip() for p in paths),
                        f'uncertain subagent package paths: {metadata}')
                for name in paths:
                    definitions((root / name).resolve(), kind)

    def node_modules(root):
        if not present(root):
            return
        require(root.is_dir(), f'uncertain npm discovery directory: {root}')
        for p in sorted(root.iterdir()):
            if p.name.startswith('.'):
                continue
            present(p)
            if not p.is_dir():
                continue
            if p.name.startswith('@'):
                for child in sorted(p.iterdir()):
                    present(child)
                    if child.is_dir() and not child.name.startswith('.'):
                        package(child)
            else:
                package(p)

    def expand(name):
        if name == '~' or name.startswith('~/'):
            return str(home) + name[1:]
        return str(project / name) if not Path(name).is_absolute() else name

    def settings(path, value):
        require(isinstance(value, dict), f'uncertain discovery settings: {path}')
        for item in value.get('packages', []):
            source = item if isinstance(item, str) else item.get('source')
            require(isinstance(source, str), f'uncertain package source: {path}')
            if source.startswith('npm:'):
                name = source[4:].rsplit('@', 1)[0] if '@' in source[5:] else source[4:]
                package(path.parent / 'npm/node_modules' / name)
            elif source.startswith(('git:', 'https:', 'http:')):
                raise Refusal(f'nonlocal settings package discovery needs explicit resolution: {path}')
            else:
                source = source.removeprefix('file:')
                resolved = Path(expand(source)) if source.startswith('~') else (path.parent / source).resolve()
                package(resolved)
        config = value.get('subagents', {})
        require(isinstance(config, dict), f'uncertain subagent settings: {path}')
        scan_dirs = config.get('agentScanDirs', [])
        require(isinstance(scan_dirs, list), f'uncertain agent scan directories: {path}')
        for name in scan_dirs:
            require(isinstance(name, str) and name.strip(), f'uncertain agent scan path: {path}')
            pattern = Path(expand(name.strip().replace('\\', os.sep)))
            require('*' not in str(pattern) or (str(pattern).count('*') == 1 and '*' in pattern.parts),
                    f'unsupported agent scan pattern: {path}')
            roots = [pattern]
            if '*' in pattern.parts:
                index = pattern.parts.index('*')
                base = Path(*pattern.parts[:index])
                # Unlike glob(), an unreadable directory must not look empty.
                roots = [p.joinpath(*pattern.parts[index + 1:]) for p in base.iterdir() if p.is_dir()] if present(base) else []
            for root in roots:
                definitions(root, 'agent')

    try:
        definitions(agent / 'agents', 'agent')
        definitions(agent / 'chains', 'chain')
        node_modules(agent / 'npm/node_modules')
        # The older .agents tree is already refused by the general ambient guard.
        for name in os.environ.get('PI_SUBAGENT_EXTRA_AGENT_DIRS', '').split(os.pathsep):
            if name.strip():
                definitions(Path(expand(name.strip())), 'agent')
        # Scan the reconciled final settings, not roots that this deployment replaces.
        # Only the new frozen inventory may legitimize a definition.
        if effective_settings is None:
            effective_settings = read_json(Path(generation['path']) / 'defaults/settings.json')
        settings(agent / 'settings.json', effective_settings)
        for directory in (project, *project.parents):
            if directory == home:
                break
            package(directory)
            # Include ordinary dependencies conservatively as well as Pi's npm area;
            # normal packages with no agent/chain declarations are not rejected.
            node_modules(directory / 'node_modules')
            node_modules(directory / '.pi/npm/node_modules')
            definitions(directory / '.pi/chains', 'chain')
        global_root = global_npm_root(home, project)
        if global_root:
            node_modules(global_root)
        return {'offline': global_root is None, 'globalNpmRoot': str(global_root) if global_root else None,
                'extraAgentDirs': os.environ.get('PI_SUBAGENT_EXTRA_AGENT_DIRS', ''), 'path': os.environ.get('PATH', '')}
    except (OSError, ValueError) as error:
        if isinstance(error, Refusal):
            raise
        raise Refusal('cannot completely inspect subagent discovery inputs; activation refused') from error
