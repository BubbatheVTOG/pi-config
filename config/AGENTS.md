# AGENTS.md — global context for pi on this machine

Global file: loaded in every Pi session regardless of cwd. Project `AGENTS.md` /
`CLAUDE.md` files from the working directory and its parents still load on top of
this. The authoritative copy lives in `~/git/pi-config/config/AGENTS.md`; the live copy is
`~/.pi/agent/AGENTS.md`. Run `/reload` after editing.

## Presenting information

Choose the shape that makes the relationship visible. Prose is the fallback, not the default.

| Content                                          | Shape                                               |
| ------------------------------------------------ | --------------------------------------------------- |
| items with two or more comparable attributes     | table                                               |
| options with trade-offs                          | table: one row per option, one column per criterion |
| ordered steps or phases                          | numbered list                                       |
| branching flow, retries, state or status changes | ASCII diagram                                       |
| file layout, ownership, or data shape            | ASCII tree or labelled boxes                        |
| before/after, migration, or change summary       | two-column table (`before` / `after`)               |
| a single fact or a one-sentence answer           | prose                                               |

- Lead with the conclusion, then the table or diagram that supports it. Do not make the reader
  assemble the summary from the detail.
- Keep tables narrow enough to read without horizontal scrolling, with a header that names what
  every column holds. Short cells belong in the table; long prose belongs in a sentence under it.
- Diagrams are plain ASCII or box-drawing characters, never Mermaid: the reader is a terminal.
- Label every state, edge, and direction; an unlabelled box is decoration.
- One idea per diagram. Split into two rather than nesting one inside the other.
- Keep row order stable across a comparison so the difference stands out, and align numbers on
  their digits.
- Never decorate a one-line answer with a table, and never let a table replace the sentence that
  explains it.

## Autonomy threshold

Act on your best judgment when you are confident; ask only when you are not.

```text
decision point
   │
   ├─ requirement missing, or an approval gate applies ────► ask
   │
   └─ confidence ≥ threshold?
        ├─ yes ──► take the most confident option, state it in one line
        └─ no  ──► ask one batched question
```

- **Default threshold: 70%.** At or above it, choose the option you judge most likely to be
  right and continue; say which one you chose and why in one line, not a paragraph. Below it,
  ask.
- The threshold is session state, not a constant: when the user says "set autonomy to 85%" or
  "ask me more", use that value for the rest of the session and state the new value once. It
  returns to 70% in the next session unless the user asks to change this file.
- A higher threshold means more confidence is needed before acting without asking, so you ask
  more often; a lower one means you act on thinner evidence. Keep it above 50%.
- Ask at most one decision-relevant question, batched through `ask_user_question` with concrete
  2–4 options, and only when the answer would actually change what you do next. Never ask for
  permission to narrate your reasoning.
- The threshold never overrides an approval gate or a safety rule: destructive or irreversible
  operations, credentials, spending, publishing, rewriting shared history, and anything else
  this file marks as needing approval still ask, whatever your confidence.
- Prefer a cheap reversible experiment over a question: if you can try a path and undo it, do
  that and verify instead of interrupting.
- Uncertainty about the requirement is not the same as uncertainty about the answer. A missing
  requirement is asked about regardless of confidence.

## Command-line tools

Prefer these over GNU defaults when constructing bash commands:

| Instead of | Use            | Notes                                          |
| ---------- | -------------- | ---------------------------------------------- |
| grep       | `rg`           | recursive by default                           |
| find       | `fd`           | skips hidden/ignored; add `-H`/`-u` to include |
| ls         | `eza`          | `-la --icons` for detail                       |
| cat        | `bat`          | add `-p` when output is piped or parsed        |
| df         | `duf`          |                                                |
| ps         | `procs`        |                                                |
| du         | `ncdu` / `duf` |                                                |
| top        | `btop`         | interactive monitoring                         |
| man        | `tldr`         | practical examples first, then man             |

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
- Pi provides native `read`, `write`, `edit`, `bash`, `grep`, `find`, and `ls` tools. Use the
  dedicated tools for file operations and code search; use `rg`/`fd`/`eza` inside bash when
  constructing shell commands.
