# AGENTS.md — global context for pi on this machine

Global file: loaded in every pi session regardless of cwd. Project `AGENTS.md` /
`CLAUDE.md` files from the working directory and its parents still load on top of
this. Run `/reload` after editing.

## Command-line tools

Prefer these over GNU defaults when constructing bash commands:

| Instead of | Use   | Notes                                          |
| ---------- | ----- | ---------------------------------------------- |
| grep       | `rg`  | recursive by default                           |
| find       | `fd`  | skips hidden/ignored; add `-H`/`-u` to include |
| ls         | `eza` | `-la --icons` for detail                       |
| cat        | `bat` | add `-p` when output is piped or parsed        |
| df         | `duf` |                                                |
| ps         | `procs` |                                              |
| du         | `ncdu` / `duf` |                                       |
| top        | `btop` | interactive monitoring                        |
| man        | `tldr` | practical examples first, then man            |

Also:

- `jq` for any JSON parsing/filtering
- `gh` for GitHub API/PR/issue operations instead of raw curl
- `just` — if a justfile exists, read it and use `just <recipe>` for common tasks
- `hyperfine` for benchmarking commands
- `git` diffs render via `delta` (configured as the global pager)

Caveats:

- These tools colorize output; when piping or parsing, add `-p`/`--plain` or pipe through `cat`.
- For POSIX sh scripts, still use POSIX utilities.
- If a tool is missing, fall back to the GNU default rather than failing the command.
- pi's built-in tool set is `read`, `write`, `edit`, `bash`. There is no built-in grep/find/ls
  tool, so search and listing go through bash with `rg`/`fd`/`eza`.
- Package manifest: `~/git/sigint/dotfiles/install-cli-tools.sh` installs all of these on either host.

## pi workflow

Installed extensions: `pi-subagents`, `@tintinweb/pi-tasks`, `@nguyenquangthai/pi-ask`,
`pi-powerline-footer` (plus `pi-lens`, `@narumitw/pi-btw`).

- **Delegation** — `subagent` spawns focused children. Built-ins: `scout` (codebase recon
  before you understand the code), `researcher` (web research, writes `research.md`),
  `worker` (implementation), `reviewer` (review a diff/change), `oracle` (second opinion
  before acting, no edits), `delegate` (general, behaves like the parent).
  Recommended loop: `clarify → scout → worker → fresh reviewers → worker`.
