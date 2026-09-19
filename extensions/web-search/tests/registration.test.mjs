// Offline registration tests: never read live settings or contact a service.
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, beforeEach, test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PKG = process.env.PI_CODING_AGENT_ROOT;
assert.ok(PKG, "Set PI_CODING_AGENT_ROOT to pi-coding-agent's package root");
const temporaryRoot = mkdtempSync(path.join(tmpdir(), "pi-web-search-test-"));
const agentDir = path.join(temporaryRoot, "agent");
const settingsPath = path.join(agentDir, "settings.json");
mkdirSync(agentDir);
const previousAgentDir = process.env.PI_CODING_AGENT_DIR;
const previousCwd = process.cwd();
process.env.PI_CODING_AGENT_DIR = agentDir;
after(() => {
  process.chdir(previousCwd);
  if (previousAgentDir === undefined) delete process.env.PI_CODING_AGENT_DIR;
  else process.env.PI_CODING_AGENT_DIR = previousAgentDir;
  rmSync(temporaryRoot, { recursive: true, force: true });
});
beforeEach((t) => {
  rmSync(settingsPath, { recursive: true, force: true });
  t.mock.method(globalThis, "fetch", () => {
    throw new Error("Unexpected network request");
  });
});

const { createJiti } = await import(
  pathToFileURL(path.join(PKG, "node_modules/jiti/lib/jiti-static.mjs")).href
);
const jiti = createJiti(import.meta.url, {
  moduleCache: false,
  fsCache: false,
  alias: {
    "@earendil-works/pi-coding-agent": path.join(PKG, "dist/index.js"),
    "@earendil-works/pi-ai": path.join(PKG, "node_modules/@earendil-works/pi-ai/dist/index.js"),
    "@earendil-works/pi-tui": path.join(PKG, "node_modules/@earendil-works/pi-tui/dist/index.js"),
    typebox: path.join(PKG, "node_modules/typebox/build/index.mjs"),
  },
});
const factory = await jiti.import(path.join(ROOT, "src/index.ts"), { default: true });
const allTools = ["web_search", "fetch_content", "get_search_content"];
const fetchTools = ["fetch_content", "get_search_content"];
const saveSettings = (settings) => writeFileSync(settingsPath, JSON.stringify(settings));
function registeredTools() {
  const tools = [];
  factory({ registerTool: (tool) => tools.push(tool) });
  assert.equal(globalThis.fetch.mock.callCount(), 0, "registration must not probe a service");
  return tools;
}

for (const [name, settings, expected] of [
  ["missing settings file", undefined, allTools],
  ["omitted webSearch", {}, allTools],
  ["omitted enabled", { webSearch: {} }, allTools],
  ["explicit true", { webSearch: { enabled: true } }, allTools],
  ["explicit false", { webSearch: { enabled: false } }, fetchTools],
]) {
  test(`${name}: registers the expected tools`, () => {
    if (settings !== undefined) saveSettings(settings);
    assert.deepEqual(registeredTools().map((tool) => tool.name), expected);
  });
}

test("each factory load rereads settings; no restart-only module cache", () => {
  saveSettings({ webSearch: { enabled: false } });
  assert.deepEqual(registeredTools().map((tool) => tool.name), fetchTools);
  saveSettings({ webSearch: { enabled: true } });
  assert.deepEqual(registeredTools().map((tool) => tool.name), allTools);
});

test("global setting cannot be overridden by project settings", () => {
  const projectDir = path.join(temporaryRoot, "project");
  mkdirSync(path.join(projectDir, ".pi"), { recursive: true });
  writeFileSync(path.join(projectDir, ".pi/settings.json"), '{"webSearch":{"enabled":true}}');
  saveSettings({ webSearch: { enabled: false } });
  try {
    process.chdir(projectDir);
    assert.deepEqual(registeredTools().map((tool) => tool.name), fetchTools);
  } finally {
    process.chdir(previousCwd);
  }
});

for (const settings of [null, [], { webSearch: null }, { webSearch: [] },
  { webSearch: false }, { webSearch: { enabled: "false" } },
  { webSearch: { enabled: 0 } }, { webSearch: { enabled: null } }]) {
  test(`invalid configuration fails visibly: ${JSON.stringify(settings)}`, () => {
    saveSettings(settings);
    const tools = [];
    assert.throws(() => factory({ registerTool: (tool) => tools.push(tool) }), /web-search:.*settings|web-search:.*webSearch/);
    assert.deepEqual(tools, [], "invalid configuration must not partially register tools");
  });
}

test("malformed JSON does not expose settings contents in the diagnostic", () => {
  writeFileSync(settingsPath, '{"privateValue":"do-not-print",');
  assert.throws(() => registeredTools(), (error) => {
    assert.match(error.message, /web-search:.*settings/);
    assert.doesNotMatch(error.message, /do-not-print/);
    return true;
  });
});

test("unreadable settings do not silently enable search", () => {
  mkdirSync(settingsPath);
  assert.throws(() => registeredTools(), /web-search:.*settings/);
});

test("both fetch tools still execute when search is disabled", async (t) => {
  saveSettings({ webSearch: { enabled: false } });
  const tools = registeredTools();
  t.mock.method(globalThis, "fetch", async (url) => {
    assert.equal(String(url), "https://example.test/page");
    return new Response("<p>Offline fetch works</p>", { headers: { "content-type": "text/html" } });
  });
  for (const name of fetchTools) {
    const result = await tools.find((tool) => tool.name === name).execute("test", { url: "https://example.test/page" });
    assert.match(result.content[0].text, /Offline fetch works/);
  }
  assert.equal(globalThis.fetch.mock.callCount(), 2);
});

test("work overlay disables search; the baseline retains its default", () => {
  const configDir = path.resolve(ROOT, "../../config");
  const baseline = JSON.parse(readFileSync(path.join(configDir, "settings.json"), "utf8"));
  const work = JSON.parse(readFileSync(path.join(configDir, "settings.work.json"), "utf8"));
  saveSettings(baseline);
  assert.deepEqual(registeredTools().map((tool) => tool.name), allTools);
  saveSettings({ ...baseline, ...work });
  assert.deepEqual(registeredTools().map((tool) => tool.name), fetchTools);
});
