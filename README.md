# pi-config

Personal Pi configuration kept in a normal Git repository.

This repository intentionally uses Pi's native package and resource model. It
is not a deployment framework and does not generate configuration snapshots.

## Contents

- `config/settings.json` — native Pi settings baseline, including package specs
- `config/models.json` — model/provider configuration using environment-backed
  credentials where needed
- `config/skills/` — local skills
- `extensions/` — local extensions and plugin configuration
- `config/themes/` — local theme files
- `config/pi-vcc-config.json` — VCC configuration
- `config/tasks-config.json` — task configuration
- `config/transcript-window.json` — transcript-window configuration

## Native package management

List installed packages:

```bash
pi list
```

Install or update a package:

```bash
pi install npm:package@version
pi install git:github.com/user/repository@commit-or-tag
pi update --extensions
```

The current custom bash renderer is installed natively as:

```text
git:github.com/BubbatheVTOG/pi-boxed-tools@2262c69
```

Voice and the local/cloud toggle are native Git packages pinned in
`config/settings.json`. Their code and tests stay in their owning repositories:

- [agent-voice](https://github.com/BubbatheVTOG/agent-voice)
- [pi-local-cloud-toggle](https://github.com/BubbatheVTOG/pi-local-cloud-toggle)

Do not also copy or link these extensions into `~/.pi/agent/extensions/`.
Voice remains inactive without its executable backend; the toggle registers no
controls without an enabled, available local model. Neither guard starts a
backend or installs missing prerequisites. Backend presence does not prove that
playback or inference will succeed. Review and publish plugin fixes in their
own repositories before updating the pins here.

Pi stores global packages under `~/.pi/agent/npm/` and `~/.pi/agent/git/`.
Local runtime state, credentials, sessions, caches, and backups are deliberately
outside this repository.

## Backups

Before substantial changes, back up `~/.pi/agent/` to a private local backup
location. Git protects this source repository; Pi's native package manager
protects package installation and update behavior.

After changing settings or packages, run `/reload` in Pi or start a fresh Pi
process. No custom generation, receipt, or deployment step is required.
