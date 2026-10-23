"""OTTO-2: exploratory dev fits F2 -> F3 with changed size, negatives or recipe (not the contract).

``.venv/bin/python -I scripts/otto2_dev.py --name NAME --arm BA [--n-t N] [--negatives N]
[--iterations N] [--depth N] [--learning-rate X] [--seed 2026]``

Reuses ``otto_model.fit``/``evaluate`` under the committed prereg context with the
overrides applied, and writes fit and evaluation to ``artifacts/otto/otto2-dev/<name>/``.
OTTO-1 receipts, fits and gates are not read for writing and not changed. Training
sessions are still the first N per type in sha256 order, so they must lie inside the
F2 collection (its union is the first ``oc.N_T`` per type): N above ``oc.N_T`` is refused.
Results are exploratory: they pick what goes into the next run, they do not confirm.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts import otto_common as oc  # noqa: E402
from scripts import otto_model as om  # noqa: E402

OUTPUT_ROOT = 'otto2-dev'


def output_root(name):
    return oc.artifacts_dir()/OUTPUT_ROOT/oc.output_name(name)


def run(name, arm='BA', seed=oc.SEEDS[0], n_t=None, negatives=None, recipe=None):
    oc.require(arm in ('B', 'BA'), 'otto2-dev fits B or BA')
    ctx = om.Context.contract()
    try:
        if n_t is not None:
            oc.require(0 < int(n_t) <= oc.N_T, f'N_t must be in (0, {oc.N_T}]: the F2 collection holds no more')
            ctx.n_t = int(n_t)
        if negatives is not None:
            ctx.negatives = int(negatives)
        ctx.recipe_overrides.update(recipe or {})
        root = output_root(name)
        fit = om.fit(ctx, 'dev', arm, seed, output=root/'fit')
        ev = om.evaluate(ctx, 'dev', arm, seed, fit_directory=root/'fit', output=root/'eval')
        summary = dict(name=name, arm=arm, seed=int(seed), N_t=ctx.n_t, negatives=ctx.negatives,
                       recipe=ctx.recipe(seed), fit_seconds=fit['seconds'], eval_seconds=ev['seconds'],
                       rows={t: v['rows'] for t, v in fit['training'].items()},
                       recall=ev['metrics']['recall'], score=ev['metrics']['score'], ceiling=ev['ceiling'])
        oc.atomic_json(root/'summary.json', summary)
        return summary
    finally:
        ctx.close()


def main(argv=None):
    oc.isolated()
    p = argparse.ArgumentParser()
    p.add_argument('--name', required=True)
    p.add_argument('--arm', default='BA')
    p.add_argument('--seed', type=int, default=oc.SEEDS[0])
    p.add_argument('--n-t', type=int)
    p.add_argument('--negatives', type=int)
    p.add_argument('--iterations', type=int)
    p.add_argument('--depth', type=int)
    p.add_argument('--learning-rate', type=float)
    a = p.parse_args(argv)
    recipe = {k: v for k, v in (('iterations', a.iterations), ('depth', a.depth),
                                ('learning_rate', a.learning_rate)) if v is not None}
    with om.quiet_stdout():
        summary = run(a.name, a.arm, a.seed, a.n_t, a.negatives, recipe)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
