import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { chmodSync, existsSync, mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { tmpdir } from 'node:os';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const deps = process.env.PI_CANDIDATE_DEPENDENCIES;
const scripts = fileURLToPath(new URL('../scripts', import.meta.url));
const oracle = fileURLToPath(new URL('./pinned-agent-discovery.mjs', import.meta.url));
const prompt = '---\nname: reviewer\ndescription: Synthetic project override\n---\nInspect only synthetic examples.\n';
const chain = { name: 'example-chain', description: 'Synthetic chain', chain: [{ agent: 'reviewer', task: 'Inspect a synthetic example' }] };

function fixture(run, { projectIsHome = false } = {}) {
  const root = mkdtempSync(join(tmpdir(), 'pi-agent-inventory-'));
  const home = join(root, 'home'), project = projectIsHome ? home : join(root, 'project'), agent = join(home, '.pi/agent');
  const generation = join(root, 'generation'), state = join(root, 'state');
  const put = (path, value) => {
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, typeof value === 'string' ? value : JSON.stringify(value));
  };
  mkdirSync(project, { recursive: true });
  mkdirSync(home, { recursive: true });
  mkdirSync(join(generation, 'stow/agent'), { recursive: true });
  const inventory = {};
  for (const [path, value] of [['defaults/settings.json', {}], ['defaults/models.json', { providers: {} }]]) {
    const data = JSON.stringify(value);
    put(join(generation, path), data);
    inventory[path] = { sha256: createHash('sha256').update(data).digest('hex'), executable: false };
  }
  put(join(generation, 'generation.json'), { path: generation, inventory, modes: {}, roots: [] });
  const env = { PATH: process.env.PATH, HOME: home, PI_CODING_AGENT_DIR: agent, PI_OFFLINE: '1',
    PI_CANDIDATE_DEPENDENCIES: deps, PYTHONDONTWRITEBYTECODE: '1' };
  const discover = () => {
    const result = spawnSync(process.execPath, [oracle], { cwd: project, env, encoding: 'utf8', timeout: 20000 });
    assert.equal(result.status, 0, result.stderr);
    return JSON.parse(result.stdout);
  };
  const plan = () => spawnSync('python3', ['-c',
    `import sys; from pathlib import Path; sys.path.insert(0, ${JSON.stringify(scripts)}); from deployment import deployment_plan; deployment_plan(*map(Path,sys.argv[1:]))`,
    generation, agent, state, home, project], { cwd: project, env, encoding: 'utf8', timeout: 20000 });
  const scan = () => spawnSync('python3', ['-c',
    `import sys; from pathlib import Path; sys.path.insert(0, ${JSON.stringify(scripts)}); from composition import read_json; from subagent_inventory import assert_subagent_inventory; p=Path(sys.argv[1])/'settings.json'; assert_subagent_inventory(*map(Path,sys.argv[1:4]),read_json(sys.argv[4]),read_json(p) if p.exists() else None)`,
    agent, home, project, join(generation, 'generation.json')], { cwd: project, env, encoding: 'utf8', timeout: 20000 });
  const refused = result => {
    assert.notEqual(result.status, 0, 'unowned definitions must refuse deployment_plan');
    assert.match(result.stderr, /unmanaged (subagent|ambient|target)|uncertain|cannot .*discovery/);
    assert.equal(existsSync(state), false, 'no state writes before refusal');
    assert.equal(existsSync(join(agent, 'managed')), false, 'no activation before refusal');
  };
  try { run({ root, home, project, agent, put, env, discover, plan, scan, refused }); }
  finally { rmSync(root, { recursive: true, force: true }); }
}

for (const spelling of ['pi', 'pi-subagents']) {
  test(`root package ${spelling} agent overrides real pinned reviewer, deployment refuses`, { skip: !deps }, () => {
    fixture(({ project, put, discover, plan, refused }) => {
      const declaration = { agents: ['./custom-agents'] };
      put(join(project, 'package.json'), { name: 'synthetic-project', [spelling]: spelling === 'pi' ? { subagents: declaration } : declaration });
      const path = join(project, 'custom-agents/reviewer.md');
      put(path, prompt);
      assert.equal(discover().agents.find(a => a.name === 'reviewer').filePath, path);
      refused(plan());
    });
  });
}

for (const location of ['.pi/npm/node_modules/example-addon', '.pi/npm/node_modules/@example/addon']) {
  test(`pinned discovery reads agents and chains from ${location}`, { skip: !deps }, () => {
    fixture(({ project, put, discover, plan, refused }) => {
      const pkg = join(project, location);
      put(join(pkg, 'package.json'), { name: 'synthetic-addon', pi: { subagents: { agents: ['./agents'], chains: ['./chains'] } } });
      put(join(pkg, 'agents/reviewer.md'), prompt);
      put(join(pkg, 'chains/example.chain.json'), chain);
      const actual = discover();
      assert.equal(actual.agents.find(a => a.name === 'reviewer').filePath, join(pkg, 'agents/reviewer.md'));
      assert.equal(actual.chains.find(c => c.name === 'example-chain').filePath, join(pkg, 'chains/example.chain.json'));
      refused(plan());
    });
  });
}

test('root package chain-only declaration is found by pinned discovery and refused', { skip: !deps }, () => {
  fixture(({ project, put, discover, plan, refused }) => {
    put(join(project, 'package.json'), { name: 'synthetic-project', pi: { subagents: { chains: ['./custom-chains'] } } });
    const path = join(project, 'custom-chains/example.chain.json');
    put(path, chain);
    assert.equal(discover().chains.find(c => c.name === 'example-chain').filePath, path);
    refused(plan());
  });
});

