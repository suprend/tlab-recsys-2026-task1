"""Actual ordinary CLI lineage gate on tiny synthetic accepted collections.

These tests use real tiny DuckDB producers and real legacy/strict validators.
They stop at the preparation boundary; CatBoost is replaced before lazy loading
and no native model constructor, fit, prediction or model artifact is allowed.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
import shutil
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

from scripts import development_training as helper
from scripts import metadata_price_collection as strict
from scripts import train_baselines as b
from scripts import train_development as cli
from scripts.protocol_manifest import canonical_json, load_protocol, sha256_file
from tests import test_development_collection as development_tests


ROOT = Path(__file__).resolve().parents[1]
STRICT_SOURCE = ('scripts/metadata_price_collection.py', 'scripts/metadata_price_features.py')


class PreparationReached(RuntimeError):
    """Successful pre-fit boundary, never an attempted training run."""


class DevelopmentCLILineageTests(unittest.TestCase):
    def setUp(self):
        fixture = development_tests.DevelopmentRuntimeTests(
            'test_actual_producers_wait_for_external_review_then_resume_full_features_and_cache')
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        self.fixture, self.root = fixture, fixture.root
        # The producer fixture owns its module roots; consumption has two more owners.
        stack = fixture.stack
        stack.enter_context(patch.object(b, 'ROOT', self.root))
        stack.enter_context(patch.object(strict, 'ROOT', self.root))
        for name in set(b.CODE) | set(cli.CODE):
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/name, path)

        self.paths, self.states = {}, {}
        fixture.execute(); fixture.approve_shards(); fixture.execute()
        self._accept_collection('train')

        phase = fixture.d.load_phase(ROOT/'configs/development/selection.json',
                                     load_protocol(ROOT/'configs/protocols/clock-48h.json'))
        phase.update(range=dict(start='2019-10-11T00:00:00Z', end='2019-10-12T00:00:00Z'),
                     label_available_before='2019-10-12T00:00:00Z', shard_days=1,
                     model_timing=deepcopy(fixture.phase['model_timing']),
                     budget=dict(max_queries=2, max_candidate_pairs=12, wall_seconds=60))
        fixture.phase, fixture.phase_path = phase, self.root/'configs/development/selection.json'
        fixture.d._atomic_json(fixture.phase_path, phase)
        fixture.plan = fixture.d.prepare_execution_plan(fixture.phase_path, fixture.db)
        fixture.directory = fixture.output/fixture.plan['collection_id']
        fixture.d._atomic_json(fixture.producer,
            dict(version=1, approved=True, scope='reviewed_producers_and_phase_plan',
                 collection_id=fixture.plan['collection_id'],
                 fingerprints=fixture.plan['execution_inputs']['fingerprints']))
        fixture.execute(); fixture.approve_shards(); fixture.execute()
        self._accept_collection('selection')

        self.constructor = Mock(side_effect=AssertionError('No model construction allowed'))
        catboost = ModuleType('catboost')
        catboost.CatBoostClassifier = self.constructor
        stack.enter_context(patch.dict(sys.modules, {'catboost': catboost}))
        self.fit = stack.enter_context(patch.object(helper, 'fit_development',
            side_effect=AssertionError('No fit allowed')))
        self.prepare = stack.enter_context(patch.object(b, 'prepare_dataset',
            side_effect=PreparationReached('Actual CLI reached preparation')))
        self.environment_formats = []
        def environment(*, platform_format):
            self.assertEqual(platform_format, 'kernel')
            self.environment_formats.append(platform_format)
            return dict(backend='inert ML; tiny synthetic collections', platform_format=platform_format)
        stack.enter_context(patch.object(b, 'environment_snapshot', side_effect=environment))

    def _accept_collection(self, role):
        """Fixture approval construction; all consumer verification stays real."""
        fixture = self.fixture
        state, plan = fixture.read_state(), fixture.plan
        names = {str(fixture.directory.relative_to(self.root))+'/state.json',
                 str(fixture.directory.relative_to(self.root))+'/plan.json', state['attempts'][-1]}
        names.update(plan['execution_inputs']['fingerprints'])
        for entry in state['shards']:
            names.add(entry['acceptance']['path'])
            for kind in ('anchor', 'candidate', 'features'):
                names.update(entry[kind]['fingerprints'])
                manifest = b._read_json(self.root/entry[kind]['directory']/'run.json')
                names.update(manifest['identity']['code_hashes'])
                names.update(manifest['identity']['input_hashes'])
        path = self.root/('artifacts/acceptance/'+role+'-collection.json')
        b._atomic_json(path, dict(version=1, approved=True, scope='reviewed_development_collection',
            collection_id=plan['collection_id'], complete_attempt_report=state['attempts'][-1],
            fingerprints={name: sha256_file(self.root/name) for name in sorted(names)}))
        self.paths[role], self.states[role] = path, fixture.directory/'state.json'

    def args(self, name):
        return cli.parser().parse_args([
            '--train-acceptance', str(self.paths['train']),
            '--validation-acceptance', str(self.paths['selection']),
            '--output', str(self.root/name), '--max-iterations', '5', '--train-query-cap', '1',
            '--max-matrix-rows', '100', '--depth', '2', '--learning-rate', '.1',
            '--l2-leaf-reg', '3', '--random-seed', '7', '--cpu-seconds', '10',
            '--wall-seconds', '20', '--rss-bytes', str(2**30)])

    def assert_no_training(self, name):
        self.constructor.assert_not_called()
        self.fit.assert_not_called()
        report = b._read_json(self.root/name/'report.json')
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['fit_attempt_count'], 0)
        self.assertFalse((self.root/name/'recipe.json').exists())
        return report

    def _omit_and_reseal(self, role, kinds):
        """Omit Q/C claims together and refresh every affected transport seal."""
        state_path = self.states[role]
        state = b._read_json(state_path)
        entry = state['shards'][0]
        approval_path = self.root/entry['acceptance']['path']
        manifest_path = self.root/entry['features']['directory']/'run.json'
        report_path = manifest_path.parent/'report.json'
        paths = (state_path, approval_path, manifest_path, report_path, self.paths[role])
        originals = {path: path.read_bytes() for path in paths}
        manifests = {kind: b._read_json(self.root/entry[kind]['directory']/'run.json')
                     for kind in ('anchor', 'candidate')}
        missing = [manifests['anchor']['artifact_refs']['queries'] if kind == 'Q'
                   else manifests['candidate']['artifact_refs']['candidates'] for kind in kinds]
        approval = b._read_json(approval_path)
        for name in missing:
            del approval['fingerprints'][name]
        b._atomic_json(approval_path, approval)
        entry['acceptance']['sha256'] = sha256_file(approval_path)
        manifest = b._read_json(manifest_path)
        for name in missing:
            del manifest['identity']['input_hashes'][name]
        manifest['identity']['input_hashes'][entry['acceptance']['path']] = entry['acceptance']['sha256']
        manifest['run_id'] = hashlib.sha256(canonical_json(manifest['identity']).encode()).hexdigest()
        b._atomic_json(manifest_path, manifest)
        report = b._read_json(report_path)
        report['run_id'] = manifest['run_id']
        b._atomic_json(report_path, report)
        entry['features']['run_id'] = manifest['run_id']
        for path in (manifest_path, report_path):
            entry['features']['fingerprints'][str(path.relative_to(self.root))] = sha256_file(path)
        b._atomic_json(state_path, state)
        outer = b._read_json(self.paths[role])
        for path in paths[:-1]:
            outer['fingerprints'][str(path.relative_to(self.root))] = sha256_file(path)
        b._atomic_json(self.paths[role], outer)
        return originals

    def test_actual_lazy_loader_binds_strict_guard_and_intact_inputs_reach_preparation(self):
        runtime = cli.load_runtime()
        self.assertIs(runtime.verify_collection, strict.verify_collection_strict)
        self.assertIs(runtime.b.verify_collection, b.verify_collection)
        with self.assertRaisesRegex(PreparationReached, 'reached preparation'):
            cli.run(self.args('intact'))
        self.prepare.assert_called_once()
        call = self.prepare.call_args
        self.assertEqual(call.args[0]['phase']['role'], 'train')
        self.assertEqual((call.kwargs['max_queries'], call.kwargs['max_rows']), (1, 100))
        self.assertEqual(self.environment_formats, ['kernel'])
        report = self.assert_no_training('intact')
        self.assertEqual(report['environment']['platform_format'], 'kernel')

    def test_Q_only_C_only_and_combined_resealed_omissions_reject_before_preparation(self):
        for role in ('train', 'selection'):
            for kinds in (('Q',), ('C',), ('Q', 'C')):
                with self.subTest(role=role, omissions=kinds):
                    originals = self._omit_and_reseal(role, kinds)
                    try:
                        # This confirms a lineage failure, rather than stale transport hashes.
                        self.assertEqual(b.verify_collection(self.paths[role])['phase']['role'], role)
                        name = role+'-omit-'+''.join(kinds)
                        with self.assertRaisesRegex(ValueError, 'canonical14'):
                            cli.run(self.args(name))
                        self.prepare.assert_not_called()
                        self.assertEqual(self.environment_formats, [])
                        report = self.assert_no_training(name)
                        self.assertEqual(report['error_type'], 'ValueError')
                    finally:
                        for path, raw in originals.items():
                            path.write_bytes(raw)

    def test_new_strict_import_sources_are_pinned_and_rechecked(self):
        train = strict.verify_collection_strict(self.paths['train'])
        selection = strict.verify_collection_strict(self.paths['selection'])
        pins = cli.input_pins(b, train, selection, lambda: None)
        for name in STRICT_SOURCE:
            with self.subTest(source=name):
                self.assertIn(name, cli.CODE)
                self.assertEqual(pins[name], sha256_file(self.root/name))
                path = self.root/name
                original = path.read_bytes()
                try:
                    path.write_bytes(original+b'\n# synthetic source mutation\n')
                    with self.assertRaisesRegex(ValueError, 'Input changed'):
                        cli.recheck_pins(b, pins, lambda: None)
                finally:
                    path.write_bytes(original)
        self.prepare.assert_not_called()
        self.constructor.assert_not_called()
        self.fit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
