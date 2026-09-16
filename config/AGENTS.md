# Pi configuration source

This repository is the human-readable source of the personal Pi setup.

- `config/settings.json` is the native Pi settings baseline.
- `config/models.json` contains model/provider configuration without credentials.
- `config/skills/`, `extensions/`, and `config/themes/` contain local resources.
- Third-party packages are installed and updated with Pi's native `pi install`,
  `pi remove`, `pi update`, and `pi list` commands.
- Runtime state, sessions, caches, credentials, package stores, and backups stay
  under `~/.pi/agent/` and are never committed here.
- Do not reintroduce generated generations, deployment receipts, custom lock
  files, or a second package manager around Pi.
