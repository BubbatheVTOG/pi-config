# Configuration ownership

Source is not a live deployment target. Never point live paths into mutable source.

| Content | Source owner | Deployed form |
| --- | --- | --- |
| Settings and feature manifest | pi-config, plus explicit optional overlay operations | Local writable `settings.json`; resource paths point into one frozen generation |
| Provider/model definitions | Feature owner, keyed by provider/model ID | Local writable `models.json`; credentials stay outside source |
| Global instructions | Section/feature owner | Local writable `AGENTS.md`, composed from active sections |
| VCC/tasks/tool-display/transcript config | Shared core | Local writable copies with generated baseline receipt |
| Local web tools, splash, plan, pi-improver | pi-config | Stow links only from frozen generation, under `managed/` |
| Theme fallback snapshots | OpenCodeHyperTermTheme | Frozen snapshot resources; never live generated-theme source links |
| Boxed text tools | pi-boxed-tools | Exact upstream commit in generation-local dependency tree |
| Other npm plugins | Their package owners | One combined lock/install in generation-local dependency tree |
| Optional voice extension | agent-voice | Exact upstream archive/hash copied into frozen generation; no fork |
| Auth, sessions, cache, task/issue state | Local Pi runtime/user | Never captured, published, adopted or restored |

Singletons are byte copies (not source symlinks or hardlinks). The deployment receipt
is local and stores generated baselines, not a capture of current credentials.
A later deployment compares old-generated/current/new-generated and refuses conflicts.
Rollback uses the same comparison, preserving later local edits and seed values.

`managed/` is not a Pi auto-discovery root. Generated settings point once to immutable
resource paths there; no second copy is installed into auto-discovery directories.
The `extensions/` directory at the target contains only declared writable plugin
config, not duplicate code. Unknown resources, directories, symlinks and ambient
skill/project discovery are refused, never silently deleted or adopted.

Classify meaningful changes with the user before promotion: **Personal/shared**,
**Enterprise-only**, **Split**, **Local**. Unclassified remains unpublished. Generic
settings for shared packages, including pi-subagents, live only in public core.
Local tweaks are not automatically public, even when reconciliation preserves them.
