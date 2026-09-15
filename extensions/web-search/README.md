# local-web-search

Local-first web tools for [pi](https://pi.dev), backed by the self-hosted
SearXNG instance on this box. Built 2026-09-13 (see
`~/.pi/agent/OPTIMIZATION-LOG.md` for the full evidence trail).

## Why this exists

pi core ships **no** web tools (verified in pi 0.85.1: built-ins are
`read`/`bash`/`edit`/`write`). After the 2026-09-08 `pi-web-access`
uninstall, the model (trained on that tool surface) kept calling
`web_search`/`fetch_content`/`get_search_content` — 26 "tool not found"
errors across sessions. Owner decision 2026-09-13: **keep pi defaults
intact; extend only with this local SearXNG tool; install no npm
package.**

## Open/Closed

- **Closed for modification**: zero changes to pi core, `settings.json`,
  `models.json`, or any built-in tool. The installed pi package is
  untouched.
- **Open for extension**: all capability arrives through the official
  `pi.registerTool()` API. The extension's entire behavioral surface is
  three tool registrations — no `pi.on` event interception, no command /
  shortcut / widget registration, no session entries, no prompt
  rewriting. Purely additive; no built-in name is shadowed (pi has no
  built-in web tools to collide with). The 2026-09-14 compact-TUI
  renderers (below) are part of the same three registrations — display
  slots only; `execute` and parameter schemas are untouched.

## Tools

| Tool | Does |
| --- | --- |
| `web_search` | Query the **local** SearXNG (`SEARXNG_URL`, default `http://127.0.0.1:8080`). Keyless, on-box only. Returns numbered title/URL/snippet. Optional `time_range` (day/week/month/year), `num_results` (1–10, default 5). If SearXNG is unreachable the result is a graceful message with a curl+jq fallback one-liner — never a crash, never fake results. |
| `fetch_content` | Fetch an absolute http(s) URL and return readable text (HTML: script/style/nav/form/aside stripped, block tags → newlines, entities decoded; plain text/markdown/JSON pass through verbatim). 1.5 MB raw body cap; 20k-char default output cap; 40k hard cap. Localhost allowed by design (e.g. local vLLM `/metrics`, n8n). |
| `get_search_content` | Alias of `fetch_content` (same code path). Kept because the model is trained on this exact name from opencode conventions; drop the registration block if you want the bare two-tool surface. |

`source_check` is intentionally **not** registered (it was a
pi-web-access-only name; 0 dead calls in history).

## Config

Env only, no config file:

- `SEARXNG_URL` — default `http://127.0.0.1:8080`
- `WEB_FETCH_TIMEOUT_MS` — default `20000`

## Dependencies

None. Node global `fetch` only (Node ≥ 18).

## Layout

Standard pi package layout (same shape as any published pi package —
auto-discovered from `~/.pi/agent/extensions/*/`, no `settings.json`
changes, installable later via `pi install` from git if it's ever
published):

```
web-search/
├── package.json    # pi package manifest ("extensions" entry)
├── README.md
├── src/
│   └── index.ts    # the whole extension (+ renderers)
└── tests/
    └── renderers.test.mjs  # jiti-based renderer/execute harness (not loaded by pi)
```

## Compact TUI rendering (added 2026-09-14)

Each tool definition carries `renderCall`/`renderResult` (pi's documented
custom-rendering slots; `docs/extensions.md` → “Custom Rendering”). The
renderers live **in this extension, not in pi-tool-display's
`customToolOverrides`**, for a verified reason:

- pi-tool-display decorates custom tools two ways: (1) a `pi.registerTool`
  interceptor installed when *it* loads, and (2) a `session_start` scan.
- Extension load order is path-alphabetical: `…/extensions/web-search` sorts
  before `…/npm/node_modules/pi-tool-display`, so the web tools register
  **before** the interceptor exists → path (1) never sees them.
- Path (2) is broken on pi 0.85.x: `registerMcpToolOverrides()` iterates
  `pi.getAllTools()`, which returns **flat copies**
  (`{name, description, parameters, promptGuidelines, sourceInfo}`) — the
  in-place decoration mutates the copies, not the live definitions.
  (Confirmed by reading `core/agent-session.js` getAllTools +
  `core/tools/renderers/index.js` `withBuiltInRenderers` in pi 0.85.1, and
  by a probe that showed `renderCall: undefined` on all three tools while
  pi-tool-display's built-in overrides *were* active.)

Behavior (display-only, all states unit-tested in `tests/renderers.test.mjs`):

| Tool | Collapsed | Expanded (Ctrl+O) |
| --- | --- | --- |
| `web_search` | one-line header (`query · n · range`) + full result list — the output is already ≤3 lines per hit, so there is nothing to hide | same |
| `fetch_content` / `get_search_content` | one-line header (`host/path · max N`) + first 6 lines + `… +N more lines · <expand hint>` | full text |
| any | error/empty results (SearXNG down, HTTP failure, no results, …) render in the error color; `isPartial` shows a working-state line | |

The expand hint uses `keyHint("app.tools.expand")` (respects configured
keybindings) with a `try/catch` fallback to the literal `Ctrl+O` for
non-TUI contexts (headless render, export) where the keybinding manager is
uninitialized — a renderer must never throw. `context.lastComponent` is
reused in place (pi's documented component-reuse pattern).

### Renderer-only rollback

Drop the `renderCall`/`renderResult` entries from the three registrations
and the `// ── compact TUI rendering ──` section; `execute`/params are
totally independent of them. Full rollback below is unchanged.

## Verify

```bash
# clean load (stderr must be empty)
(sleep 8) | timeout 25 pi --mode rpc --no-session >/tmp/o 2>/tmp/e; cat /tmp/e

# live tool call (local model)
cd /tmp && pi -p --no-session --model vllm/bubba \
  "Use the web_search tool once with query 'pi coding agent'. Reply with ONLY the first result's title and URL."
```

Both verified 2026-09-13: 0-byte stderr; real SearXNG results returned.

Renderer harness (no LLM, deterministic; loads the real module through pi's
own jiti pipeline with the same core-package aliases pi's loader uses):

```bash
PI_CODING_AGENT_ROOT=/path/to/@earendil-works/pi-coding-agent \
  node extensions/web-search/tests/renderers.test.mjs
```

Verified 2026-09-14: all renderer states pass (normal/error/empty/partial,
collapsed/expanded, component reuse) and `execute` returns live SearXNG
results.

## Rollback

```bash
rm -rf ~/.pi/agent/extensions/web-search && /reload
```
