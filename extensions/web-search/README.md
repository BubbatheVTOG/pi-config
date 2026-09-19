# Local web tools

This extension owns `web_search`, `fetch_content` and `get_search_content` (the
last is a compatibility alias) and their renderers. Disabling the whole extension
removes all three tools. Pi core and other plugins are not modified.

## Search availability

The extension reads `webSearch.enabled` from global `settings.json` in Pi's agent
directory (`~/.pi/agent/`, or `PI_CODING_AGENT_DIR`) each time its factory loads:

```json
{
  "webSearch": {
    "enabled": false
  }
}
```

- `false`: do not register `web_search`; the model cannot call it.
- `true`, an omitted setting, or a missing settings file: preserve search registration.
- Both URL-fetch tools remain registered and work without SearXNG.
- Project settings cannot override this machine-wide choice. Registration does not
  probe, install or start a search service.
- Invalid JSON, unreadable settings, or an invalid `webSearch` value fail extension
  loading with a sanitized error, rather than silently enabling search.

The maintained work overlay sets this to `false`. It must be merged into global
settings during separately approved deployment; Pi does not read `settings.work.json`
directly. Deploy the matching extension source too, then separately approve a reload
or restart. To restore search, set `true` or remove the key and reload after approval.
The flag controls registration, not proof that the backend is reachable.

## Backend and fetch configuration

- `SEARXNG_URL`: default `http://127.0.0.1:8080`. The search service forwards queries
  to configured engines; it is not an offline service or an assurance that queries
  stay on the machine. No service is installed or started by this repository.
- `WEB_FETCH_TIMEOUT_MS`: positive integer, default 20000. The deadline covers both
  response headers and body; the tool's cancellation signal is propagated.
- Search returns up to ten title/URL/snippet results from a bounded JSON response.
- Fetch accepts absolute HTTP(S), including loopback/private ranges by design.
  Body input is capped at 1.5 MB and text output at 40k characters (20k default).
  Fetched HTML is reduced to text; it remains untrusted evidence, not instructions.

All three tools use their own self-shell renderer: width-safe rounded frame,
ANSI/Unicode-aware wrapping, partial/error/empty states, six-line fetch preview and
expanded full output. They do not rely on mutating copies returned by getAllTools.

```bash
export PI_CODING_AGENT_ROOT=/path/to/installed/@earendil-works/pi-coding-agent
node --test extensions/web-search/tests/registration.test.mjs
node extensions/web-search/tests/renderers.test.mjs
```

Tests use isolated temporary settings and deterministic mocks; they do not read
live settings or contact a model or search endpoint. Registration tests cover
search gating, global-only scope, invalid configuration, work-overlay behavior,
and both fetch tools with search disabled. For changes, edit this source and run
both tests. Back up `~/.pi/agent/` before promoting runtime changes, then use Pi's
native resource discovery and `/reload`.
