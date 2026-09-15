---
name: self-optimize
description: Audit and improve pi's own configuration — skills, prompts, subagents, tools, keybindings, themes, and settings — using evidence from real sessions, then apply only the approved changes with backups, validation, and a reload. Finds repetitive work and turns it into a skill, prompt template, alias, or subagent. Use when asked to make pi better, after a session that fought you, or on a periodic review pass. Proposes first; never changes anything unasked.
---

# Self-optimize

Recursively improve pi itself. Every pass should leave pi measurably better at
the work this user actually does — fewer repeated corrections, fewer steps for
common jobs, sharper skills, cheaper models where capability doesn't matter.

**This skill edits pi's own brain.** Optimism is not a safety property here: a
bad edit can break every future session. So: propose, get approval, back up,
change, validate, reload, record.

## Scope: what "pi itself" means

```
~/.pi/agent/
├── settings.json        global settings (model, theme, packages, resources, compaction)
├── models.json          custom providers/models, compat flags, sampling
├── web-search.json      pi-web-access config (SearXNG endpoint, provider keys)
├── AGENTS.md            global context — the durable preferences
├── SYSTEM.md            replaces the system prompt (rarely touch)
├── keybindings.json     shortcut overrides
├── themes/*.json        pi theme files (51 required tokens)
├── skills/**/SKILL.md   this file's peers — on-demand capabilities
├── prompts/*.md         prompt templates, invoked as /name
├── extensions/*.ts      local extensions (tools, commands, UI, events)
├── agents/**/*.md       pi-subagents custom agents
└── sessions/**/*.jsonl  the evidence — real transcripts of real work
```

Also in scope: `~/.agents/skills/` (shared skills), `.pi/` project overrides, and
shell-level glue the agent leans on (aliases, `justfile` recipes, dotfiles).

Out of scope — **never modify**: `auth.json`, session `.jsonl` files, `.env`,
`node_modules/` of installed packages (a `pi update` silently overwrites them —
use settings overrides like `modelOverrides` / `subagents.agentOverrides`
instead), and anything holding credentials.

## The loop

### 1. Snapshot before touching anything

```bash
cp ~/.pi/agent/settings.json ~/.pi/agent/settings.json.bak.$(date +%s)
```

Back up each file you are about to edit. Cheap, and it makes every change a
rollback instead of an apology.

### 2. Gather evidence — do not optimize from vibes

Signals, in rough order of value:

- **Repeated corrections.** The user said "no, don't do X" or "always do Y" more
  than once. That is a missing rule. Search recent transcripts:
  ```bash
  rg -l --glob '*.jsonl' -i 'no,|don.t |stop |instead' ~/.pi/agent/sessions -m1 | tail -20
  ```
- **Repeated multi-step sequences.** The same 4–8 tool calls in the same order,
  more than twice → candidate for a skill, prompt template, alias, or subagent.
- **Failed or retried tool calls.** Errors in transcripts point at a skill with a
  wrong command, a stale path, or a missing precondition.
- **Heavy compaction / long contexts.** Sessions that compact repeatedly have a
  context-hygiene problem: verbose skills, huge context files, or
  `compaction.keepRecentTokens` set wrong.
- **Cost spikes.** Long runs on a strong model doing work a cheap one could do →
  model tiering.
- **Stale facts in config.** Paths that no longer exist (case errors, moved
  repos), commands that no longer work, endpoints that are down.
- **Model catalog drift.** Models get cheaper, better, or disappear. Compare the
  tier table in `AGENTS.md` and the pins in `settings.json` →
  `subagents.agentOverrides` against the live catalog:
  ```bash
  jq -r '.["opencode-go"].models | to_entries[] | [.value.id, .value.cost.input, .value.cost.output] | @tsv' \
    ~/.pi/agent/models-store.json | sort -t$'\t' -k2 -n
  ```
  Propose re-tiering when a cheaper model fits a role, a pinned model vanished, or
  a new one is clearly better for the job. Pins are a baseline; the main agent
  still overrides per run.

### 3. Classify each candidate

| Class | Test | Action |
|---|---|---|
| **Broken** | It doesn't work at all — wrong path, dead endpoint, invalid JSON | Fix now; highest priority |
| **Weak** | It works but is vague, slow, or makes the agent guess | Tighten: add verification, concrete commands, stop conditions |
| **Missing** | The capability doesn't exist and the work is recurring | Add: skill, prompt, alias, recipe, or subagent |
| **Dead** | Nothing invokes it, or it duplicates something better | Propose removal — disable first, delete only on confirmation |
| **Costly** | Right result, wrong model/tool for the job | Reroute: cheaper model, `scout` child, local model |

### 4. Score and pick a short list

Rank by `impact × frequency ÷ risk`. Prefer reversible changes. Bring **at most
3–5 proposals** per pass — a menu of fifteen is a menu nobody reads.

### 5. Propose, don't presume

Use `ask_user_question` before any edit. One question per decision, batched into
a single dialog:

- Which of these fixes to apply (multiSelect, `recommended: true` on the
  highest-value one)
