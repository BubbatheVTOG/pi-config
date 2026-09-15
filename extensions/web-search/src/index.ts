// local-web-search (package: web-search/) — local-first web tools for pi.
//
// Pure extension (open for extension, closed for modification): registers
// new tools via the official pi.registerTool() API only. No event
// interception, no command/shortcut/widget registration, no settings or
// core changes. See ./README.md for the full design + verification notes.
//
// Renderers (display-only, 2026-09-15): the three tools carry
// renderCall/renderResult for compact TUI display (one-line call header,
// collapsed preview with expand hint, full content on expand). They live in
// the tool definitions themselves because pi-tool-display's
// customToolOverrides cannot reach tools registered before it loads (its
// session-start scan decorates getAllTools() copies, not live definitions;
// verified against pi 0.85.1). Rollback: drop the renderers + this section.
//
// Registers `web_search` (self-hosted SearXNG JSON API) and `fetch_content` /
// `get_search_content` (HTTP fetch + HTML→text). Zero dependencies: Node 18+
// global fetch only. The model (esp. local opencode-convention models) is
// trained to call these exact tool names; this restores that surface without
// re-adding pi-web-access.
//
// Config (env, all optional):
//   SEARXNG_URL     default http://127.0.0.1:8080
//   WEB_FETCH_TIMEOUT_MS  default 20000
//
// Security note: fetch_content will fetch any http(s) URL, including
// localhost/private ranges (deliberate — this box serves local vLLM/n8n
// metrics the user may want to read). It never follows non-http(s) schemes.

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { keyHint } from "@earendil-works/pi-coding-agent";
import { Text } from "@earendil-works/pi-tui";
import { Type } from "typebox";

const SEARXNG_URL = (
  process.env.SEARXNG_URL || "http://127.0.0.1:8080"
).replace(/\/+$/, "");
const FETCH_TIMEOUT_MS = Number(process.env.WEB_FETCH_TIMEOUT_MS || 20000);
const FETCH_BODY_LIMIT = 1_500_000; // stop reading at 1.5 MB
const DEFAULT_MAX_CHARS = 20_000;
const HARD_MAX_CHARS = 40_000;

interface SearxngResult {
  url?: unknown;
  title?: unknown;
  content?: unknown;
}

function str(v: unknown, max: number): string {
  if (typeof v !== "string") return "";
  return v.length > max ? v.slice(0, max) + "…" : v;
}

// ── web_search ───────────────────────────────────────────────────────────────

async function runSearch(
  query: string,
  numResults: number,
  timeRange?: string,
): Promise<string> {
  const params = new URLSearchParams({ q: query, format: "json" });
  if (timeRange) params.set("time_range", timeRange);

  let res: Response;
  try {
    res = await fetch(`${SEARXNG_URL}/search?${params.toString()}`, {
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
      headers: { accept: "application/json" },
    });
  } catch (err) {
    return (
      `SearXNG unreachable at ${SEARXNG_URL} (${
        err instanceof Error ? err.message : String(err)
      }). ` +
      `Fallback: curl -s '${SEARXNG_URL}/search?q=${encodeURIComponent(query)}&format=json' | jq -r '.results[:5][] | "\\(.title) | \\(.url)"'.`
    );
  }
  if (!res.ok)
    return `SearXNG HTTP ${res.status} for query "${query}". Check the service: docker ps | rg searxng`;

  let body: {
    results?: SearxngResult[];
    unresponsive_engines?: unknown;
  };
  try {
    body = (await res.json()) as typeof body;
  } catch (err) {
    return `SearXNG returned non-JSON (HTTP ${res.status}). ${
      err instanceof Error ? err.message : String(err)
    }`;
  }

  const results = Array.isArray(body.results) ? body.results : [];
  if (results.length === 0)
    return `No results for "${query}". Try different keywords or drop time_range.`;

  const lines: string[] = [];
  for (const [i, r] of results.slice(0, numResults).entries()) {
    const url = str(r.url, 500);
    const title = str(r.title, 200) || "(untitled)";
    const snippet = str(r.content, 400);
    lines.push(
      `${i + 1}. ${title}\n   ${url}${snippet ? `\n   ${snippet}` : ""}`,
    );
  }

  const dead = Array.isArray(body.unresponsive_engines)
    ? body.unresponsive_engines
    : [];
  const footer =
    dead.length > 0
      ? `\n(note: ${dead.length} engine(s) unresponsive: ${String(
          Array.isArray(dead[0]) ? dead[0].join(", ") : dead.join(", "),
        ).slice(0, 120)})`
      : "";
  return lines.join("\n") + footer;
}

