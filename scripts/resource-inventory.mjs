// Pi 0.85.1 filesystem discovery only. No extension factory/session/provider is run.
// The version-bound adapter is checked against installed package-manager.js; it
// uses Pi's own filters rather than approximating minimatch semantics.
import assert from 'node:assert/strict';
import { readFileSync, realpathSync, existsSync } from 'node:fs';
import { basename, join, resolve, sep } from 'node:path';
import { pathToFileURL } from 'node:url';

const [generation, pkg] = process.argv.slice(2).map(path => resolve(path));
assert.ok(generation && pkg);
assert.equal(JSON.parse(readFileSync(join(pkg, 'package.json'))).version, '0.85.1', 'Review inventory adapter for this Pi version');
assert.ok(process.env.PI_OFFLINE === '1' && process.env.PI_CODING_AGENT_DIR, 'isolated inventory environment required');
const settings = JSON.parse(readFileSync(join(generation, 'defaults/settings.json')));
for (const entry of settings.packages ?? []) {
  assert.equal(typeof entry, 'object');
  assert.ok(entry.source.startsWith(generation + sep) && existsSync(entry.source), 'only present generation-local packages allowed');
}
const { DefaultPackageManager } = await import(pathToFileURL(join(pkg, 'dist/core/package-manager.js')));
const manager = new DefaultPackageManager({
  cwd: process.cwd(), agentDir: process.env.PI_CODING_AGENT_DIR,
  settingsManager: { getGlobalSettings: () => settings, getProjectSettings: () => ({}), isProjectTrusted: () => false },
});
manager.installParsedSource = async () => { throw new Error('Inventory cannot install'); };
manager.spawnCommand = () => { throw new Error('Inventory cannot spawn'); };
manager.spawnCaptureCommand = () => { throw new Error('Inventory cannot spawn'); };
const resolved = await manager.resolve(async () => 'error');
const inventory = {};
const names = new Set();
for (const [kind, entries] of Object.entries(resolved)) {
  inventory[kind] = [];
  for (const entry of entries.filter(entry => entry.enabled)) {
    const path = realpathSync(entry.path);
    assert.ok(path.startsWith(generation + sep), `unmanaged discovered resource: ${path}`);
    let name;
    if (kind === 'skills') {
      const content = readFileSync(path, 'utf8');
      name = content.match(/^name:\s*["']?([a-z0-9-]+)["']?\s*$/m)?.[1];
      assert.ok(name && /^description:\s*\S/m.test(content), `invalid skill frontmatter: ${path}`);
    } else if (kind === 'themes') {
      name = JSON.parse(readFileSync(path)).name;
    } else if (kind === 'prompts') {
      name = basename(path, '.md');
    }
    if (name) {
      assert.ok(!names.has(`${kind}:${name}`), `duplicate ${kind} name: ${name}`);
      names.add(`${kind}:${name}`);
    }
    inventory[kind].push({ path, ...(name ? { name } : {}) });
  }
}
console.log(JSON.stringify(inventory));