- **Tasks** — pi-tasks gives `TaskCreate`/`TaskList`/`TaskGet`/`TaskUpdate`/`TaskOutput`/
  `TaskStop`/`TaskExecute` plus `/tasks` and a live widget. Mark `in_progress` before
  starting, `completed` when done. `TaskExecute` and auto-cascade are inert: they expect
  `@tintinweb/pi-subagents`, which is not installed (we use nicobailon's `pi-subagents`).
- **Research** — pi has **no built-in web tools** (built-in set is read/bash/edit/write;
  verified in pi 0.85.1 source). Web capability comes from the local `local-web-search`
  package (`~/.pi/agent/extensions/web-search/`, standard pi package layout, auto-loaded;
  README inside for design/verify/rollback). Owner decision 2026-09-13: pi defaults stay
  untouched — open for extension, closed for modification — extend only with this local
  SearXNG tool (pure `pi.registerTool` addition; no core/settings changes, no npm install):
  `web_search` → local
  **SearXNG** (127.0.0.1:8080, keyless, on-box only; optional `time_range`) returns
  title/URL/snippet; `fetch_content` (+ `get_search_content` alias) → http(s) URL as
  readable text (HTML stripped; 20k-char default, 40k hard cap; localhost allowed for
  vLLM/n8n). Use these tools, not raw curl. If SearXNG is down the tool result includes a
  one-line curl+jq fallback:
  `curl -s 'http://127.0.0.1:8080/search?q=<urlencoded-query>&format=json' | jq -r '.results[:5][] | "\(.title) | \(.url)"'`
  Multi-step web research → delegate to a subagent. Model for the child: **local `vllm/bubba`
  is the default everywhere** (free, 256k ctx); `researcher`/`scout` are pinned to it in
  settings.json. If the local model is down on a retryable failure, retry the launch with an
  explicit `opencode/nemotron-3.5-lightning-free` (free) override — **never add a thinking
  suffix to that model** — the `:off` suffix breaks the opencode endpoint (verified
  2026-09-11). The child uses web_search +
  fetch_content (the global extension loads in child sessions too) and returns **only** a
  distilled brief with URL citations — raw HTML never enters the parent context. Verify claims
  against primary sources.
  No built-in PDF/YouTube/GitHub extraction anymore — use `pdftotext` / `yt-dlp` / `gh` if
  a task needs them.
- **Questions** — `ask_user_question` (pi-ask) for structured 1–4 question dialogs.
- **Config** — `~/.pi/agent/settings.json` (global), `.pi/settings.json` (project).
  Themes are the `hyper-term-*` set in `~/.pi/agent/themes/`; they hot-reload.
  `/reload` picks up changes to extensions, skills, prompts, themes, and context files.
- **Voice output** — local `agent-voice` extension (`~/.pi/agent/extensions/agent-voice/`)
  can speak short hands-free announcements via local TTS (`agent-say`, Kokoro; no cloud,
  no keys). **OFF by default — everything is opt-in.** Precedence, highest wins:
  `AGENT_VOICE_OFF=1` env (kill switch) > `/voice on|off` (session, in-memory) > project
  `agentVoice` in `.pi/settings.json` > global `agentVoice` in `~/.pi/agent/settings.json`.
  `/voice status` shows the resolved config with per-key provenance; `/voice stop` kills
  running announcements. **Source of truth: `~/git/agent-voice`** (git, MIT, pushed) —
  the live `~/.local/agent-say` and `~/.pi/agent/extensions/agent-voice` are symlinks
  into it; `./install.sh` is the one-shot (re)installer; edits through the live paths
  are repo edits. The announcement policy, word budget, full config reference, and the
  evidence behind all of it: `~/git/agent-voice/extension/README.md`.
  When voice is enabled, call `speak` before the final response for a substantial
  user-requested task that just completed, using a concise summary under 45 words.
  Keep routine replies and quick successes silent; never speak logs, code, commands,
  secrets, or paths containing sensitive information.

## Subagents and model selection

**Subagents exist — use them when the work is the right shape for one.** Reach for delegation
when the task is parallelizable, benefits from a second opinion, is read-only recon, or is a
mechanical edit against a clear spec. Don't delegate trivial one-step operations, single-file
edits, or anything that needs the full conversation to be safe.

- Good fits: codebase recon before planning, reviewing a diff, researching a claim,
  independent second opinion on a risky decision, running several checks in parallel.
- Bad fits: "rename this variable", answering from context you already have, anything where
  a wrong guess is expensive and the child lacks the context to catch it.

**Pick the cheapest model that will reliably do the job.** Model choice is the main agent's
discretion, not a fixed default — a summarization pass does not need a frontier model, and a
subtle multi-file refactor does. Thinking level matters about as much as the model: low for
recon and extraction, medium or high for implementation and review.

`opencode-go` catalog as of 2026-09-08, $/million tokens (input / output). Models and prices
move — refresh this table from `~/.pi/agent/models-store.json` during `/skill:self-optimize` passes:

| Tier | Models | Use for |
| ---- | ------ | ------- |
| Cheap | `glm-5.3-flash` 0.075/0.25 · `hy3` 0.14/0.58 · `qwen3.8-flash` 0.15/0.47 · `gpt-5.6-luna` 0.20/1.20 | summarising, classifying, extracting, recon, lookups, mechanical edits |
| Mid | `minimax-m3` 0.30/1.20 · `qwen3.7-plus` 0.40/1.60 | routine multi-file implementation, focused reviews, most delegation |
| Strong | `hy4-preview` 0.83/2.50 · `kimi-k2.7-code` 0.95/4.00 · `glm-5.3` 1.40/4.40 · `grok-4.6` 2.00/6.00 · `kimi-k3` 3.00/15.00 | hard or ambiguous implementation, architecture, subtle bugs, judgment calls |

The session and subagent default is local `vllm/bubba` (free, 256k ctx, reasoning) — cloud
tiers above are only for explicit escalation (per-run `model:` override).

How to set it, strongest precedence first: per-run `model` on the `subagent` call →
`subagents.agentOverrides.<name>.model` → agent frontmatter `model:` →
`subagents.defaultModel` → the parent session model. Use `model: "inherit"` to take the
parent session model explicitly.

Not usable here: `deepseek-v4-flash` and `deepseek-v4-pro` return `403 RegionError` on this
opencode-go account (verified 2026-09-08) — do not pin them.

Baseline pins live in `~/.pi/agent/settings.json` → `subagents.agentOverrides`: `scout` and
`researcher` → local `vllm/bubba`; `researcher` also has
`tools: "inherit"` (its bundled allowlist is read/write only — no shell, so it cannot curl;
verified 2026-09-11); `oracle` → high thinking; `worker`, `reviewer`, `delegate` inherit the
session model (default `vllm/bubba`; settings.json `defaultProvider`/`defaultModel` is
`vllm`/`bubba` as of 2026-09-11). **These are a floor, not a rule.** The main agent decides at
runtime: pass `model:` on the call when a task needs more (or less) than the baseline, and
re-tier when the catalog changes. Do not pass a thinking suffix with
`opencode/nemotron-3.5-lightning-free`. **No auto-fallback since pi-subagents 0.68.0**
(`fallbackModels` removed 2026-09-15): a retryable provider failure (rate limit, overload,
unavailable model, timeout) fails the launch — recover by re-launching with an explicit
`model:` override (e.g. `opencode/nemotron-3.5-lightning-free` for cheap retries).

## This machine

- **GPU**: RTX 3090 (passthrough setup documented in `~/git/QEMU-3090-Passthrough`).
- **Local inference**: vLLM at `https://ai.xorro.tech/v1`, model id `bubba` — 256k context,
  reasoning, `xhigh` thinking. Configured in pi as provider `vllm` in `~/.pi/agent/models.json`
  and in opencode as provider `vllm`.
- **Search**: SearXNG in Docker on `127.0.0.1:8080` (compose: `~/docker/searxng`,
  settings `~/docker/searxng/searxng/settings.yml`, JSON format enabled).
- **Other Docker services**: `n8n` on :5678, `lmfarm-postgres-1` on :5432, `hawser-agent`,
  `watch_tower`.
- Shell is zsh; dotfiles are symlinked from `~/git/sigint/dotfiles`. `mise` manages runtimes.
- Git identity is set globally; `delta` is the pager.

## Coding Principles and Rules

- Keep the functional core separate from the imperative shell. Use straightforward control
  flow when it is clearer or more efficient.
- Do not introduce custom generic abstractions unless they provide meaningful type safety or
  eliminate real duplication.
- Avoid nested control flow: use guards, invert conditions, or extract cohesive operations.
- Prefer immutable records or simple data classes for data.
- Define interfaces only at meaningful boundaries; use default methods only for behavior that
  is safe and broadly applicable.
- Prefer unary or binary functions where practical. For more inputs, introduce cohesive
  parameter objects.
- Write self-explanatory code. Add comments only for non-obvious constraints, decisions, or
  tradeoffs.
- Make it work, then make it correct, then make it fast.
- Apply practical test-driven development.
- Write fast, deterministic tests that do not depend on external services.
- Fail fast and keep the system responsive.
- Avoid hot-path allocations, pre-size collections when their size is known, and profile
  before optimizing allocations.
- Keep reference and variable names consistent with their class names.
- Do not create custom annotations.
- Prefer composition over inheritance.

### SOLID (design decisions: libraries, functional cores, non-trivial refactors —

not throwaway scripts or tests)

