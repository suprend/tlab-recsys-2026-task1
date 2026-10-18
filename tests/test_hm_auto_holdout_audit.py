"""Tiny invented source witnesses; never read the real H&M DB or reservation."""
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import hm_auto_holdout_audit as audit


class IndependentCandidateTests(unittest.TestCase):
    def setUp(self):
        import duckdb
        self.con = duckdb.connect(":memory:")
        self.con.execute("SET threads=1")
        self.con.execute("SET memory_limit='512MB'")
        self.con.execute("CREATE TABLE transactions(t_dat DATE,customer_id VARCHAR,article_id VARCHAR)")
        self.con.execute("CREATE TABLE ha_users(customer_id VARCHAR)")
        self.con.executemany("INSERT INTO ha_users VALUES (?)",[("q1",),("q2",)])
        self.cutoff = date(2020,9,16)
        left = self.cutoff-timedelta(days=90)
        self.rows = [(left,"population",f"a{i:03}") for i in range(150)]
        self.rows += [(left,"q1","a149"),(left,"q2","a148")]
        self.rows += [(self.cutoff-timedelta(days=1),"buyer1","a001"),
                      (self.cutoff-timedelta(days=1),"buyer2","a001")]
        self.rows += [(self.cutoff-timedelta(days=1),"buyer3","a000")]*9

    def tearDown(self):
        self.con.close()

    def populate(self):
        self.con.executemany("INSERT INTO transactions VALUES (?,?,?)",self.rows)

    def reference(self):
        history = [row for row in self.rows if self.cutoff-timedelta(days=90)<=row[0]<self.cutoff]
        buyers = {}
        for day,user,article in history:
            buyers.setdefault(article,set())
            if day >= self.cutoff-timedelta(days=7):
                buyers[article].add(user)
        global_order = sorted(buyers,key=lambda a:(-len(buyers[a]),a))
        result = {}
        for user in ("q1","q2"):
            recent = {}
            for day,customer,article in history:
                if customer == user:
                    recent[article] = max(day,recent.get(article,day))
            ordered = sorted(recent,key=lambda a:(-recent[a].toordinal(),a))[:20]
            for article in global_order:
                if article not in ordered:
                    ordered.append(article)
            result[user] = ordered[:120]
        return result

    def actual(self):
        audit.rebuild_c0q120(self.con,"2020-09-16",audit.metric_math.Deadline(10))
        result = {"q1":[],"q2":[]}
        for user,article in self.con.execute("SELECT customer_id,article_id FROM ha_expected_candidates ORDER BY customer_id,candidate_rank").fetchall():
            result[user].append(article)
        return result

    def test_population_distinct_buyers_and_zero7_refill(self):
        self.populate()
        observed = self.actual()
        self.assertEqual(observed,self.reference())
        self.assertEqual(observed["q1"][:3],["a149","a001","a000"])
        self.assertEqual(len(observed["q1"]),120)
        self.assertIn("a100",observed["q1"])

    def test_recent20_tie_order_and_dedup_then_fill(self):
        self.rows += [(self.cutoff-timedelta(days=2),"q1",f"a{i:03}") for i in range(21)]
        self.populate()
        observed = self.actual()
        self.assertEqual(observed,self.reference())
        self.assertEqual(observed["q1"][:20],[f"a{i:03}" for i in range(20)])
        self.assertEqual(len(set(observed["q1"])),120)

    def test_halfopen_history_and_week_boundaries(self):
        self.rows += [(self.cutoff,"future", "must-not-enter"),
                      (self.cutoff-timedelta(days=91),"past","too-old"),
                      (self.cutoff-timedelta(days=7),"left7","a007")]
        self.populate()
        observed = self.actual()
        self.assertEqual(observed,self.reference())
        self.assertNotIn("must-not-enter",observed["q1"])
        self.assertNotIn("too-old",observed["q1"])
        self.assertEqual(observed["q1"][:4],["a149","a001","a000","a007"])

    def test_wrong_cached_candidate_rejected_and_key_digest_stable(self):
        self.populate()
        self.actual()
        self.con.execute("CREATE TABLE ha_candidates AS SELECT customer_id,article_id FROM ha_expected_candidates")
        audit.compare_source_candidates(self.con)
        deadline = audit.metric_math.Deadline(10)
        self.assertEqual(audit.candidate_identity(self.con,"ha_candidates",deadline),
                         audit.candidate_identity(self.con,"ha_expected_candidates",deadline))
        self.con.execute("UPDATE ha_candidates SET article_id='foreign' WHERE customer_id='q1' AND article_id='a001'")
        with self.assertRaisesRegex(ValueError,"source C0"):
            audit.compare_source_candidates(self.con)

    def test_insufficient_catalog_rejected(self):
        self.rows = self.rows[:100]
        self.populate()
        with self.assertRaisesRegex(ValueError,"catalog"):
            self.actual()