// ── fetch_content / get_search_content ──────────────────────────────────────

function htmlToText(html: string): string {
  let s = html;
  // Drop non-content blocks.
  s = s
    .replace(/<script\b[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[\s\S]*?<\/style>/gi, " ")
    .replace(/<noscript\b[\s\S]*?<\/noscript>/gi, " ")
    .replace(/<svg\b[\s\S]*?<\/svg>/gi, " ")
    .replace(/<template\b[\s\S]*?<\/template>/gi, " ")
    .replace(/<(nav|header|footer|aside|form)\b[\s\S]*?<\/\1>/gi, " ");
  // Block-level boundaries → newlines.
  s = s
    .replace(
      /<\/(p|div|section|article|li|tr|h[1-6]|blockquote|pre|table|figure)>/gi,
      "\n",
    )
    .replace(/<(br|hr)\s*\/?>/gi, "\n")
    .replace(/<li\b[^>]*>/gi, "\n- ");
  // Strip remaining tags.
  s = s.replace(/<[^>]+>/g, " ");
  // Decode common entities.
  s = s
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, n: string) =>
      Number(n) > 0 && Number(n) < 0x110000
        ? String.fromCodePoint(Number(n))
        : " ",
    );
  // Normalize whitespace.
  s = s
    .split("\n")
    .map((line) => line.replace(/[ \t]+/g, " ").trim())
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  return s;
}

async function runFetch(url: string, maxChars: number): Promise<string> {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return `Invalid URL: ${url}`;
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:")
    return `Unsupported protocol "${parsed.protocol}" — http/https only.`;

  const max = Math.min(maxChars, HARD_MAX_CHARS);
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), FETCH_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(parsed, {
      signal: ac.signal,
      redirect: "follow",
      headers: {
        "user-agent": "pi-coding-agent/1.0 (+local research; respect robots)",
        accept: "text/markdown, text/html, text/plain, application/json; q=0.8",
      },
    });
  } catch (err) {
    return `Fetch failed for ${url}: ${
      err instanceof Error ? err.message : String(err)
    }`;
  } finally {
    clearTimeout(timer);
  }

  const contentType = res.headers.get("content-type") ?? "";
  const finalUrl = res.url || url;
  if (!res.ok)
    return `HTTP ${res.status} from ${finalUrl} (content-type: ${contentType}). Not fetched.`;

  // Read with a byte cap.
  const reader = res.body?.getReader();
  if (!reader) return `No readable body for ${finalUrl}.`;
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value) {
      chunks.push(value);
      total += value.byteLength;
      if (total >= FETCH_BODY_LIMIT) {
        reader.cancel().catch(() => {});
        break;
      }
    }
  }
  const raw = Buffer.from(chunks.flatMap((c) => Array.from(c))).toString(
    "utf8",
  );
  if (raw.length === 0) return `Empty body from ${finalUrl} (${contentType}).`;

  let text: string;
  if (contentType.includes("html")) text = htmlToText(raw);
  else text = raw; // text/plain, markdown, json — keep verbatim

  const truncated = text.length > max;
  if (truncated) text = text.slice(0, max) + "\n…[truncated]";
  return (
    `--- ${finalUrl} (content-type: ${contentType || "unknown"}, ${raw.length} bytes raw) ---\n` +
    text
  );
}

// ── compact TUI rendering (display-only; execute/params untouched) ─────────
//
// Collapsed: one-line header + short preview + expand hint. Expanded: full
// content. Error/empty results are detected by content shape and shown in the
// error color.

const PREVIEW_LINES = 6;
interface WebTheme {
  fg(color: string, text: string): string;
  bold(text: string): string;
}
interface WebToolContext {
  args?: unknown;
  toolCallId?: string;
  cwd?: string;
  argsComplete?: boolean;
  isPartial?: boolean;
  expanded?: boolean;
  showImages?: boolean;
  isError?: boolean;
  state?: unknown;
  lastComponent?: unknown;
  invalidate?: () => void;
}

