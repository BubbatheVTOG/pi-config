# AGENTS.md — global context for pi on this machine

Global file: loaded in every Pi session regardless of cwd. Project `AGENTS.md` /
`CLAUDE.md` files from the working directory and its parents still load on top of
this. The authoritative copy lives in `~/git/pi-config/config/AGENTS.md`; the live copy is
`~/.pi/agent/AGENTS.md`. Run `/reload` after editing.

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
- Pi provides native `read`, `write`, `edit`, `bash`, `grep`, `find`, and `ls` tools. Use the
  dedicated tools for file operations and code search; use `rg`/`fd`/`eza` inside bash when
  constructing shell commands.
- Package manifest: `~/git/sigint/dotfiles/install-cli-tools.sh` installs all of these on either host.

## pi workflow

Installed packages include `pi-subagents`, `@tintinweb/pi-tasks`,
`@weihannpmgo/pi-ask-user-question`, `pi-foot` (the footer), `pi-lens`,
`pi-tool-display`, `pi-vcc`, and other packages listed by
`pi list`. Local extensions and skills are loaded from `~/.pi/agent/`.

- **Delegation** — `subagent` spawns focused children. Built-ins: `scout` (codebase recon
  before you understand the code), `researcher` (web research, writes `research.md`),
  `worker` (implementation), `reviewer` (review a diff/change), `oracle` (second opinion
  before acting, no edits), `delegate` (general, behaves like the parent).
  Recommended loop: `clarify → scout → worker → fresh reviewers → worker`.
