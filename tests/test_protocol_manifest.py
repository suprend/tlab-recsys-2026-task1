"""Provisional protocol and run provenance checks; no source-data scans."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.protocol_manifest import (
    build_run_manifest,
    load_protocol,
    load_run_manifest,
    sha256_file,
    validate_protocol,
    validate_run_manifest,
    write_protocol,
    write_run_manifest,
)

ROOT = Path(__file__).resolve().parents[1]


class ProtocolManifestTests(unittest.TestCase):
    def setUp(self):
        self.config = load_protocol(ROOT / 'configs/protocols/clock-7d.json')
        self.code = {'scripts/temporal_contract.py': 'a' * 64, 'uv.lock': 'b' * 64}
        self.inputs = {'data/raw/2019-Oct.csv.gz': 'c' * 64}

    def manifest(self, config=None, **changes):
        args = dict(code_hashes=self.code, input_hashes=self.inputs,
                    components=[{'name': 'fixed_prior', 'fit_cutoff': '2019-10-08T00:00:00Z',
                                 'available_at': '2019-10-08T00:00:00Z',
                                 'refresh_policy': 'frozen_parameters_past_history'}],
                    artifact_refs={'counts': 'artifacts/pilot/counts.json'},
                    created_at='2026-10-15T00:00:00Z')
        args.update(changes)
        return build_run_manifest(config or self.config, **args)

    def test_two_pilot_configs_differ_only_in_eligibility(self):
        other = load_protocol(ROOT / 'configs/protocols/clock-48h.json')
        self.assertEqual(self.config['query']['eligibility_hours'], 168)
        self.assertEqual(other['query']['eligibility_hours'], 48)
        other['query']['eligibility_hours'] = 168
        self.assertEqual(self.config, other)

    def test_protocol_roundtrip_is_stable_and_detached_from_caller(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'protocol.json'
            write_protocol(self.config, p)
            first = p.read_bytes()
            loaded = load_protocol(p)
            write_protocol(loaded, p)
            self.assertEqual(first, p.read_bytes())
            loaded['query']['sample_seed'] += 1
            self.assertEqual(self.config['query']['sample_seed'], 2026)

    def test_unknown_fields_at_multiple_levels_are_rejected(self):
        for location in [None, 'query', 'target', 'candidates', 'budget']:
            config = deepcopy(self.config)
            (config if location is None else config[location])['surprise'] = True
            with self.subTest(location=location), self.assertRaisesRegex(ValueError, 'unknown'):
                validate_protocol(config)

    def test_missing_fields_and_boolean_counts_are_rejected(self):
        config = deepcopy(self.config)
        del config['target']['include_anchor']
        with self.assertRaisesRegex(ValueError, 'missing'):
            validate_protocol(config)
        config = deepcopy(self.config)
        config['query']['max_users_per_day'] = True
        with self.assertRaises(ValueError):
            validate_protocol(config)

    def test_non_utc_and_incompatible_bounds_fail(self):
        for timestamp in ['2019-10-08T00:00:00', '2019-10-08T00:00:00+03:00', '2019-02-30T00:00:00Z']:
            config = deepcopy(self.config)
            config['pilot']['start'] = timestamp
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                validate_protocol(config)
        config = deepcopy(self.config)
        config['pilot']['start'] = '2019-10-07T00:00:00Z'
        with self.assertRaisesRegex(ValueError, 'lookback'):
            validate_protocol(config)
        config['pilot']['start'] = '2019-10-08T01:00:00Z'
        with self.assertRaisesRegex(ValueError, 'midnights'):
            validate_protocol(config)

    def test_malformed_event_types_and_unbounded_durations_are_rejected(self):
        for group, key, value in [('query', 'eligibility_event_types', [{}]),
                                  ('query', 'eligibility_hours', 10**30),
                                  ('target', 'horizon_hours', 10**30),
                                  ('candidates', 'popular_window_hours', 10**30),
                                  ('candidates', 'popular_limit', 1000)]:
            config = deepcopy(self.config)
            config[group][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_protocol(config)

    def test_final_horizon_endpoint_cannot_be_silently_censored(self):
        config = deepcopy(self.config)
        config['pilot'] = {'start': '2019-10-29T00:00:00Z', 'end': '2019-11-01T00:00:00Z'}
        self.assertEqual(validate_protocol(config), config)
        config['target']['include_end'] = True
        with self.assertRaisesRegex(ValueError, 'immature'):
            validate_protocol(config)
        config['target']['include_end'] = False
        config['target']['availability_delay_seconds'] = 1
        with self.assertRaisesRegex(ValueError, 'immature'):
            validate_protocol(config)

    def test_sampling_and_output_budget_are_explicit(self):
        for group, key, value in [('query', 'max_users_per_day', 2001),
                                  ('query', 'sampling', 'sample_future_buyers'),
                                  ('budget', 'max_anchors', 5999),
                                  ('budget', 'max_candidate_pairs', 1319999),
                                  ('candidates', 'max_unique', 221)]:
            config = deepcopy(self.config)
            config[group][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_protocol(config)

    def test_duplicate_json_keys_and_non_finite_values_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'invalid.json'
            p.write_text('{"version":1,"version":2}')
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                load_protocol(p)
            p.write_text('{"version":NaN}')
            with self.assertRaisesRegex(ValueError, 'Non-finite'):
                load_protocol(p)

    def test_run_identity_ignores_creation_time_and_artifact_location(self):
        first = self.manifest()
        other = self.manifest(created_at='2026-10-15T01:00:00Z',
                              artifact_refs={'counts': 'artifacts/another/counts.json'})
        self.assertEqual(first['run_id'], other['run_id'])
        self.assertNotEqual(first['created_at'], other['created_at'])

    def test_semantic_protocol_and_input_changes_change_identity(self):
        first = self.manifest()['run_id']
        config = deepcopy(self.config)
        config['query']['sample_seed'] += 1
        self.assertNotEqual(first, self.manifest(config)['run_id'])
        self.assertNotEqual(first, self.manifest(input_hashes={'data/raw/2019-Oct.csv.gz': 'd' * 64})['run_id'])

    def test_run_manifest_roundtrip_detects_tampering(self):
        manifest = self.manifest()
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'run.json'
            write_run_manifest(manifest, p)
            self.assertEqual(load_run_manifest(p), manifest)
        tampered = deepcopy(manifest)
        tampered['identity']['protocol']['query']['sample_seed'] += 1
        with self.assertRaisesRegex(ValueError, 'digest'):
            validate_run_manifest(tampered)

    def test_future_fitted_components_and_duplicate_names_are_rejected(self):
        component = {'name': 'encoder', 'fit_cutoff': '2019-10-08T00:00:01Z',
                     'available_at': '2019-10-08T00:00:01Z',
                     'refresh_policy': 'frozen_parameters_past_history'}
        with self.assertRaisesRegex(ValueError, 'newer'):
            self.manifest(components=[component])
        component['fit_cutoff'] = '2019-10-08T00:00:00Z'
        component['available_at'] = '2019-10-08T00:00:00Z'
        with self.assertRaisesRegex(ValueError, 'unique'):
            self.manifest(components=[component, deepcopy(component)])

    def test_checkpoint_availability_is_separate_from_fit_data_cutoff(self):
        component = {'name': 'encoder', 'fit_cutoff': '2019-10-07T00:00:00Z',
                     'available_at': '2019-10-08T00:00:01Z',
                     'refresh_policy': 'frozen_parameters_past_history'}
        with self.assertRaisesRegex(ValueError, 'available_at.*newer'):
            self.manifest(components=[component])
        component['available_at'] = '2019-10-06T23:59:59Z'
        with self.assertRaisesRegex(ValueError, 'precedes'):
            self.manifest(components=[component])
        component['available_at'] = '2019-10-07T00:00:00Z'
        first = self.manifest(components=[component])['run_id']
        component['available_at'] = '2019-10-07T01:00:00Z'
        self.assertNotEqual(first, self.manifest(components=[component])['run_id'])
        del component['available_at']
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.manifest(components=[component])

    def test_invalid_hashes_paths_and_missing_dependency_lock_fail(self):
        for kwargs in [{'code_hashes': {'scripts/anything.py': 'a' * 64}},
                       {'input_hashes': {'data/source.csv': 'not-a-hash'}},
                       {'artifact_refs': {'counts': '../outside.json'}},
                       {'artifact_refs': {'counts': '/absolute/path.json'}}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.manifest(**kwargs)

    def test_streaming_file_fingerprint_matches_known_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'input.txt'
            p.write_bytes(b'abc')
            self.assertEqual(sha256_file(p), hashlib.sha256(b'abc').hexdigest())


if __name__ == '__main__':
    unittest.main()
