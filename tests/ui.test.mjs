import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { resolve, join } from 'node:path';
import { readFileSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import test from 'node:test';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const pkg = process.env.PI_CODING_AGENT_ROOT;
assert.ok(pkg, 'PI_CODING_AGENT_ROOT must identify the installed Pi package');
const require = createRequire(join(pkg, 'package.json'));
const { createJiti } = require('jiti');
const alias = Object.fromEntries(['pi-coding-agent', 'pi-ai', 'pi-agent-core', 'pi-tui'].map(name => [
  `@earendil-works/${name}`, name === 'pi-coding-agent' ? join(pkg, 'dist/index.js') : join(pkg, `node_modules/@earendil-works/${name}/dist/index.js`),
]));
alias.typebox = require.resolve('typebox');
const jiti = createJiti(import.meta.url, { alias, moduleCache: false });
const { visibleWidth } = await import(alias['@earendil-works/pi-tui']);
const theme = { fg: (_key, text) => text, bg: (_key, text) => text, bold: text => text };
const factory = await jiti.import(join(root, 'extensions/web-search/src/index.ts'), { default: true });
const tools = [];
factory({ registerTool: tool => tools.push(tool) });
const fetchTool = tools.find(t => t.name === 'fetch_content');
const searchTool = tools.find(t => t.name === 'web_search');

// The tests never make an HTTP request, start a Pi session, reload, or speak.
globalThis.fetch = async () => { throw new Error('Unexpected network call'); };

test('web renderers fit narrow widths, preserve long words and wide characters', () => {
  const text = 'longword'.repeat(40) + '\n界'.repeat(10) + ' e\u0301 emoji 🙂';
  for (const tool of tools) {
    assert.equal(tool.renderShell, 'self');
    for (const width of [0, 1, 2, 5, 6, 10, 40, 80]) {
      const component = tool.renderResult({ content: [{ type: 'text', text }] }, { expanded: true }, theme);
      component.invalidate();
      const rows = component.render(width);
      assert.ok(rows.every(row => visibleWidth(row) <= width), `${tool.name}: width ${width}`);
      if (width === 40) assert.equal(rows.join('').match(/longword/g)?.length >= 20, true);
    }
  }
});

test('fetch bounds one oversize chunk and reports raw-body truncation', async () => {
  let cancelled = false;
  globalThis.fetch = async () => new Response(new ReadableStream({
    start(controller) { controller.enqueue(new Uint8Array(1_500_200).fill(120)); },
    cancel() { cancelled = true; },
  }), { headers: { 'content-type': 'text/plain' } });
  const result = await fetchTool.execute('x', { url: 'https://example.invalid', max_chars: 40000 });
  assert.match(result.content[0].text, /1500000 bytes raw/);
  assert.match(result.content[0].text, /raw body capped/);
  assert.ok(result.content[0].text.length < 40500);
  assert.ok(cancelled);
});

test('abort signal remains effective after headers, including alias', async () => {
  for (const tool of tools.filter(t => t !== searchTool)) {
    const controller = new AbortController();
    let headers;
    const arrived = new Promise(resolve => { headers = resolve; });
    globalThis.fetch = async (_url, options) => {
      headers();
      return new Response(new ReadableStream({
        start(stream) { options.signal.addEventListener('abort', () => stream.error(new Error('cancelled body'))); },
      }));
    };
    const pending = tool.execute('x', { url: 'https://example.invalid' }, controller.signal);
    await arrived;
    controller.abort();
    assert.match((await pending).content[0].text, /Fetch failed.*cancelled body/);
  }
});

test('search JSON is bounded and malformed responses are visible', async () => {
  globalThis.fetch = async () => new Response('not JSON');
  assert.match((await searchTool.execute('x', { query: 'example' })).content[0].text, /non-JSON/);
  globalThis.fetch = async () => new Response('x'.repeat(1_500_001));
  assert.match((await searchTool.execute('x', { query: 'example' })).content[0].text, /exceeds body limit/);
});

test('fetch does not accept non-HTTP schemes or use the network for them', async () => {
  globalThis.fetch = async () => { throw new Error('Unexpected network'); };
  assert.match((await fetchTool.execute('x', { url: 'file:///example' })).content[0].text, /Unsupported protocol/);
});

const splash = await jiti.import(join(root, 'extensions/splash/index.ts'), { default: true });
function splashHost(mode = 'tui', deferred = false) {
  const events = new Map();
  let mounted, component, doneCount = 0, headerCount = 0;
  const tui = { terminal: { columns: 100, rows: 40 } };
  const ctx = { mode, hasUI: true, ui: {
    setHeader() { headerCount++; },
    custom(factory) {
      mounted = () => { component = factory(tui, theme, {}, () => doneCount++); };
      if (!deferred) mounted();
      return Promise.resolve();
    },
  } };
  splash({ on: (name, fn) => events.set(name, fn) });
  return { events, ctx, tui, mount: () => mounted(), component: () => component,
    counts: () => ({ doneCount, headerCount }) };
}

test('splash is standalone, startup-only, resize-aware and closes once', () => {
  const h = splashHost();
  h.events.get('session_start')({ reason: 'startup' }, h.ctx);
  assert.equal(h.component().render(80).length, 28);
  assert.ok(h.component().render(80).every(row => visibleWidth(row) <= 80));
  h.tui.terminal.columns = 20;
  assert.deepEqual(h.component().render(20).map(row => visibleWidth(row)), [1]);
  h.events.get('before_agent_start')();
  h.events.get('session_shutdown')();
  assert.equal(h.counts().doneCount, 1);
  const reload = splashHost();
  reload.events.get('session_start')({ reason: 'reload' }, reload.ctx);
  assert.equal(reload.component(), undefined);
  for (const mode of ['rpc', 'json', 'print']) {
    const h = splashHost(mode);
    h.events.get('session_start')({ reason: 'startup' }, h.ctx);
    assert.equal(h.counts().headerCount, 0);
  }
});

test('splash shutdown before UI mount does not leak an overlay', () => {
  const h = splashHost('tui', true);
  h.events.get('session_start')({ reason: 'startup' }, h.ctx);
  h.events.get('session_shutdown')();
  h.mount();
  assert.equal(h.counts().doneCount, 1);
});

test('theme fallback snapshots retain installed required color tokens', async () => {
  const schema = JSON.parse(readFileSync(join(pkg, 'dist/modes/interactive/theme/theme-schema.json')));
  for (const color of ['green', 'orange', 'purple', 'red', 'teal', 'white', 'yellow']) {
    const theme = JSON.parse(readFileSync(join(root, `config/themes/hyper-term-${color}.json`)));
    for (const key of schema.properties.colors.required) assert.ok(key in theme.colors, `${color}: ${key}`);
  }
});

const deps = process.env.PI_CANDIDATE_DEPENDENCIES;
test('pinned boxed-tools owns five text tools and delegates real read/bash', { skip: !deps }, async () => {
  const boxed = await jiti.import(join(deps, 'node_modules/pi-boxed-tools/src/index.ts'), { default: true });
  const registered = [];
  boxed({ registerTool: tool => registered.push(tool) });
  assert.deepEqual(registered.map(t => t.name).sort(), ['bash', 'find', 'grep', 'ls', 'read']);
  const split = JSON.parse(readFileSync(join(root, 'extensions/pi-tool-display/config.json')));
  for (const tool of registered) {
    assert.equal(split.registerToolOverrides[tool.name], false);
    assert.equal(tool.renderShell, 'self');
    assert.ok(tool.parameters && tool.description);
    const rows = tool.renderResult({ content: [{ type: 'text', text: 'example output' }] }, { expanded: true }, theme).render(80);
    assert.ok(rows.every(row => visibleWidth(row) <= 80));
  }
  assert.equal(split.registerToolOverrides.edit, true);
  assert.equal(split.registerToolOverrides.write, true);
  assert.equal(split.enableNativeUserMessageBox, true);
  const tmp = mkdtempSync(join(tmpdir(), 'pi-boxed-test-'));
  try {
    writeFileSync(join(tmp, 'example.txt'), 'synthetic example\n');
    const result = await registered.find(t => t.name === 'read').execute('x', { path: join(tmp, 'example.txt') });
    assert.match(result.content[0].text, /synthetic example/);
    const command = await registered.find(t => t.name === 'bash').execute('x', { command: 'printf synthetic' });
    assert.match(command.content[0].text, /synthetic/);
  } finally { rmSync(tmp, { recursive: true, force: true }); }
});
