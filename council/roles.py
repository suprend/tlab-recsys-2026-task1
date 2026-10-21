"""Data roles, recipes and paths of the council rehearsal on REES46 January-February 2020
(council/runs/rees46-2020/contract.md). Constants only; nothing here reads data."""
from datetime import date, timedelta
from pathlib import Path

from task1 import period as P

if P.PERIOD != '2020':
    raise SystemExit('the council rehearsal runs with TASK1_PERIOD=2020')

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / 'council/runs/rees46-2020'          # under git: contract, prereg, cards, logs
OUT = P.ART / 'council'                           # artifacts: fits, probes
FITS = OUT / 'fits'
PROBES = OUT / 'probes'
DAYS6 = P.ART / 'days6'
LLM_DIR = Path('/tmp/tlab-council-llm')

SPANS = {
    'T_fit': ('2020-01-15', '2020-02-02'),
    'S0': ('2020-02-03', '2020-02-07'),
    'train': ('2020-01-15', '2020-02-07'),
    'val': ('2020-02-08', '2020-02-13'),
    'refit': ('2020-01-15', '2020-02-13'),
    'test': ('2020-02-14', '2020-02-29'),
}
TEST_EXCLUDED = ('2020-02-27', '2020-02-28')     # replication-2020/spec.json: broken label or history day
EXPLORE, SELECT = 'A', 'B'                        # exp.half within S0
PROBE_DAYS = ('2020-01-20', '2020-02-05', '2020-02-10')

BASE = dict(loss='Logloss', l2=10, neg=50, neg_mode='random', half_life=None, train_frac=1.0, drop=[],
            threads=10, depth=8)
RECIPES = {
    'plan': BASE | dict(iterations=300, lr=0.12, cap=60000),
    'full_val': BASE | dict(iterations=500, lr=0.08, cap=101959),
    'full_test': BASE | dict(iterations=500, lr=0.08, cap=140680),
}
PLACEBO_SEED = 4242

# H+r = H+ of the replication (task1/runs/replication-2020/spec.json, arm Hp): base days6 + 34 tables.
HPLUS = ['dfs_p', 'dfs_c', 'dfs_b', 'dfs_u'] + [
    'agent_night20_r1p1_first_touch_conversion', 'agent_night20_r1p2_coacq_cf', 'agent_night20_r1p3_buyer_price_profile',
    'agent_night20_r1p4_new_reach', 'agent_night20_r1p5_cp_staleness', 'agent_night20_r2p1_cmp_session_win_lift',
    'agent_night20_r2p2_cp_category_complement', 'agent_night20_r2p3_acq_seed_coview_cf',
    'agent_night20_r2p4_revisit_consideration', 'agent_night20_r2p5_view_dwell_time',
    'agent_night20_r3p1_view_session_last_choice', 'agent_night20_r3p2_intraday_momentum_12h',
    'agent_night20_r3p3_user_user_cf_acq', 'agent_night20_r3p4_brand_cat_price_sibling',
    'agent_night20_r3p5_category_search_depth', 'agent_night20_r4p1_acq_regularity_7d',
    'agent_night20_r4p2_cat_acq_concentration', 'agent_night20_r4p3_weekday_seasonality_14d',
    'agent_night20_r4p4_cat_to_item_transition', 'agent_night20_r4p5_brand_switch_transition',
    'agent_night20_r5p1_cf_xday_new_acq_transition', 'agent_night20_r5p2_cf_next_view_adjacency',
    'agent_night20_r5p3_cf_converting_session_coview', 'agent_night20_r5p4_uc_nextday_continuation',
    'agent_night20_r5p5_cf_considered_seed_coview', 'agent_night20_r6p1_older_view_seed_coview',
    'agent_night20_r6p2_dwell_seed_coview', 'agent_night20_r6p3_abandoned_cart_seed_coview',
    'agent_night20_r6p4_user_level_cooccurrence_cf', 'agent_night20_r6p5_fresh_2d_coview_graph']
HPLUS_FEATURES = 274
TEST_SEEDS = [(2026, 0), (7, 1), (11, 2), (13, 3)]
NOISE_SEEDS = [(2026, 0), (7, 1)]
CONFIRM_SEEDS = [(3001, 31), (3002, 32)]


def plan_seed(r):
    """Seed and negative seed of plan fit r = 1..48."""
    return 1000 + r, r


def days(span):
    """Anchor days of a span name of SPANS, as dates."""
    a, b = (date.fromisoformat(x) for x in SPANS[span])
    return [a + timedelta(n) for n in range((b - a).days + 1)]
