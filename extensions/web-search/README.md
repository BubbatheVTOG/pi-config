# Local web tools

Feature `searxng` owns `web_search`, `fetch_content` and `get_search_content` (the
last is a compatibility alias), their renderers and instruction section. Excluding
that feature removes them together. This is additive public extension source;
Pi core and other plugins are not modified.

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
node extensions/web-search/tests/renderers.test.mjs
```

Tests use deterministic mocks and do not contact a model or search endpoint. For
changes, edit this source and run the renderer test. Back up `~/.pi/agent/` before
promoting runtime changes, then use Pi's native resource discovery and `/reload`.
