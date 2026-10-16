"""Synthetic typed9 parser -> daily queries -> candidate reachability canary.

The production profile supplies only the literal typed9 parsing contract.
Calendar coverage is declared, and maturity is artificially asserted solely
to enter the candidate validator. No archive, Y, features, fit, production
October incidence, complete CLI, or quality claim is tested here.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import unittest

import duckdb
from scripts.anchor_pilot import create_queries
from scripts.candidate_pilot import ROOT, create_candidates
from scripts.protocol_manifest import load_protocol
from scripts.source_import import PRODUCTION_PROFILE, parse_row

SCHEMA = [
    ("event_time", "TIMESTAMP"), ("event_type", "VARCHAR"), ("product_id", "BIGINT"),
    ("category_id", "BIGINT"), ("category_code", "VARCHAR"), ("brand", "VARCHAR"),
    ("price", "DECIMAL(12,2)"), ("user_id", "BIGINT"), ("user_session", "VARCHAR"),
]
T = datetime(2019, 10, 8, tzinfo=timezone.utc)
H1 = datetime(2019, 10, 7, 23)
H2 = datetime(2019, 10, 7, 22)
P = ["2019-10-07 23:00:00 UTC", "view", "101", "1001", "electronics.phone",
     "fixture_brand", "12.34", "7", "fixture-session"]
N = P.copy()
N[2] = ""
BUY = ["2019-10-07 22:00:00 UTC", "purchase", "202", "2002", "appliances.kitchen",
       "fixture_buyer_brand", "56.78", "8", "fixture-buyer-session"]
M = P.copy()
for position in (3, 4, 5, 6, 8):
    M[position] = ""


class CandidateReachabilityTests(unittest.TestCase):
    def test_typed9_query_candidate_boundary(self):
        self.assertEqual(PRODUCTION_PROFILE["fields"], [name for name, _ in SCHEMA])
        self.assertEqual(PRODUCTION_PROFILE["types"], [kind for _, kind in SCHEMA])
        config = deepcopy(load_protocol(ROOT / "configs/protocols/clock-48h.json"))
        config["pilot"] = {"start": "2019-10-08T00:00:00Z", "end": "2019-10-09T00:00:00Z"}
        self.assertEqual(config["query"]["eligibility_hours"], 48)
        self.assertGreater(config["query"]["max_users_per_day"], 2)
        # Q tuple: user, eligibility rows, history rows, distinct history products,
        # active days, last history time, declared calendar coverage, unset maturity.
        q_null = [(7, 1, 1, 0, 1, H1, 1.0, None)]
        q_product = [(7, 1, 1, 1, 1, H1, 1.0, None)]
        q_np = [(7, 1, 1, 0, 1, H1, 1.0, None), (8, 1, 1, 1, 1, H2, 1.0, None)]
        # C tuple: user, product, popular flag, recent flag, distinct buyers,
        # popular rank, recent rank, last personal event time. These are literal oracles.
        c_product = [(7, 101, False, True, 0, None, 1, H1)]
        c_np = [(7, 202, True, False, 1, 1, None, None), (8, 202, True, True, 1, 1, 1, H2)]
        histories = [("N", [N], q_null, []), ("P", [P], q_product, c_product),
                     ("NP", [N, BUY], q_np, c_np),
                     ("M_before", [P.copy()], q_product, c_product),
                     ("M_after", [M], q_product, c_product)]
        self.assertEqual(sum(len(rows) for _, rows, _, _ in histories), 6)
        observed = {}
        for name, tokens, expected_q, expected_c in histories:
            with self.subTest(history=name):
                con = duckdb.connect(":memory:", config={"threads": "1", "enable_external_access": "false"})
                try:
                    con.execute("SET memory_limit='64MB'")
                    con.execute("SET max_temp_directory_size='0B'")
                    con.execute("CREATE TABLE events (" + ",".join(n + " " + t for n, t in SCHEMA) + ")")
                    parsed = [parse_row(row, PRODUCTION_PROFILE) for row in tokens]
                    con.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)", parsed)
                    self.assertEqual([tuple(r[:2]) for r in con.execute("DESCRIBE events").fetchall()], SCHEMA)
                    self.assertEqual(con.execute("SELECT count(*) FROM events").fetchone()[0], len(tokens))
                    if name in {"N", "NP"}:
                        self.assertIsNone(parsed[0][2])
                        self.assertEqual(con.execute("SELECT product_id FROM events WHERE user_id=7").fetchone(), (None,))
                    if name in {"P", "M_before"}:
                        self.assertEqual(parsed[0], (H1, "view", 101, 1001, "electronics.phone",
                                                     "fixture_brand", Decimal("12.34"), 7, "fixture-session"))
                    if name == "M_after":
                        self.assertEqual(parsed[0], (H1, "view", 101, None, None, None, None, 7, None))
                        self.assertEqual(con.execute("SELECT category_id,category_code,brand,price,user_session FROM events").fetchone(),
                                         (None, None, None, None, None))
                    query_result = create_queries(con, config)
                    expected_population = [{"anchor": T, "eligible_users": len(expected_q),
                                            "sampled_queries": len(expected_q), "active_eligibility_keys": len(expected_q)}]
                    self.assertEqual(query_result["population"], expected_population)
                    q = con.execute("""SELECT user_id,eligibility_events,history_events_7d,
                        history_distinct_items_7d,history_active_days_7d,last_history_time,
                        history_coverage_7d,label_is_mature FROM pilot_queries ORDER BY user_id""").fetchall()
                    self.assertEqual(q, expected_q)
                    self.assertEqual(con.execute("SELECT DISTINCT anchor FROM pilot_queries").fetchall(), [(T.replace(tzinfo=None),)])
                    # Artificial calendar/maturity premise, only to satisfy validate_queries;
                    # no labels or target outcomes are created or inferred.
                    con.execute("UPDATE pilot_queries SET label_is_mature=TRUE")
                    self.assertEqual(con.execute("SELECT DISTINCT label_is_mature FROM pilot_queries").fetchall(), [(True,)])
                    candidate_result = create_candidates(con, config)
                    c = con.execute("""SELECT q.user_id,c.product_id,c.from_popular,c.from_recent,
                        c.popularity_distinct_users,c.popular_source_rank,c.recent_source_rank,
                        c.last_user_event_time FROM pilot_candidates c LEFT JOIN pilot_queries q
                        USING(query_id) ORDER BY q.user_id,c.product_id""").fetchall()
                    self.assertEqual(c, expected_c)
                    self.assertEqual(candidate_result["candidate_rows"], len(expected_c))
                    self.assertNotIn("pilot_labels", {r[0] for r in con.execute("SHOW TABLES").fetchall()})
                    observed[name] = (q, c)
                finally:
                    con.close()
        self.assertEqual(observed["P"], observed["M_before"])
        self.assertEqual(observed["M_before"], observed["M_after"])


if __name__ == "__main__":
    unittest.main()