- **Tasks** — pi-tasks gives `TaskCreate`/`TaskList`/`TaskGet`/`TaskUpdate`/`TaskOutput`/
  `TaskStop`/`TaskExecute` plus `/tasks` and a live widget. Mark `in_progress` before
  starting, `completed` when done. `TaskExecute` and auto-cascade are inert: they expect
  `@tintinweb/pi-subagents`, which is not installed (we use nicobailon's `pi-subagents`).
  For multi-step work (3+ distinct steps), proactively create tasks with `TaskCreate` and
  keep statuses updated as work progresses — do not wait to be asked.
- **Research** — when enabled, `web_search` uses SearXNG (`SEARXNG_URL`, default
  `127.0.0.1:8080`). The work overlay disables search where no backend is available;
  do not assume SearXNG is installed or try to start it. `fetch_content` and
  `get_search_content` fetch URLs directly and do not require SearXNG. Use only
  available tools; without search, use known primary-source URLs or report the
  discovery limitation. Search is for discovery; fetch primary sources before
  relying on claims. Prefer the `researcher` subagent for multi-angle research
  when its required tools are available. Return a distilled brief with URL citations
  rather than raw HTML. Use `pdftotext`, `yt-dlp`, or `gh` when a task needs those formats.
- **Questions** — `ask_user_question` (pi-ask) for structured 1–4 question dialogs.
- **Config** — `~/.pi/agent/settings.json` (global), `.pi/settings.json` (project).
  Themes are the `hyper-term-*` set in `~/.pi/agent/themes/`; they hot-reload.
  `/reload` picks up changes to extensions, skills, prompts, themes, and context files.

## Subagents

**Use subagents when the work benefits from delegation.** Good fits include codebase recon,
research, independent review, parallel checks, and mechanical edits with a clear spec. Do not
delegate trivial one-step operations or work where the child lacks the context to be safe.

Choose a model and thinking level appropriate to the task. Keep model names, provider defaults,
pricing, and fallback behavior in Pi's live settings and package documentation rather than in
this general instruction file.

## Coding Principles and Rules

### General

- Keep the functional core separate from the imperative shell; use straightforward control
  flow when it is clearer or more efficient.
- No generic abstraction without real type safety or real duplication eliminated. Prefer
  composition over inheritance; interfaces only at meaningful boundaries.
- Prefer immutable records; keep names consistent with the types they describe; no custom
  annotations.
- Unary or binary functions where practical; for more inputs, a cohesive parameter object.
- Write self-explanatory code; comment only non-obvious constraints, decisions, or tradeoffs.
- Make it work, then correct, then fast. Pre-size collections, avoid hot-path allocations, and
  profile before optimizing.
- Fail fast and keep the system responsive.
- Test-first for behavior changes when practical; other changes get the checks that fit them.
  Tests are fast, deterministic, and need no external services.

### Complexity

Optimize for the next reader. Cognitive complexity decides; cyclomatic complexity is the
supporting check. Obvious beats clever or short.

- Small, single-purpose functions. If the name needs "and" or "or", split it; if a block needs
  a comment, extract a well-named function.
- At most two nesting levels. Deeper means early return, `continue`, or an extracted helper.
- Handle invalid, empty, and error cases first, so the happy path stays unindented and last.
- Named predicates instead of negated `&&`/`||` chains; no double negation or inverted flags.
- No flag parameters: they usually mean two functions sharing a body.
- Data-driven dispatch over `if`/`else if`/`switch` chains whose branches do the same kind of
  thing. Nest ternaries at most one level.
- Never compress code to cut line count; dense lines trade a metric for cognitive load.
- Cyclomatic complexity at or below 10 per function; 15 is a hard stop, split first.
- Refactor before extending. A change that adds a branch should remove one; a net increase
  needs a stated reason in the commit or pull request.

### Organization

Structure is design. It is a stronger lever on complexity and readability than any single
function you will rewrite.

- Deep modules: a small, stable interface over a substantial hidden implementation. If callers
  must read internals to use it, the interface is too shallow.
- Group files by what they do together, not what they are. Nest a directory only when the level
  names a real boundary; flat is right for one concept. No catch-all `utils/`, `common/`,
  `helpers/`.
- Move code as you work. A function that belongs elsewhere moves now, even into a new file, with
  imports and call sites updated in the same change and no shims or duplicate copies left behind.
- Dependencies run one way: a module may use its own internals and the shared core, never reach
  up into callers or sideways into unrelated siblings.
- Never reimplement an existing capability. If a module provides it behind an interface, call
  that interface; when two modules need the same thing, extract a module both depend on. One
  implementation, one place to fix it.
- DRY is about knowledge, not appearance: lookalike code encoding different rules stays apart.
- Unrelated responsibilities accumulating in one file is a signal to split it.

### Logging

- Use an established library; never hand-roll a logger, formatter, or sink. Levels, formats, and
  destinations are configuration.
- Structured single-line records with stable field names (JSON where supported). Timestamps are
  sortable and unambiguous (`YYYY-MM-DD HH:MM:SS` plus offset), never locale-dependent.
- A correlation id on every record, propagated explicitly across boundaries. Durations from an
  injected monotonic clock, timestamps from wall clock, so tests control time.
- Log once, where the failure is recovered, reported, or returned: not at every layer, never
  log-and-rethrow, and preserve the cause chain instead of wrapping it.
- Error records stand alone: what failed, on what, and why. Never "something went wrong", never
  a bare exception. ERROR means a human must act; expected failures are INFO or WARN.
- WARN means degraded but handled: fallback taken, retry that succeeded, deprecated path. INFO
  records the timeline, not each item in a loop. DEBUG is diagnosis, off in production.
- Never log secrets, credentials, tokens, or unnecessary personal data; redact in the logging
  layer, not by caller discipline. Nothing in hot paths or tight loops.
- Logging is not error handling. A failure that changes control flow needs a returned error.

### IO and network logging

- One record per call crossing a process, network, or storage boundary, emitted by the module
  that makes it: target, correlation id, timestamp, outcome status, elapsed duration. Request
  and response share the record; a call that fails before responding still emits one.
- Headers and bodies are logged by data class, not by default: include them when the payload
  explains the failure, otherwise log content type and byte length.
- Redact authorization headers, cookies, tokens, keys, and personal data before writing,
  including in echoed bodies, and size-cap large, binary, or streaming payloads.

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
