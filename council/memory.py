"""Memory trial of the contract (§2 «Пик памяти»): the training of an arm in recipe full_test on the refit span, in
its own process, as council.fit does it (pool, exp.sample_train, join, exp.fit). Nothing is scored and nothing but the
peak is written: the model is discarded, so no day of C_test is read. Prints and appends to RUNS/memory.jsonl
{arm, recipe, tables, features, train_rows, fit_queries, peak_rss_gb, seconds}.
  TASK1_PERIOD=2020 .venv/bin/python -m council.memory --arm Hrp
"""
import argparse
import json
import time

from council import fit, plan, roles
from task1 import exp, placebo
from task1 import model as M


def trial(arm, recipe='full_test', span='refit'):
    tables = plan.arms(plan._load('curation.json'))[arm]
    s = {'name': f'memory_{arm}_{recipe}', 'fit': span, 'eval': None, 'keep_half': None, 'recipe': recipe,
         'extra': tables, 'seed': roles.TEST_SEEDS[0][0], 'neg_seed': roles.TEST_SEEDS[0][1], 'placebo': None}
    for t in tables:
        fit._table(t, s['name'])
    cfg = fit.config(s)
    t0 = time.time()
    train = exp.sample_train(fit.pool(roles.days(span), cfg['days'], cfg['cap']), cfg)
    train, _ = fit.join(train, s)
    features = M.base_features(train, cfg['drop'])
    rows, queries = len(train), int(train.qid.nunique())
    t1 = time.time()
    exp.fit(train, features, cfg)
    rec = dict(arm=arm, recipe=recipe, span=span, tables=len(tables), features=len(features), train_rows=rows,
               fit_queries=queries, peak_rss_gb=placebo.peak_gb(),
               seconds={'prepare': round(t1 - t0), 'fit': round(time.time() - t1)},
               started=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t0)))
    with open(roles.RUNS / 'memory.jsonl', 'a') as f:
        f.write(json.dumps(rec) + '\n')
    print(json.dumps(rec), flush=True)
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--arm', default='Hrp', choices=['Hr', 'Hrp', 'ALLP', 'Rb1', 'Rb2'])
    ap.add_argument('--recipe', default='full_test', choices=sorted(roles.RECIPES))
    a = ap.parse_args(argv)
    trial(a.arm, a.recipe)


if __name__ == '__main__':
    main()