function resultText(result: unknown): string {
  const r = result as
    | { content?: Array<{ type?: string; text?: string }> }
    | undefined;
  const parts = Array.isArray(r?.content) ? r.content : [];
  return parts
    .filter((p) => p && p.type === "text" && typeof p.text === "string")
    .map((p) => p.text as string)
    .join("");
}

function isProblemText(text: string): boolean {
  return (
    /^SearXNG (unreachable|HTTP|returned)/.test(text) ||
    /^No results for/.test(text) ||
    /^Invalid URL:/.test(text) ||
    /^Unsupported protocol/.test(text) ||
    /^Fetch failed/.test(text) ||
    /^HTTP \d{3} from/.test(text) ||
    /^No readable body/.test(text) ||
    /^Empty body/.test(text)
  );
}

function shortHost(url: string): string {
  try {
    const u = new URL(url);
    return `${u.host}${u.pathname.length > 60 ? u.pathname.slice(0, 57) + "…" : u.pathname}`;
  } catch {
    return url.length > 80 ? url.slice(0, 77) + "…" : url;
  }
}

function expandHint(): string {
  try {
    // Respects the user's configured keybinding when the TUI runtime is
    // initialized; falls back to the default literal in non-TUI contexts
    // (headless rendering, export) where the keybinding manager is absent.
    return keyHint("app.tools.expand", "to expand");
  } catch {
    return "Ctrl+O to expand";
  }
}

function updateSlot(
  context: WebToolContext | undefined,
  build: (t: Text) => void,
): Text {
  const t = (context?.lastComponent as Text | undefined) ?? new Text("", 0, 0);
  build(t);
  return t;
}

// ── boxed result frame (self-contained copy of the tool-box frame) ──────────
// Same aesthetic as pi-tool-display's user message box / the local tool-box
// extension: rounded frame, accent title, userMessageBg background fill.
// Deliberately duplicated (not imported from ../tool-box) so this package
// stays standalone/publishable.

