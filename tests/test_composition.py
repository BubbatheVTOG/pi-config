import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from composition import (KINDS, Refusal, binding, check_lock, compose, dependency_manifest,
                         digest, encoded, read_json, validate)
from deployment import (MISSING, deploy, deployment_plan, external, merge, plan_digest,
                        prepare, verify_generation)


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else encoded(value))


def commit(root):
    subprocess.run(['git', '-C', str(root), 'add', '.'], check=True, capture_output=True)
    env = {**os.environ, 'GIT_AUTHOR_NAME': 'Example', 'GIT_AUTHOR_EMAIL': 'tester@example.invalid',
           'GIT_COMMITTER_NAME': 'Example', 'GIT_COMMITTER_EMAIL': 'tester@example.invalid'}
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Example', '-c', 'user.email=tester@example.invalid',
                    'commit', '-qm', 'Fixture checkpoint'], check=True, env=env)


def entry(value, feature='base', **kw):
    return dict(feature=feature, owner='example', value=value, **kw)


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='pi-config-test-')
        self.root = Path(self.tmp.name)
        self.core = self.root / 'core'
        self.core.mkdir()
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(self.core)], check=True)
        self.manifest = {'schema': 1, 'features': {'base': {'description': 'Base'}, 'optional': {'description': 'Optional'}},
                         'entries': {kind: {} for kind in KINDS}}
        self.manifest['entries']['settings'] = {'/theme': entry('dark'), '/retry/maxRetries': entry(3)}
        self.manifest['entries']['instructions']['base'] = entry('Read before editing.')
        self.manifest['entries']['resources'] = {
            'demo': entry({'source': 'demo', 'type': 'extensions'}, claims=['tool:demo']),
            'plugin.json': entry({'source': 'plugin.json', 'type': 'copy'}),
            'seed.json': entry({'source': 'seed.json', 'type': 'seed'})}
        put(self.core / 'demo/index.ts', b'export default function() {}\n')
        put(self.core / 'plugin.json', {'enabled': True, 'size': 8})
        put(self.core / 'seed.json', {'initial': True})
        self.save()
        self.home = self.root / 'home'
        self.agent = self.home / '.pi/agent'
        self.state = self.root / 'state'
        self.project = self.root / 'project'
        self.project.mkdir()

    def tearDown(self):
        for directory, dirs, names in os.walk(self.root):
            os.chmod(directory, 0o700)
            for name in names:
                p = Path(directory) / name
                if not p.is_symlink():
                    os.chmod(p, 0o600)
        self.tmp.cleanup()

    def save(self):
        put(self.core / 'manifest.json', self.manifest)
        commit(self.core)

    def composed(self):
        return compose(self.core, clean=True)

    def lock(self, composed):
        path = self.root / ('lock-' + composed['inputDigest'][:10])
        put(path / 'package.json', dependency_manifest(composed))
        put(path / 'binding.json', binding(composed))
        put(path / 'package-lock.json', {'lockfileVersion': 3, 'packages': {'': {'dependencies': dependency_manifest(composed)['dependencies']}}})
        return path

    def generation(self, name):
        c, origins = self.composed()
        output = self.root / name
        with patch('deployment.npm_run') as npm, patch('deployment.resource_inventory', return_value={}):
            prepare(c, origins, output, self.lock(c))
            self.assertEqual(npm.call_count, 1)
        return output

    def plan(self, generation):
        return deployment_plan(generation, self.agent, self.state, self.home, self.project)

    def activate_fixture(self, generation):
        plan = self.plan(generation)
        return deploy(generation, self.agent, self.state, self.home, self.project, plan_digest(plan))

    def overlay(self, operations, features=None):
        overlay = self.root / 'overlay'
        overlay.mkdir()
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(overlay)], check=True)
        c, _ = self.composed()
        put(overlay / 'overlay.json', {'schema': 1, 'coreDigest': c['coreDigest'],
            'features': features or {}, 'operations': operations})
        commit(overlay)
        return overlay

    def test_optional_overlay_excludes_every_owned_fragment(self):
        records = self.manifest['entries']
        records['settings']['/optional'] = entry(True, 'optional')
        records['instructions']['optional'] = entry('Optional instructions.', 'optional')
        records['providers']['example'] = entry({'baseUrl': 'https://example.invalid'}, 'optional')
        records['models']['example/small'] = entry({'id': 'small'}, 'optional')
        records['resources']['extra'] = entry({'source': 'demo', 'type': 'data'}, 'optional')
        records['packages']['example-addon'] = entry({'spec': '1.2.3'}, 'optional')
        self.save()
        overlay = self.overlay([{'op': 'exclude', 'feature': 'optional'}])
        combined, _ = compose(self.core, overlay, clean=True)
        self.assertNotIn('optional', combined['features'])
        for records in combined['entries'].values():
            self.assertFalse(any(e['feature'] == 'optional' for e in records.values()))
        self.assertEqual(dependency_manifest(combined)['dependencies'], {})

    def test_explicit_replace_remove_add_and_array_replacement(self):
        self.manifest['entries']['settings']['/items'] = entry([1, 2])
        self.save()
        c, _ = self.composed()
        ops = [{'op': 'replace', 'kind': 'settings', 'id': '/items',
                'expect': digest(c['entries']['settings']['/items']), 'entry': entry([3])},
               {'op': 'remove', 'kind': 'settings', 'id': '/theme',
                'expect': digest(c['entries']['settings']['/theme'])},
               {'op': 'add', 'kind': 'settings', 'id': '/new', 'entry': entry(True)}]
        combined, _ = compose(self.core, self.overlay(ops))
        settings, _ = validate(combined)
        self.assertEqual(settings['items'], [3])
        self.assertNotIn('theme', settings)
        self.assertTrue(settings['new'])

    def test_owner_drift_and_undeclared_conflicts_fail(self):
        overlay = self.overlay([{'op': 'add', 'kind': 'settings', 'id': '/theme', 'entry': entry('light')}])
        with self.assertRaisesRegex(Refusal, 'add conflict'):
            compose(self.core, overlay)
        value = read_json(overlay / 'overlay.json')
        value['operations'][0].update(op='replace', expect='0' * 64)
        put(overlay / 'overlay.json', value)
        with self.assertRaisesRegex(Refusal, 'owner/value drift'):
            compose(self.core, overlay)

    def test_shared_plugin_settings_cannot_be_shadowed(self):
        self.manifest['entries']['settings']['/ui'] = entry({'tree': True, 'fleetView': True, 'asyncWidget': True}, shared=True)
        self.save()
        c, _ = self.composed()
        overlay = self.overlay([{'op': 'replace', 'kind': 'settings', 'id': '/ui',
            'expect': digest(c['entries']['settings']['/ui']), 'entry': entry({'tree': False})}])
        with self.assertRaisesRegex(Refusal, 'belongs in core'):
            compose(self.core, overlay)

    def test_unknown_keys_and_dangling_references_fail(self):
        self.manifest['surprise'] = True
        self.save()
        with self.assertRaisesRegex(Refusal, 'unknown keys'):
            self.composed()
        del self.manifest['surprise']
        self.manifest['entries']['resources']['demo']['requires'] = ['optional']
        self.save()
        with self.assertRaisesRegex(Refusal, 'dangling feature'):
            compose(self.core, self.overlay([{'op': 'exclude', 'feature': 'optional'}]))

    def test_duplicate_capabilities_and_model_refs_fail(self):
        c, _ = self.composed()
        c['entries']['instructions']['duplicate'] = entry('More', claims=['tool:demo'])
        with self.assertRaisesRegex(Refusal, 'duplicate capability'):
            validate(c)
        del c['entries']['instructions']['duplicate']
        c['entries']['settings']['/subagents/defaultModel'] = entry('missing/model')
        with self.assertRaisesRegex(Refusal, 'undeclared subagent'):
            validate(c)

    def test_paths_are_anchored_and_symlinks_refused(self):
        self.manifest['entries']['resources']['demo']['value']['source'] = '../elsewhere'
        self.save()
        with self.assertRaisesRegex(Refusal, 'unsafe path'):
            self.composed()
        with self.assertRaisesRegex(Refusal, 'outside'):
            external(self.core / 'generation', [self.core])

    def test_core_input_drift_invalidates_overlay_and_lock(self):
        c, _ = self.composed()
        lock = self.lock(c)
        overlay = self.overlay([])
        put(self.core / 'demo/index.ts', b'export default function changed() {}\n')
        commit(self.core)
        changed, _ = self.composed()
        with self.assertRaisesRegex(Refusal, 'binding drift'):
            check_lock(changed, lock)
        with self.assertRaisesRegex(Refusal, 'input digest drift'):
            compose(self.core, overlay)

    def test_frozen_links_and_writable_singletons(self):
        gen = self.generation('one')
        self.activate_fixture(gen)
        link = self.agent / 'managed/demo/index.ts'
        self.assertTrue(link.is_symlink())
        self.assertTrue(link.resolve().is_relative_to(gen))
        settings = self.agent / 'settings.json'
        self.assertFalse(settings.is_symlink())
        self.assertEqual(settings.stat().st_nlink, 1)
        put(self.core / 'demo/index.ts', b'changed source')
        self.assertNotEqual(link.read_bytes(), b'changed source')
        put(settings, {'theme': 'light', 'retry': {'maxRetries': 3}, 'packages': [],
                       'extensions': [str(gen / 'stow/agent/managed/demo')]})
        self.assertEqual(read_json(self.core / 'manifest.json')['entries']['settings']['/theme']['value'], 'dark')

    def test_three_way_preserves_local_values_seeds_and_credentials_on_rollback(self):
        one = self.generation('one')
        self.activate_fixture(one)
        put(self.agent / 'plugin.json', {'enabled': True, 'size': 24})
        put(self.agent / 'seed.json', {'initial': False, 'local': 'preserve'})
        put(self.agent / 'auth.json', b'fictional credential sentinel')
        put(self.core / 'plugin.json', {'enabled': False, 'size': 8})
        commit(self.core)
        two = self.generation('two')
        self.activate_fixture(two)
        self.assertEqual(read_json(self.agent / 'plugin.json'), {'enabled': False, 'size': 24})
        self.activate_fixture(one)
        self.assertEqual(read_json(self.agent / 'plugin.json'), {'enabled': True, 'size': 24})
        self.assertEqual(read_json(self.agent / 'seed.json')['local'], 'preserve')
        self.assertEqual((self.agent / 'auth.json').read_bytes(), b'fictional credential sentinel')

    def test_conflicts_refuse_before_mutation(self):
        one = self.generation('one')
        self.activate_fixture(one)
        put(self.agent / 'plugin.json', {'enabled': True, 'size': 24})
        put(self.core / 'plugin.json', {'enabled': True, 'size': 12})
        commit(self.core)
        two = self.generation('two')
        link_before = os.readlink(self.agent / 'managed/demo/index.ts')
        with self.assertRaisesRegex(Refusal, 'conflict'):
            self.plan(two)
        self.assertEqual(os.readlink(self.agent / 'managed/demo/index.ts'), link_before)

    def test_unknown_target_and_ambient_resources_are_never_adopted(self):
        gen = self.generation('one')
        put(self.agent / 'settings.json', {})
        with self.assertRaisesRegex(Refusal, 'unowned singleton'):
            self.plan(gen)
        (self.agent / 'settings.json').unlink()
        put(self.agent / 'extensions/unknown.ts', b'unknown')
        with self.assertRaisesRegex(Refusal, 'unmanaged target'):
            self.plan(gen)
        shutil.rmtree(self.agent / 'extensions')
        put(self.home / '.agents/skills/extra/SKILL.md', b'unknown skill')
        with self.assertRaisesRegex(Refusal, 'unmanaged ambient'):
            self.plan(gen)

    def test_concurrent_diff_drift_and_corrupted_generation_fail(self):
        gen = self.generation('one')
        self.activate_fixture(gen)
        plan = self.plan(gen)
        put(self.agent / 'plugin.json', {'enabled': True, 'size': 20})
        with self.assertRaisesRegex(Refusal, 'diff drift'):
            deploy(gen, self.agent, self.state, self.home, self.project, plan_digest(plan))
        p = gen / 'defaults/plugin.json'
        p.chmod(0o600)
        p.write_bytes(b'corrupt')
        with self.assertRaisesRegex(Refusal, 'generation has changed'):
            verify_generation(gen)

    def test_package_filters_keep_pi_semantics_and_generation_local_paths(self):
        filters = {'extensions': ['src/*.ts', '!src/old.ts', '+src/extra.ts', '-src/hidden.ts'],
                   'skills': [], 'prompts': ['+prompts/one.md']}
        self.manifest['entries']['packages']['example-addon'] = entry({'spec': '1.2.3', 'filters': filters})
        self.save()
        c, origins = self.composed()
        output = self.root / 'filtered'
        def install(target, _args):
            put(target / 'node_modules/example-addon/package.json', {'name': 'example-addon', 'version': '1.2.3'})
        with patch('deployment.npm_run', side_effect=install), patch('deployment.resource_inventory', return_value={}):
            prepare(c, origins, output, self.lock(c))
        package = read_json(output / 'defaults/settings.json')['packages'][0]
        self.assertEqual(package, {'source': str(output / 'dependencies/node_modules/example-addon'), **filters})
        self.assertEqual(dependency_manifest(c)['dependencies'], {'example-addon': '1.2.3'})

    def test_overlay_relative_sources_do_not_resolve_against_core_or_cwd(self):
        overlay = self.overlay([{'op': 'add', 'kind': 'resources', 'id': 'extra',
            'entry': entry({'source': 'local', 'type': 'extensions'})}])
        put(overlay / 'local/index.ts', b'export default function extra() {}')
        commit(overlay)
        c, origins = compose(self.core, overlay, clean=True)
        output = self.root / 'combined'
        with patch('deployment.npm_run'), patch('deployment.resource_inventory', return_value={}):
            prepare(c, origins, output, self.lock(c))
        self.assertIn('extra()', (output / 'stow/agent/managed/extra/index.ts').read_text())
        public, _ = self.composed()
        with self.assertRaisesRegex(Refusal, 'binding drift'):
            check_lock(c, self.lock(public))

    def test_linked_or_hardlinked_singleton_refused(self):
        gen = self.generation('one')
        self.activate_fixture(gen)
        singleton = self.agent / 'plugin.json'
        singleton.unlink()
        singleton.symlink_to(self.core / 'plugin.json')
        with self.assertRaisesRegex(Refusal, 'symlink'):
            self.plan(gen)
        singleton.unlink()
        os.link(self.core / 'plugin.json', singleton)
        with self.assertRaisesRegex(Refusal, 'nonlocal writable'):
            self.plan(gen)

    def test_unknown_local_keys_and_package_paths_refused_even_without_new_defaults(self):
        gen = self.generation('one')
        self.activate_fixture(gen)
        put(self.agent / 'plugin.json', {'enabled': True, 'size': 8, 'unknown': 1})
        with self.assertRaisesRegex(Refusal, 'unknown local JSON'):
            self.plan(gen)
        put(self.agent / 'plugin.json', {'enabled': True, 'size': 8})
        settings = read_json(self.agent / 'settings.json')
        settings['packages'] = ['/unmanaged/example']
        put(self.agent / 'settings.json', settings)
        with self.assertRaisesRegex(Refusal, 'unmanaged local resource'):
            self.plan(gen)

    def test_unchanged_json_preserves_formatting_without_rewrite(self):
        put(self.core / 'plugin.json', b'{ "size": 8, "enabled": true }\n')
        commit(self.core)
        gen = self.generation('one')
        self.activate_fixture(gen)
        plan = self.plan(gen)
        self.assertEqual(plan[3], {})
        self.assertEqual((self.agent / 'plugin.json').read_bytes(), b'{ "size": 8, "enabled": true }\n')

    def test_interrupted_journal_refuses_retry_and_preserves_target(self):
        gen = self.generation('one')
        self.activate_fixture(gen)
        before = (self.agent / 'settings.json').read_bytes()
        put(self.state / 'transaction.json', {'interrupted': True})
        with self.assertRaisesRegex(Refusal, 'journal exists'):
            self.plan(gen)
        self.assertEqual(before, (self.agent / 'settings.json').read_bytes())

    def test_public_identity_preflight_rejects_ambient_override_without_exposing_it(self):
        for key, value in [('user.name', 'Example'), ('user.email', 'tester@example.invalid')]:
            subprocess.run(['git', '-C', str(self.core), 'config', '--local', key, value], check=True)
        script = Path(__file__).resolve().parents[1] / 'scripts/check-public-identity.py'
        env = {**os.environ, 'GIT_AUTHOR_NAME': 'Example', 'GIT_AUTHOR_EMAIL': 'tester@example.invalid',
               'GIT_COMMITTER_NAME': 'Example', 'GIT_COMMITTER_EMAIL': 'tester@example.invalid'}
        command = [sys.executable, str(script), '--repo', str(self.core)]
        self.assertEqual(subprocess.run(command, env=env, capture_output=True).returncode, 0)
        env['GIT_AUTHOR_NAME'] = 'Unexpected Example'
        failed = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(failed.returncode, 1)
        self.assertIn('ambient Git author differs', failed.stderr)
        self.assertNotIn('Unexpected Example', failed.stderr)

    def test_source_dirty_freeze_and_unknown_json_key_fail(self):
        put(self.core / 'untracked', b'not approved')
        with self.assertRaisesRegex(Refusal, 'dirty source'):
            self.composed()
        with self.assertRaisesRegex(Refusal, 'unknown local JSON'):
            merge({'a': 1}, {'a': 2, 'surprise': 1}, {'a': 3})
        with self.assertRaisesRegex(Refusal, 'conflict'):
            merge([1, 2], [1, 3], [2])


if __name__ == '__main__':
    unittest.main()
