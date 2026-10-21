"""Post-hoc placebo for the H&M MA arm: port MA with the agent block permuted by rows within each anchor.

Spec: docs/hm-ma-placebo.md, written before any run. Outside the MA contract: the agent
set, the prereg, the sidecars, the MA fits, the gate and the submissions are not touched.
``fit`` calls the unchanged ``hm_agent_kaggle.fit_ma`` with ``sidecar_rows`` wrapped so that
the 34 agent columns of every anchor are permuted by rows (one permutation for all columns);
the report is then marked ``arm MApl`` so that contrast and gate of the contract refuse it.
``read`` applies the spec's rule once. Run as ``python -I scripts/hm_ma_placebo.py``.
"""
from __future__ import annotations

from datetime import date
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts import hm_agent_kaggle as ma  # noqa: E402
from scripts import hm_experiment as experiment  # noqa: E402
from scripts import hm_kaggle as kaggle  # noqa: E402

SALT = 20261021
ARM = 'MApl'
RESULT_FORMAT = 'hm-ma-placebo-result-v1'
SPEC = 'docs/hm-ma-placebo.md'
CODE = ('scripts/hm_ma_placebo.py', 'tests/test_hm_ma_placebo.py', SPEC)
READINGS = ('прирост MA несёт содержание колонок агента, а не их число', 'MA не отличима от плацебо',
            'плацебо лучше MA', 'не решено')


def permutation(n, seed, anchor):
    import numpy as np
    return np.random.default_rng([SALT, seed, date.fromisoformat(anchor).toordinal()]).permutation(n)


def permute(block, columns, seed, anchor):
    """Rows of ``block`` keep their keys; row i gets the values of all ``columns`` of row perm[i]."""
    perm = permutation(len(block), seed, anchor)
    out = block.copy(deep=False)  # column replacement below never writes into ``block``
    for column in columns:
        out[column] = block[column].to_numpy()[perm]
    return out