- Package manifest: `~/git/sigint/dotfiles/install-cli-tools.sh` installs all of these on either host.

## pi workflow

Packages are managed by `pi` (`pi list`, `pi install`, `pi remove`, `pi update`); do not keep a
second list here. Local extensions and skills load from `~/.pi/agent/`.

- **Delegation** — `subagent` spawns focused children; built-ins are `scout`, `researcher`,
  `worker`, `reviewer`, `oracle`, and `delegate`. Recommended loop:
  `clarify → scout → worker → fresh reviewers → worker`.
- **Tasks** — pi-tasks gives `TaskCreate`/`TaskList`/`TaskGet`/`TaskUpdate`/`TaskOutput`/
  `TaskStop`/`TaskExecute`, `/tasks`, and a live widget. Create tasks for 3+ step work, mark
  `in_progress` before starting and `completed` when done. `TaskExecute` and auto-cascade are
  inert: they need a subagents extension speaking pi-tasks' `subagents:rpc` protocol, which
  nicobailon's `pi-subagents` does not implement — delegate with the `subagent` tool instead.
- **Research** — `web_search` uses SearXNG where a backend is available; do not assume it is
  installed or start one. `fetch_content` and `get_search_content` fetch URLs directly. Without
  search, use known primary-source URLs or report the limitation. Search is for discovery, then
  fetch primary sources; prefer the `researcher` subagent for multi-angle work and reach for
  `pdftotext`, `yt-dlp`, or `gh` when a task needs those formats. Return a cited brief, not raw
  HTML.
- **Questions** — `ask_user_question` (pi-ask) for structured 1–4 question dialogs.
- **Config** — `~/.pi/agent/settings.json` (global), `.pi/settings.json` (project). Themes are
  the `hyper-term-*` set in `~/.pi/agent/themes/`; they hot-reload. `/reload` picks up
  extensions, skills, prompts, themes, and context files.

## Subagents

**Use subagents when the work benefits from delegation.** Good fits include codebase recon,
research, independent review, parallel checks, and mechanical edits with a clear spec. Do not
delegate trivial one-step operations or work where the child lacks the context to be safe.

Choose a model and thinking level appropriate to the task. Keep model names, provider defaults,
pricing, and fallback behavior in Pi's live settings and package documentation rather than in
this general instruction file.

## Coding Principles and Rules

### General

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
- For behavior changes, write or update a focused test first when practical. For documentation,
  configuration, and mechanical changes, use the checks appropriate to the change; do not add
  a test solely to satisfy a test-first rule.
- Write fast, deterministic tests that do not depend on external services.
- Fail fast and keep the system responsive.
- Avoid hot-path allocations: pre-size collections when their size is known, and prefer
  arena, region, or pool allocation for many short-lived values sharing a lifetime where the
  runtime supports it. Profile before optimizing allocations.
- Keep reference and variable names consistent with their class names.
- Do not create custom annotations.
- Prefer composition over inheritance.

### Complexity

Optimize for the next reader: cognitive complexity decides, cyclomatic complexity supports it.

- Small, single-purpose functions; a name needing "and" or "or" means split.
- Extract a block into a well-named function when it needs a comment to explain it.
- Nest at most two levels; deeper means early return, `continue`, or a helper.
- Handle invalid, empty, and error cases first; keep the happy path unindented and last.
- Extract named predicates instead of `&&`/`||` chains with negations; no double negation or
  inverted flags.
- Replace flag parameters with separate functions or an explicit type.
- Prefer data-driven dispatch over `if`/`else if`/`switch` chains with like branches.
- Nest ternaries at most one level.
- Never compress code to cut line count; dense lines trade a metric for cognitive load.
- Cyclomatic complexity at or below 10 per function; 15 is a hard stop.
- Refactor before extending, so restructuring is separate from the behavior change.
- A change that adds a branch should remove one; a net increase needs a stated reason.

### Organization

Structure is design, and it is a stronger lever on complexity than any single function.

