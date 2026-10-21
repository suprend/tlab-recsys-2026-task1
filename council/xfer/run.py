"""Entry point of the council on xfer (council/runs/xfer/contract.md §3, §4): one dataset per process.

Run: python -I council/xfer/run.py --dataset tinkoff|sber [--root /tmp/tlab-<...>] <stage> [options]
(from the repository root, e.g. .venv/bin/python -I council/xfer/run.py --dataset tinkoff info)

-I is required: without it the directory of this file is on sys.path and council/xfer/queue.py would shadow the
standard module of the same name. ROOT is appended to sys.path as in the xfer scripts. TASK1_PERIOD is set to 2020
when unset (council.evidence and council.design are imported unchanged); any other value is refused. --root moves
every council path (runs, artifacts, the LLM directory) under a test root below /tmp/tlab- (contract §8.8); the
queue hands it to the fit processes.

Stages (STAGES below; each is a thin wrapper, the work is in the module named):
  info          anchors per phase, paths, code identity against the prereg (read-only)    run.py
  stages        this list                                                                  run.py
  queue-path    queue-path.json: path checks + noise fits                                  plan.path_queue
  queue NAME    run queue-NAME.json, one fit per process under the heavy lock              queue.run
  prereg0       path checks, noise, power gate -> prereg-0.json                            plan.prereg0
  reference     Rb<k> (--k 1|2) -> reference-rb<k>.json                                    agents.reference
  wave1         G1-G4 cards -> cards-wave1.json                                            agents.wave1
  evidence      probes of the cards and Rb proposals -> probes.json (gate before each)     sandbox.probe_stage
  cross         critiques -> critiques.json                                                agents.cross_exam
  authors       replies -> cards-final.json                                                agents.author_replies
  prereg1       -> prereg-1.json                                                           agents.prereg1
  curate        -> curation.json                                                           curate.stage
  compute       council tables -> sidecars, compute.json (heavy)                           compute.stage
  plan-build    -> prereg-2.json, queue-plan.json                                          plan.build
  analyze       -> plan-result.json (+ queue-confirm.json)                                 plan.analyze
  select        -> selection.json                                                          plan.select
  start-test    the test.started marker after «да»                                         broker.start_test
  test-queue    -> queue-test.json                                                         plan.test_queue
  read-test     -> test.json                                                               plan.read_test
  fit-one       one fit (--spec, --stamp, --data: files), spawned by queue.run             fit.main

council.xfer.agents (the LLM stages) is written by its own implementer; until it exists those stages exit with a
message. Plain imports inside the wrappers: no module of this package imports a stage it does not run.
"""
import sys

if not sys.flags.isolated:
    raise SystemExit('run with python -I council/xfer/run.py (the package directory would shadow the stdlib queue)')

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

PERIOD = '2020'


def period() -> None:
    """TASK1_PERIOD = 2020 for this process (set when unset, refused when different)."""
    value = os.environ.setdefault('TASK1_PERIOD', PERIOD)
    if value != PERIOD:
        raise SystemExit(f'TASK1_PERIOD={value!r}: the council on xfer runs with TASK1_PERIOD={PERIOD}')


def _json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))


def _agents():
    try:
        from council.xfer import agents
    except ImportError as e:
        if getattr(e, 'name', None) == 'council.xfer.agents':
            raise SystemExit('council.xfer.agents is not implemented yet: the LLM stages are not available') from None
        raise
    return agents


def _load(ds, name: str):
    p = ds.paths.run_file(name)
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def cards_for_evidence(ds) -> list[dict]:
    """The cards the evidence stage probes: cards-final.json once the authors replied, else cards-wave1.json
    (both {'cards': [...]})."""
    for name in ('cards-final.json', 'cards-wave1.json'):
        state = _load(ds, name)
        if state and state.get('cards'):
            return state['cards']
    raise SystemExit('run wave1 first: no cards')


def reference_sets(ds) -> dict:
    """{k: proposals} of reference-rb1.json and reference-rb2.json that exist ({'proposals': [{table, level, sql,
    columns}]})."""
    return {k: s['proposals'] for k in (1, 2) if (s := _load(ds, f'reference-rb{k}.json')) and s.get('proposals')}


# ---------------------------------------------------------------- stages

def info(ds, args) -> dict:
    from council.xfer import roles
    ident = roles.identity(ds)
    prereg = roles.prereg_code(ds)
    out = {
        'dataset': ds.name,
        'anchors': {'fit': [str(a) for a in ds.fit_anchors], 'select': str(ds.s0_anchor),
                    'test_train': [str(a) for a in ds.test_train_anchors], 'test': str(ds.test_anchor),
                    'probe': [str(a) for a in ds.probe_anchors]},
        'probe_users': ds.probe_users, 'K': ds.K,
        'paths': {'root': ds.paths.root, 'runs': ds.paths.runs, 'out': ds.paths.out, 'llm': ds.paths.llm},
        'code_matches_prereg': ident['code'] == prereg,
        'council': ident['council'],
    }
    _json(out)
    return out


def stages(ds, args) -> dict:
    out = {name: doc for name, (_, doc) in STAGES.items()}
    _json(out)
    return out


def queue_path(ds, args):
    from council.xfer import plan
    return len(plan.path_queue(ds))


def queue_run(ds, args):
    from council.xfer import queue
    if not args.name:
        raise SystemExit('queue needs the queue name: queue NAME (queue-NAME.json)')
    out = queue.run(ds, ds.paths.queue(args.name), wait=not args.no_wait)
    _json(out)
    return out


