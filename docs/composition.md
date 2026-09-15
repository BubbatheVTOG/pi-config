# Composition, candidate dependencies and deployment

## Contract

The personal core is standalone. `--overlay <repository>` is optional and is the
only overlay input; the composer has no environment-specific paths or knowledge.
Sources must be repository roots. A snapshot requires clean committed inputs and
is fixed to both source commits and SHA-256 input digests. It contains only selected
resource copies, dependency artifacts, generated defaults and a generation receipt,
not a copy of either source repository. Never publish generation/state directories.

## Manifest interface

`manifest.json` has exactly `schema: 1`, `features` and `entries`. Feature keys are
stable lowercase IDs with a `description`. `entries` has six identity maps:

| Map | Key | Value |
| --- | --- | --- |
| `packages` | npm identity, including scoped name | `{spec, filters?}`; exact npm version or HTTPS archive URL ending in a 40-hex commit |
| `resources` | relative deployed resource ID/path | `{type, source}` or `{type, archive: {url, sha256, path}}` |
| `settings` | JSON pointer such as `/retry/maxRetries` | Any explicitly declared JSON value; arrays replace as a unit |
| `providers` | provider ID | Provider object without `models` |
| `models` | `provider/model-id` | Model object with matching `id` |
| `instructions` | section ID | Markdown text |

Every entry has `feature`, `owner` and exactly one of `value` or `source`.
A top-level `source` reads a JSON or Markdown source file; optional `pointer`
selects a JSON object member. Source paths are anchored to the declaring repository,
not cwd, settings location or the other repository. No `..`, absolute paths, source
symlinks or special files. `resources.value.source` names the file/tree to snapshot.

Optional entry fields:

- `shared: true` prohibits overlay replacement/removal of shared values. Shared
  pointer overlaps and exclude/re-add shadowing also fail. Explicit whole-feature
  exclusion is permitted, but cannot replace a shared package with another version.
- `claims: ["tool:example", "command:example", "skill:example", "renderer:example"]`
  declares reviewed capability ownership; repeated claims fail even for one owner.
- `requires: ["feature-id"]` makes surviving dependencies on an excluded feature
  fail instead of silently leaving broken references. Declare plugin references,
  config fragments and instructions with their feature, not in an unrelated section.

Resource types `extensions`, `skills`, `prompts`, `themes` are explicitly loaded
from the frozen generation. `data` is copied but not loaded. `copy` makes a JSON
plugin config a local writable singleton at the resource ID/path. `seed` initializes
a JSON local file only if absent and never overwrites it. Do not put executable Pi
resources in copy/seed paths. `settings.json`, `models.json`, `AGENTS.md`, `auth.json`
and `trust.json` are reserved. Plugin configuration that contains environment-only
routing should be a separately owned declaration, not a duplicate shared config.

The composer validates declaration shape, ownership, duplicate claims, resource
paths, provider/default/subagent model references and feature closure. It does not
pretend to understand every arbitrary plugin's configuration schema or code. A new
plugin/key needs source/docs review and targeted tests. No unknown live resource or
new undeclared live JSON key is automatically adopted.

## Overlay interface

An overlay root contains `overlay.json`:

```json
{
  "schema": 1,
  "coreDigest": "<coreDigest from compose>",
  "features": {"extra": {"description": "Optional example capability"}},
  "operations": [
    {"op": "exclude", "feature": "voice"},
    {"op": "add", "kind": "instructions", "id": "example",
     "entry": {"feature": "extra", "owner": "example", "value": "Use approved examples."}}
  ]
}
```

Operations run in order:

- `add`: absent identity only; provide `kind`, `id`, `entry`.
- `replace`: existing identity only; provide `kind`, `id`, `entry` and `expect`.
- `remove`: existing identity only; provide `kind`, `id` and `expect`, no entry.
- `exclude`: provide `feature`; removes its declarations across all six maps.

`expect` is the SHA-256 of the canonical **materialized entry**, including owner,
feature and value. `compose` prints `entryDigests` for this purpose. `coreDigest`
binds the overlay to actual core inputs. No implicit last-writer-wins merge, array
concatenation, unknown operation, conflicting add or drifted replacement is allowed.
Providers/models are not merged as ordinary arrays: model identities are composed
first, and Pi's model array is emitted only at generation time.

