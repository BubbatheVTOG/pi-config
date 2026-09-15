# Configuration ownership map

The live filesystem is a deployment target. Source files belong to one
repository only; live Pi paths should symlink back to that owner.

| Live path | Owner | Boundary |
| --- | --- | --- |
| `~/.pi/agent/settings.json` | `pi-config` | Repository-owned settings and package specs |
| `~/.pi/agent/models.json` | `pi-config` | Provider/model definitions; credentials remain in environment |
| `~/.pi/agent/AGENTS.md` | `pi-config` | Global Pi instructions |
| `~/.pi/agent/themes/` | `OpenCodeHyperTermTheme` | Generated Pi theme output; `pi-config/config/themes/` is a fallback snapshot only |
| `~/.pi/agent/skills/` | `pi-config` | Backed-up custom skills |
| `~/.pi/agent/extensions/web-search/` | `pi-config` | Local web-search extension |
| `~/.pi/agent/extensions/pi-splash.ts` | `pi-config` | Local startup splash |
| `~/.pi/agent/extensions/pi-tool-display/config.json` | `pi-config` | Renderer ownership/configuration |
| `~/.pi/agent/npm/package.json` | `pi-config` | npm package manifest snapshot |
| `~/.pi/agent/npm/package-lock.json` | `pi-config` | npm lock snapshot |
| `~/.pi/agent/extensions/agent-voice/` | `agent-voice` repo | Symlink into `~/git/agent-voice/extension` |
| `~/.pi/agent/extensions/ask-herdr-notify.ts` | SIGINT repo | Symlink into SIGINT/dotfiles |
| `~/.pi/agent/extensions/herdr-agent-state.ts` | Herdr | Generated/managed; never hand-edit or back up |
| `~/.pi/agent/sessions/` | Pi runtime | Local state; never commit |
| `~/.pi/agent/auth.json` | Pi runtime | Secret; never copy |
| `~/.pi/agent/*-cache/` | Pi/runtime services | Generated cache; never commit |

## Repository boundaries

- `~/git/pi-config` owns portable Pi configuration and local extensions that
  are intentionally bundled in this backup. Its `config/themes/` directory is
  a fallback snapshot, not the preferred live theme source.
- `~/git/OpenCodeHyperTermTheme` owns the OpenCode source themes and generated
  Pi themes under `pi/themes/`; its generator may update the live Pi theme
  directory.
- `~/git/pi-boxed-tools` owns the published boxed-tool package. Pi installs it
  from its GitHub remote; `pi-config` does not duplicate its source.
- `~/git/agent-voice` owns the voice extension and its implementation.
- `~/git/sigint` owns SIGINT/dotfiles, including the Herdr notification hook.
- Other repositories under `~/git` own unrelated projects and must not absorb
  Pi configuration merely because a symlink points into them.

There are currently no nested `.git` directories under `~/git`; the
`sigint/dotfiles` directory is content inside the SIGINT repository, not a
second repository.