def prereg0(ds, args):
    from council.xfer import plan
    return plan.prereg0(ds)


def reference(ds, args):
    if args.k not in (1, 2):
        raise SystemExit('reference needs --k 1 or --k 2')
    return _agents().reference(ds, args.k)


def wave1(ds, args):
    return _agents().wave1(ds)


def probe_gate(ds):
    """The gate of sandbox.probe_stage (contract §8.7): a callable without arguments, asked before every probe;
    it returns the reasons a probe may not run now ([] = it may): queue.light_gate('probe') next to the heavy step
    of the moment (queue.heavy_now over the queue journals of both datasets). The stage waits while there are
    reasons."""
    from council.xfer import queue, roles
    journals = [roles.paths(x, ds.paths.root).queue_log for x in roles.DATASETS]

    def gate() -> list[str]:
        return queue.light_gate('probe', heavy=queue.heavy_now(journals))
    return gate


def evidence(ds, args):
    from council.xfer import sandbox
    out = sandbox.probe_stage(ds, cards_for_evidence(ds), reference_sets(ds), gate=probe_gate(ds),
                              threads=args.threads)
    print(len(out.get('cards', {})), 'cards measured')
    return out


def cross(ds, args):
    return _agents().cross_exam(ds)


def authors(ds, args):
    return _agents().author_replies(ds)


def prereg1(ds, args):
    return _agents().prereg1(ds)


def curate(ds, args):
    from council.xfer import curate as C
    return C.stage(ds)


def compute(ds, args):
    from council.xfer import compute as C
    return C.stage(ds, threads=args.threads)


def plan_build(ds, args):
    from council.xfer import plan
    return plan.build(ds)


def analyze(ds, args):
    from council.xfer import plan
    return plan.analyze(ds)


def select(ds, args):
    from council.xfer import plan
    cut = tuple(x for x in (args.cut or '').split(',') if x)
    return plan.select(ds, cut=cut, cut_plan=args.cut_plan)


def start_test(ds, args):
    from council.xfer import broker
    return broker.start_test(ds)


def test_queue(ds, args):
    from council.xfer import plan
    return len(plan.test_queue(ds))


def read_test(ds, args):
    from council.xfer import plan
    return plan.read_test(ds)


def fit_one(ds, args):
    from council.xfer import fit
    if not (args.spec and args.stamp and args.data):
        raise SystemExit('fit-one needs --spec FILE --stamp FILE --data FILE (queue.fit_command)')
    # stamp and data travel as files (contract §8.4); fit.main gets their JSON text inside this process only
    stamp, data = (Path(f).read_text(encoding='utf-8') for f in (args.stamp, args.data))
    raise SystemExit(fit.main(ds, ['--spec', args.spec, '--stamp', stamp, '--data', data]))


STAGES = {
    'info': (info, 'anchors, paths, code identity against the prereg'),
    'stages': (stages, 'this list'),
    'queue-path': (queue_path, 'queue-path.json (path checks + noise)'),
    'queue': (queue_run, 'run queue-NAME.json under the heavy lock'),
    'prereg0': (prereg0, 'prereg-0.json'),
    'reference': (reference, 'reference-rb<k>.json (--k)'),
    'wave1': (wave1, 'cards-wave1.json'),
    'evidence': (evidence, 'probes.json'),
    'cross': (cross, 'critiques.json'),
    'authors': (authors, 'cards-final.json'),
    'prereg1': (prereg1, 'prereg-1.json'),
    'curate': (curate, 'curation.json'),
    'compute': (compute, 'council tables and compute.json'),
    'plan-build': (plan_build, 'prereg-2.json and queue-plan.json'),
    'analyze': (analyze, 'plan-result.json'),
    'select': (select, 'selection.json'),
    'start-test': (start_test, 'the test.started marker'),
    'test-queue': (test_queue, 'queue-test.json'),
    'read-test': (read_test, 'test.json'),
    'fit-one': (fit_one, 'one fit, spawned by the queue'),
}


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], allow_abbrev=False)
    ap.add_argument('--dataset', required=True, choices=['tinkoff', 'sber'])
    ap.add_argument('--root', help='test root of the council paths, under /tmp/tlab- (contract §8.8)')
    ap.add_argument('stage', choices=list(STAGES))
    ap.add_argument('name', nargs='?', help='queue: the queue name (queue-NAME.json)')
    ap.add_argument('--k', type=int, choices=[1, 2], help='reference: Rb<k>')
    ap.add_argument('--threads', type=int, default=4)
    ap.add_argument('--no-wait', action='store_true', help='queue: refuse instead of waiting for the lock')
    ap.add_argument('--cut', help='select: comma-separated arms cut from the test queue (contract §4, §9.3)')
    ap.add_argument('--cut-plan', action='store_true', help='select: SEL = ALL_P without the plan (§4 items 4-5)')
    ap.add_argument('--spec', help='fit-one: the spec file')
    ap.add_argument('--stamp', help='fit-one: the code stamp file of the queue (JSON)')
    ap.add_argument('--data', help='fit-one: the data stamp file of the spec (JSON)')
    return ap


def main(argv=None) -> int:
    period()
    argv = sys.argv[1:] if argv is None else list(argv)
    ap = parser()
    args = ap.parse_args(argv)
    from council.xfer import roles
    try:
        ds = roles.activate(args.dataset, root=args.root)
    except ValueError as e:
        raise SystemExit(str(e)) from None
    STAGES[args.stage][0](ds, args)
    return 0


if __name__ == '__main__':
    sys.exit(main())
