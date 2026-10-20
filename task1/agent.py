"""LLM agent that proposes SQL features; greedy forward selection through task1.exp.

Each round the LLM sees the protocol, the current feature names and every earlier attempt with its
measured effect or error, and proposes SQL features. The sandbox (task1.extra) computes each one on the
train and validation days; task1.exp fits the proxy config with the accepted set (the round's base) and
with accepted + proposal, and compares them on validation half A (paired bootstrap over queries). The
best proposal of the round is accepted if its lower 95% bound is above zero and its gain above
--min-gain on two fits with different seeds (the bootstrap over queries does not see the spread of the
fit itself: a seed-only change can exclude zero); the second fit runs only for proposals passing the first. Half B and test days are never used here; test days of accepted features are computed later
with task1.extra (summary.json has the command).

Run: .venv/bin/python -m task1.agent --proxy '{"train_frac": 0.3, "iterations": 300, "lr": 0.12}'
Resume: the same with --run <run-id>; config and proxy come from the log, an unfinished round is closed
with the proposals it had evaluated.
"""
import argparse
import hashlib
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

import duckdb

from task1 import exp
from task1 import period as P
from task1.extra import FeatureError, compute
from task1.model import EXTRA, GROUPS, ROOT, base_features

RUNS = ROOT / 'task1/runs'
LLM_DIR = Path('/tmp/tlab-agent-llm')  # empty working directory; no built-in tools, no MCP servers

PROMPT = """You are a feature engineer for a ranking model of new products. Reply with JSON only.

Task. REES46 multi-category online store, events from 2019-10-01 to 2019-11-30. Every day at the anchor
t = 00:00 UTC we rank products for the users active in [t-48h, t) who have at least one target. A target is
a product whose FIRST cart or purchase by the user happens in [t, t+24h) and that the user never touched
(no event of any type) before t. About 280 candidates per user come from six sources: the global top by
distinct cart/purchase users over 7 days; the top products of the user's 3 heaviest categories and of the
2 heaviest brands; session co-view neighbours of the user's 10 latest views; aggregated co-view scores and
view->acquisition transition scores over the user's 20 latest views. Every product the user touched before
t is excluded, so the (user, candidate) pair itself has no history: user signals work only through the
candidate's category, brand, price, popularity and item-item links to what the user did. A CatBoost model
scores each (user, product) pair; the metric is NDCG@20 per user. Train anchors 2019-10-15..11-07,
validation 11-08..11-13.

Data caveat: cart logging changes level while purchases stay flat (~22k a day): about 33k carts a day
drop to ~18k from Oct 28 and jump x4 (to ~70k) from Nov 8, exactly where validation starts. Raw cart
counts therefore shift between train and validation; prefer normalised forms (shares, ratios, lifts,
ranks, logs) and treat cart and purchase together. The base set reads a 14-day window [t-14d, t).

You can read two DuckDB tables:
  hist(event_time TIMESTAMP, event_type VARCHAR -- 'view'|'cart'|'purchase',
       product_id BIGINT, category_id BIGINT, category_code VARCHAR -- e.g. 'electronics.smartphone', often NULL,
       brand VARCHAR -- often NULL, price DECIMAL(12,2), user_id BIGINT, user_session VARCHAR)
       -- all events strictly before t, starting 2019-10-01; tens of millions of rows, mostly views
  active_users(user_id) -- users with any event in the last 48 hours (a superset of the ranked users)
Write the anchor as TIMESTAMP '{{t}}' (literally, with the braces), e.g.
  event_time >= TIMESTAMP '{{t}}' - INTERVAL 3 DAY

Features already in the model, by prefix (s_ candidate source, u_ user, i_ item, uc_ candidate's category
in the user's history, ub_ brand, up_ price vs user, ui_ popularity vs user, cf_ item-item from recent
views, f_x_ SQL features: hand-written ones of the base and those accepted earlier in this run):
{features}

Rules for a feature query:
- one DuckDB SELECT statement (WITH is fine) reading only hist and active_users; no other tables,
  files or settings;
- returns key columns user_id and/or product_id plus 1-3 numeric value columns named f_x_<something>,
  names not used by any earlier feature;
- exactly one row per key, no NULL keys; keys without a row get NULL; afterwards only the keys present
  among the day's candidates are kept;
- the query cannot see the candidates: product-level features cover all products; user-level and
  pair-level queries must filter user_id IN (SELECT user_id FROM active_users), and pair-level ones must
  enumerate pairs narrowly (e.g. products of the user's recent categories or neighbours of recent views)
  so the result stays well under 50M rows;
- a user-level feature is constant within a user's ranking and helps only through interactions;
- it runs once per day for 30 days with a hard limit of 120 s per day; aim for under 10 s.

Earlier attempts in this run: gain in NDCG@20 on validation half A with its 95% interval (accepted ones
are already in the model; acceptance needs the lower bound above 0 and the gain above {min_gain} on two seeds):
{history}

Propose {n} new features that are likely to improve ranking beyond the current set and differ from
earlier attempts. Think about what signals the current set misses. Answer with a JSON list only:
[{{"name": "short_snake_case", "idea": "one sentence", "sql": "SELECT ..."}}]
"""


