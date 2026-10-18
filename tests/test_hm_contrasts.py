"""Tiny audited-array fixtures; no models, feature caches or raw data."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts import hm_contrasts as contrasts


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2)+"\n",encoding="utf-8",newline="\n")


class ContrastTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="hm-contrasts-unit-",dir=contrasts.ROOT/"artifacts")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.audit=self.root/"audit";self.audit.mkdir()
        self.spec=self.root/"fixed-spec.json"
        self.report=dict(format="hm-independent-result-audit-v1",status="PASS",checker_sha256="a"*64,
            collection=dict(anchor="2020-09-02",qcy_identity="b"*64,candidate_identity="c"*64,manifest_sha256="d"*64),fits=[])
        self.rows={}
        self.add_arm(0,[1.,0.,0.]);self.add_arm(1,[0.,1.,0.]);self.add_arm(2,[.25,.25,0.])
        self.contrast=[dict(name="mean_two_seeds_minus_manual",positive=["arm-00","arm-01"],negative=["arm-02"])]
        self.finish()

    def add_arm(self,number,aps,users=("01","02","empty"),targets=(2,2,0),covered=(2,2,0)):
        import duckdb
        name=f"arm-{number:02d}"
        rows=[(u,t,120,c,ap) for u,t,c,ap in zip(users,targets,covered,aps)]
        path=self.audit/(name+".parquet")
        db=duckdb.connect(":memory:")
        db.execute("CREATE TABLE metrics(customer_id VARCHAR,targets BIGINT,candidate_count BIGINT,covered BIGINT,ap12 DOUBLE)")
        db.executemany("INSERT INTO metrics VALUES (?,?,?,?,?)",rows)
        db.sql("SELECT * FROM metrics").write_parquet(str(path));db.close()
        positive=[ap for _,target,_,_,ap in rows if target>0]
        arm=dict(arm=number,fit_identity=f"{number+1:064x}",report_sha256=f"{number+10:064x}",
            private_query_metrics=dict(file=path.name,sha256=sha(path)),
            metrics=dict(queries=len(rows),positive_queries=len(positive),map_at_12_conditional=sum(positive)/len(positive) if positive else None))
        self.report["fits"]=[entry for entry in self.report["fits"] if entry["arm"]!=number]+[arm]
        self.rows[name]={u:dict(targets=t,candidate_count=n,covered=c,ap12=ap) for u,t,n,c,ap in rows}

    def finish(self):
        write(self.audit/"report.json",self.report)
        write(self.spec,dict(audit_report_sha256=sha(self.audit/"report.json"),contrasts=self.contrast))

    def run_fixture(self,name="result"):
        return contrasts.run(self.audit,self.spec,self.root/name,30)

    def test_correlated_model_seeds_are_averaged_before_user_bootstrap(self):
        result=self.run_fixture()
        item=result["contrasts"][0]
        self.assertEqual(item["queries"],2)
        self.assertEqual(item["mean_delta"],.25)
        self.assertEqual(item["percentile_95"],[.25,.25])
        self.assertEqual(item["draws"],2000)
        self.assertEqual(result["arm_mean_ap"]["arm-00"]["conditional"],.5)
        self.assertEqual(result["queries"],3)
        self.assertNotIn('"01"',json.dumps(result))

    def test_selected_minus_mean_three_random_controls_keeps_one_user_unit(self):
        self.add_arm(3,[.25,.25,0.])
        self.contrast=[dict(name="selected_minus_average_random",positive=["arm-00"],negative=["arm-01","arm-02","arm-03"])]
        self.finish();result=self.run_fixture()
        self.assertEqual(result["contrasts"][0]["queries"],2)
        self.assertAlmostEqual(result["contrasts"][0]["mean_delta"],1/6)

    def test_mismatched_q_y_or_coverage_is_rejected(self):
        for field,value in (("targets",1),("candidate_count",119),("covered",1)):
            arms=deepcopy(self.rows);arms["arm-01"]["01"][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,"identical"):
                contrasts.compute_contrasts(self.contrast,arms)
        arms=deepcopy(self.rows);arms["arm-01"]["other"]=arms["arm-01"].pop("01")
        with self.assertRaisesRegex(ValueError,"same customer IDs"):
            contrasts.compute_contrasts(self.contrast,arms)

    def test_duplicate_unavailable_and_overlapping_arms_rejected(self):
        for positive,negative in ((["arm-00","arm-00"],["arm-02"]),(["arm-00"],["arm-00"]),(["arm-xx"],["arm-02"])):
            spec=dict(audit_report_sha256="a"*64,contrasts=[dict(name="invalid",positive=positive,negative=negative)])
            with self.subTest(positive=positive),self.assertRaises(ValueError):contrasts.parse_spec(spec)
        self.contrast[0]["positive"]=["arm-99"];self.finish()
        with self.assertRaisesRegex(ValueError,"unavailable"):self.run_fixture()

    def test_audit_identity_and_private_file_hash_mismatch_fail_closed(self):
        self.report["status"]="FAIL";self.finish()
        with self.assertRaisesRegex(ValueError,"PASS"):self.run_fixture("bad-status")
        self.report["status"]="PASS";self.finish()
        path=self.audit/"arm-00.parquet";path.write_bytes(path.read_bytes()+b"tampered")
        with self.assertRaisesRegex(ValueError,"artifact SHA256"):self.run_fixture("bad-artifact")
        spec=json.loads(self.spec.read_text());spec["audit_report_sha256"]="0"*64;write(self.spec,spec)
        with self.assertRaisesRegex(ValueError,"fixed spec"):self.run_fixture("bad-report")

    def test_invalid_ap_duplicate_query_and_empty_target_nonzero_are_rejected(self):
        for values,users,targets,covered in (([float("nan"),0.,0.],("01","02","empty"),(2,2,0),(2,2,0)),
            ([1.1,0.,0.],("01","02","empty"),(2,2,0),(2,2,0)),
            ([.5,0.,.1],("01","02","empty"),(2,2,0),(2,2,0)),
            ([.5,.5,0.],("01","01","empty"),(2,2,0),(2,2,0))):
            self.add_arm(0,values,users,targets,covered);self.finish()
            with self.subTest(values=values),self.assertRaises(ValueError):self.run_fixture(f"invalid-{len(list(self.root.glob('invalid-*')))}")

    def test_missing_population_identity_and_escaping_artifact_rejected(self):
        self.report["collection"]["qcy_identity"]="not-a-hash";self.finish()
        with self.assertRaisesRegex(ValueError,"SHA256"):self.run_fixture("bad-qy")
        self.report["collection"]["qcy_identity"]="a"*64
        self.report["fits"][0]["private_query_metrics"]["file"]="../outside.parquet";self.finish()
        with self.assertRaisesRegex(ValueError,"escapes"):self.run_fixture("bad-path")

    def test_no_future_purchasers_report_null_difference_and_interval(self):
        for number in range(3):
            self.add_arm(number,[0.,0.,0.],targets=(0,0,0),covered=(0,0,0))
        self.finish();result=self.run_fixture()
        self.assertEqual(result["positive_queries"],0)
        self.assertIsNone(result["contrasts"][0]["mean_delta"])
        self.assertIsNone(result["contrasts"][0]["percentile_95"])
        self.assertEqual(result["arm_mean_ap"]["arm-00"]["all_query_empty_zero"],0.)

    def test_reported_arm_mean_and_duplicate_inventory_are_rejected(self):
        self.report["fits"][0]["metrics"]["map_at_12_conditional"]=.99;self.finish()
        with self.assertRaisesRegex(ValueError,"aggregate AP"):self.run_fixture("bad-mean")
        self.report["fits"].append(deepcopy(self.report["fits"][0]));self.finish()
        with self.assertRaisesRegex(ValueError,"Duplicate audited arm"):self.run_fixture("bad-inventory")

    def test_heuristic_identifiers_and_new_output_guards(self):
        self.report["heuristics"]=dict(status="evaluated",recency=deepcopy(self.report["fits"][2]),popularity=deepcopy(self.report["fits"][1]))
        self.contrast=[dict(name="manual_minus_recency",positive=["arm-00"],negative=["recency"])]
        self.finish();result=self.run_fixture()
        self.assertEqual(result["contrasts"][0]["mean_delta"],.25)
        with self.assertRaises(FileExistsError):self.run_fixture()
        with self.assertRaisesRegex(ValueError,"artifacts"):
            contrasts.run(self.audit,self.spec,self.root.parent.parent/"outside-artifacts",30)


if __name__=="__main__":unittest.main()
