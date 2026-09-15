#!/usr/bin/env python3
"""Compose, lock, freeze, diff and deploy Pi without starting or reloading Pi."""
import argparse
import json
import sys
from pathlib import Path

from composition import Refusal, compose, digest, encoded
from deployment import (deploy, deployment_plan, external, make_lock, plan_digest,
                        prepare, report_plan, verify_generation)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('compose', 'lock', 'prepare'):
        p = sub.add_parser(command)
        p.add_argument('--core', type=Path, default=Path(__file__).resolve().parent.parent)
        p.add_argument('--overlay', type=Path)
        if command != 'compose':
            p.add_argument('--output', type=Path, required=True, help='new destination outside all source repositories')
        if command == 'prepare':
            p.add_argument('--lock', type=Path, help='combined lock directory; required with an overlay')
    for command in ('diff', 'deploy'):
        p = sub.add_parser(command)
        p.add_argument('--generation', type=Path, required=True)
        p.add_argument('--agent-dir', type=Path, required=True)
        p.add_argument('--state-dir', type=Path, required=True)
        p.add_argument('--home', type=Path, required=True, help='target user home, for ambient skill discovery')
        p.add_argument('--project', type=Path, required=True, help='intended working directory; ancestor discovery is audited')
        if command == 'deploy':
            p.add_argument('--expect', required=True, help='reviewed diffDigest (not approval to reload)')
    p = sub.add_parser('verify-generation')
    p.add_argument('generation', type=Path)
    args = parser.parse_args()
    if args.command in ('compose', 'lock', 'prepare'):
        composed, origins = compose(args.core, args.overlay, clean=args.command == 'prepare')
        if args.command == 'compose':
            composed['entryDigests'] = {kind: {name: digest(entry) for name, entry in records.items()}
                                        for kind, records in composed['entries'].items()}
            result = composed
        else:
            roots = [args.core.resolve()] + ([args.overlay.resolve()] if args.overlay else [])
            output = external(args.output, roots)
            if args.command == 'lock':
                make_lock(composed, output)
                result = {'lock': str(output)}
            else:
                if args.overlay and not args.lock:
                    raise Refusal('--lock must name the reviewed combined-union lock with an overlay')
                lock = args.lock or args.core / 'config' / 'dependencies'
                result = prepare(composed, origins, output, lock.resolve())
    elif args.command == 'verify-generation':
        result = verify_generation(args.generation.absolute())
    else:
        generation, agent, state, home, project = (p.absolute() for p in
            (args.generation, args.agent_dir, args.state_dir, args.home, args.project))
        if args.command == 'diff':
            plan = deployment_plan(generation, agent, state, home, project)
            result = {**report_plan(plan), 'diffDigest': plan_digest(plan)}
        else:
            result = deploy(generation, agent, state, home, project, args.expect)
    print(encoded(result).decode(), end='')


if __name__ == '__main__':
    try:
        main()
    except (Refusal, OSError, ValueError) as error:
        print(f'REFUSED: {error}', file=sys.stderr)
        sys.exit(1)
