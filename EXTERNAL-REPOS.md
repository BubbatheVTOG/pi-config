# External repositories and machine integrations

These are intentionally referenced instead of vendored into this backup.
Clone them only if the target machine needs the corresponding feature.

| Component | Repository | Setup |
| --- | --- | --- |
| `pi-boxed-tools` | `git@github.com:BubbatheVTOG/pi-boxed-tools.git` | Installed from `config/packages.txt` |
| `agent-voice` | `git@github.com:BubbatheVTOG/agent-voice.git` | Clone to `~/git/agent-voice`, then link `extension/` into Pi extensions |
| SIGINT/dotfiles | `git@github.com:BubbatheVTOG/SIGINT.git` | Provides `ask-herdr-notify.ts` and other machine dotfiles |
| Herdr | Herdr-managed integration | Reinstall through Herdr; do not copy `herdr-agent-state.ts` |
| SearXNG | local Docker service | Run separately at `127.0.0.1:8080` for the included web-search extension |

The backup does not clone private repositories automatically. The bootstrap
script creates the local extension directory and installs the self-contained
pieces; external private repositories are an explicit follow-up step.