- **S — Single responsibility.** One reason to change per module, class, or function; if
  you can't name the responsibility in a single sentence, split it before adding features.
- **O — Open/closed.** Extend behavior (hooks, plugins, overrides, composition) instead of
  modifying working code; never change default or core behavior to add a feature — add it
  around the boundary. (Local example: the pi `web-search` extension — pure
  `pi.registerTool` addition, zero core or settings changes.)
- **L — Liskov substitution.** Subtypes must be substitutable for their base without
  breaking callers. A subclass that special-cases itself, tightens preconditions, or
  weakens postconditions is a design error — restructure instead of patching.
- **I — Interface segregation.** Keep interfaces narrow and role-specific; never force a
  consumer to depend on members it does not use. Split a fat interface rather than
  shipping no-op or default stubs.
- **D — Dependency inversion.** Depend on abstractions (interfaces, protocols, injected
  deps), not concrete classes; high-level policy never imports low-level details — both
  depend on the shared abstraction, and concretes are wired at a composition root.

## Code & git

- Verify before claiming done: run the project's checks/tests when they exist, and say what
  you ran. If you can't verify, say so instead of implying success.
- Use `gh` for GitHub reads/writes; never force-push or rewrite shared history without asking.
- Never commit secrets, keys, or credentials. `~/.pi/agent/auth.json` and `.env` files stay out.
- Prefer small, focused commits with an imperative subject line; match the surrounding
  repository's conventions when they differ.

### Notes, research & scratch files (keep the filesystem clean)

- Research and notes belong in the session transcript, not in files. Do **not** write
  "research"/"report"/"notes" markdown into `$HOME` — owner instruction 2026-09-13: that
  is clutter. Keep findings in context; summarize, don't dump.
- If an artifact must persist (user asked for it, or it's genuine project documentation),
  put it in the project repo (e.g. `docs/`) — never in `$HOME`.
- Scratch/intermediate output goes to `/tmp` only, and is deleted when the task is done.

## Herdr

Sessions on this machine may run inside Herdr (terminal workspace manager).
A `herdr` skill is available — use it when parallel agents, background command
monitoring, or extra terminal panes would help. Verify `HERDR_ENV=1` first;
if unset, you are not inside Herdr and its CLI cannot control the session.