def committed():
    """HEAD, once the spec, this module and its tests are committed."""
    run = lambda *a: subprocess.run(['git', *a], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    dirty = run('status', '--porcelain', '--', *CODE)
    if dirty:
        raise RuntimeError(f'commit the spec, the code and the tests first:\n{dirty}')
    return run('rev-parse', 'HEAD').strip()


def unchanged_since(commit):
    """True when the spec, this module and its tests are byte-equal at ``commit`` and HEAD."""
    return not subprocess.run(['git', 'diff', '--name-only', commit, 'HEAD', '--', *CODE], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()


def permutation_problem(report, permuted):
    """Each input anchor permuted exactly once, over exactly its fit rows; else the reason."""
    populations = report['training_populations']+[report['validation_population']]
    expected = [dict(anchor=p['anchor'], rows=p['fit_rows']) for p in populations]
    if [i['anchor'] for i in report['inputs']] != [e['anchor'] for e in expected]:
        return 'inputs and populations disagree on anchors'
    if permuted != expected:
        return f'permuted {permuted} differs from the fit rows {expected}'
    return None


def own_code():
    return {name: experiment.sha256_file(ROOT/name) for name in CODE}


def fit(seed, train, validation, sidecars, prereg, output, threads=8, wall_seconds=14400):
    commit = committed()
    if validation is None:
        raise ValueError('The placebo is a port fit: --validation is required')
    original = ma.sidecar_rows
    anchors = []

    def wrapped(con, frame, path, columns):
        block = original(con, frame, path, columns)
        anchor = Path(path).parent.name
        anchors.append(dict(anchor=anchor, rows=len(block)))
        return permute(block, columns, seed, anchor)

    output = kaggle.private_path(output)
    if output.exists():
        raise FileExistsError(f'{output}: placebo output must be new; an existing report is never touched')
    ma.sidecar_rows = wrapped
    problem = None
    try:
        ma.fit_ma(seed, train, sidecars, prereg, output, validation, threads, wall_seconds)
    finally:
        ma.sidecar_rows = original
        path = output/'report.json'
        if path.is_file():  # created by this call: the output did not exist before
            stored = kaggle.read_json(path)
            stored['arm'] = ARM
            stored['placebo'] = dict(spec=SPEC, rule='rows of the agent block permuted within each anchor, '
                                     'one permutation for all agent columns',
                                     rng=f'numpy.random.default_rng([{SALT}, seed, anchor.toordinal()])',
                                     permuted=anchors, commit=commit, code=own_code())
            if stored.get('status') == 'completed':
                problem = permutation_problem(stored, anchors)
                if problem:
                    stored['status'], stored['error'] = 'failed', dict(type='PlaceboError', message=problem)
            kaggle.atomic_json(path, stored)
    if problem:
        raise RuntimeError(problem)
    return kaggle.read_json(output/'report.json')


def port_fit(path, arm):
    path = Path(path).resolve()
    report = kaggle.read_json(path/'report.json')
    formats = {'M': kaggle.FIT_FORMAT, 'MA': ma.FIT_FORMAT, ARM: ma.FIT_FORMAT}
    if (report.get('format'), report.get('arm')) != (formats[arm], arm) or report.get('status') != 'completed' \
            or 'validation_metrics' not in report:
        raise ValueError(f'{path}: completed {arm} port fit with validation required')
    if experiment.sha256_file(path/'query-metrics.parquet') != report['files']['query-metrics.parquet']:
        raise ValueError(f'{path}: query-metrics.parquet differs from its report')
    return dict(path=path, report=report, seed=report['seed'], name=f"{arm}{report['seed']}")


def metrics(path):
    import duckdb
    con = duckdb.connect(':memory:')
    try:
        return {u: dict(targets=t, ap12=ap) for u, t, ap in con.execute(
            'SELECT customer_id,targets,ap12 FROM read_parquet(?) ORDER BY customer_id',
            [str(Path(path)/'query-metrics.parquet')]).fetchall()}
    finally:
        con.close()


def average(groups):
    first = groups[0]
    return {u: dict(targets=first[u]['targets'], ap12=math.fsum(g[u]['ap12'] for g in groups)/len(groups))
            for u in first}


def reading(diffs):
    """Rule of the spec over the per-seed (d, [lo, hi])."""
    if all(d > 0 and lo > 0 for d, (lo, hi) in diffs):
        return READINGS[0]
    if all(lo <= 0 <= hi for _, (lo, hi) in diffs):
        return READINGS[1]
    if all(hi < 0 for _, (lo, hi) in diffs):
        return READINGS[2]
    return READINGS[3]


def read(ma_paths, placebo_paths, m_paths, output):
    from scripts import hm_result_audit as audit
    head = committed()
    output = kaggle.private_path(output)
    if output.exists():
        raise FileExistsError('The reading is done once: output must be new')
    arms = {'MA': [port_fit(p, 'MA') for p in ma_paths], ARM: [port_fit(p, ARM) for p in placebo_paths],
            'M': [port_fit(p, 'M') for p in m_paths]}
    seeds = sorted(f['seed'] for f in arms['MA'])
    if len(seeds) != 2 or any(sorted(f['seed'] for f in fits) != seeds for fits in arms.values()):
        raise ValueError('Every arm needs the same two seeds')
    base = arms['MA'][0]['report']
    hyper = lambda r: {k: v for k, v in r['hyperparameters'].items() if k != 'random_seed'}
    for f in arms['MA'][1:]+arms[ARM]+arms['M']:
        r = f['report']
        if (r['inputs'] != base['inputs'] or r['training_populations'] != base['training_populations'] or
                r['validation_population'] != base['validation_population'] or hyper(r) != hyper(base) or
                r['runtime'] != base['runtime'] or r['database'] != base['database'] or
                r['features']['contract_digest'] != base['features']['contract_digest']):
            raise ValueError(f"{f['name']} is not paired with MA: inputs, populations, recipe, runtime and database "
                             'must be equal')
    commits = {f['report'].get('placebo', {}).get('commit') for f in arms[ARM]}
    if len(commits) != 1 or None in commits:
        raise ValueError('Both placebo fits must come from one commit of this module')
    commit = commits.pop()
    if not unchanged_since(commit):
        raise ValueError(f'The spec, the code or the tests changed since the placebo fits ({commit})')
    for f in arms[ARM]:
        r = f['report']
        if r['agent'] != base['agent'] or r['features'] != base['features'] or r['code'] != base['code']:
            raise ValueError(f"{f['name']} differs from MA in agent set, features or code")
        if r['placebo']['code'] != own_code():
            raise ValueError(f"{f['name']} was fitted by another version of this module")
        problem = permutation_problem(r, r['placebo']['permuted'])
        if problem:
            raise ValueError(f"{f['name']}: {problem}")
    values = {f['name']: metrics(f['path']) for fits in arms.values() for f in fits}
    first = next(iter(values.values()))
    if any({u: v['targets'] for u, v in m.items()} != {u: v['targets'] for u, v in first.items()} for m in values.values()):
        raise ValueError('Fits must share validation users and target counts')
    positive = [u for u, v in first.items() if v['targets'] > 0]
    maps = {}
    for fits in arms.values():
        for f in fits:
            computed = math.fsum(values[f['name']][u]['ap12'] for u in positive)/len(positive)
            if abs(computed-f['report']['validation_metrics']['map_at_12_conditional']) > audit.TOLERANCE:
                raise ValueError(f"{f['name']}: query metrics disagree with its reported MAP")
            maps[f['name']] = computed

    def diff(reference, alternative):
        b = audit.paired_bootstrap(reference, alternative, draws=ma.BOOTSTRAP_DRAWS, seed=ma.BOOTSTRAP_SEED)
        return dict(d=b['mean_delta'], ci=b['percentile_95'])

    by = lambda arm, seed: values[f'{arm}{seed}']
    D = {str(s): diff(by(ARM, s), by('MA', s)) for s in seeds}
    P = {str(s): diff(by('M', s), by(ARM, s)) for s in seeds}
    MA_M = {str(s): diff(by('M', s), by('MA', s)) for s in seeds}
    mean = {name: average([by(arm, s) for s in seeds]) for name, arm in (('MA', 'MA'), (ARM, ARM), ('M', 'M'))}
    result = dict(format=RESULT_FORMAT, spec=SPEC, commit=commit, read_head=head, code=own_code(), positive_queries=len(positive),
                  map_by_fit=maps, D=D, reading=reading([(v['d'], v['ci']) for v in D.values()]),
                  P=P, MA_minus_M=MA_M,
                  mean_of_seeds=dict(D=diff(mean[ARM], mean['MA']), P=diff(mean['M'], mean[ARM]),
                                     MA_minus_M=diff(mean['M'], mean['MA'])),
                  fits={f['name']: dict(path=f['path'].relative_to(ROOT).as_posix(),
                                        report_sha256=experiment.sha256_file(f['path']/'report.json'))
                        for fits in arms.values() for f in fits},
                  created_at_utc=kaggle.utc_now())
    output.parent.mkdir(parents=True, exist_ok=True)
    kaggle.atomic_json(output, result)
    return result


def main(argv=None):
    if not sys.flags.isolated:
        print(json.dumps(dict(status='failed', error_type='RuntimeError', message='run with python -I')))
        return 1
    parser = kaggle.Parser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('fit', help='one port MA fit with the agent block permuted within each anchor')
    command.add_argument('--seed', type=int, choices=(2026, 2027), required=True)
    command.add_argument('--train', type=Path, nargs='+', required=True)
    command.add_argument('--validation', type=Path, required=True)
    command.add_argument('--sidecars', type=Path, required=True)
    command.add_argument('--prereg', type=Path, required=True)
    command.add_argument('--output', type=Path, required=True)
    command.add_argument('--threads', type=int, default=8)
    command.add_argument('--wall-seconds', type=float, default=14400)
    command = sub.add_parser('read', help='the reading of the spec, once')
    command.add_argument('--ma', type=Path, nargs=2, required=True)
    command.add_argument('--placebo', type=Path, nargs=2, required=True)
    command.add_argument('--m', type=Path, nargs=2, required=True)
    command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'fit':
            r = fit(args.seed, args.train, args.validation, args.sidecars, args.prereg, args.output, args.threads,
                    args.wall_seconds)
            summary = dict(status=r['status'], arm=r['arm'], seed=r['seed'], trees=r.get('actual_trees'),
                           permuted=r['placebo']['permuted'],
                           train_positive_rows=sum(p['positive_rows'] for p in r['training_populations']),
                           map_at_12_conditional=r['validation_metrics']['map_at_12_conditional'])
        else:
            r = read(args.ma, args.placebo, args.m, args.output)
            summary = dict(reading=r['reading'], D=r['D'], P=r['P'], map_by_fit=r['map_by_fit'],
                           mean_of_seeds=r['mean_of_seeds'])
        print(json.dumps(summary, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps(dict(status='failed', command=args.command, error_type=type(exc).__name__,
                              message=str(exc)[:500])))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