Keep generic plugin changes in core. Both setups inherit the same pi-subagents
package and shared settings; do not invent a second private package or copy generic
UI/default configuration. Upstream tree/FleetView/async widget defaults remain on.
Only explicitly environment-specific routing/compatibility belongs in the overlay.
New resources and private skills need their own feature/owner and collision checks.

## Complete union lock

Public lock files live under `config/dependencies/`:

- `package.json`: exact complete dependency map, including the pinned boxed-tools archive.
- `package-lock.json`: npm lockfileVersion 3, complete resolution/integrity graph.
- `binding.json`: `coreDigest`, combined `inputDigest`, dependency manifest digest,
  `scripts: "ignore"`, `peerPolicy: "host-provided"`.

For a changed core or any overlay, generate **one complete union** into a new
**disposable** directory, never by concatenating locks or sequential installations:

```bash
python3 scripts/pi-config.py lock --overlay /path/to/overlay --output /tmp/union-lock
```

Omit `--overlay` for standalone. Review the three files before copying them into the
appropriate source lock directory. Rebind/regenerate after any input change, even
if versions did not move. Core inputs include the manifest, referenced source bytes
and composition/deployment/inventory/verification scripts, not the dependency lock itself. Overlay
inputs include its manifest and selected resource/source bytes. Repositories' commit
IDs are recorded separately so committing the reviewed lock does not create a hash
cycle. Do not commit disposable installs or current live settings.

`lock` performs one `npm install --package-lock-only`; `prepare` performs one `npm ci`
in a new generation. Both ignore lifecycle scripts, isolate npm config/cache/home,
disable audit/fund calls, and use host-provided Pi peers. All locked artifacts must
have HTTPS resolution and integrity. Normal proxy and TLS certificate policy is inherited; npm auth and user npmrc are
not. CLI status JSON stays on stdout and npm progress/errors on stderr. No install
runs in source or the live target. Failures stop; there is no alternative agent protocol or startup repair install.

`prepare --overlay` requires `--lock /path/to/reviewed/union-lock`. The public lock
cannot be reused for a changed union. Package entries in effective settings become
`{source: "/absolute/generation/dependencies/node_modules/name", ...filters}`.
Filter keys, empty arrays, `!pattern`, `+path` and `-path` values remain byte-for-byte
JSON values, relative to that package root. Do not expand them relative to settings.

## Frozen deployment and reconciliation

`prepare` requires clean inputs, a bound lock and a new output path outside both
repositories. It installs dependencies, copies selected resources, writes defaults,
records an inventory and marks the tree read-only. A generation cannot be moved:
settings use anchored absolute paths. Parent-traversal (`..`) and symlink-ancestor
aliases are refused for generation, target and state paths before writes; containment
and target/state disjointness use canonical paths. Immutable single files and trees
preserve executable intent before read-only freezing. Integrity checks include that
executable intent and are rerun before diff/deploy.
Set `PI_CODING_AGENT_ROOT` to the installed Pi package. A Pi-0.85.1-bound adapter
runs only Pi's filesystem resource discovery in an isolated temporary home, using
the exact package filters; it records discovered paths and checks skill/prompt/theme
names for collisions. It starts no extension factories or session. A different Pi
version requires adapter review, not a silent fallback. Read-only permissions are
an accident guard, not a security sandbox.

`diff` requires explicit `--generation`, `--agent-dir`, `--state-dir`, `--home` and
`--project`. It is read-only and prints changed paths, preserved files and a
`diffDigest`, never local values. It inspects the intended working directory's
ancestor Pi/agent discovery paths and the target user's shared skill root; unknown
resources fail. The pi-subagents 0.68 inventory also inspects root/package declarations
(`pi-subagents` and `pi.subagents` agents/chains), scoped and unscoped npm packages,
settings package sources, user/default agent and chain roots, `.pi/chains`,
`subagents.agentScanDirs` (including its supported single-directory wildcard), and
`PI_SUBAGENT_EXTRA_AGENT_DIRS`. Ordinary dependencies without declarations are allowed;
unowned definition candidates and unreadable/malformed discovery inputs refuse.
The scan is conservative across project ancestors and ordinary `node_modules` too;
exclusion settings do not authorize otherwise unowned definitions.