class JoinError(RuntimeError):
    pass


def ask_llm(prompt, model):
    t0 = time.time()
    LLM_DIR.mkdir(exist_ok=True)
    r = subprocess.run(['claude', '-p', prompt, '--model', model, '--output-format', 'json', '--tools', '', '--strict-mcp-config'],
                       capture_output=True, text=True, cwd=LLM_DIR, timeout=900)
    out = json.loads(r.stdout)
    meta = {'seconds': round(time.time() - t0, 1), 'cost_usd': out.get('total_cost_usd')}
    m = re.search(r'\[.*\]', out['result'], re.S)
    if not m:
        raise ValueError(f"no JSON list in the answer: {out['result'][:300]}")
    return json.loads(m.group(0)), meta


def day_features(days_dir):
    """Feature columns of the day tables, read from the schema of one file."""
    f = min(Path(days_dir).glob('*.parquet'))
    return base_features(duckdb.read_parquet(str(f)))


def extra_columns(name):
    f = min((EXTRA / name).glob('[0-9]*.parquet'))
    return [c for c in duckdb.read_parquet(str(f)).columns if c.startswith('f_x_')]


def list_features(names):
    groups = {g: [n for n in names if n.startswith(g)] for g in GROUPS}
    return '\n'.join(f"  {g}: {', '.join(v)}" for g, v in groups.items() if v)


def describe(attempts, accepted):
    if not attempts:
        return '(none yet)'
    lines = []
    for h in attempts:
        if 'error' in h:
            lines.append(f"- {h['name']}: FAILED: {h['error'][:300]}\n  sql: {h['sql']}")
        elif 'd' in h:
            lines.append(f"- {h['name']} ({h['idea']}) {h['columns']}: dNDCG={h['d']:+.5f} "
                         f"[{h['ci'][0]:+.5f}, {h['ci'][1]:+.5f}]"
                         + (f", second seed {h['d2']:+.5f}" if 'd2' in h else '')
                         + f" {'ACCEPTED' if h['name'] in accepted else 'rejected'}"
                         f"\n  sql: {h['sql']}")
    return '\n'.join(lines)


def render(features, attempts, accepted, n, min_gain):
    return PROMPT.format(features=list_features(features), history=describe(attempts, accepted), n=n, min_gain=min_gain)


