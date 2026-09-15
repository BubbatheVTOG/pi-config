#!/usr/bin/env python3
"""Refuse ambient Git identities or outgoing metadata unlike repo-local identity."""
import argparse
from pathlib import Path
import re
import subprocess
import sys


def check(root, base=None):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()
    name = git('config', '--local', 'user.name')
    email = git('config', '--local', 'user.email')
    if not name or not email:
        raise ValueError('explicit repository-local public identity is required')
    expected = f'{name} <{email}>'
    for role in ('AUTHOR', 'COMMITTER'):
        ident = git('var', f'GIT_{role}_IDENT')
        match = re.fullmatch(r'(.+ <[^<>]+>) \d+ [+-]\d{4}', ident)
        if not match or match[1] != expected:
            raise ValueError(f'ambient Git {role.lower()} differs from repo-local identity; set explicit overrides before committing')
    if base:
        subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', base, 'HEAD'], check=True)
        rows = git('log', '--format=%an%x00%ae%x00%cn%x00%ce', f'{base}..HEAD').splitlines()
        for row in rows:
            if row.split('\0') != [name, email, name, email]:
                raise ValueError('outgoing commit metadata differs from approved repo-local identity; stop publication')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--base', help='review only commits after this already-approved ancestor')
    args = parser.parse_args()
    try:
        check(args.repo, args.base)
    except (ValueError, subprocess.CalledProcessError) as error:
        print(f'REFUSED: {error}', file=sys.stderr)
        return 1
    print('Public Git identity and requested outgoing metadata checks passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
