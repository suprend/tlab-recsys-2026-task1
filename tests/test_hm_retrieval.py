"""Independent tiny pure oracle for source quotas, overlap and time boundaries."""
from collections import Counter, defaultdict
from contextlib import redirect_stderr
import ast
from datetime import date,timedelta
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest

SPEC=importlib.util.spec_from_file_location("hm_retrieval_tested",Path(__file__).resolve().parents[1]/"scripts"/"hm_retrieval.py")
hm=importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name]=hm
SPEC.loader.exec_module(hm)


def pure_oracle(events,metadata,anchor,limit,seed=2026):
    history=[e for e in events if anchor-timedelta(days=90)<=e[0]<anchor]
    users=sorted({e[1] for e in history},key=lambda u:(hashlib.sha256(f"{u}:{seed}".encode()).hexdigest(),u))[:limit]
    catalog={e[2] for e in history}
    buyers=defaultdict(set)
    for day,u,a in history:
        if day>=anchor-timedelta(days=7):
            buyers[a].add(u)
    global_items=sorted(catalog,key=lambda a:(-len(buyers[a]),a))
    old_global=[a for a in global_items if buyers[a]][:100]
    expected={}
    for u in users:
        past=[e for e in history if e[1]==u]
        seen={e[2] for e in past}
        last={a:max(e[0] for e in past if e[2]==a) for a in seen}
        recent=sorted(seen,key=lambda a:(-last[a].toordinal(),a))[:20]
        sibling_seeds={}
        for rank,a in enumerate(recent,1):
            product=metadata[a][0]
            if product is None or not product.strip():
                continue
            for candidate in catalog:
                if metadata[candidate][0]==product and candidate not in seen:
                    sibling_seeds[candidate]=min(rank,sibling_seeds.get(candidate,rank))
        siblings=sorted(sibling_seeds,key=lambda a:(sibling_seeds[a],-len(buyers[a]),a))[:20]
        type_counts=Counter()
        for _,_,a in past:
            typ,name=metadata[a][1:]
            if typ is not None and typ.strip() not in ("","-1") and (name is None or name.strip().lower()!="unknown"):
                type_counts[typ]+=1
        preferred=sorted(type_counts,key=lambda typ:(-type_counts[typ],typ))[:2]
        typed=[]
        for typ in preferred:
            candidates=[a for a in catalog if metadata[a][1]==typ and a not in seen and a not in siblings]
            typed.extend(sorted(candidates,key=lambda a:(-len(buyers[a]),a))[:20])
        for policy in hm.POLICIES:
            source=[(a,"recent") for a in recent]
            if policy=="C1-Q120":
                source += [(a,"sibling") for a in siblings]+[(a,"type") for a in typed]
            used={a for a,_ in source}
            refill=old_global if policy=="C0" else global_items
            for a in refill:
                if a not in used and (policy=="C0" or len(source)<120):
                    source.append((a,"global"));used.add(a)
            expected[policy,u]=source
    return expected


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        import duckdb
        self.con=duckdb.connect(":memory:")
        self.con.execute("CREATE TABLE transactions(t_dat DATE,customer_id VARCHAR,article_id VARCHAR,price DOUBLE,sales_channel_id VARCHAR)")
        self.con.execute("CREATE TABLE articles(article_id VARCHAR,product_code VARCHAR,product_type_no VARCHAR,product_type_name VARCHAR)")
        self.anchor=date(2020,9,2)
        self.metadata={}
        self.events=[]
        # Background establishes a full catalog and common7d popularity ties.
        for i in range(260):
            article=f"{i:010d}"
            product="P" if i<100 else f"P{i}"
            typ="01" if i<180 else "02"
            self.metadata[article]=(product,typ,"Valid")
            self.events.append((self.anchor-timedelta(days=1),"background",article))
        # u bought60 same-product siblings90d ago (beyond recent20) and has
        # second preferred type02. This defeats naive fixed40 pruning.
        self.events += [(self.anchor-timedelta(days=20),"u",f"{i:010d}") for i in range(60)]
        self.events += [(self.anchor-timedelta(days=1),"u","0000000000"),
                        (self.anchor-timedelta(days=2),"u","0000000180")]
        # Labels: a repeat, a sibling, an offcatalog item, and future exclusion.
        self.metadata["9999999999"]=("future","01","Valid")
        self.events += [(self.anchor,"u","0000000000"),(self.anchor,"u","0000000060"),
                        (self.anchor+timedelta(days=1),"u","9999999999"),
                        (self.anchor+timedelta(days=7),"u","0000000061"),
                        (self.anchor,"futureonly","0000000000")]

    def tearDown(self):
        self.con.close()

    def load(self):
        self.con.executemany("INSERT INTO articles VALUES (?,?,?,?)",[(a,*m) for a,m in self.metadata.items()])
        self.con.executemany("INSERT INTO transactions VALUES (?,?,?,?,?)",[(d,u,a,.1,"2") for d,u,a in self.events])

    def rows(self):
        result=hm.create_candidates(self.con,self.anchor,20)
        columns=[x[0] for x in result.description]
        return [dict(zip(columns,row)) for row in result.fetchall()]

    def test_sql_matches_independent_pure_oracle(self):
        self.load()
        rows=self.rows()
        actual=defaultdict(list)
        for r in rows:
            actual[r["policy"],r["customer_id"]].append((r["article_id"],r["source"]))
        expected=pure_oracle(self.events,self.metadata,self.anchor,20)
        self.assertEqual(dict(actual),expected)
        for key,items in actual.items():
            self.assertEqual(len(items),len(set(a for a,_ in items)))
            if key[0]!="C0":
                self.assertEqual(len(items),120)

    def test_novel_sources_exclude_older_purchases_and_dedup_before_quota(self):
        self.load()
        rows=[r for r in self.rows() if r["customer_id"]=="u" and r["policy"]=="C1-Q120"]
        siblings=[r for r in rows if r["source"]=="sibling"]
        self.assertEqual(len(siblings),20)
        self.assertEqual(siblings[0]["article_id"],"0000000060")
        self.assertTrue(all(int(r["article_id"])>=60 for r in siblings))
        type_rows=[r for r in rows if r["source"]=="type"]
        self.assertEqual(Counter(r["preferred_type_rank"] for r in type_rows),{1:20,2:20})
        self.assertEqual([r["type_rank"] for r in type_rows if r["preferred_type_rank"]==1],list(range(1,21)))

    def test_full_y_repeat_new_coverage_and_horizon(self):
        self.load();self.rows()
        report=hm.collect_diagnostics(self.con,self.anchor.isoformat())
        targets=self.con.execute("SELECT article_id,repeat90 FROM hm_r_targets WHERE customer_id='u' ORDER BY article_id").fetchall()
        self.assertEqual(targets,[("0000000000",True),("0000000060",False),("9999999999",False)])
        self.assertEqual(report["selected_users"],2)
        self.assertEqual(report["primary_paired_bootstrap"]["draws"],2000)
        self.assertEqual(report["primary_paired_bootstrap"]["queries"],1)
        c1=next(m for m in report["metrics"] if m["policy"]=="C1-Q120")
        self.assertEqual(c1["target_pairs"],3)
        self.assertAlmostEqual(c1["oracle_ap12_conditional"],2/3)
        self.assertEqual(c1["repeat90_target_pairs"],1)
        self.assertEqual(c1["new_to_observed90d_target_pairs"],2)

    def test_global_refill_allows_zero7_history_and_no_future_injection(self):
        self.events=[(self.anchor-timedelta(days=20),u,a) if u=="background" else (d,u,a)
                     for d,u,a in self.events]
        self.load()
        rows=self.rows()
        for policy in ("C0-Q120","C1-Q120"):
            ids={r["article_id"] for r in rows if r["policy"]==policy and r["customer_id"]=="u"}
            self.assertEqual(len(ids),120)
            self.assertNotIn("9999999999",ids)

    def test_type_no_borrow_and_invalid_metadata(self):
        # Type02 contains just one novel article. Its spare quota must go to
        # global, not type01. Unknown-name type must not become preferred.
        for a,m in list(self.metadata.items()):
            if m[1]=="02" and int(a)>181:
                self.metadata[a]=(m[0],"-1","Unknown")
        self.metadata["0000000001"]=("", "03"," uNkNoWn ")
        self.events += [(self.anchor-timedelta(days=1),"u","0000000001")]*100
        self.load();rows=self.rows()
        typed=[r for r in rows if r["policy"]=="C1-Q120" and r["customer_id"]=="u" and r["source"]=="type"]
        self.assertEqual(Counter(r["preferred_type_rank"] for r in typed),{1:20,2:1})
        self.assertEqual(dict(self.con.execute("SELECT product_type_no,preference_rank FROM hm_r_preferred WHERE customer_id='u'").fetchall()),{"01":1,"02":2})

    def test_reject_after_boundary_and_small_catalog(self):
        with self.assertRaisesRegex(ValueError,"after"):
            hm.create_candidates(self.con,"2020-09-17",20)
        with self.assertRaisesRegex(ValueError,"fewer than120"):
            hm.create_candidates(self.con,"2020-09-02",20)

    def test_history_boundaries_and_deterministic_small_cohort(self):
        self.events += [(self.anchor-timedelta(days=90),"boundary","0000000000"),
                        (self.anchor-timedelta(days=91),"expired","0000000000")]
        self.load()
        rows=self.rows()
        self.assertEqual({r["customer_id"] for r in rows},{"u","background","boundary"})
        result=hm.create_candidates(self.con,self.anchor,1).fetchall()
        selected={r[1] for r in result}
        expected={u for _,u in pure_oracle(self.events,self.metadata,self.anchor,1)}
        self.assertEqual(selected,expected)
        first=sorted(result)
        # Event insertion order must not alter source/candidate ranks.
        self.con.execute("DELETE FROM transactions")
        self.con.executemany("INSERT INTO transactions VALUES (?,?,?,?,?)",[(d,u,a,.1,"2") for d,u,a in reversed(self.events)])
        self.assertEqual(sorted(hm.create_candidates(self.con,self.anchor,1).fetchall()),first)

    def test_source_ties_preserve_lexical_type_codes_and_leading_zero_ids(self):
        self.events=[e for e in self.events if e[1]!="u"]
        self.events += [(self.anchor-timedelta(days=1),"u","0000000000"),
                        (self.anchor-timedelta(days=1),"u","0000000180")]
        self.load();rows=self.rows()
        self.assertEqual(self.con.execute("SELECT product_type_no FROM hm_r_preferred WHERE customer_id='u' ORDER BY preference_rank").fetchall(),[("01",),("02",)])
        recent=[r for r in rows if r["policy"]=="C1-Q120" and r["customer_id"]=="u" and r["source"]=="recent"]
        self.assertEqual([r["article_id"] for r in recent],["0000000000","0000000180"])

    def test_diagnostics_reject_mismatched_history_anchor(self):
        self.load();self.rows()
        with self.assertRaisesRegex(ValueError,"differs"):
            hm.collect_diagnostics(self.con,"2020-08-26")

    def test_final_provenance_joins_use_hash_keys_instead_of_cartesian_checks(self):
        self.load();self.rows()
        # EXPLAIN the actual source query, not a second handwritten query that
        # could diverge. Global pool's tiny bounded inner theta join is allowed;
        # the two large LEFT provenance joins must stay hash joins on all keys.
        tree=ast.parse(Path(hm.__file__).read_text(encoding="utf-8"))
        statement=next(node.value for node in ast.walk(tree)
            if isinstance(node,ast.Constant) and isinstance(node.value,str)
            and "CREATE TEMP TABLE hm_r_candidates AS" in node.value)
        query=statement.split("CREATE TEMP TABLE hm_r_candidates AS",1)[1]
        plan=json.loads(self.con.execute("EXPLAIN (FORMAT JSON) "+query).fetchone()[1])
        def flatten(nodes):
            for node in nodes:
                yield node
                yield from flatten(node.get("children",[]))
        provenance=[node for node in flatten(plan)
            if node.get("extra_info",{}).get("Join Type")=="LEFT"
            and any("source" in condition for condition in node.get("extra_info",{}).get("Conditions",[]))]
        self.assertEqual(len(provenance),2)
        self.assertTrue(all(node["name"]=="HASH_JOIN" for node in provenance))
        self.assertFalse(any(node["name"]=="BLOCKWISE_NL_JOIN"
            and node.get("extra_info",{}).get("Join Type")=="LEFT" for node in flatten(plan)))

    def test_history_builder_reusable_later_but_cli_and_targets_are_restricted(self):
        self.load()
        self.assertGreater(hm.create_candidates(self.con,"2020-09-09",20).count("*").fetchone()[0],0)
        self.assertGreater(hm.create_candidates(self.con,"2020-09-16",20).count("*").fetchone()[0],0)
        with self.assertRaisesRegex(ValueError,"boundary"):
            hm.collect_diagnostics(self.con,"2020-09-09")
        with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as caught:
            hm.main(["--database","unused","--output","unused","--anchor","2020-09-09"])
        self.assertEqual(caught.exception.code,2)


if __name__=="__main__":
    unittest.main()
