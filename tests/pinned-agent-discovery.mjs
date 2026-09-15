// Test-only oracle: run actual pinned discovery, never register an extension or launch an agent.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
const deps = process.env.PI_CANDIDATE_DEPENDENCIES;
const pkg = join(deps, 'node_modules/pi-subagents');
assert.equal(JSON.parse(readFileSync(join(pkg, 'package.json'))).version, '0.68.0');
const require = createRequire(join(deps, 'package.json'));
const { createJiti } = require('jiti');
const jiti = createJiti(import.meta.url, { moduleCache: false, fsCache: false });
const discovery = await jiti.import(join(pkg, 'src/agents/agents.ts'));
const result = discovery.discoverAgentSnapshot(process.cwd(), 'both');
console.log(JSON.stringify({
  agents: result.effective.agents.map(({ name, source, filePath }) => ({ name, source, filePath })),
  chains: result.all.chains.map(({ name, source, filePath }) => ({ name, source, filePath })),
}));
