import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const script = fileURLToPath(new URL('../scripts/resource-inventory.mjs', import.meta.url));
const pkg = process.env.PI_CODING_AGENT_ROOT;
assert.ok(pkg);
function fixture(run) {
  const root = mkdtempSync(join(tmpdir(), 'pi-discovery-test-'));
  const gen = join(root, 'generation');
  const packageRoot = join(gen, 'dependencies/node_modules/example-addon');
  const put = (path, value) => {
    mkdirSync(resolve(path, '..'), { recursive: true });
    writeFileSync(path, typeof value === 'string' ? value : JSON.stringify(value));
  };
  put(join(packageRoot, 'package.json'), { name: 'example-addon', pi: { extensions: ['./extensions'], skills: ['./skills'] } });
  for (const name of ['one', 'two', 'three']) put(join(packageRoot, `extensions/${name}.ts`), 'export default function() {}');
  put(join(packageRoot, 'skills/example/SKILL.md'), '---\nname: example\ndescription: Synthetic example.\n---\n');
  const inspect = settings => {
    put(join(gen, 'defaults/settings.json'), settings);
    return spawnSync(process.execPath, [script, gen, pkg], {
      cwd: root, env: { PATH: process.env.PATH, HOME: root, PI_OFFLINE: '1', PI_CODING_AGENT_DIR: join(root, 'agent') },
      encoding: 'utf8', timeout: 15000,
    });
  };
  try { run({ gen, packageRoot, put, inspect }); }
  finally { rmSync(root, { recursive: true, force: true }); }
}

test('real Pi filters preserve exact include/exclude semantics without loading code', () => {
  fixture(({ packageRoot, inspect }) => {
    const result = inspect({ packages: [{ source: packageRoot,
      extensions: ['extensions/*.ts', '!extensions/two.ts', '-extensions/three.ts', '+extensions/two.ts'], skills: [] }] });
    assert.equal(result.status, 0, result.stderr);
    const paths = JSON.parse(result.stdout);
    assert.deepEqual(paths.extensions.map(e => e.path).sort(), [join(packageRoot, 'extensions/one.ts'), join(packageRoot, 'extensions/two.ts')]);
    assert.deepEqual(paths.skills, []);
  });
});

test('actual discovered duplicate skill names fail rather than trusting claims', () => {
  fixture(({ gen, packageRoot, put, inspect }) => {
    const extra = join(gen, 'extra/SKILL.md');
    put(extra, '---\nname: example\ndescription: Synthetic duplicate.\n---\n');
    const result = inspect({ packages: [{ source: packageRoot }], skills: [extra] });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /duplicate skills name/);
  });
});

test('missing dependency and unmanaged explicit resource refuse before loading', () => {
  fixture(({ packageRoot, put, inspect }) => {
    const result = inspect({ packages: [{ source: packageRoot + '-missing' }] });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /only present generation-local packages/);
    // The test exercises a separate temporary path, not an actual agent directory.
    const external = join(resolve(packageRoot, '../../../../'), 'outside-example.ts');
    put(external, 'export default function() {}');
    const unknown = inspect({ packages: [{ source: packageRoot }], extensions: [external] });
    assert.notEqual(unknown.status, 0);
    assert.match(unknown.stderr, /unmanaged discovered resource/);
  });
});
