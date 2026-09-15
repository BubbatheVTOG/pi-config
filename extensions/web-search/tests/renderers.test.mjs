// Unit tests for the web-search extension's renderers (display-only paths).
// Loads the real extension module through pi's own jiti pipeline (same alias
// setup pi's loader uses for npm installs) and exercises every renderer state.
// Results are boxed (see "boxed result frame" in src/index.ts) — assertions
// check the frame and the content lines inside it.
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PKG = process.env.PI_CODING_AGENT_ROOT;
if (!PKG) {
  console.error("Set PI_CODING_AGENT_ROOT to pi-coding-agent's package root");
  process.exit(2);
}
const { createJiti } = await import(
  pathToFileURL(path.join(PKG, "node_modules/jiti/lib/jiti-static.mjs")).href
);
const alias = {
  "@earendil-works/pi-coding-agent": path.join(PKG, "dist/index.js"),
  "@earendil-works/pi-tui": path.join(
    PKG,
    "node_modules/@earendil-works/pi-tui/dist/index.js",
  ),
  typebox: path.join(PKG, "node_modules/typebox/build/index.mjs"),
};

const jiti = createJiti(import.meta.url, { moduleCache: false, alias });
const factory = await jiti.import(path.join(ROOT, "src/index.ts"), {
  default: true,
});
if (typeof factory !== "function") {
  console.error(
    "FATAL: extension default export is not a function:",
    typeof factory,
  );
  process.exit(1);
}
console.log("LOAD OK — extension factory is a function");

const tools = [];
const fakePi = { registerTool: (t) => tools.push(t) };
factory(fakePi);
for (const name of ["web_search", "fetch_content", "get_search_content"]) {
  const t = tools.find((x) => x.name === name);
  if (
    !t ||
    typeof t.renderCall !== "function" ||
    typeof t.renderResult !== "function" ||
    typeof t.execute !== "function"
  ) {
    console.error(`FAIL ${name}: missing renderCall/renderResult/execute`);
    process.exit(1);
  }
}
console.log("OK  all three tools registered with render slots + execute");

const theme = { fg: (_c, s) => s, bold: (s) => `[b]${s}[/b]` };
let failures = 0;
function check(label, cond, extra = "") {
  if (cond) {
    console.log(`OK  ${label}`);
  } else {
    failures++;
    console.error(`FAIL ${label}${extra ? `: ${extra}` : ""}`);
  }
}

const renderComp = (comp, width) => comp.render(width);
const ws = tools.find((t) => t.name === "web_search");
const fc = tools.find((t) => t.name === "fetch_content");
const gsc = tools.find((t) => t.name === "get_search_content");
const WIDTH = 80;

// ── call renderers (slim headers, unchanged style) ──
const call1 = ws.renderCall(
  { query: "pi coding agent tools", num_results: 2, time_range: "week" },
  theme,
);
check(
  "web_search renderCall → Text one-liner",
  typeof call1.render === "function" &&
    call1.text.includes("web_search") &&
    call1.text.includes("pi coding agent tools"),
  JSON.stringify(call1.text),
);

const call2 = fc.renderCall(
  { url: "https://example.com/x", max_chars: 5000 },
  theme,
);
check(
  "fetch_content renderCall → Text one-liner with host + max",
  typeof call2.render === "function" &&
    call2.text.includes("example.com") &&
    call2.text.includes("max 5000"),
  JSON.stringify(call2.text),
);

// ── web_search results: boxed ──
const normal = ws.renderResult(
  {
    content: [
      { type: "text", text: "1. Title A\n   https://a.example\n   snippet a" },
    ],
  },
  { expanded: false, isPartial: false },
  theme,
);
const nLines = renderComp(normal, WIDTH);
check(
  "web_search normal → framed",
  nLines[0].startsWith("╭") &&
    nLines[0].includes("web_search") &&
    nLines.at(-1).startsWith("╰"),
  JSON.stringify(nLines[0]),
);
check(
  "web_search normal → content inside box",
  nLines.some((l) => l.includes("Title A") && l.startsWith("│")),
);

const noRes = renderComp(
  ws.renderResult(
    { content: [{ type: "text", text: 'No results for "xyzzy".' }] },
    { expanded: false, isPartial: false },
    theme,
  ),
  WIDTH,
);
check(
  "web_search no-results → error content inside frame",
  noRes.some((l) => l.startsWith("│") && l.includes("No results for")),
);

const partial = renderComp(
  ws.renderResult({ content: [] }, { expanded: false, isPartial: true }, theme),
  WIDTH,
);
check(
  "web_search isPartial → searching… inside frame",
  partial.some((l) => l.includes("searching…")),
);

// ── fetch results: boxed, preview + expand hint ──
const bigBody =
  "--- https://example.com/x (content-type: text/html, 4200 bytes raw) ---\n" +
  Array.from(
    { length: 50 },
    (_, i) => `line ${i + 1} of the fetched page`,
  ).join("\n");
const collapsed = renderComp(
  fc.renderResult(
    { content: [{ type: "text", text: bigBody }] },
    { expanded: false, isPartial: false },
    theme,
  ),
  WIDTH,
);
check(
  "fetch collapsed → framed",
  collapsed[0].startsWith("╭") && collapsed.at(-1).startsWith("╰"),
);
check(
  "fetch collapsed → 6 preview lines + hint",
  collapsed.some((l) => l.includes("line 5 of")) &&
    !collapsed.some((l) => l.includes("line 6 of")) &&
    collapsed.some((l) => l.includes("+45 more lines")),
  JSON.stringify(collapsed.slice(-4)),
);

const expanded = renderComp(
  fc.renderResult(
    { content: [{ type: "text", text: bigBody }] },
    { expanded: true, isPartial: false },
    theme,
  ),
  WIDTH,
);
check(
  "fetch expanded → full content in frame",
  expanded.some((l) => l.includes("line 50 of")),
);

const fetchFail = renderComp(
  fc.renderResult(
    {
      content: [
        {
          type: "text",
          text: "Fetch failed for https://down.example: ECONNREFUSED",
        },
      ],
    },
    { expanded: false, isPartial: false },
    theme,
  ),
  WIDTH,
);
check(
  "fetch failure → error content inside frame",
  fetchFail.some((l) => l.startsWith("│") && l.includes("Fetch failed")),
);

const partialFetch = renderComp(
  fc.renderResult({ content: [] }, { expanded: false, isPartial: true }, theme),
  WIDTH,
);
check(
  "fetch isPartial → fetching… inside frame",
  partialFetch.some((l) => l.includes("fetching…")),
);

const short = renderComp(
  gsc.renderResult(
    { content: [{ type: "text", text: "short body" }] },
    { expanded: false, isPartial: false },
    theme,
  ),
  WIDTH,
);
check(
  "get_search_content short body → framed fully (no hint)",
  short.some((l) => l.includes("short body")) &&
    !short.some((l) => l.includes("more lines")),
);

console.log(failures === 0 ? "\nALL PASS" : `\n${failures} FAILURE(S)`);
process.exit(failures === 0 ? 0 : 1);