class SavedMetricTests(unittest.TestCase):
    def test_native_CBM_float_serialization_witness_and_material_corruption(self):
        reported=dict(bayesian_matrix_reg=.10000000149011612,learning_rate=.05000000074505806,
                      depth=8,use_best_model=False,task_type="GPU",nested=[1,dict(x=.1),None])
        reloaded=dict(reported,bayesian_matrix_reg=.1000000015,learning_rate=.05000000075)
        self.assertTrue(audit.same_model_parameters(reloaded,reported))
        for changed in (dict(reloaded,learning_rate=.051),dict(reloaded,depth=9),
                        dict(reloaded,depth=8.0),dict(reloaded,use_best_model=0),
                        dict(reloaded,task_type="CPU"),dict(reloaded,extra=1),
                        dict(reloaded,nested=[1,dict(x=.1)]),dict(reloaded,nested=[True,dict(x=.1),None]),
                        dict(reloaded,learning_rate=float("nan")),dict(reloaded,learning_rate=float("inf"))):
            with self.subTest(changed=changed):
                self.assertFalse(audit.same_model_parameters(changed,reported))

    def test_full_y_offcandidate_and_zero_hit_queries(self):
        positive = audit.query_metrics([("01",1,.9),("02",2,.8)],{"01","off-C"},2,1)
        empty = audit.query_metrics([("01",1,.9),("02",2,.8)],set(),2,0)
        self.assertEqual(positive["ap12"],.5)
        self.assertEqual(positive["recall12"],.5)
        summary = audit.metric_math.aggregate_queries({"p":positive,"e":empty})
        self.assertEqual(summary["map_at_12_conditional"],.5)
        self.assertEqual(summary["map_at_12_all_queries_empty_zero"],.25)

    def test_invalid_ranks_scores_duplicates_ties(self):
        cases = [[("a",1.0,.9),("b",2,.8)],[("a",1,.9),("b",3,.8)],
                 [("a",1,.9),("a",2,.8)],[("a",1,float("nan")),("b",2,.8)],
                 [("b",1,.9),("a",2,.9)]]
        for predictions in cases:
            with self.subTest(case=predictions),self.assertRaises(ValueError):
                audit.query_metrics(predictions,{"a"},2,1)

    def test_full_y_denominator_capped12_and_shared_precision(self):
        truth = {f"a{i:02}" for i in range(20)}
        predictions = [(f"a{i:02}",i+1,float(20-i)) for i in range(12)]
        row = audit.query_metrics(predictions,truth,120,20)
        self.assertEqual(row["ap12"],1)
        self.assertEqual(row["recall12"],.6)


