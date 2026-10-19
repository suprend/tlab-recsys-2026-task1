"""LLM agent that proposes SQL features; greedy forward selection on validation.

Each round the LLM sees the data schema, the current feature set and every earlier attempt
with its measured effect or error, and proposes new SQL features. The sandbox computes each
proposal without access to the future; a model with current set + proposal is trained on
Oct 8-20 and compared with the current model on validation Oct 22-25 (paired bootstrap over
queries). The best proposal of the round is accepted if the lower 95% bound of its NDCG gain
is above zero. Test days are never used here.
"""
import argparse
import json
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

from task1.extra import FeatureError, compute
from task1.model import base_features, bootstrap_diff, fit, load, per_query, predict

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / 'task1/runs'

PROMPT = """You are a feature engineer for a purchase-ranking model. Reply with JSON only.

Task. Every day at t = 00:00 UTC we rank candidate products for a user by the chance that the
user buys them in the next 24 hours. Candidates are about 200 products with the most distinct
buyers in the last 7 days plus the user's 20 most recently touched products. A CatBoost model
scores each (user, product) pair; the metric is NDCG@20 per user.

Data. REES46 e-commerce store, October 2019, 42M events. You can read two DuckDB tables:
  hist(event_time TIMESTAMP, event_type VARCHAR -- 'view'|'cart'|'purchase',
       product_id BIGINT, category_id BIGINT, category_code VARCHAR -- e.g. 'electronics.smartphone', often NULL,
       brand VARCHAR -- often NULL, price DECIMAL(12,2), user_id BIGINT, user_session VARCHAR)
       -- all events strictly before t, starting 2019-10-01; about 40 views per purchase
  active_users(user_id) -- users with any event in the last 48 hours; filter by it for speed
Write the anchor as TIMESTAMP '{{t}}' (literally, with the braces), e.g.
  event_time >= TIMESTAMP '{{t}}' - INTERVAL 3 DAY

Features already in the model:
{features}

Rules for a feature query:
- one DuckDB SELECT statement, reading only hist and active_users;
- returns key columns user_id and/or product_id and 1-3 value columns named f_x_<something>;
- exactly one row per key; keys without a row get NULL;
- user-level and pair-level queries must filter user_id IN (SELECT user_id FROM active_users);
- it runs once per day for 24 days, so keep it under about 10 seconds.

Earlier attempts in this run (accepted ones are already in the model):
{history}

Propose {n} new features that are likely to improve ranking beyond the current set and differ
from earlier attempts. Think about what signals the current set misses. Answer with a JSON
list only: [{{"name": "short_snake_case", "idea": "one sentence", "sql": "SELECT ..."}}]
"""


def ask_llm(prompt, model):
    t0 = time.time()
    r = subprocess.run(['claude', '-p', prompt, '--model', model, '--output-format', 'json'],
                       capture_output=True, text=True, cwd='/tmp', timeout=900)
    out = json.loads(r.stdout)
    text = out['result']
    m = re.search(r'\[.*\]', text, re.S)
    return json.loads(m.group(0)), {'seconds': round(time.time() - t0, 1), 'cost_usd': out.get('total_cost_usd')}


def describe(history):
    if not history:
        return '(none yet)'
    lines = []
    for h in history:
        if 'error' in h:
            lines.append(f"- {h['name']}: FAILED: {h['error'][:300]}\n  sql: {h['sql']}")
        else:
            lines.append(f"- {h['name']} ({h['idea']}): dNDCG={h['d_ndcg']:+.5f} "
                         f"[{h['ci'][0]:+.5f}, {h['ci'][1]:+.5f}] {'ACCEPTED' if h.get('accepted') else 'rejected'}"
                         f"\n  sql: {h['sql']}")
    return '\n'.join(lines)


def evaluate(extras, neg=50):
    train, val = load('train', extras, neg), load('val', extras)
    f = base_features(train)
    model = fit(train, f)
    return per_query(val, predict(model, val, f)), f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=6)
    ap.add_argument('--per-round', type=int, default=5)
    ap.add_argument('--model', default='sonnet')
    ap.add_argument('--run', help='resume this run directory name')
    args = ap.parse_args()
    run = RUNS / (args.run or datetime.now().strftime('agent-%Y%m%d-%H%M'))
    run.mkdir(parents=True, exist_ok=True)
    log = run / 'log.jsonl'
    history = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
    attempts = [h for h in history if 'name' in h]
    accepted = [h['name'] for h in attempts if h.get('accepted')]
    current, features = evaluate(accepted)
    start_round = max((h.get('round', 0) for h in history), default=0) + 1

    def write(rec):
        with log.open('a') as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + '\n')

    for rnd in range(start_round, start_round + args.rounds):
        prompt = PROMPT.format(features='\n'.join('- ' + f for f in features),
                               history=describe(attempts), n=args.per_round)
        try:
            proposals, meta = ask_llm(prompt, args.model)
        except Exception as e:
            write({'round': rnd, 'llm_error': str(e)[:500]})
            continue
        write({'round': rnd, 'llm': meta, 'proposals': len(proposals)})
        best = None
        for p in proposals[:args.per_round]:
            name = f"r{rnd}_{re.sub(r'[^a-z0-9_]', '', p['name'].lower())[:40]}"
            rec = {'round': rnd, 'name': name, 'idea': p.get('idea', ''), 'sql': p['sql']}
            t0 = time.time()
            try:
                rec['columns'] = compute(name, p['sql'])
                rec['compute_s'] = round(time.time() - t0, 1)
                m, _ = evaluate(accepted + [name])
                d, lo, hi = bootstrap_diff(current.ndcg, m.ndcg.reindex(current.index))
                rec.update(d_ndcg=d, ci=[lo, hi], ndcg=float(m.ndcg.mean()), recall=float(m.recall.mean()),
                           total_s=round(time.time() - t0, 1))
                if lo > 0 and (best is None or d > best[0]['d_ndcg']):
                    best = (rec, m)
            except (FeatureError, KeyError, ValueError, TypeError) as e:
                rec['error'] = str(e)[:500]
            attempts.append(rec)
            print(json.dumps({k: rec.get(k) for k in ('name', 'd_ndcg', 'ci', 'error')}), flush=True)
        if best:
            best[0]['accepted'] = True
            accepted.append(best[0]['name'])
            current = best[1]
        for rec in attempts[-len(proposals[:args.per_round]):]:
            write(rec)
        features = base_features(load('val', accepted).head(1))
        write({'round': rnd, 'accepted_set': accepted, 'val_ndcg': float(current.ndcg.mean())})


if __name__ == '__main__':
    main()
