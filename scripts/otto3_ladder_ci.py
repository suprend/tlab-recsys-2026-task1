"""Paired bootstrap CI on dev F3 for the steps of the OTTO ladder (OTTO-2 → OTTO-3 i1 → i2 → i3).

Analysis of finished predictions only: nothing is trained or re-ranked. Each arm is the
committed final model of its step, read from its ``eval-F3/ranked.parquet``. The ranked
file must match the SHA-256 and the Score in its ``report.json``, and the model digest of
that report must equal the one in the arm's ``eval-F5/report.json``: the F3 lists come
from the model whose F5 lists went to Kaggle. All arms are scored by ``otto_common.metric``
on the same 300k dev population and open F3 labels, and each pair goes through
``otto_common.bootstrap_ratio`` (2000 draws, seed 2026).

OTTO-2, i1 and i2 are required; i3 joins when its F3 evaluation exists. The committed
receipt is not overwritten when its content (without ``created_utc``) would change,
unless ``--force`` is given; a check run writes elsewhere with ``--output``.

F3 was used to choose between candidates at every step, so these intervals describe
sampling noise of the dev population, not selection: they are descriptive.

    .venv/bin/python -I scripts/otto3_ladder_ci.py [--threads 2] [--output PATH] [--force]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.append(str(_HERE))

from scripts import otto_common as oc  # noqa: E402

ARMS = {
    'OTTO-2': 'artifacts/otto/otto2-pool/f4all-lr10-it2000',
    'i1': 'artifacts/otto3/i1/otto2-pool/f4all-lr10-it2000',
    'i2': 'artifacts/otto3/i2/otto2-pool/f4all-lr10-it2000',
    'i3': 'artifacts/otto3/i3/otto2-pool/f4all-lr10-it2000',
}
REQUIRED = ('OTTO-2', 'i1', 'i2')
OUTPUT = 'docs/otto3-run/ladder-ci-F3.json'


def arms_present():
    present = {name: _HERE/path for name, path in ARMS.items() if (_HERE/path/'eval-F3'/'report.json').exists()}
    missing = [name for name in REQUIRED if name not in present]
    oc.require(not missing, f'Required arms without an F3 evaluation: {", ".join(missing)}')
    for name in ARMS:
        if name not in present:
            print(f'{name}: no F3 evaluation at {ARMS[name]}, skipped', flush=True)
    return present


def read_arm(name, root, digest):
    report = json.loads((root/'eval-F3'/'report.json').read_text(encoding='utf-8'))
    oc.require(report.get('status') == 'completed' and report.get('fold') == 3, f'{name}: not a completed F3 eval')
    oc.require(report['population']['digest'] == digest, f'{name}: another population')
    ranked = root/'eval-F3'/report['ranked']['file']
    oc.require(oc.sha256_file(ranked) == report['ranked']['sha256'], f'{name}: ranked file differs from its report')
    kaggle = root/'eval-F5'/'report.json'
    oc.require(kaggle.exists(), f'{name}: no F5 evaluation to tie the F3 lists to the submitted model')
    oc.require(json.loads(kaggle.read_text(encoding='utf-8'))['models'] == report['models'],
               f'{name}: F3 and F5 come from different models')
    return report, ranked


def write(out, path, force):
    if path.exists() and not force:
        old = json.loads(path.read_text(encoding='utf-8'))
        same = {k: v for k, v in old.items() if k != 'created_utc'} == {k: v for k, v in out.items() if k != 'created_utc'}
        oc.require(same, f'{path} exists with other content; use --output for a check run or --force to replace it')
        print(f'{path}: same content, kept', flush=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(path, flush=True)


def main(threads, output, force):
    collection = Path(oc.collection_dir('val')).resolve()
    population = oc.read_population(collection)
    digest = oc.sessions_digest(population)
    labels = collection/'labels.parquet'
    values, arms = {}, {}
    for name, root in arms_present().items():
        report, ranked = read_arm(name, root, digest)
        result = oc.metric(ranked, labels, sessions=population, threads=threads)
        oc.require(abs(result['score']-report['score']) < 1e-12, f'{name}: Score {result["score"]} != report {report["score"]}')
        values[name] = result
        arms[name] = dict(eval=(root/'eval-F3').relative_to(_HERE).as_posix(), score=result['score'],
                          recall=result['recall'], ranked_sha256=report['ranked']['sha256'], models=report['models'])
        print(f'{name}: {result["score"]:.5f}', flush=True)
    names = list(values)
    pairs = {}
    for i in range(1, len(names)):
        for ref in (names[i-1], names[0]) if i > 1 else (names[0],):
            key = f'{names[i]} - {ref}'
            pairs[key] = {k: v for k, v in oc.bootstrap_ratio(values[ref], values[names[i]]).items() if k != 'sessions'}
            print(f'{key}: {pairs[key]["diff"]:+.5f} CI [{pairs[key]["ci"][0]:+.5f}, {pairs[key]["ci"][1]:+.5f}]',
                  flush=True)
    out = dict(format='otto3-ladder-ci-v1', status='descriptive', fold=3, collection=collection.name,
               population=dict(n=len(population), digest=digest), labels_sha256=oc.sha256_file(labels),
               draws=oc.BOOTSTRAP_DRAWS, seed=oc.BOOTSTRAP_SEED, arms=arms, pairs=pairs, created_utc=oc.utc_now(),
               note='F3 chose between candidates at every step: the CI covers dev sampling noise, not selection.')
    write(out, Path(output) if Path(output).is_absolute() else _HERE/output, force)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--output', default=OUTPUT)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    oc.isolated()
    main(args.threads, args.output, args.force)