class ReservationSourceTests(unittest.TestCase):
    def setUp(self):
        import duckdb
        self.con = duckdb.connect(":memory:")
        self.con.execute("SET threads=1")
        self.con.execute("SET memory_limit='512MB'")
        self.con.execute("CREATE TABLE transactions(t_dat DATE,customer_id VARCHAR,article_id VARCHAR)")
        customers = [hashlib.sha256(f"invented{i}".encode()).hexdigest() for i in range(40)]
        self.con.executemany("INSERT INTO transactions VALUES ('2020-08-01',?,'a')",[(customer,) for customer in customers])
        h = lambda value:hashlib.sha256(value.encode()).hexdigest()
        excluded = sorted(customers,key=lambda customer:(h(customer+":2026"),customer))[:2]
        self.salt = "invented-reservation"
        self.reserved = sorted(set(customers)-set(excluded),key=lambda customer:(h(customer+":"+self.salt),customer))[:2]
        self.con.execute("CREATE TABLE ha_excluded(customer_id VARCHAR)")
        self.con.executemany("INSERT INTO ha_excluded VALUES (?)",[(customer,) for customer in excluded])
        self.con.execute("CREATE TABLE ha_reserved(customer_id VARCHAR,cohort_hash VARCHAR,reservation_rank BIGINT)")
        self.con.executemany("INSERT INTO ha_reserved VALUES (?,?,?)",[(customer,h(customer+":"+self.salt),i+1) for i,customer in enumerate(self.reserved)])
        self.con.execute("CREATE TABLE ha_supervised_0 AS SELECT customer_id FROM ha_excluded")

    def tearDown(self):
        self.con.close()

    def run_check(self):
        audit.rebuild_reserved_ids(self.con,self.salt,2,2,["ha_supervised_0"],audit.metric_math.Deadline(10))

    def test_exact_source_reservation_disjoint_and_future_ids_ignored(self):
        self.con.execute("INSERT INTO transactions VALUES ('2020-09-16','future-ID','future-item')")
        self.run_check()
        self.assertEqual(self.con.execute("SELECT count(*) FROM ha_reserved r JOIN ha_excluded e USING(customer_id)").fetchone()[0],0)

    def test_corrupted_reserved_hash_rejected(self):
        self.con.execute("UPDATE ha_reserved SET cohort_hash='wrong' WHERE reservation_rank=1")
        with self.assertRaisesRegex(ValueError,"hash ordering"):
            self.run_check()

    def test_supervised_reserved_overlap_rejected(self):
        self.con.execute("INSERT INTO ha_supervised_0 SELECT customer_id FROM ha_reserved WHERE reservation_rank=1")
        with self.assertRaisesRegex(ValueError,"supervised query ID"):
            self.run_check()

    def test_wrong_exclusion_union_rejected(self):
        self.con.execute("INSERT INTO ha_excluded VALUES ('invented-extra')")
        with self.assertRaisesRegex(ValueError,"old cohort union"):
            self.run_check()