- Prefer deep modules: a small stable interface over a substantial hidden implementation.
- Group files by what they do together, not by what they are.
- Nest a directory only where the level names a real boundary; flat is right for one concept.
- No catch-all `utils/`, `common/`, or `helpers/`, and no new layer to postpone a decision.
- Move code as you work; a misplaced function moves now, even into a new file.
- Keep moves complete: update imports, exports, and call sites in the same change.
- Leave no re-export shims, duplicated copies, or half-moved code behind.
- Reduce cross-cutting: shared behavior lives in one place and is imported, not copied.
- Never reimplement an existing capability; when two callers need it, extract a module both
  depend on, so there is one implementation and one place to fix it.
- DRY is about knowledge, not appearance; lookalike code encoding different rules stays apart.
- Split a file that accumulates unrelated responsibilities.

### Logging

- Use an established library; never hand-roll a logger, formatter, or sink.
- Structured single-line records with stable field names (JSON where supported).
- A correlation id on every record, propagated explicitly across boundaries.
- Timestamps are UTC in RFC 3339 / ISO 8601 form with fixed-width fractional seconds
  (`2025-01-15T14:23:05.123Z`), so they sort lexicographically and parse everywhere. Local
  and space-separated forms are for human display only, never the logged value, and never a
  locale-dependent format.
- Durations from a monotonic clock, timestamps from wall clock, both injected so tests can
  control time.
- Log once, where the failure is recovered, reported, or returned; never log-and-rethrow.
- Error records stand alone: what failed, on what, and why, with enough context to act.
- Preserve the cause chain; log the underlying error once with its message and stack.
- ERROR means a human must act; expected failures are INFO or WARN.
- WARN means degraded but handled: fallback taken, retry that succeeded, deprecated path.
- INFO records lifecycle and state transitions, never each item in a loop.
- DEBUG is diagnosis only, and is off in production.
- Never log secrets, credentials, tokens, keys, or personal data; redact in the logging layer.
- No logging in hot paths or tight loops; sample, aggregate, or drop it.
- Logging is not error handling; a failure that changes control flow needs a returned error.

### IO and network logging

- One record per call crossing a process, network, or storage boundary, emitted by the module
  that makes it.
- Record target, correlation id, timestamp, outcome status, and elapsed duration together.
- Request and response share one record; a call failing before a response still emits one.
- Headers and bodies by data class, not by default: include them when the payload explains
  the failure.
- Otherwise log content type and byte length, size-capped; never dump large or binary bodies.
- Redact authorization headers, cookies, tokens, keys, and personal data before writing.
- Measure elapsed time in the client from the injected clock; callers do not duplicate it.

## Code & git

- Verify before claiming done: run the project's checks/tests when they exist, and say what
  you ran. If you can't verify, say so instead of implying success.
- Use `gh` for GitHub reads/writes; never force-push or rewrite shared history without asking.
- Never commit secrets, keys, or credentials. `~/.pi/agent/auth.json` and `.env` files stay out.
- Prefer small, focused commits with an imperative subject line; match the surrounding
  repository's conventions when they differ.

## Configuration and activation

- Keep source configuration separate from runtime state. Edit authoritative source files in
  `~/git/pi-config`, then review and promote them into `~/.pi/agent/` deliberately.
- Pi packages are managed natively with `pi install`, `pi remove`, `pi update`, and `pi list`.
  Do not reintroduce generated generations, deployment receipts, custom lockfiles, or a second
  package manager around Pi.
- Runtime settings, credentials, sessions, caches, and installed package stores are local
  state. Never commit credentials, transcripts, caches, or private configuration.
- Installation, publication, and `/reload` are separate actions. A source edit does not
  activate itself. Verify JSON, frontmatter, extension tests, and package discovery first.
- When voice is enabled, use `speak` for failures, requests needing user input, long-running
  completion, or substantial completed user work. Keep routine replies silent and never speak
  logs, code, commands, credentials, or sensitive paths.

## Herdr

Sessions on this machine may run inside Herdr (terminal workspace manager).
The `herdr` skill is materialized in this repository
(`config/skills/herdr/SKILL.md`, promoted to `~/.pi/agent/skills/herdr/`) — use it
when parallel agents, background command monitoring, or extra terminal panes
would help. Verify `HERDR_ENV=1` first; if unset, you are not inside Herdr and its
CLI cannot control the session. `herdr --skill` remains the upstream authority for
current command syntax; re-capture the skill file after a Herdr update.
