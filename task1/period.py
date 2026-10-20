"""Which REES46 period task 1 runs on, chosen by the environment variable TASK1_PERIOD.

2019 (default) is the study: October and November 2019. 2020 is the replication on January and February
2020 (task1/runs/replication-2020/spec.md). Everything that differs between the periods lives here: raw
files, the database, the artifact directory, the DuckDB temp directory, the anchor splits and the time limit of a
sandbox query. With the default every module reads exactly the paths and days it read before the switch existed.

Decisions are taken on 2019 only (the DFS column selection, the agent, final.json); the steps that make them
call only_2019 and stop for another period.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERIOD = os.environ.get('TASK1_PERIOD', '2019')

if PERIOD == '2019':
    RAW = ROOT / 'data/raw'
    MONTHS = ['2019-Oct', '2019-Nov']
    DB = ROOT / 'data/processed/rees46.duckdb'
    ART = ROOT / 'artifacts/task1/v2'  # day tables, event files, extra tables, runs
    TMP = ROOT / 'data/tmp/duckdb'
    SPLITS = {
        'train': ('2019-10-15', '2019-11-07'),
        'val': ('2019-11-08', '2019-11-13'),
        'refit': ('2019-10-15', '2019-11-13'),
        'test': ('2019-11-18', '2019-11-28'),
    }
    SANDBOX_TIMEOUT_S = 120  # what the feature agent was held to
elif PERIOD == '2020':
    RAW = ROOT / 'data/raw2020'
    MONTHS = ['2020-Jan', '2020-Feb']
    DB = ROOT / 'data/processed/rees46-2020.duckdb'
    ART = ROOT / 'artifacts/task1/v2020'
    TMP = ROOT / 'data/tmp/duckdb-2020'
    SPLITS = {  # labels of 02-13 end at 02-14 00:00; the data end at 03-01 00:00, so 02-29 is the last anchor
        'train': ('2020-01-15', '2020-02-07'),
        'val': ('2020-02-08', '2020-02-13'),
        'refit': ('2020-01-15', '2020-02-13'),
        'test': ('2020-02-14', '2020-02-29'),
    }
    SANDBOX_TIMEOUT_S = 600  # a limit of the machine, not of the feature: up to 59 days of history per anchor
else:
    raise SystemExit(f"TASK1_PERIOD={PERIOD!r}: expected '2019' or '2020'")


def only_2019(step):
    """Stop a step whose decision belongs to the study period."""
    if PERIOD != '2019':
        raise SystemExit(f'{step} runs on the 2019 study period only (TASK1_PERIOD={PERIOD})')
