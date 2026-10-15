"""One consumed synthetic setup fit; launch requires reviewed harness allowance."""
import time
ENTRY_MONOTONIC = time.monotonic()
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import resource
import re
import sys

BUILDER = Path('/tmp/tlab-build-heldout-native-fixture.py')


def need(value, message):
    if not value:
        raise ValueError(message)


def exclusive(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(body, stream, sort_keys=True, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


def build(root, freeze_path, freeze_sha256):
    root = Path(root).resolve(); freeze_path = Path(freeze_path).resolve()
    need(root.is_dir() and ' ' in root.name and root.is_relative_to(Path('/private/tmp').resolve()), 'Isolated TMP root with spaces required')
    own = resource.getrusage(resource.RUSAGE_SELF); children = resource.getrusage(resource.RUSAGE_CHILDREN)
    need(children.ru_utime + children.ru_stime == 0, 'Fresh setup child required')
    with freeze_path.open('rb') as stream:
        freeze_raw = stream.read(8*2**20+1)
    need(type(freeze_sha256) is str and re.fullmatch('[a-f0-9]{64}', freeze_sha256) is not None and len(freeze_raw) <= 8*2**20 and
        hashlib.sha256(freeze_raw).hexdigest() == freeze_sha256, 'Original issued harness-freeze SHA required')
    freeze = json.loads(freeze_raw)
    need(root == Path(freeze['isolated_root']).resolve(), 'Original reviewed setup root cannot be replaced/refilled')
    need(Path(__file__).resolve() == BUILDER.resolve(), 'Reviewed setup source identity differs')
    need(hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == freeze['harness_files'][str(BUILDER)], 'Frozen setup bytes differ')
    setup = root/'fixture-setup'; setup.mkdir(exist_ok=False)
    exclusive(setup/'attempt.consumed.json', dict(version=1, scope='synthetic_native_fixture_setup_only',
        fit_attempt_count=1, training_rows=8, historical_authentication_exercised=False,
        started_monotonic=ENTRY_MONOTONIC, cpu_seconds=60, wall_seconds=120, rss_bytes=2**30))
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (59, 60))
        need(resource.getrlimit(resource.RLIMIT_CPU) == (59, 60), 'Setup CPU fence readback failed')
        sys.path.insert(0, str(root))
        from scripts import feature_programs, strong_baseline, heldout_predictions
        for name, module in [('scripts.feature_programs', feature_programs), ('scripts.strong_baseline', strong_baseline), ('scripts.heldout_predictions', heldout_predictions)]:
            need(Path(module.__file__).resolve().is_relative_to(root), 'Setup imports escaped copied root: '+name)
        for name, digest in freeze['production_files'].items():
            need(hashlib.sha256((root/name).read_bytes()).hexdigest() == digest, 'Copied production pin changed')
        import numpy as np
        from catboost import CatBoostClassifier, Pool
        registry = json.loads((root/'configs/features/manual-18.json').read_text())
        pool = feature_programs.generate_pool(json.loads((root/'configs/features/automation-pool.json').read_text()), registry)
        names = [field['name'] for field in pool['identity']['base_model_schema']]
        need(len(names) == 41 and len(set(names)) == 41, 'Public B41 names required')
        matrix = np.array([[(row*(col+3)+col+1) % 17 / 17 for col in range(41)] for row in range(8)], dtype=np.float32)
        labels = np.array([0,1,0,1,0,1,0,1], dtype=np.int64)
        params = strong_baseline.model_parameters(dict(depth=6, l2_leaf_reg=30))
        model = CatBoostClassifier(**params)
        # Exactly one fit; no eval_set, OD, native replay or selection in setup.
        model.fit(Pool(matrix, labels, feature_names=names))
        artifact = setup/'B.cbm'
        need(not artifact.exists(), 'Exclusive setup model output required')
        model.save_model(str(artifact))
        loaded = CatBoostClassifier(); loaded.load_model(str(artifact))
        model_ref = dict(path='fixture-setup/B.cbm', sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
        spec = dict(model=model_ref, feature_names=names, trained_iterations=300, scoring_prefix=300,
            population=26000, effective_parameters=deepcopy(loaded.get_all_params()))
        heldout_predictions.verify_model(loaded, spec)
        for role in ['B', 'W']:
            need(spec['trained_iterations'] == loaded.tree_count_, 'Setup tree count differs')
        own = resource.getrusage(resource.RUSAGE_SELF); children = resource.getrusage(resource.RUSAGE_CHILDREN)
        peak = int(own.ru_maxrss if sys.platform == 'darwin' else own.ru_maxrss*1024)
        cpu = own.ru_utime + own.ru_stime
        need(children.ru_utime+children.ru_stime == 0, 'Forbidden setup descendant')
        need(cpu < 60 and time.monotonic()-ENTRY_MONOTONIC < 120 and 0 < peak <= 2**30, 'Setup prospective bound exceeded')
        exclusive(setup/'model-spec.json', spec)
        exclusive(setup/'result.json', dict(version=1, scope='synthetic_native_fixture_setup_only',
            status='setup_complete_pending_external_exit_tail', fit_attempt_count=1, training_rows=8,
            protocol_population_literal=26000, actual_historical_population_reproduced=False,
            trained_iterations=loaded.tree_count_, scoring_prefix=300, feature_count=len(names),
            child_cpu_seconds=cpu, child_peak_rss_bytes=peak, children_cpu_seconds=0,
            elapsed_seconds=time.monotonic()-ENTRY_MONOTONIC, native_prediction_count=0,
            synthetic_labels_only=True, real_recommendation_quality_claim=False, model=model_ref))
    except BaseException as error:
        try:
            exclusive(setup/'failed.json', dict(version=1, scope='synthetic_native_fixture_setup_only',
                status='failed_consumed_attempt_no_retry', error_type=type(error).__name__, fit_attempt_count=1))
        except BaseException as secondary:
            error.add_note('Setup failure persistence: '+type(secondary).__name__)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--root', required=True); parser.add_argument('--freeze', required=True)
    parser.add_argument('--issued-freeze-sha256', required=True)
    args = parser.parse_args(); build(args.root, args.freeze, args.issued_freeze_sha256)