def saved_fixture(root):
    """Two invented Q,150 historical articles, four fake model byte strings.

    A test-only gate injects the tiny plan; the real production gate independently
    requires20k IDs and the real implementation pins. No frozen module is patched.
    """
    import duckdb
    outroot=root/"artifacts/fixture"
    outroot.mkdir(parents=True)
    con=duckdb.connect(":memory:")
    con.execute("SET threads=1")
    def write(path,value):
        path.write_text(json.dumps(value,sort_keys=True)+"\n",encoding="utf-8",newline="\n")
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    def ref(path,with_size=True):
        value=dict(path=path.relative_to(root).as_posix(),sha256=sha(path))
        if with_size:
            value["bytes"]=path.stat().st_size
        return value
    def parquet(path,sql,parameters=None):
        con.sql(sql,params=parameters or []).write_parquet(str(path))
    h=lambda value:hashlib.sha256(value.encode()).hexdigest()
    customers=[h(f"fixture-user{i}") for i in range(40)]
    excluded=sorted(customers,key=lambda u:(h(u+":2026"),u))[:2]
    salt="fixture-reservation"
    reserved=sorted(set(customers)-set(excluded),key=lambda u:(h(u+":"+salt),u))[:2]
    database=outroot/"source.duckdb"
    source=duckdb.connect(str(database))
    source.execute("CREATE TABLE transactions(t_dat DATE,customer_id VARCHAR,article_id VARCHAR)")
    source.executemany("INSERT INTO transactions VALUES ('2020-08-01',?,'a000')",[(u,) for u in customers])
    source.executemany("INSERT INTO transactions VALUES ('2020-08-01',?,?)",[(customers[0],f"a{i:03}") for i in range(150)])
    source.executemany("INSERT INTO transactions VALUES ('2020-09-16',?,?)",[(reserved[0],"a001"),(reserved[0],"off-C")])
    source.close()
    dbref=ref(database)
    reservation=outroot/"reservation"
    reservation.mkdir()
    con.execute("CREATE TABLE fixture_reserved(customer_id VARCHAR,cohort_hash VARCHAR,reservation_rank INTEGER)")
    con.executemany("INSERT INTO fixture_reserved VALUES (?,?,?)",[(u,h(u+":"+salt),i+1) for i,u in enumerate(reserved)])
    con.execute("CREATE TABLE fixture_excluded(customer_id VARCHAR)")
    con.executemany("INSERT INTO fixture_excluded VALUES (?)",[(u,) for u in excluded])
    parquet(reservation/"reserved-users.parquet","SELECT * FROM fixture_reserved ORDER BY reservation_rank")
    parquet(reservation/"excluded-users.parquet","SELECT * FROM fixture_excluded ORDER BY customer_id")
    def idsha(values):
        return hashlib.sha256(b"".join(len(u.encode()).to_bytes(4,"big")+u.encode() for u in values)).hexdigest()
    code={"fixture.py":"0"*64}
    runtime={"fixture":"invented"}
    features=dict(digest="1"*64,registry=[dict(name="x",kind="numeric")])
    refs=[]
    inputs=[]
    for index,anchor in enumerate(audit.OLD_ANCHORS[1:-1]):
        train=outroot/f"train{index}"
        train.mkdir()
        parquet(train/"users.parquet","SELECT customer_id FROM fixture_excluded")
        (train/"frame.parquet").write_bytes(b"invented historical frame bytes only")
        (train/"targets.parquet").write_bytes(b"invented historical target bytes only")
        stored=dict(anchor=anchor,features=features,database={key:dbref[key] for key in ("sha256","bytes")},
                    files={name:sha(train/name) for name in ("frame.parquet","users.parquet","targets.parquet")},
                    qcy_identity="2"*64,candidate_identity="3"*64)
        write(train/"manifest.json",stored)
        refs.append(dict(anchor=anchor,manifest=ref(train/"manifest.json",False),users=ref(train/"users.parquet")))
        inputs.append(dict(anchor=anchor,manifest_sha256=sha(train/"manifest.json"),qcy_identity=stored["qcy_identity"],candidate_identity=stored["candidate_identity"]))
    old=[dict(anchor=r["anchor"],**r["users"]) for r in refs]
    write(reservation/"manifest.json",dict(status="completed",counts_history_only=dict(actual_old_cohorts=old)))
    cohort=dict(kind="reserved_customer_holdout",anchor="2020-09-16",horizon_days=7,users=2,history_days=90,salt=salt,policy="C0-Q120")
    collection=outroot/"collection"
    collection.mkdir()
    parquet(collection/"users.parquet","SELECT *,120::INTEGER full_candidate_count FROM fixture_reserved ORDER BY reservation_rank")
    parquet(collection/"targets.parquet","SELECT ?::VARCHAR customer_id,'a001' article_id UNION ALL SELECT ?,'off-C'",[reserved[0],reserved[0]])
    con.execute("CREATE TABLE fixture_frame AS SELECT customer_id,'a'||lpad(i::VARCHAR,3,'0') article_id FROM fixture_reserved CROSS JOIN range(120) t(i)")
    parquet(collection/"frame.parquet","SELECT *,customer_id=? AND article_id='a001' AS label,120::INTEGER full_candidate_count,1.0/120 AS query_weight FROM fixture_frame",[reserved[0]])
    keydigest=hashlib.sha256()
    for user in sorted(reserved):
        for index in range(120):
            for value in (user,f"a{index:03}"):
                encoded=value.encode();keydigest.update(len(encoded).to_bytes(4,"big"));keydigest.update(encoded)
    files={name:sha(collection/name) for name in ("frame.parquet","users.parquet","targets.parquet")}
    manifest=dict(format="hm-auto-holdout-collection-v2",status="completed",anchor="2020-09-16",horizon_days=7,
                  policy="C0-Q120",requested_users=2,holdout_lock_sha256="f"*64,cohort=cohort,code=code,runtime=runtime,
                  reservation_manifest_sha256=sha(reservation/"manifest.json"),
                  reserved_ordered_ids_sha256=idsha(reserved),excluded_ordered_ids_sha256=idsha(sorted(excluded)),
                  id_checks=dict(reserved_users=2,excluded_overlap_users=0,training_overlap_users=0),
                  database={key:dbref[key] for key in ("sha256","bytes")},features=features,files=files,
                  qcy_identity=audit.metric_math.canonical_digest({name:files[name] for name in ("users.parquet","targets.parquet")}),
                  candidate_identity=keydigest.hexdigest(),population=dict(candidate_rows=240,positive_rows=1,selected_queries=2,target_pairs=2))
    write(collection/"manifest.json",manifest)
    fitdirs=[]
    modelmeta={}
    truths={reserved[0]:{"a001","off-C"},reserved[1]:set()}
    params=dict(iterations=500,depth=8,l2_leaf_reg=10,task_type="GPU",loss_function="Logloss")
    valinput=dict(anchor=manifest["anchor"],manifest_sha256=sha(collection/"manifest.json"),qcy_identity=manifest["qcy_identity"],candidate_identity=manifest["candidate_identity"])
    for index,(arm,seed) in enumerate((("M",2026),("M",2027),("E",2026),("E",2027))):
        folder=outroot/f"fit{index}"
        folder.mkdir();fitdirs.append(folder)
        predictions=[("a001",1,12.0)]+[("a000" if i==2 else f"a{i-1:03}",i,float(13-i)) for i in range(2,13)]
        values={u:audit.query_metrics(predictions,truths[u],120,int(u==reserved[0])) for u in reserved}
        con.execute("CREATE OR REPLACE TABLE fixture_pred(customer_id VARCHAR,article_id VARCHAR,rank INTEGER,score DOUBLE)")
        con.executemany("INSERT INTO fixture_pred VALUES (?,?,?,?)",[(u,*row) for u in reserved for row in predictions])
        parquet(folder/"predictions-top12.parquet","SELECT * FROM fixture_pred")
        con.execute("CREATE OR REPLACE TABLE fixture_metrics(customer_id VARCHAR,targets INTEGER,candidate_count INTEGER,hits12 INTEGER,covered INTEGER,ap12 DOUBLE,recall12 DOUBLE,oracle_ap12 DOUBLE)")
        con.executemany("INSERT INTO fixture_metrics VALUES (?,?,?,?,?,?,?,?)",[(u,*(values[u][key] for key in ("targets","candidate_count","hits12","covered","ap12","recall12","oracle_ap12"))) for u in reserved])
        parquet(folder/"query-metrics.parquet","SELECT * FROM fixture_metrics")
        (folder/"model.cbm").write_bytes(b"fake metadata model never natively loaded")
        parameters=dict(params,random_seed=seed)
        producer=dict(format="hm-auto-holdout-fit-v2",status="completed",fit_count=1,actual_trees=500,
                      holdout_lock_sha256="f"*64,holdout_arm=arm,reservation_manifest_sha256=sha(reservation/"manifest.json"),cohort=cohort,
                      features=dict(numeric=["x"],categorical=[],contract_digest=features["digest"]),hyperparameters=parameters,
                      training_user_limit=2,negative_sample=20,sampling_seed=2026,inputs=inputs+[valinput],code=code,runtime=runtime,
                      resolved_model_parameters=parameters,validation_metrics=audit.metric_math.aggregate_queries(values),
                      validation_population=dict(selected_queries=2,full_candidate_rows=240,fit_rows=240,positive_rows=1,target_pairs=2),
                      files={name:sha(folder/name) for name in ("model.cbm","query-metrics.parquet","predictions-top12.parquet")})
        producer["fit_identity"]=audit.metric_math.canonical_digest(audit.fit_identity_payload(producer))
        write(folder/"report.json",producer)
        modelmeta[str(folder/"model.cbm")]=dict(trees=500,names=["x"],categorical=[],parameters=parameters)
    data=dict(cohort=cohort,training=dict(train_users=2),outputs=dict(audit=(outroot/"audit").relative_to(root).as_posix()),
              implementation=dict(code=code,runtime=runtime),train_collections=refs,database=dbref,
              reservation=dict(manifest=ref(reservation/"manifest.json",False),files={name:ref(reservation/name) for name in ("reserved-users.parquet","excluded-users.parquet")},
                               reserved_ordered_ids_sha256=idsha(reserved),excluded_ordered_ids_sha256=idsha(sorted(excluded))),
              features={arm:dict(numeric=["x"],categorical=[]) for arm in ("M","E")},hyperparameters={arm:params for arm in ("M","E")})
    plan=SimpleNamespace(data=data,sha256="f"*64)
    def authorize(plan,got_collection,got_fits,got_output):
        audit.require(got_collection==collection and got_fits==fitdirs and got_output==outroot/"audit","Test authorization paths differ")
        audit.require(not got_output.exists(),"Test audit output already exists")
    gate=SimpleNamespace(load_lock=lambda path,sha:plan,authorize_audit=authorize)
    con.close()
    return plan,gate,collection,fitdirs,outroot/"audit",modelmeta


