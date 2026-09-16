# pi-config maintainer instructions

This repository is a personal, Git-backed Pi configuration source. Keep it
portable where practical and keep credentials, sessions, caches, package stores,
and backups outside the repository.

## Working practices

- Stay on `main`; preserve unrelated work and never rewrite history.
- Read the installed Pi and plugin documentation before relying on an API.
- Edit this repository's source files, not installed package internals or live
  runtime copies.
- Use Pi's native package commands for third-party packages:
  `pi install`, `pi remove`, `pi update`, and `pi list`.
- Keep package sources in `config/settings.json`; use normal npm versions or Git
  tags/commits supported by Pi.
- Keep local extensions, skills, and themes in this repository and copy or review
  them into the corresponding `~/.pi/agent/` directories when promoting changes.
- Back up `~/.pi/agent/` privately before substantial runtime changes.
- Never commit credentials, transcripts, caches, package stores, backups, or
  generated runtime state.
- Validate JSON, skill frontmatter, extension tests, and package discovery before
  asking to reload. A source change does not activate itself.

## Ownership

- Generic shared plugin configuration belongs in the repository.
- Provider credentials and machine-local state stay outside the repository.
- Third-party plugin repositories retain ownership of their source.
- Do not add a second package manager, generated configuration generations,
  deployment receipts, custom dependency locks, or ownership-reconciliation layer
  around Pi.

## Activation

Installation, source publication, and `/reload` are separate approvals. Report
exact commands and results, and distinguish static validation from live behavior.