const BG_COLOR = "userMessageBg";
const ANSI_SGR_PATTERN = /\u001b\[[0-9;?]*[A-Za-z]/g;
const ANSI_BG_RESET = "\u001b[49m";

interface BoxTheme {
  fg(color: string, text: string): string;
  bold?(text: string): string;
  bg?(color: string, text: string): string;
  getBgAnsi?(color: string): string;
}

function bgFill(theme: BoxTheme | undefined, text: string): string {
  if (!text) return text;
  try {
    if (typeof theme?.getBgAnsi === "function") {
      return `${theme.getBgAnsi(BG_COLOR)}${text}${ANSI_BG_RESET}`;
    }
  } catch {
    /* fall through */
  }
  try {
    if (typeof theme?.bg === "function") {
      return theme.bg(BG_COLOR, text);
    }
  } catch {
    /* fall through */
  }
  return text;
}

function fgSafe(
  theme: BoxTheme | undefined,
  color: string,
  text: string,
): string {
  if (!text) return text;
  try {
    return theme ? theme.fg(color, text) : text;
  } catch {
    return text;
  }
}

function boxedWebResult(
  lines: string[],
  title: string,
  width: number,
  theme: BoxTheme | undefined,
): string[] {
  // Keep edge rows below the terminal wrap boundary in self-shell mode.
  const w = Math.max(12, width - 2);
  const inner = Math.max(0, w - 2);
  const t = title.slice(0, inner);
  const fill = "─".repeat(Math.max(0, inner - t.length));
  const out: string[] = [
    bgFill(
      theme,
      `${fgSafe(theme, "border", "╭")}${fgSafe(theme, "accent", t)}${fgSafe(theme, "border", `${fill}╮`)}`,
    ),
  ];
  const bodyInner = Math.max(1, w - 4);
  for (const line of lines) {
    const clean = line.replace(/[ \t]+$/, "");
    const rows: string[] = [];
    if (clean.length <= bodyInner) {
      rows.push(clean);
    } else {
      // word-aware wrap so long lines fill the frame instead of truncating
      let row = "";
      for (const word of clean.split(" ")) {
        const candidate = row ? `${row} ${word}` : word;
        if (candidate.length > bodyInner && row) {
          rows.push(row);
          row = word.slice(0, bodyInner);
        } else if (candidate.length > bodyInner) {
          rows.push(word.slice(0, bodyInner));
          row = "";
        } else {
          row = candidate;
        }
      }
      if (row) rows.push(row);
    }
    for (const row of rows) {
      const pad = " ".repeat(Math.max(0, bodyInner - row.length));
      out.push(
        bgFill(
          theme,
          `${fgSafe(theme, "border", "│")} ${row}${pad} ${fgSafe(theme, "border", "│")}`,
        ),
      );
    }
  }
  out.push(bgFill(theme, fgSafe(theme, "border", `╰${"─".repeat(inner)}╯`)));
  return out;
}

function webBoxComponent(
  theme: BoxTheme | undefined,
  title: string,
  build: (width: number) => string[],
): { render: (width: number) => string[] } {
  let cachedKey = "";
  let cached: string[] = [];
  return {
    render(width: number) {
      const lines = build(width);
      const key = `${width}\u0000${lines.length}\u0000${lines[lines.length - 1] ?? ""}`;
      if (key !== cachedKey || cached.length === 0) {
        cached = boxedWebResult(lines, title, width, theme);
        cachedKey = key;
      }
      return cached;
    },
  };
}

function webSearchRenderCall(
  args: Record<string, unknown>,
  theme: WebTheme,
  context?: WebToolContext,
) {
  const query = typeof args.query === "string" ? args.query : "";
  const n =
    typeof args.num_results === "number" ? ` · ${args.num_results}` : "";
  const tr = typeof args.time_range === "string" ? ` · ${args.time_range}` : "";
  return updateSlot(context, (t) => {
    let s = theme.fg("toolTitle", theme.bold("web_search "));
    s += theme.fg("muted", str(query, 120));
    s += theme.fg("dim", `${n}${tr}`);
    t.setText(s);
  });
}

// web_search output is already compact (3 lines per hit) — the collapsed view
// shows it all in the box; there is nothing to hide behind the expand key.
function webSearchRenderResult(
  result: unknown,
  options: { expanded?: boolean; isPartial?: boolean },
  theme: WebTheme,
  context?: WebToolContext,
) {
  if (options.isPartial) {
    return webBoxComponent(theme, " web_search ", () => [
      theme.fg("warning", "searching…"),
    ]);
  }
  const text = resultText(result);
  if (!text.trim()) {
    return webBoxComponent(theme, " web_search ", () => [
      theme.fg("error", "(empty result)"),
    ]);
  }
  const colored = isProblemText(text)
    ? text.split("\n").map((l) => theme.fg("error", l))
    : text.split("\n");
  return webBoxComponent(theme, " web_search ", () => colored);
}

function fetchRenderCall(
  label: string,
  args: Record<string, unknown>,
  theme: WebTheme,
  context?: WebToolContext,
) {
  const url = typeof args.url === "string" ? args.url : "";
  const max =
    typeof args.max_chars === "number" ? ` · max ${args.max_chars}` : "";
  return updateSlot(context, (t) => {
    let s = theme.fg("toolTitle", theme.bold(`${label} `));
    s += theme.fg("muted", shortHost(url));
    s += theme.fg("dim", max);
    t.setText(s);
  });
}

function fetchRenderResult(
  result: unknown,
  options: { expanded?: boolean; isPartial?: boolean },
  theme: WebTheme,
  context?: WebToolContext,
) {
  const box = (lines: string[]) =>
    webBoxComponent(theme, " fetch ", () => lines);
  if (options.isPartial) {
    return box([theme.fg("warning", "fetching…")]);
  }
  const text = resultText(result);
  if (!text.trim()) {
    return box([theme.fg("error", "(empty result)")]);
  }
  if (isProblemText(text)) {
    return box(text.split("\n").map((l) => theme.fg("error", l)));
  }
  const allLines = text.split("\n");
  if (options.expanded) {
    return box(allLines);
  }
  const hidden = allLines.length - PREVIEW_LINES;
  if (hidden <= 0) {
    return box(allLines);
  }
  return box([
    ...allLines.slice(0, PREVIEW_LINES),
    theme.fg("dim", `… +${hidden} more lines · ${expandHint()}`),
  ]);
}

// ── registration ─────────────────────────────────────────────────────────────

const WEB_SEARCH_PARAMS = Type.Object({
  query: Type.String({
    description:
      "Search query for the local SearXNG metasearch (multi-engine web search).",
  }),
  num_results: Type.Optional(
    Type.Integer({
      minimum: 1,
      maximum: 10,
      description: "Max results to return (default 5).",
      default: 5,
    }),
  ),
  time_range: Type.Optional(
    Type.Union(
      [
        Type.Literal("day"),
        Type.Literal("week"),
        Type.Literal("month"),
        Type.Literal("year"),
      ],
      {
        description:
          "Recency filter (optional). Use for freshness-sensitive questions.",
      },
    ),
  ),
});

const FETCH_PARAMS = Type.Object({
  url: Type.String({
    description:
      "Absolute http(s) URL to fetch and convert to text (HTML pages are stripped to readable text).",
  }),
  max_chars: Type.Optional(
    Type.Integer({
      minimum: 1000,
      maximum: HARD_MAX_CHARS,
      default: DEFAULT_MAX_CHARS,
      description: `Max characters to return (default ${DEFAULT_MAX_CHARS}, hard cap ${HARD_MAX_CHARS}).`,
    }),
  ),
});

export default function (pi: ExtensionAPI): void {
  pi.registerTool({
    name: "web_search",
    label: "Web Search",
    description:
      "Web search via the local self-hosted SearXNG (127.0.0.1:8080) — no API key, traffic stays on this box. " +
      "Returns numbered results: title, URL, snippet. For full page content of a result, call fetch_content (or get_search_content) with its URL. " +
      "Prefer this over curl-ing the SearXNG JSON API by hand.",
    parameters: WEB_SEARCH_PARAMS,
    renderCall: webSearchRenderCall,
    renderResult: webSearchRenderResult,
    async execute(_id, params) {
      const text = await runSearch(
        params.query,
        params.num_results ?? 5,
        params.time_range,
      );
      return { content: [{ type: "text" as const, text }], details: {} };
    },
  });

  pi.registerTool({
    name: "fetch_content",
    label: "Fetch Content",
    description:
      "Fetch an absolute http(s) URL and return its content as readable text (HTML is stripped of scripts/styles/navigation and tags; plain text/Markdown/JSON pass through verbatim). " +
      "Capped at 1.5 MB raw, output truncated to max_chars (default 20,000). " +
      "Use to read the full text of a search result or any web page. Localhost URLs are allowed (e.g. local vLLM /metrics, n8n).",
    parameters: FETCH_PARAMS,
    renderCall: (args, theme, context) =>
      fetchRenderCall("fetch_content", args, theme, context),
    renderResult: fetchRenderResult,
    async execute(_id, params) {
      const text = await runFetch(
        params.url,
        params.max_chars ?? DEFAULT_MAX_CHARS,
      );
      return { content: [{ type: "text" as const, text }], details: {} };
    },
  });

  // Alias: local models are also trained on this name from opencode conventions.
  pi.registerTool({
    name: "get_search_content",
    label: "Get Search Content",
    description:
      "Fetch the full readable text of a single search-result URL (alias of fetch_content). " +
      "Pass the absolute http(s) URL from a web_search result.",
    parameters: Type.Object({
      url: Type.String({
        description: "Absolute http(s) URL of the search result to read.",
      }),
      max_chars: Type.Optional(
        Type.Integer({
          minimum: 1000,
          maximum: HARD_MAX_CHARS,
          default: DEFAULT_MAX_CHARS,
          description: `Max characters to return (default ${DEFAULT_MAX_CHARS}).`,
        }),
      ),
    }),
    renderCall: (args, theme, context) =>
      fetchRenderCall("get_search_content", args, theme, context),
    renderResult: fetchRenderResult,
    async execute(_id, params) {
      const text = await runFetch(
        params.url,
        params.max_chars ?? DEFAULT_MAX_CHARS,
      );
      return { content: [{ type: "text" as const, text }], details: {} };
    },
  });
}
