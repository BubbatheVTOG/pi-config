# Pi configuration backup

Portable backup and bootstrap configuration for the Pi coding harness.

![Pi opening screen](docs/assets/pi-config-opening.png)

## What this repository contains

- Pi settings and pinned package specifications
- Provider/model configuration using environment-variable credentials only
- All custom themes
- `pi-tool-display` ownership configuration
- Local `web-search` extension source and tests
- `pi-splash.ts`
- Custom skills (`plan`, `self-optimize`)
- Global `AGENTS.md`
- Bootstrap scripts and external-repository notes
- A clean Pi opening-screen capture
- A deliberately busy/dirty workflow capture showing tasks, subagents, LSP,
  diagnostics, tests, bash, and web search:

![Dirty workflow example](docs/assets/pi-config-dirty-workflow.png)

## Security boundary

This repository intentionally contains **no credentials and no logs**.

Excluded permanently:

- `auth.json`
- API keys, tokens, secrets, `.env` files, private keys
- session JSONL files and transcripts
- run history
- task/mission runtime state
- debug logs and package debug output
- model catalogs/cache files
- npm `node_modules`
- Herdr-managed state
- backup files

`config/models.json` references `$VLLM_API_KEY`; the value must be provided by
the target machine's environment, never committed here.

## Recreate on Ubuntu or Asahi Linux

Install the Pi CLI and Git first, then clone this repository:

```bash
git clone git@github.com:BubbatheVTOG/pi-config.git ~/git/pi-config
cd ~/git/pi-config
./bootstrap.sh
```

The bootstrap script:

1. verifies that `pi` is available
2. installs the pinned npm and Git packages from `config/packages.txt`
3. installs the saved settings, models, themes, skills, and local extensions
4. installs the `pi-tool-display` ownership split
5. prints the environment variables still required by the provider config

After bootstrap, run `/reload` in Pi.

## Provider credentials

Set provider credentials outside this repository. For the current vLLM setup:

```bash
export VLLM_API_KEY='…'
```

Do not put that value into `config/models.json`, shell history, or this repo.

## Package and extension inventory

The exact pinned package list is in [`config/packages.txt`](config/packages.txt).
External repositories and machine integrations are documented in
[`EXTERNAL-REPOS.md`](EXTERNAL-REPOS.md).

The local web-search extension uses a SearXNG service at
`http://127.0.0.1:8080` by default. Its source is included under
`extensions/web-search/`; the service itself is intentionally not part of this
repository.

## Verification

The backup includes deterministic renderer tests for the local web-search
extension. Run them after Pi is installed:

```bash
./scripts/verify.sh
```

The verification script checks JSON, scans for forbidden secret/log files,
and runs the local renderer harnesses where the Pi core package is available.

## Files that are intentionally not here

- Pi's CLI installation itself — reinstall/update with `pi update --self`
- Herdr's managed integration — reinstall through Herdr
- `agent-voice` source — maintained in its own repository and listed in
  `EXTERNAL-REPOS.md`
- SIGINT/dotfiles — maintained in its own repository
- SearXNG/Docker — machine service, not Pi configuration
