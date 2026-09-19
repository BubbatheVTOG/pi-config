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

Installed packages include `pi-subagents`, `@tintinweb/pi-tasks`, `@nguyenquangthai/pi-ask`,
`pi-powerline-footer`, `pi-lens`, `@narumitw/pi-btw`, `pi-tool-display`, and other packages
listed by `pi list`. Local extensions and skills are loaded from `~/.pi/agent/`.

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
- **Research** — `web_search`, `fetch_content`, and `get_search_content` are provided by the
  local web-search extension and routed through SearXNG at `127.0.0.1:8080`. Search is for
  discovery; fetch the primary source before relying on a claim. Prefer the `researcher`
  subagent for multi-angle research. Return a distilled brief with URL citations rather than
  raw HTML. Use `pdftotext`, `yt-dlp`, or `gh` when a task needs those formats.
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
A `herdr` skill is available — use it when parallel agents, background command
monitoring, or extra terminal panes would help. Verify `HERDR_ENV=1` first;
if unset, you are not inside Herdr and its CLI cannot control the session.