def main():
    P.only_2019('the feature agent')
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default='{"days": "artifacts/task1/v2/days6"}', help='JSON over exp.DEFAULT')
    ap.add_argument('--proxy', default='{}', help='JSON over --config for the search fits')
    ap.add_argument('--rounds', type=int, default=6)
    ap.add_argument('--per-round', type=int, default=5)
    ap.add_argument('--max-llm-calls', type=int, default=15)
    ap.add_argument('--model', default='opus')
    ap.add_argument('--min-gain', type=float, default=0.001)
    ap.add_argument('--threads', type=int, default=8, help='sandbox threads')
    ap.add_argument('--run', help='resume this run id')
    args = ap.parse_args()
    rid = args.run or datetime.now().strftime('agent%Y%m%d_%H%M')
    tag = re.sub(r'[^a-z0-9_]', '_', rid.lower())  # exp and extra names; no dates, exp parses them from paths
    run = RUNS / rid
    run.mkdir(parents=True, exist_ok=True)
    log = run / 'log.jsonl'
    records = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []

    def write(rec):
        records.append(rec)
        with log.open('a') as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + '\n')

    if not records:
        cfg = exp.DEFAULT | json.loads(args.config)
        cfg['days'] = str(ROOT / cfg['days'])
        write({'start': datetime.now().isoformat(timespec='seconds'), 'config': cfg,
               'proxy': json.loads(args.proxy), 'args': vars(args)})
    cfg, proxy = records[0]['config'], records[0]['proxy']
    search = cfg | proxy
    attempts = [r for r in records if 'sql' in r]
    closed = [r for r in records if 'accepted_set' in r]
    accepted = list(closed[-1]['accepted_set']) if closed else []
    llm_calls = sum(1 for r in records if 'llm' in r or 'llm_error' in r)
    fixed = list(cfg.get('extra', []))  # extra tables of the frozen base (hand-written), always in the model
    base_cols = day_features(cfg['days']) + [c for n in fixed for c in extra_columns(n)]

    def close_round(rnd):
        ok = [a for a in attempts if a['round'] == rnd and 'd2' in a and min(a['ci'][0], a['ci2'][0]) > 0
              and min(a['d'], a['d2']) > args.min_gain]
        best = max(ok, key=lambda a: a['d'] + a['d2'], default=None)
        if best:
            accepted.append(best['name'])
        write({'round': rnd, 'accepted': best and best['name'], 'accepted_set': list(accepted)})
        acc = [a for a in attempts if a['name'] in accepted]
        (run / 'summary.json').write_text(json.dumps({
            'run': rid, 'config': cfg, 'proxy': proxy, 'rounds': rnd, 'llm_calls': llm_calls,
            'llm_cost_usd': round(sum((r['llm'].get('cost_usd') or 0) for r in records if 'llm' in r), 4),
            'extra': fixed + accepted,  # the agent arm's full extra list (base tables first)
            'accepted': [{k: a.get(k) for k in ('name', 'round', 'idea', 'columns', 'd', 'ci', 'd2', 'ci2', 'sql')}
                         for a in acc],
            'test_command': f".venv/bin/python -m task1.extra {' '.join(accepted)} --splits test"
                            if accepted else None}, indent=1, ensure_ascii=False) + '\n')

    last = max((r['round'] for r in records if 'round' in r), default=0)
    if last and last not in {r['round'] for r in closed}:
        close_round(last)

    def evaluate(rnd, i, p, base):
        slug = re.sub(r'[^a-z0-9_]', '', str(p.get('name', 'x')).lower())[:40]
        rec = {'round': rnd, 'name': f'{tag}_r{rnd}p{i}_{slug}', 'idea': p.get('idea', ''), 'sql': p.get('sql', '')}
        try:
            t0 = time.time()
            rec['columns'] = compute(rec['name'], rec['sql'], ('train', 'val'), args.threads, days_dir=cfg['days'])
            rec['compute_s'] = round(time.time() - t0, 1)
            taken = set(base_cols) | {c for a in attempts if a['name'] in accepted for c in a['columns']}
            if taken & set(rec['columns']):
                raise FeatureError(f'column names already used: {sorted(taken & set(rec["columns"]))}')
            t0 = time.time()
            r = exp.run(rec['name'], **search | {'extra': fixed + accepted + [rec['name']]})
            rec['fit_s'] = round(time.time() - t0, 1)
            if r['features'] != base['features'] + len(rec['columns']):
                raise JoinError(f"task1.exp trained on {r['features']} features, expected "
                                f"{base['features']} + {len(rec['columns'])}: extra columns did not reach the model")
            c = exp.compare(base['name'], rec['name'], on='A')
            rec.update(d=c['d'], ci=c['ci'], ndcg_A=r['ndcg_A'])
            if c['ci'][0] > 0 and c['d'] > args.min_gain:
                seed2 = {'seed': search['seed'] + 1, 'neg_seed': search['neg_seed'] + 1}
                b2 = f'{tag}_r{rnd}_base2'
                if not (exp.OUT / f'{b2}.parquet').exists():
                    exp.run(b2, **search | seed2 | {'extra': fixed + accepted})
                exp.run(rec['name'] + '_s2', **search | seed2 | {'extra': fixed + accepted + [rec['name']]})
                c2 = exp.compare(b2, rec['name'] + '_s2', on='A')
                rec.update(d2=c2['d'], ci2=c2['ci'])
        except JoinError:
            raise
        except Exception as e:
            rec['error'] = f'{type(e).__name__}: {str(e)[:500]}'
        return rec

    for rnd in range(last + 1, last + 1 + args.rounds):
        if llm_calls >= args.max_llm_calls:
            print(f'LLM call budget {args.max_llm_calls} spent', flush=True)
            break
        cols = [c for c in base_cols if not c.startswith(tuple(search['drop']))] + \
            [c for a in attempts if a['name'] in accepted for c in a['columns']]
        prompt = render(cols, attempts, accepted, args.per_round, args.min_gain)
        phash = hashlib.sha256(prompt.encode()).hexdigest()[:12]
        (run / f'prompt-r{rnd}.txt').write_text(prompt)
        llm_calls += 1
        try:
            proposals, meta = ask_llm(prompt, args.model)
        except Exception as e:
            write({'round': rnd, 'prompt_hash': phash, 'llm_error': str(e)[:500]})
            close_round(rnd)
            continue
        write({'round': rnd, 'prompt_hash': phash, 'llm': meta, 'proposals': len(proposals)})
        t0 = time.time()
        base = exp.run(f'{tag}_r{rnd}_base', **search | {'extra': fixed + accepted})
        if base['features'] != len(cols):
            write({'round': rnd, 'fatal': f"task1.exp base trained on {base['features']} features, expected {len(cols)}"})
            raise JoinError(records[-1]['fatal'])
        write({'round': rnd, 'base': base['name'], 'ndcg_A': base['ndcg_A'], 'features': base['features'],
               'fit_s': round(time.time() - t0, 1)})
        for i, p in enumerate(proposals[:args.per_round], 1):
            try:
                rec = evaluate(rnd, i, p if isinstance(p, dict) else {}, base)
            except JoinError as e:
                write({'round': rnd, 'fatal': str(e)})
                raise
            write(rec)
            attempts.append(rec)
            print(json.dumps({k: rec.get(k) for k in ('name', 'd', 'ci', 'd2', 'compute_s', 'fit_s', 'error')}), flush=True)
        close_round(rnd)
        print(json.dumps({'round': rnd, 'accepted_set': accepted}), flush=True)


if __name__ == '__main__':
    main()