Unless `PI_OFFLINE` is `1`, `true` or `yes` (case-insensitive, matching upstream),
preflight uses a bounded read-only `npm root -g` with the intended target HOME/PATH
and npm environment, then inspects relevant package metadata there. Timeout or
ambiguous output refuses, with npm stderr suppressed. No package code is executed,
no network/install is requested, and no prompt bodies are read by this scan. Offline
mode, resolved global root, PATH and extra-agent roots are bound into the reviewed
diff digest. Use the **same intended runtime mode/environment** at preflight and
activation; offline tests do not certify omitted global resources for online use.
Run it for the actual deployment home/project, not fictional paths. Changing cwd,
mode, discovery environment or future CLI resource flags requires another inventory
review. This does not sandbox arbitrary future project or plugin behavior.

`deploy` requires the same arguments plus `--expect <diffDigest>` after deployment
approval. A local lock serializes deployments; the digest and per-file checks catch
concurrent drift. Stow uses only `generation/stow/agent`, with `--no-folding`; it never
uses mutable source or `--adopt`. Writable singletons are atomic local copies, with
mode 0600. Their generated baselines and link ownership live in the local receipt.

Reconciliation compares old-generated, current and new-generated:

- unchanged current takes new defaults;
- unchanged generator preserves a known local edit;
- equal new/current converges;
- objects merge per key; ordinary arrays and instruction text are atomic;
- unknown local JSON keys and competing edits refuse before target mutation;
- resource package/path lists and renderer ownership cannot drift locally;
- default and subagent model references must remain in effective inventory;
- existing unowned singletons refuse, even if their bytes happen to match;
- seeds are not overwritten; auth and runtime state, including subagent missions,
  are not read or captured;
- Pi's automatic `lastChangelogVersion` metadata is preserved locally when it is
  a valid version string; it is not promoted into source defaults. Other unknown
  settings keys still require review.

Roll back by diffing/deploying an earlier intact generation through the **same**
three-way comparison. Never restore a stale settings backup over later edits or
credentials. A changed removed file causes a conflict rather than deletion. A local
preference intended for promotion must be re-expressed in the classified owner source;
there is intentionally no automatic source-capture/export command.

## Limits and failure recovery

Deployment is not a multi-file filesystem transaction. A journal is written before
mutation. Interrupted Stow/I/O or a late concurrent write leaves it in place and
blocks further deployment, rather than attempting a destructive rollback. Stop the
affected workflow; the owner must compare the planned receipt, old generation and
actual target, preserve later edits, and approve recovery. Never blindly delete a
journal to retry. Keep Pi idle during deployment: advisory locks cannot prevent an
uncooperative process writing between the final check and atomic replacement.

Before any public commit, explicitly set `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`,
`GIT_COMMITTER_NAME` and `GIT_COMMITTER_EMAIL` from the approved repo-local public
identity, and run `python3 scripts/check-public-identity.py --base origin/main` in
that environment. Repo config alone does not outrank ambient identity variables.
The check refuses mismatches without printing the unexpected identity. Verify the
resulting commit's identity, exact tree and ancestry again before publication.

There is no automatic migration/adoption of existing unmanaged installations. The
initial owner inventory is a separate human-reviewed prerequisite. Unknown paths
are never silently deleted. Additional runtime state names may require a reviewed
allowlist change; an unknown cache is not permission to skip the whole directory.

Declared capability claims are a review aid, not arbitrary-plugin static analysis.
Extensions can dynamically register tools/providers, discover more resources, start
processes or interpret their own config. Pi trust is not a sandbox. The filesystem
inventory rejects unmanaged resources; it cannot prove malicious plugin behavior
safe. Project context files and later resource flags also remain subject to Pi's
own loading rules. Validate the actual chosen package/filter union before activation,
with synthetic mocks and any separately approved live checks clearly distinguished.
