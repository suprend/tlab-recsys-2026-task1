"""OTTO-3: the OTTO-1 agent with more candidate rounds, in an isolated tree (exploratory, after OTTO-1).

Every command runs one iteration ``--iteration ID`` (see ``ITERATIONS``) and then hands its
arguments to the OTTO-1 entry point it names, with these changes made in the process only:

- outputs under ``artifacts/otto3/<ID>/``; the load partitions keep their OTTO-1 paths (view
  digests record them); ``collections``, ``calibration``, ``probe``,
  ``smoke`` and ``gate`` are symlinks to the OTTO-1 directories and are only read;
- the agent set is ``configs/datasets/otto3-<ID>-set.json``, the journal ``docs/otto3-run/<ID>/``;
- the prereg gate is OTTO-1's with the iteration set in place of the OTTO-1 set: committed
  prereg, base as recorded there, code identity as in the prereg or its last deviation (the
  OTTO-1 modules unchanged), the iteration set committed clean with a clean audit;
- the agent gets ``rounds`` rounds, the first ``s_rounds`` of them for tables and sources,
  up to ``max_sources`` sources and ``ba_max`` candidates per session;
- ``replay``: the valid proposals of an earlier iteration's set are evaluated again in their
  rounds (S rounds as they were, F rounds moved behind the new S rounds) without an LLM call,
  so the agent of this iteration sees them as accepted and proposes beyond them.

``.venv/bin/python -I scripts/otto3.py --iteration ID setup``
``.venv/bin/python -I scripts/otto3.py --iteration ID run --probe artifacts/otto/probe/probe1 --name run-ID``
``.venv/bin/python -I scripts/otto3.py --iteration ID agent freeze|audit|sidecar|leakcheck ...``
``.venv/bin/python -I scripts/otto3.py --iteration ID pool fit|evaluate ...``
``.venv/bin/python -I scripts/otto3.py --iteration ID data assemble ...``
``.venv/bin/python -I scripts/otto3.py --iteration ID check-shared``

OTTO-1 code, receipts and artifacts are not changed; this file is outside ``CODE_MODULES``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

_HERE = Path(__file__).resolve().parents[1]
if str(_HERE) not in sys.path:
    sys.path.append(str(_HERE))

from scripts import otto_common as oc  # noqa: E402
from scripts import otto_agent as oa  # noqa: E402
from scripts import otto_model as om  # noqa: E402

ROOT = oc.ROOT

require = oc.require

ITERATIONS = {
    'i1': dict(rounds=8, s_rounds=4, max_sources=10, ba_max=300, replay=None),
    # i1 replayed (S rounds 1-4, F rounds 5-8 -> 7-10), two new S rounds (5-6) and two new F rounds (11-12)
    'i2': dict(rounds=12, s_rounds=6, max_sources=14, ba_max=300, replay='i1'),
}
SHARED = ('collections', 'calibration', 'probe', 'smoke', 'gate')
OTTO1 = ('artifacts', 'otto')
SNAPSHOT = 'shared-snapshot.json'
AGENT_COMMANDS = ('freeze', 'audit', 'sidecar', 'leakcheck')
_ORIGINAL = dict(artifacts=oc.ARTIFACTS, config_path=oc.config_path, require_prereg=oc.require_prereg,
                 frozen_agent_columns=om.frozen_agent_columns, journal_dir=oa.journal_dir, load_tree=oc._load_tree,
                 constants={k: getattr(oa, k) for k in ('ROUNDS', 'S_ROUNDS', 'MAX_CALLS', 'MAX_SOURCES', 'BA_MAX')},
                 prompt=dict(oa.PROMPT_CONSTANTS), ba_union=oa.ba_union.__defaults__)


def iteration_root(iteration):
    return ROOT/'artifacts'/'otto3'/iteration


def set_path(iteration):
    return ROOT/'configs'/'datasets'/f'otto3-{iteration}-set.json'


def journal_dir(iteration):
    return ROOT/'docs'/'otto3-run'/iteration


def require_prereg3(check_code=True):
    """OTTO-1's gate with the iteration set: prereg and base committed as recorded, code as in the
    prereg or its last deviation, the iteration set committed clean with a clean audit."""
    prereg = oc.receipt('prereg')
    base = _ORIGINAL['config_path']('base')
    require(oc.committed_clean(base) and oc.sha256_file(base) == prereg['base_sha256'], 'base differs from prereg')
    path = oc.config_path('set')
    require(oc.committed_clean(path), f'{path.name} is not committed clean')
    record = oa.read_set(path, oc.read_base())          # schema, digest, phases, audit of this digest
    oc.require_clean_audit(record)
    # the prompt identity covers rounds, S rounds, sources and the candidate cap of the iteration
    require(record['prompt_digest'] == oa.prompt_identity()['digest'],
            'The set was made with other iteration settings (prompt identity differs)')
    if check_code:
        require(oc.code_identity(strict=True)['files'] == oc.latest_code(prereg),
                'Code differs from prereg and deviations')
    return prereg


def configure(iteration):
    """Point the OTTO-1 modules at the iteration (process-local); returns its settings."""
    require(iteration in ITERATIONS, f'Unknown iteration {iteration!r}: {sorted(ITERATIONS)}')
    cfg = ITERATIONS[iteration]
    require(1 <= cfg['s_rounds'] < cfg['rounds'], 'S rounds come before at least one F round')
    oc.ARTIFACTS = ('artifacts', 'otto3', iteration)

    def config_path(kind):
        return set_path(iteration) if kind == 'set' else _ORIGINAL['config_path'](kind)

    oc.config_path = config_path
    # the load partitions stay at their OTTO-1 paths: view digests (probe.json, the set) record them
    oc._load_tree = lambda source: ROOT.joinpath(*OTTO1, 'load', oc._LOAD_TREES[source])
    oc.require_prereg = require_prereg3
    om.frozen_agent_columns = lambda prereg, agent_set: oc.agent_columns(agent_set)
    oa.journal_dir = lambda: journal_dir(iteration)
    oa.ROUNDS, oa.S_ROUNDS = cfg['rounds'], cfg['s_rounds']
    oa.MAX_CALLS = 2*cfg['rounds']
    oa.MAX_SOURCES, oa.BA_MAX = cfg['max_sources'], cfg['ba_max']
    oa.ba_union.__defaults__ = (cfg['ba_max'],)
    oa.PROMPT_CONSTANTS.update(rounds=cfg['rounds'], s_rounds=cfg['s_rounds'], f_first_round=cfg['s_rounds']+1,
                               max_sources=cfg['max_sources'], ba_max=cfg['ba_max'])
    return cfg


def restore():
    """Undo ``configure`` (tests)."""
    oc.ARTIFACTS, oc.config_path = _ORIGINAL['artifacts'], _ORIGINAL['config_path']
    oc.require_prereg, om.frozen_agent_columns = _ORIGINAL['require_prereg'], _ORIGINAL['frozen_agent_columns']
    oa.journal_dir, oc._load_tree = _ORIGINAL['journal_dir'], _ORIGINAL['load_tree']
    for key, value in _ORIGINAL['constants'].items():
        setattr(oa, key, value)
    oa.PROMPT_CONSTANTS.clear()
    oa.PROMPT_CONSTANTS.update(_ORIGINAL['prompt'])
    oa.ba_union.__defaults__ = _ORIGINAL['ba_union']


def setup(iteration):
    """The iteration tree with read-only symlinks to the shared OTTO-1 directories and their snapshot."""
    root = iteration_root(iteration)
    root.mkdir(parents=True, exist_ok=True)
    for kind in SHARED:
        link = root/kind
        target = Path(os.path.relpath(ROOT.joinpath(*OTTO1, kind), root))
        if link.is_symlink():
            require(Path(os.readlink(link)) == target, f'{link} points elsewhere')
            continue
        require(not link.exists(), f'{link} exists and is not the symlink')
        link.symlink_to(target, target_is_directory=True)
    snapshot = root/SNAPSHOT
    if not snapshot.exists():
        oc.atomic_json(snapshot, shared_state())
    return dict(root=str(root), shared=list(SHARED))


def shared_state():
    """(size, mtime_ns) of every file under the shared OTTO-1 directories."""
    out = {}
    for kind in SHARED:
        base = ROOT.joinpath(*OTTO1, kind)
        for path in sorted(base.rglob('*')):
            if path.is_file() and not path.is_symlink():
                stat = path.stat()
                out[path.relative_to(ROOT).as_posix()] = [stat.st_size, stat.st_mtime_ns]
    return out


def check_shared(iteration):
    before = oc.read_json(iteration_root(iteration)/SNAPSHOT)
    now = shared_state()
    changed = sorted(k for k in set(before) | set(now) if before.get(k) != now.get(k))
    require(not changed, f'Shared OTTO-1 files changed: {changed[:5]}')
    return dict(files=len(now), changed=0)


# ------------------------------------------------------------------------------- replay

def replay_plan(iteration):
    """{round: [proposal fields]} of the valid proposals of the replayed set (empty without replay)."""
    cfg = ITERATIONS[iteration]
    if cfg['replay'] is None:
        return {}
    previous = ITERATIONS[cfg['replay']]
    require(previous['s_rounds'] <= cfg['s_rounds'], 'The replayed S rounds must fit into the new S rounds')
    record = oc.read_json(set_path(cfg['replay']))
    require(oc.committed_clean(set_path(cfg['replay'])), 'The replayed set is not committed clean')
    oc.require_clean_audit(record)
    require(record['digest'] == oa.set_digest(record['proposals']), 'The replayed set differs from its digest')
    shift = cfg['s_rounds']-previous['s_rounds']
    plan = {}
    for proposal in record['proposals']:
        number = proposal['round'] if proposal['round'] <= previous['s_rounds'] else proposal['round']+shift
        plan.setdefault(number, []).append({key: proposal[key] for key in oa.FIELDS})
    require(max(plan) <= cfg['rounds'], 'The replayed rounds exceed the rounds of the iteration')
    require(all(len(items) <= oa.PROPOSALS for items in plan.values()), 'A replayed round holds too many proposals')
    return plan


def replay_ask(plan, ask=None):
    """``ask`` of run_loop: the replayed proposals of a planned round, otherwise the LLM call."""
    ask = oa.ask_proposals if ask is None else ask
    marker = 'This is round '

    def call(prompt, model):
        start = prompt.rindex(marker)+len(marker)
        number = int(prompt[start:].split(' ', 1)[0])
        if number in plan:
            text = json.dumps(plan[number], ensure_ascii=False)
            return oa.parse_proposals(text), dict(cost_usd=0.0, seconds=0.0, text=text, replay=True)
        return ask(prompt, model)

    return call


def run(iteration, probe, name, smoke=None, retry_of=None, reason=None):
    cfg = ITERATIONS[iteration]
    plan = replay_plan(iteration)
    result = oa.run_loop(Path(probe), name, rounds=cfg['rounds'], max_calls=oa.MAX_CALLS,
                         ask=replay_ask(plan) if plan else None, retry_of=retry_of, reason=reason, smoke=smoke)
    return dict(command='run', path=result['path'], calls=result['calls'], cost_usd=result['cost_usd'],
                rounds=result['rounds_run'], stop=result['stop'], attempts=result['attempts'], valid=result['valid'],
                sources=result['sources'], columns=len(result['columns']), replayed=sum(map(len, plan.values())))


# ------------------------------------------------------------------------------- CLI

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    require(len(argv) >= 3 and argv[0] == '--iteration', 'usage: otto3.py --iteration ID COMMAND ...')
    iteration, command, rest = argv[1], argv[2], argv[3:]
    configure(iteration)
    if command == 'setup':
        print(json.dumps(setup(iteration)))
        return 0
    if command == 'check-shared':
        print(json.dumps(check_shared(iteration)))
        return 0
    require((iteration_root(iteration)/SNAPSHOT).exists(), 'Run setup first')
    if command == 'run':
        import argparse
        parser = argparse.ArgumentParser(prog='otto3.py run')
        parser.add_argument('--probe', type=Path, required=True)
        parser.add_argument('--name', required=True)
        parser.add_argument('--smoke', type=Path)
        parser.add_argument('--retry-of', type=Path)
        parser.add_argument('--reason')
        args = parser.parse_args(rest)
        oc.isolated()
        print(json.dumps(run(iteration, args.probe, args.name, args.smoke, args.retry_of, args.reason),
                         ensure_ascii=False))
        return 0
    if command == 'agent':
        # run goes through the wrapper (rounds and replay); export, calibration and probe belong to OTTO-1
        require(rest and rest[0] in AGENT_COMMANDS, f'agent commands here: {", ".join(AGENT_COMMANDS)}')
        return oa.main(rest)
    if command == 'pool':
        from scripts import otto2_pool as op
        return op.main(rest)
    if command == 'data':
        from scripts import otto_data as od
        return od.main(rest)
    raise SystemExit(f'Unknown command {command!r}')


if __name__ == '__main__':
    raise SystemExit(main())