- For a "missing capability", what form it should take: skill vs. prompt
  template vs. shell alias vs. subagent (each option's label carries the
  tradeoff — "skill: loads on demand, carries docs and scripts" vs. "alias:
  fastest, no docs")
- Whether to reload immediately after applying

Never bundle a risky change into a batch of safe ones and hope it rides along.

### 6. Apply safely

- One file at a time for anything structural; batch only trivial, independent edits.
- **Validate JSON** after every settings/theme/keybinding change:
  ```bash
  jq -e . ~/.pi/agent/settings.json >/dev/null && echo "settings ok"
  jq -e . ~/.pi/agent/themes/<name>.json >/dev/null && echo "theme ok"
  ```
- **Validate skill frontmatter**: `name` (lowercase, digits, hyphens; ≤64; no
  leading/trailing or doubled hyphens) and a non-empty `description` (≤1024).
  A skill without a description is silently not loaded.
- **Theme changes**: all 51 required tokens must be present, or pi warns and the
  theme misbehaves.
- Minimal targeted diffs. Never rewrite a working skill wholesale — you will
  silently delete hard-won detail.

### 7. Verify, then reload

Smoke-test that pi still starts clean before declaring victory:

```bash
(sleep 6) | timeout 15 pi --mode rpc --no-session 2>/tmp/pi-err.txt | head -5
cat /tmp/pi-err.txt        # must be empty — extension/skill load errors land here
```

Then `/reload` — it picks up skills, prompts, themes, extensions, keybindings,
and context files. **Settings changes to `packages` need a full restart**, not a
reload; say so instead of letting the user discover it.

If the smoke test is dirty, roll back from the `.bak` immediately and reload.
Do not debug forward into a broken pi.

### 8. Record it

Append to `~/.pi/agent/OPTIMIZATION-LOG.md`:

```markdown
## YYYY-MM-DD — <what and why>
- Evidence: <transcript / repetition / failure that prompted it>
- Change: <file> — <before> -> <after>
- Verified: <command and result>
- Rollback: cp <file>.bak.<ts> <file> && /reload
```

The log is what makes this recursive instead of forgetful: the next pass reads
it, skips what was already done, and looks for regressions of past fixes.

### 9. Schedule the next pass

Offer a cadence rather than guessing: after N sessions, at the end of a session
that went badly, or on demand via `/skill:self-optimize`. Say when you'd look
again and why.

## Turning repetition into capability

When the same work shows up repeatedly, pick the lightest form that solves it:

| Symptom | Best form | Why |
|---|---|---|
| Multi-step with judgment, needs docs or scripts | **Skill** (`skills/<name>/SKILL.md`) | Loads on demand, carries reference files and scripts |
| A prompt you keep retyping | **Prompt template** (`prompts/<name>.md` → `/name`) | One slash command |
| A one-line shell incantation | **Alias / function** in dotfiles | Fastest, zero context cost |
| Project-specific command sequence | **`justfile` recipe** | Discoverable, documented in-repo |
| Work that should happen in parallel or in the background | **Subagent** (`agents/<name>.md`) | Own context, own model, parallelizable |
| Needs a registered tool, event hook, or UI | **Extension** — research first, then build | Last resort — most power, most risk |

Prefer skills and CLI tools over extensions. Extensions are for things that
genuinely need the extension API, not for things that merely feel tool-shaped.

## Research before building or installing

If something that already exists could close the gap, find it before writing it.
Work this order:

1. **Already installed but unused.** Run `pi list`. The capability may be present
   and merely switched off — `pi config` toggles package resources, and a lot of
   "missing features" are really a disabled extension.
2. **Configurable inside something installed.** Read the installed package's own
   docs before adding anything. A flag, an agent file, or a settings override
   (e.g. `subagents.agentOverrides`, `modelOverrides`) usually beats a new package.
3. **A published pi package.** Search npm for the `pi-package` keyword and the
   pi.dev package gallery; check GitHub for the repo.
   - Use `researcher` when the question is open-ended ("what's the best way to do
     X in pi?"); use `web_search` + `fetch_content` directly for a targeted look.
   - Read the package's own README or source, not just the registry blurb.
   - Install forms: `pi install npm:<name>`, pinned `npm:<name>@x.y.z`,
     or `git:host/user/repo@ref`.
4. **Build it** — minimal, and only when nothing fits.

Evaluate a candidate before proposing it:

- **Compatibility** with your pi version (`pi --version`) — check the declared pi
  version or recent issues, not just that it installs.
- **Maintenance** — last publish date, issue volume, abandoned or alive.
- **Collisions** — will it claim a tool or command another installed package
  already owns? Two packages fighting over `subagent` or a slash command is a
  real failure mode, not a hypothetical one.
- **Source review** — pi packages run with full system access. Skim the extension
  entry point before installing: extensions execute arbitrary code, and skills can
  instruct the model to run anything. If you can't read it, say so in the proposal.
- **Removability** — prefer packages that come back out cleanly with `pi remove`
  and don't scatter state across the agent directory.

Then propose it like any other change: one recommendation, why it beats building,
the exact install command, and the fact that **installing a package needs a full
restart**, not just `/reload`. Record installs in the log with source, version,
and reason — a future pass needs to know why it's there before it removes it.

## Guardrails

- **Ask before every change.** The only thing you may do unprompted is read and
  analyze.
- **Back up, then edit.** No backup, no edit.
- **Never touch credentials.** No `auth.json`, no `.env`, no keys in the log.
- **Never delete unprompted.** Disable, confirm, then delete.
- **Never edit installed package internals.** Override through settings instead.
- **Don't break the running session.** Reload only after a clean smoke test.
- **One risky change per pass.** If two changes could each break pi, don't batch them.
- **Never claim an improvement you didn't verify.** Run the thing.

## Anti-patterns

- Optimizing without evidence — adding skills nobody will invoke.
- Rewriting a working skill because it isn't elegant; tighten, don't replace.
- Batching a dangerous change in with safe ones.
- Editing `node_modules/` and being surprised when `pi update` reverts it.
- Reloading into a broken pi and debugging live — roll back first.
- Skipping the log, so the next pass redoes or undoes this one.
- Growing config forever: every addition should have an observed use, or it's
  context tax on every future session.