test('settings package in ordinary node_modules is discovered and refused', { skip: !deps }, () => {
  fixture(({ project, agent, put, discover, scan, plan, refused }) => {
    const pkg = join(project, 'node_modules/example-addon');
    put(join(pkg, 'package.json'), { name: 'synthetic-addon', pi: { subagents: { agents: ['./agents'] } } });
    const path = join(pkg, 'agents/reviewer.md'); put(path, prompt);
    put(join(agent, 'settings.json'), { packages: [{ source: pkg, skills: [] }] });
    assert.equal(discover().agents.find(a => a.name === 'reviewer').filePath, path);
    refused(scan()); refused(plan());
  });
});

test('home-expanded wildcard scan roots match real pinned discovery', { skip: !deps }, () => {
  fixture(({ home, agent, put, discover, scan, refused }) => {
    const path = join(home, 'bundles/example/agents/reviewer.md'); put(path, prompt);
    put(join(agent, 'settings.json'), { subagents: { agentScanDirs: ['~/bundles/*/agents'] } });
    assert.equal(discover().agents.find(a => a.name === 'reviewer').filePath, path);
    refused(scan());
  });
});

test('real pinned .pi/chains discovery is refused', { skip: !deps }, () => {
  fixture(({ project, put, discover, plan, refused }) => {
    const path = join(project, '.pi/chains/example.chain.json');
    put(path, chain);
    assert.equal(discover().chains.find(c => c.name === 'example-chain').filePath, path);
    refused(plan());
  });
});

for (const route of ['settings', 'environment', 'default-user', 'user-chain']) {
  test(`real pinned ${route} definition discovery is refused`, { skip: !deps }, () => {
    fixture(({ root, agent, put, env, discover, plan, scan, refused }) => {
      const dir = route === 'default-user' ? join(agent, 'agents') : join(root, 'extra');
      let path = join(dir, 'reviewer.md');
      put(path, prompt);
      if (route === 'settings') put(join(agent, 'settings.json'), { subagents: { agentScanDirs: [dir] } });
      if (route === 'environment') env.PI_SUBAGENT_EXTRA_AGENT_DIRS = dir;
      if (route === 'user-chain') {
        path = join(agent, 'chains/example.chain.json'); put(path, chain);
        assert.equal(discover().chains.find(c => c.name === 'example-chain').filePath, path);
      } else assert.equal(discover().agents.find(a => a.name === 'reviewer').filePath, path);
      refused(scan());
      refused(plan());
    });
  });
}

test('HOME project package definitions match pinned discovery and are refused', { skip: !deps }, () => {
  fixture(({ project, put, discover, plan, refused }) => {
    put(join(project, 'package.json'), { name: 'synthetic-home', pi: { subagents: { agents: ['./custom-agents'] } } });
    const path = join(project, 'custom-agents/reviewer.md');
    put(path, prompt);
    assert.equal(discover().agents.find(a => a.name === 'reviewer').filePath, path);
    refused(plan());
  }, { projectIsHome: true });
});

for (const directory of ['~/agents', 'relative/agents']) {
  test(`literal extra-agent directory ${directory} matches pinned discovery`, { skip: !deps }, () => {
    fixture(({ project, put, env, discover, plan, refused }) => {
      const path = join(project, directory, 'reviewer.md');
      put(path, prompt);
      env.PI_SUBAGENT_EXTRA_AGENT_DIRS = directory;
      assert.equal(discover().agents.find(a => a.name === 'reviewer').filePath, path);
      refused(plan());
    });
  });
}

test('global npm definitions are inspected in the same non-offline mode as pinned discovery', { skip: !deps }, () => {
  fixture(({ root, put, env, discover, plan, refused }) => {
    const global = join(root, 'global'), binary = join(root, 'bin/npm');
    put(binary, `#!/bin/sh\n[ "$1 $2" = 'root -g' ] || exit 2\nprintf '%s\\n' '${global}'\n`);
    chmodSync(binary, 0o755);
    env.PATH = join(root, 'bin') + ':' + env.PATH;
    env.PI_OFFLINE = '0';
    const pkg = join(global, 'example-addon');
    put(join(pkg, 'package.json'), { name: 'synthetic-addon', 'pi-subagents': { agents: ['./agents'] } });
    const path = join(pkg, 'agents/reviewer.md'); put(path, prompt);
    assert.equal(discover().agents.find(a => a.name === 'reviewer').filePath, path);
    refused(plan());
    env.PI_OFFLINE = '1';
    assert.notEqual(discover().agents.find(a => a.name === 'reviewer').filePath, path);
    assert.equal(plan().status, 0);
  });
});

test('ordinary dependencies without definitions are accepted; malformed metadata refuses uncertainty', { skip: !deps }, () => {
  fixture(({ project, put, discover, plan, refused }) => {
    for (const prefix of ['node_modules', '.pi/npm/node_modules']) {
      put(join(project, prefix, 'ordinary/package.json'), { name: 'ordinary', version: '1.0.0' });
    }
    assert.equal(discover().agents.find(a => a.name === 'reviewer').source, 'builtin');
    assert.equal(plan().status, 0);
    put(join(project, '.pi/npm/node_modules/ordinary/package.json'), '{ malformed');
    refused(plan());
  });
});
