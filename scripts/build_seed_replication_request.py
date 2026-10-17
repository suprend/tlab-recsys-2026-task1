"""Build local source/config pins for the fixed historical seed2027 replication.

Reads no producer report/export/model body. Input authentication occurs in caller.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPE = 'historical_d35cfb6_frozen_exports_seed2027_not_current_raw_pipeline'
REPORT = dict(sha256='e62b1f47d6db808f6f5235f63a1b207970ac2f8487c09d9273902c4fbc864a9b', bytes=52763)
EXTRA_SOURCES = ('scripts/reproduce_frozen_comparison.py', 'scripts/development_training.py',
                 'scripts/adaptive_tree_selection.py', 'configs/reproduction/frozen-bw-oct2019.json',
                 'scripts/replicate_frozen_seed.py')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def parse(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'Duplicate JSON field')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def source_ref(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(512 * 1024 + 1)
    require(len(raw) <= 512 * 1024, 'Bounded source/config file exceeded')
    return dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def build_request(project_root, producer_root):
    root, producer = Path(project_root).resolve(), Path(producer_root).resolve(strict=True)
    require(producer.is_dir(), 'Retained historical producer directory required')
    # Metadata only: this is not report authentication or export acceptance.
    report = producer / 'report.json'
    require(report.is_file() and report.stat().st_size == REPORT['bytes'], 'Historical report metadata differs')
    require(not (root / 'scripts/__init__.py').exists(), 'Closed scripts namespace assumption changed')
    recipe_path = root / 'configs/reproduction/frozen-bw-oct2019.json'
    with recipe_path.open('rb') as stream:
        raw = stream.read(128 * 1024 + 1)
    require(len(raw) <= 128 * 1024, 'Bounded recipe exceeded')
    recipe = parse(raw)
    names = set(recipe['dependencies']) | set(EXTRA_SOURCES)
    for name in names:
        path = Path(name)
        require(not path.is_absolute() and '..' not in path.parts and str(path) == name,
                'Source dependency must be a normalized project-relative path')
    closure = {str(root / name): source_ref(root / name) for name in sorted(names)}
    require(sum(pin['bytes'] for pin in closure.values()) <= 3 * 2**20, 'Bounded source closure exceeded')
    return dict(version=1, scope=SCOPE, project_root=str(root), producer_root=str(producer),
        accepted_report=dict(REPORT), seed=2027, ceiling=1200, scripts_namespace_package_no_initializer=True,
        source_closure=closure, cooperative_limits=dict(cpu=3500, wall=2700, rss=12 * 2**30, spill=8 * 2**30),
        whole_operation_limits=dict(cpu=4200, wall=3600),
        whole_operation_note='External supervision must include startup, hashing, preparation, scoring, verification, failures and exit',
        expected_real_accounting=dict(fits=2, prefix_points=2400, full_parity_predicts=6,
                                     parity_scores=4902894, persisted_scores=1634298))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.expanduser().absolute()
    require(not output.exists() and not output.is_symlink() and output.parent.is_dir(), 'New request file required')
    body = build_request(ROOT, args.producer_root.expanduser())
    raw = (json.dumps(body, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf8')
    with output.open('xb') as stream:
        stream.write(raw)
    print(json.dumps(dict(path=str(output), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)), sort_keys=True))


if __name__ == '__main__':
    main()
