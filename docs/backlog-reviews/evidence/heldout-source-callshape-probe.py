"""ONE source-free callshape probe, existing RAW fixture, one R2 day.

No TestCase instance, unittest suite, persistent DB, Y, model, fit or EXPLAIN.
Output contains aggregate counts and SQL text without bound identifier values.
"""
from collections import Counter
import hashlib
import inspect
import json
from pathlib import Path
import re
import resource
import sys
import time

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import duckdb
from tests.test_heldout_source_audit import RAW, definitions
from scripts import heldout_source as producer
from tests.oracles import heldout_source_audit as oracle

PINNED = ["scripts/heldout_source.py", "tests/oracles/heldout_source_audit.py",
          "tests/test_heldout_source_audit.py", "tests/test_heldout_source.py",
          "scripts/manual_features.py", "scripts/anchor_pilot.py", "scripts/candidate_pilot.py"]
def hashes():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in PINNED}

before = hashes()
if not 0 < len(RAW) <= 32:
    raise RuntimeError("Existing fixture exceeded raw-row bound")
start_wall = time.monotonic()
start_cpu = time.process_time()
def check():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes = peak if sys.platform == "darwin" else peak * 1024
    if time.monotonic() - start_wall > 300 or time.process_time() - start_cpu > 300 or peak_bytes > 512 * 2**20:
        raise RuntimeError("Tiny probe budget exceeded")

class RecordingConnection:
    def __init__(self, connection):
        self.connection = connection
        self.calls = []
        self.active = None

    def execute(self, sql, parameters=None):
        check()
        frame = inspect.currentframe().f_back
        stack = []
        while frame:
            if frame.f_code.co_filename.endswith("heldout_source_audit.py"):
                stack.append(frame.f_code.co_name)
            frame = frame.f_back
        normal = " ".join(sql.split())
        if normal.upper().startswith("CREATE OR REPLACE TEMP VIEW _HSA_RAW"):
            kind = "raw_view_definition"
        elif re.search(r"\b_hsa_raw\b", normal, re.I):
            kind = "direct_raw_view_evaluation"
        elif normal.upper().startswith("DESCRIBE") or "current_setting(" in normal:
            kind = "metadata_only"
        else:
            kind = "derived_only_sql"
        record = dict(index=len(self.calls) + 1, kind=kind, oracle_stack=stack,
                      sql=normal, parameter_count=len(parameters or []),
                      streamed_rows=0, fetchmany_calls=0)
        self.calls.append(record)
        self.active = record
        self.connection.execute(sql, [] if parameters is None else parameters)
        check()
        return self

    def fetchone(self):
        return self.connection.fetchone()

    def fetchall(self):
        return self.connection.fetchall()

    def fetchmany(self, amount):
        rows = self.connection.fetchmany(amount)
        self.active["streamed_rows"] += len(rows)
        self.active["fetchmany_calls"] += 1
        return rows

con = duckdb.connect(":memory:")
try:
    con.execute("SET threads=2")
    con.execute("SET memory_limit='128MB'")
    con.execute("SET max_temp_directory_size='0B'")
    con.execute("CREATE TABLE heldout_raw_events(event_time TIMESTAMP,event_type VARCHAR,product_id BIGINT,user_id BIGINT,category_id BIGINT)")
    con.executemany("INSERT INTO heldout_raw_events VALUES (?,?,?,?,?)", RAW)
    pool, lock, auth = definitions("R2")
    built = producer.build_day(con, "2019-10-25T00:00:00Z", pool, lock, authenticated_choice=auth, check=check)
    relations = {"queries": "actual_queries", "candidates": "actual_candidates",
                 "base_features": "actual_base_features", "extra_features": "actual_extra_features"}
    sources = {"queries": "pilot_queries", "candidates": "pilot_candidates",
               "base_features": "heldout_base_features", "extra_features": "heldout_extra_features"}
    for key, table in relations.items():
        con.execute("CREATE TEMP TABLE " + table + " AS SELECT * FROM " + sources[key])
    ref = lambda name: dict(path="synthetic/" + name, sha256="a" * 64)
    record = dict(anchor="2019-10-25T00:00:00Z", queries=ref("q"), candidates=ref("c"),
                  base_features=ref("b"), extra_features=ref("extra"), query_count=built["query_count"],
                  candidate_count=built["candidate_count"], mature_query_count=built["mature_query_count"])
    recorded = RecordingConnection(con)
    result = oracle.audit_day(recorded, record, lock, authenticated_choice=auth, relations=relations, check=check)
    kind_counts = Counter(call["kind"] for call in recorded.calls)
    sample_calls = [call for call in recorded.calls if "_sample_values" in call["oracle_stack"]]
    streamed_calls = [call for call in recorded.calls if "_rows" in call["oracle_stack"]]
    summary = dict(raw_fixture_rows=len(RAW), audited_days=1, choice="R2",
                   query_count=result["query_count"], candidate_count=result["candidate_count"],
                   selected_pairs=result["base_core18_sample_pairs"], selected_comparisons=result["base_core18_comparisons"],
                   chosen_scalar_values=result["chosen_scalar_values"], sql_call_count=len(recorded.calls),
                   call_kinds=dict(kind_counts), sampled_formula_source_calls=len(sample_calls),
                   streamed_source_calls=len(streamed_calls), streamed_rows=sum(c["streamed_rows"] for c in streamed_calls),
                   stream_row_counts=[c["streamed_rows"] for c in streamed_calls],
                   strata=result["strata"], baseline_formula_values_complete=result["baseline_formula_values_complete"],
                   physical_scan_counts="not_measured_no_EXPLAIN_or_profile", fit_attempts=0, native_predictions=0,
                   real_source_reads=0, target_relations_created=False, test_cases_run=0)
finally:
    con.close()
check()
after = hashes()
if after != before:
    raise RuntimeError("Accepted source hashes changed")
output = dict(status="single_tiny_callshape_probe_completed", summary=summary,
              observed_source_sha256_before=before, observed_source_sha256_after=after,
              sql_calls=recorded.calls,
              tiny_resource=dict(wall_seconds=time.monotonic()-start_wall, cpu_seconds=time.process_time()-start_cpu,
                                 peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss if sys.platform == "darwin" else resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                                 threads=2, engine_memory="128MB", spill_cap="0B"))
print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))