class LockedSavedAuditTests(unittest.TestCase):
    def invoke(self,root,gate,collection,fits,output,models):
        import scripts
        with patch.object(audit,"ROOT",root),patch.object(scripts,"hm_auto_holdout_lock",gate,create=True),patch.object(audit,"inspect_model",side_effect=lambda p:models[str(p)]):
            return audit.audit(root/"not-real-lock.json","f"*64,collection,fits,output,30)

    def test_full_tiny_saved_audit_source_oracles_and_four_exports(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            plan,gate,collection,fits,output,models=saved_fixture(root)
            report=self.invoke(root,gate,collection,fits,output,models)
            self.assertEqual(report["status"],"PASS")
            self.assertEqual([entry["arm"] for entry in report["fits"]],[0,1,2,3])
            self.assertEqual(report["fits"][0]["metrics"]["map_at_12_conditional"],.5)
            self.assertEqual(report["fits"][0]["metrics"]["map_at_12_all_queries_empty_zero"],.25)
            self.assertEqual(len(list(output.glob("arm-*-query-metrics.parquet"))),4)
            self.assertEqual(report["comparisons"],[])

    def test_authorization_failure_precedes_DB_or_model_or_output(self):
        import duckdb
        import scripts
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            plan,gate,collection,fits,output,models=saved_fixture(root)
            def denied(*args):
                raise ValueError("No approved lock")
            gate.authorize_audit=denied
            with patch.object(audit,"ROOT",root),patch.object(scripts,"hm_auto_holdout_lock",gate,create=True),patch.object(audit,"inspect_model") as model,patch.object(duckdb,"connect") as connect:
                with self.assertRaisesRegex(ValueError,"approved lock"):
                    audit.audit(root/"missing.json","f"*64,collection,fits,output,30)
                model.assert_not_called();connect.assert_not_called()
            self.assertFalse(output.exists())

    def test_model_metadata_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            plan,gate,collection,fits,output,models=saved_fixture(root)
            models[str(fits[0]/"model.cbm")]["trees"]=499
            with self.assertRaisesRegex(ValueError,"Saved model capacity"):
                self.invoke(root,gate,collection,fits,output,models)
            self.assertEqual(json.loads((output/"report.json").read_text())["status"],"FAIL")

    @staticmethod
    def mutate_cache(root,collection,fits,name,sql):
        import duckdb
        con=duckdb.connect(":memory:")
        con.execute("CREATE TABLE baseline AS SELECT * FROM read_parquet(?)",[str(collection/name)])
        replacement=root/"invented-replacement.parquet"
        con.sql(sql).write_parquet(str(replacement))
        (collection/name).write_bytes(replacement.read_bytes())
        manifest=json.loads((collection/"manifest.json").read_text(encoding="utf-8"))
        manifest["files"][name]=hashlib.sha256((collection/name).read_bytes()).hexdigest()
        manifest["qcy_identity"]=audit.metric_math.canonical_digest({key:manifest["files"][key] for key in ("users.parquet","targets.parquet")})
        if name=="frame.parquet":
            con.execute("CREATE TABLE ha_candidates AS SELECT customer_id,article_id FROM read_parquet(?)",[str(collection/name)])
            manifest["candidate_identity"]=audit.candidate_identity(con,"ha_candidates",audit.metric_math.Deadline(10))
        con.close()
        (collection/"manifest.json").write_text(json.dumps(manifest)+"\n",encoding="utf-8",newline="\n")
        for fit in fits:
            path=fit/"report.json"
            producer=json.loads(path.read_text(encoding="utf-8"))
            producer["inputs"][-1].update(manifest_sha256=hashlib.sha256((collection/"manifest.json").read_bytes()).hexdigest(),
                                           qcy_identity=manifest["qcy_identity"],candidate_identity=manifest["candidate_identity"])
            producer["fit_identity"]=audit.metric_math.canonical_digest(audit.fit_identity_payload(producer))
            path.write_text(json.dumps(producer)+"\n",encoding="utf-8",newline="\n")

    def test_fullY_corruption_rejected_after_all_cache_identity_updates(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            plan,gate,collection,fits,output,models=saved_fixture(root)
            self.mutate_cache(root,collection,fits,"targets.parquet","SELECT * FROM baseline UNION ALL (SELECT customer_id,'not-purchased' article_id FROM baseline LIMIT 1)")
            with self.assertRaisesRegex(ValueError,"fullY differs"):
                self.invoke(root,gate,collection,fits,output,models)

    def test_wrong_label_rejected_after_all_cache_identity_updates(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            plan,gate,collection,fits,output,models=saved_fixture(root)
            self.mutate_cache(root,collection,fits,"frame.parquet","SELECT * REPLACE(false AS label) FROM baseline")
            with self.assertRaisesRegex(ValueError,"labels differ"):
                self.invoke(root,gate,collection,fits,output,models)

    def test_wrong_C_rejected_after_all_cache_identity_updates(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            plan,gate,collection,fits,output,models=saved_fixture(root)
            self.mutate_cache(root,collection,fits,"frame.parquet","SELECT * REPLACE(CASE WHEN article_id='a119' THEN 'not-in-source' ELSE article_id END AS article_id) FROM baseline")
            with self.assertRaisesRegex(ValueError,"source C0"):
                self.invoke(root,gate,collection,fits,output,models)

    def test_wrong_saved_AP_rejected_even_with_matching_file_hash(self):
        import duckdb
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            plan,gate,collection,fits,output,models=saved_fixture(root)
            path=fits[0]/"query-metrics.parquet"
            con=duckdb.connect(":memory:")
            con.execute("CREATE TABLE baseline AS SELECT * FROM read_parquet(?)",[str(path)])
            replacement=root/"invented-wrong-metrics.parquet"
            con.sql("SELECT * REPLACE(CASE WHEN targets>0 THEN 1.0 ELSE 0.0 END AS ap12) FROM baseline").write_parquet(str(replacement))
            con.close()
            path.write_bytes(replacement.read_bytes())
            producer=json.loads((fits[0]/"report.json").read_text(encoding="utf-8"))
            producer["files"][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
            (fits[0]/"report.json").write_text(json.dumps(producer)+"\n",encoding="utf-8",newline="\n")
            with self.assertRaisesRegex(ValueError,"per-query metrics disagree"):
                self.invoke(root,gate,collection,fits,output,models)

if __name__ == "__main__":
    unittest.main()
