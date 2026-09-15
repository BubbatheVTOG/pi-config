# Personal Pi core

A complete standalone personal configuration for Pi 0.85.1, with an optional
explicit overlay. The public core has no private dependencies.

![Pi opening screen](docs/assets/pi-config-opening.png)

## Included

White default and seven upstream theme fallback snapshots; startup splash; enabled
pi-lens; VCC; task/question UI; powerline footer; edit/write diffs, thinking labels
and native user box; boxed text tools; image tools; transcript window; pi-subagents
with upstream tree/FleetView/async defaults; primary `plan`; canonical `pi-improver`
and thin `self-optimize` entry point. Personal provider, npm BTW, voice and SearXNG
are separately owned features, so an overlay can exclude each as a complete unit.

The splash uses the latest tracked overlay implementation with bundled original
80×26 Pi art, not an unavailable home-directory artwork file. Historical screenshots
illustrate the UI but are not evidence of current live activation.

## Safe standalone setup

Prerequisites: installed Pi 0.85.1, Node 24/npm 11, Python 3.12, Git and GNU Stow.
No global installer is included. Clone using HTTPS, review source and dependencies,
and run local checks. **Do not run `pi install` against the live target.**

```bash
python3 scripts/pi-config.py compose
PI_CODING_AGENT_ROOT=/path/to/pi-coding-agent ./scripts/verify.sh

# Requires a clean committed source tree. Only this explicit candidate step
# downloads the reviewed dependencies; lifecycle scripts are ignored.
PI_CODING_AGENT_ROOT=/path/to/pi-coding-agent \
  python3 scripts/pi-config.py prepare --output /outside/source/generations/personal

# Read-only reconciliation; prints changed paths and diffDigest, never values.
python3 scripts/pi-config.py diff \
  --generation /outside/source/generations/personal \
  --agent-dir /target/home/.pi/agent --state-dir /outside/source/deployment-state \
  --home /target/home --project /target/workspace
```

`prepare` uses the public standalone lock under `config/dependencies/`. It never
starts Pi, a service or an agent. Sources and the resulting generation are disjoint.
Live settings are local writable copies, so UI writes cannot edit source.

Only **after separate deployment approval**, repeat the diff arguments with `deploy`
and `--expect <reviewed-diffDigest>`. Deployment does not reload Pi. Obtain separate
reload/restart approval after checking all work is idle. `bootstrap.sh` is now a
safe compatibility entry point for these explicit commands, not a destructive
restore script. There is no default live destination and no automatic adoption.

Existing unmanaged installations intentionally refuse deployment. Do not solve a
refusal with `rm -rf` or `stow --adopt`. Inventory, classify and resolve ownership
with the user first. For credentials use environment references or Pi's local auth
store; never copy secrets into this repository or generation defaults.

## Composition and maintenance

See [composition/deployment](docs/composition.md) for the schema, CLI, union-lock
procedure, reconciliation and rollback boundaries. [OWNERSHIP.md](OWNERSHIP.md)
describes source versus local state; [EXTERNAL-REPOS.md](EXTERNAL-REPOS.md) records
independent owners and machine prerequisites. [AGENTS.md](AGENTS.md) is the maintainer
contract, including classification before promotion and reviewed public-main workflow.

Generic changes to shared plugins belong in this core. Only environment-specific
routing/compatibility belongs in an overlay. Do not duplicate shared settings there.
Missing async UI is not proof of a disabled widget; no such fix is claimed here.

## Tests and trust boundary

```bash
PI_CODING_AGENT_ROOT=/path/to/pi-coding-agent \
PI_CANDIDATE_DEPENDENCIES=/disposable/candidate/dependencies ./scripts/verify.sh
```

Checks cover composition/exclusion/drift, real Stow against synthetic targets,
rollback preserving later edits/seeds/credential sentinels, no write-through,
ambient resource refusal, source-owned UI regressions and pinned boxed-tools when
candidate dependencies are provided. No model, audio or network request is used by
tests. Package fetching occurs only in explicit `lock`/`prepare` operations.

Extensions run with the user's full permissions. Declared inventory, static checks
and no-network mocks are **not a sandbox** or proof about arbitrary plugin behavior.
Review dynamic registrations, package lifecycle changes and project discovery before
activation. Credentials, transcripts, logs, caches and generated artifacts remain local.
