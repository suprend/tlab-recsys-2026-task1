"""Independent v2 reserved-customer audit; no fitting or native prediction.

Only explicitly authorized, locked customer-test artifacts may reach production
SQL. Source C0-Q120 is reconstructed independently of the producer builder.
The source oracle below is also exercised on tiny invented in-memory fixtures.
"""
from __future__ import annotations

from datetime import date
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import threading
import time

from scripts import hm_result_audit as metric_math

TOLERANCE = 1e-12
ROOT = Path(__file__).resolve().parents[1]
OLD_ANCHORS = ("2020-08-05","2020-08-12","2020-08-19","2020-08-26",
               "2020-09-02","2020-09-09","2020-09-16")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def candidate_identity(connection, table, deadline):
    require(table in ("ha_candidates", "ha_expected_candidates"), "Unknown audit key table")
    digest = hashlib.sha256()
    cursor = connection.execute(f"SELECT customer_id,article_id FROM {table} ORDER BY customer_id,article_id")
    while rows := cursor.fetchmany(8192):
        deadline.check()
        for row in rows:
            for value in row:
                require(isinstance(value,str), "Candidate key must be a string")
                encoded = value.encode("utf-8")
                digest.update(len(encoded).to_bytes(4,"big"))
                digest.update(encoded)
    return digest.hexdigest()


def rebuild_c0q120(connection, anchor, deadline):
    """Build source-only expected pairs for an already checked ``ha_users``.

    Unlike the producer's exclusion/refill construction, form one recent/global
    union, retain the first copy of each pair, then take its first120 entries.
    All population histories contribute global buyers. This never reads Y.
    """
    anchor = date.fromisoformat(str(anchor)).isoformat()
    require(anchor == "2020-09-16", "Customer test oracle requires September16")
    deadline.check()
    connection.execute("""CREATE TEMP TABLE ha_history AS
        SELECT t_dat,customer_id,article_id FROM transactions
        WHERE t_dat>=?::DATE-INTERVAL '90 days' AND t_dat<?::DATE""",[anchor,anchor])
    connection.execute("""CREATE TEMP TABLE ha_global AS
        SELECT article_id,row_number() OVER(ORDER BY
          count(DISTINCT customer_id) FILTER(WHERE t_dat>=?::DATE-INTERVAL '7 days') DESC,
          article_id ASC) AS popularity_rank
        FROM ha_history GROUP BY article_id""",[anchor])
    require(connection.execute("SELECT count(*) FROM ha_global").fetchone()[0] >= 120,
            "Source historical catalog cannot fill120 candidates")
    # Twenty recent entries plus200 global entries always leave enough unique
    # entries to fill120, even when every recent entry is in the global set.
    connection.execute("""CREATE TEMP TABLE ha_recent AS
        SELECT h.customer_id,h.article_id,row_number() OVER(
          PARTITION BY h.customer_id ORDER BY max(h.t_dat) DESC,h.article_id ASC) AS recent_rank
        FROM ha_history h JOIN ha_users u USING(customer_id)
        GROUP BY h.customer_id,h.article_id QUALIFY recent_rank<=20""")
    connection.execute("""CREATE TEMP TABLE ha_expected_candidates AS
        WITH unioned AS (
          SELECT customer_id,article_id,1 AS priority,recent_rank AS local_rank FROM ha_recent
          UNION ALL
          SELECT u.customer_id,g.article_id,2 AS priority,g.popularity_rank AS local_rank
          FROM ha_users u CROSS JOIN ha_global g WHERE g.popularity_rank<=200
        ), unique_entries AS (
          SELECT * FROM unioned QUALIFY row_number() OVER(
            PARTITION BY customer_id,article_id ORDER BY priority,local_rank)=1
        ) SELECT customer_id,article_id,
          row_number() OVER(PARTITION BY customer_id ORDER BY priority,local_rank,article_id) AS candidate_rank
          FROM unique_entries QUALIFY candidate_rank<=120""")
    invalid = connection.execute("""SELECT count(*) FROM (
        SELECT customer_id,count(*) n,count(DISTINCT article_id) d
        FROM ha_expected_candidates GROUP BY customer_id) WHERE n<>120 OR d<>120""").fetchone()[0]
    represented = connection.execute("SELECT count(DISTINCT customer_id) FROM ha_expected_candidates").fetchone()[0]
    require(not invalid and represented == connection.execute("SELECT count(*) FROM ha_users").fetchone()[0],
            "Independent source candidates must represent every query120 times")
    deadline.check()


def compare_source_candidates(connection):
    mismatch = connection.execute("""SELECT count(*) FROM (
        (SELECT customer_id,article_id FROM ha_candidates EXCEPT
         SELECT customer_id,article_id FROM ha_expected_candidates)
        UNION ALL
        (SELECT customer_id,article_id FROM ha_expected_candidates EXCEPT
         SELECT customer_id,article_id FROM ha_candidates))""").fetchone()[0]
    require(mismatch == 0, "Cached candidates differ from independent source C0-Q120")


def rebuild_reserved_ids(connection, salt, users, old_limit, supervised_tables, deadline):
    """Independently rebuild past-only exclusion union and exact reserved Q.

    The caller has authenticated ``ha_reserved``/``ha_excluded`` and the named
    supervised-ID tables. Production limits are checked by the lock; explicit
    small limits permit hand-sized witnesses without weakening that boundary.
    """
    require(isinstance(salt,str) and bool(salt), "A reservation salt is required")
    require(type(users) is int and users>0 and type(old_limit) is int and old_limit>0,
            "Positive reservation/source cohort sizes required")
    require(all(re.fullmatch(r"ha_supervised_[0-9]+",table) for table in supervised_tables),
            "Unknown supervised ID table")
    deadline.check()
    connection.execute("""CREATE TEMP TABLE ha_ids_history AS
        SELECT t_dat,customer_id FROM transactions
        WHERE t_dat>=DATE '2020-08-05'-INTERVAL '90 days' AND t_dat<DATE '2020-09-16'""")
    connection.execute("CREATE TEMP TABLE ha_old_queries(anchor DATE,customer_id VARCHAR)")
    for anchor in OLD_ANCHORS:
        deadline.check()
        connection.execute("""INSERT INTO ha_old_queries
            SELECT ?::DATE,customer_id FROM (
              SELECT DISTINCT customer_id FROM ha_ids_history
              WHERE t_dat>=?::DATE-INTERVAL '90 days' AND t_dat<?::DATE
              ORDER BY sha256(customer_id || ':2026'),customer_id LIMIT ?)""",
                           [anchor,anchor,anchor,old_limit])
        count = connection.execute("SELECT count(*) FROM ha_old_queries WHERE anchor=?::DATE",[anchor]).fetchone()[0]
        require(count == old_limit, "Source cannot reconstruct complete old cohorts")
    connection.execute("CREATE TEMP TABLE ha_expected_excluded AS SELECT DISTINCT customer_id FROM ha_old_queries")
    for table in ("ha_reserved","ha_excluded",*supervised_tables):
        total,unique,nulls = connection.execute(f"SELECT count(*),count(DISTINCT customer_id),count(*) FILTER(WHERE customer_id IS NULL) FROM {table}").fetchone()
        require(total>0 and total==unique and nulls==0, "Reservation/exclusion/supervised IDs must be nonempty and unique")
    mismatch = connection.execute("""SELECT count(*) FROM (
        (SELECT customer_id FROM ha_expected_excluded EXCEPT SELECT customer_id FROM ha_excluded)
        UNION ALL
        (SELECT customer_id FROM ha_excluded EXCEPT SELECT customer_id FROM ha_expected_excluded))""").fetchone()[0]
    require(mismatch==0, "Excluded IDs differ from source-reconstructed old cohort union")
    for table in supervised_tables:
        require(connection.execute(f"SELECT count(*) FROM {table} s WHERE NOT EXISTS(SELECT 1 FROM ha_excluded e WHERE e.customer_id=s.customer_id)").fetchone()[0]==0,
                "A supervised query ID is not covered by reservation exclusions")
    connection.execute("""CREATE TEMP TABLE ha_expected_reserved AS
        WITH eligible AS (
          SELECT DISTINCT h.customer_id FROM ha_ids_history h
          WHERE h.t_dat>=DATE '2020-09-16'-INTERVAL '90 days'
            AND NOT EXISTS(SELECT 1 FROM ha_expected_excluded e WHERE e.customer_id=h.customer_id)
        ) SELECT customer_id,sha256(customer_id || ':' || ?) AS cohort_hash,
          row_number() OVER(ORDER BY sha256(customer_id || ':' || ?),customer_id) AS reservation_rank
          FROM eligible ORDER BY cohort_hash,customer_id LIMIT ?""",[salt,salt,users])
    require(connection.execute("SELECT count(*) FROM ha_expected_reserved").fetchone()[0]==users,
            "Insufficient remaining source customers for reserved cohort")
    mismatch = connection.execute("""SELECT count(*) FROM (
        (SELECT customer_id,cohort_hash,reservation_rank FROM ha_expected_reserved EXCEPT
         SELECT customer_id,cohort_hash,reservation_rank FROM ha_reserved)
        UNION ALL
        (SELECT customer_id,cohort_hash,reservation_rank FROM ha_reserved EXCEPT
         SELECT customer_id,cohort_hash,reservation_rank FROM ha_expected_reserved))""").fetchone()[0]
    require(mismatch==0 and connection.execute("SELECT count(*) FROM ha_reserved").fetchone()[0]==users,
            "Reservation differs from independent source eligibility/exclusion/hash ordering")
    deadline.check()


def query_metrics(predictions, truth, candidate_count, covered):
    """Frozen independent formula plus strict integer rank validation."""
    require(all(type(rank) is int for _,rank,_ in predictions), "Prediction ranks must be integers")
    return metric_math.evaluate_query(predictions,truth,candidate_count,covered)


def artifact(value):
    path = (ROOT/Path(value)).resolve()
    allowed = (ROOT/"artifacts").resolve()
    require(path != allowed and path.is_relative_to(allowed), "Audit input/output must be inside checkout artifacts")
    return path


def read_json(path):
    def pairs(items):
        result = {}
        for key,value in items:
            require(key not in result,"Duplicate JSON property")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("Nonfinite JSON constant")
    return json.loads(Path(path).read_text(encoding="utf-8"),object_pairs_hook=pairs,parse_constant=invalid)


def checked_file(reference, deadline):
    path = artifact(reference["path"])
    require(metric_math.file_digest(path,deadline) == reference["sha256"], "Pinned input SHA256 differs")
    if "bytes" in reference:
        require(path.stat().st_size == reference["bytes"], "Pinned input byte size differs")
    return path


def ordered_ids_digest(connection, table, order, deadline):
    require((table,order) in (("ha_reserved","reservation_rank"),("ha_excluded","customer_id")), "Unknown ordered ID digest")
    digest = hashlib.sha256()
    cursor = connection.execute(f"SELECT customer_id FROM {table} ORDER BY {order}")
    while rows := cursor.fetchmany(8192):
        deadline.check()
        for (value,) in rows:
            require(isinstance(value,str), "Reservation ID must be a string")
            encoded = value.encode("utf-8")
            digest.update(len(encoded).to_bytes(4,"big"))
            digest.update(encoded)
    return digest.hexdigest()


def inspect_model(path):
    """Saved-model metadata only: no scoring, importance or training."""
    from catboost import CatBoostClassifier
    model = CatBoostClassifier()
    model.load_model(str(path))
    result = dict(trees=model.tree_count_,names=model.feature_names_,
                  categorical=model.get_cat_feature_indices(),parameters=model.get_all_params())
    del model
    return result


def same_model_parameters(actual, reported):
    """CBM JSON round-trip tolerance, confined to saved parameter metadata.

    Native CBM serialization can round float digits relative to get_all_params
    immediately after fit. All types/keys/sequence structure and nonfloats stay
    exact. This tolerance must never be used for metrics, recipes or identities.
    """
    if type(actual) is not type(reported):
        return False
    if isinstance(actual,dict):
        return (actual.keys()==reported.keys()
                and all(type(key) is str for key in actual)
                and all(same_model_parameters(actual[key],reported[key]) for key in actual))
    if isinstance(actual,(list,tuple)):
        return len(actual)==len(reported) and all(same_model_parameters(a,b) for a,b in zip(actual,reported))
    if type(actual) is float:
        return math.isfinite(actual) and math.isfinite(reported) and math.isclose(actual,reported,rel_tol=1e-8,abs_tol=1e-12)
    if type(actual) in (int,bool,str,type(None)):
        return actual==reported
    return False


def fit_identity_payload(producer):
    value = dict(inputs=producer["inputs"],features=producer["features"],hyperparameters=producer["hyperparameters"],
                 train_users=producer["training_user_limit"],negative_sample=producer["negative_sample"],
                 sampling_seed=producer["sampling_seed"],code=producer["code"],runtime=producer["runtime"])
    for key in ("holdout_lock_sha256","holdout_arm","reservation_manifest_sha256","cohort"):
        value[key] = producer[key]
    return value


def audit(decision_lock, expected_lock_sha256, collection, fits, output, wall_seconds=1800):
    """Authorize exact four artifacts before any DB/parquet/model access."""
    require(type(wall_seconds) in (int,float) and math.isfinite(wall_seconds) and 0<wall_seconds<=1800,
            "Audit wall limit must be finite, positive and at most1800 seconds")
    deadline = metric_math.Deadline(wall_seconds)
    from scripts import hm_auto_holdout_lock as gate
    plan = gate.load_lock(decision_lock,expected_lock_sha256)
    collection,output = artifact(collection),artifact(output)
    fits = [artifact(path) for path in fits]
    gate.authorize_audit(plan,collection,fits,output)
    # No label-bearing file or source SQL is touched above this authorization.
    data = plan.data
    users_count = data["cohort"]["users"]
    train_count = data["training"]["train_users"]
    require(output == artifact(data["outputs"]["audit"]), "Audit output differs from lock")
    output.mkdir(parents=True,exist_ok=False)
    report = dict(format="hm-independent-result-audit-v1",status="running",fits=[],comparisons=[],fit_vs_recency=[],
                  holdout_lock_sha256=plan.sha256,cohort=data["cohort"],
                  reservation_manifest_sha256=data["reservation"]["manifest"]["sha256"],
                  scope="Independent reserved Q/source fullY/source C0-Q120/cache/saved-top12 audit; saved-model metadata only",
                  limitation="No native omitted candidate scores or feature formulas are recalculated. Saved top12 ordering does not establish global native top12. This is a customer holdout on an already observed calendar week.",
                  heuristics=dict(status="excluded",reason="Only four locked M/E seed fits are authorized"),tolerance=TOLERANCE)
    con = timer = None
    try:
        require(shutil.disk_usage(output).free>=10*1024**3, "Audit needs at least10GiB output free space")
        manifest_path = collection/"manifest.json"
        manifest = read_json(manifest_path)
        require(manifest.get("format")=="hm-auto-holdout-collection-v2" and manifest.get("status")=="completed", "Completed custom-cohort collection required")
        require("cohort_seed" not in manifest, "Custom cohort must not masquerade as seed2026 Q")
        require(manifest.get("holdout_lock_sha256")==plan.sha256 and manifest.get("cohort")==data["cohort"], "Collection lock/cohort differs")
        require(manifest.get("code")==data["implementation"]["code"] and manifest.get("runtime")==data["implementation"]["runtime"], "Collection source/runtime differs from lock")
        expected = dict(anchor="2020-09-16",horizon_days=7,policy="C0-Q120",requested_users=users_count,
                        reservation_manifest_sha256=report["reservation_manifest_sha256"],
                        reserved_ordered_ids_sha256=data["reservation"]["reserved_ordered_ids_sha256"],
                        excluded_ordered_ids_sha256=data["reservation"]["excluded_ordered_ids_sha256"],
                        id_checks=dict(reserved_users=users_count,excluded_overlap_users=0,training_overlap_users=0))
        require(all(manifest.get(key)==value for key,value in expected.items()), "Collection reservation/recipe metadata differs")
        for name in ("frame.parquet","users.parquet","targets.parquet"):
            require(metric_math.file_digest(collection/name,deadline)==manifest["files"][name], "Collection file SHA256 mismatch")
        qcy = metric_math.canonical_digest({name:manifest["files"][name] for name in ("users.parquet","targets.parquet")})
        require(qcy==manifest["qcy_identity"], "Collection Q/Y digest mismatch")
        reservation_path = checked_file(data["reservation"]["manifest"],deadline)
        reservation = read_json(reservation_path)
        require(reservation.get("status")=="completed", "Completed history-only reservation required")
        reserved = checked_file(data["reservation"]["files"]["reserved-users.parquet"],deadline)
        excluded = checked_file(data["reservation"]["files"]["excluded-users.parquet"],deadline)
        training = []
        supervised_paths = []
        for ref in data["train_collections"]:
            path = checked_file(ref["manifest"],deadline)
            stored = read_json(path)
            require(stored["anchor"]==ref["anchor"] and stored["features"]==manifest["features"], "Training anchor/feature schema mismatch")
            require(stored["database"]==manifest["database"], "Training/holdout source mismatch")
            for name,sha in stored["files"].items():
                require(metric_math.file_digest(path.parent/name,deadline)==sha, "Training cache artifact SHA256 differs")
            training.append(dict(anchor=stored["anchor"],manifest_sha256=ref["manifest"]["sha256"],
                                 qcy_identity=stored["qcy_identity"],candidate_identity=stored["candidate_identity"]))
            supervised_paths.append(checked_file(ref["users"],deadline))
        require([item["anchor"] for item in training]==list(OLD_ANCHORS[1:-1]), "Five locked training anchors required")
        for old in reservation["counts_history_only"]["actual_old_cohorts"]:
            supervised_paths.append(checked_file(old,deadline))
        supervised_paths = list(dict.fromkeys(supervised_paths))
        database = checked_file(data["database"],deadline)
        source_stat = database.stat()
        require(manifest["database"]=={key:data["database"][key] for key in ("sha256","bytes")}, "Original source identity mismatch")
        report["collection"] = dict(anchor=manifest["anchor"],policy=manifest["policy"],manifest_sha256=metric_math.file_digest(manifest_path,deadline),
                                    qcy_identity=qcy,candidate_identity=manifest["candidate_identity"],database_identity=manifest["database"])
        import duckdb
        import pandas as pd
        con = duckdb.connect(str(database),read_only=True)
        con.execute("SET threads=2")
        con.execute("SET memory_limit='2GB'")
        con.execute("SET preserve_insertion_order=false")
        temp = output/"duckdb-temp"
        temp.mkdir()
        con.execute("SET temp_directory=?",[str(temp)])
        con.execute("SET max_temp_directory_size='8GB'")
        timer = threading.Timer(max(0,deadline.expires-time.monotonic()),con.interrupt)
        timer.daemon=True
        timer.start()
        con.execute("CREATE TEMP TABLE ha_reserved AS SELECT * FROM read_parquet(?)",[str(reserved)])
        con.execute("CREATE TEMP TABLE ha_excluded AS SELECT * FROM read_parquet(?)",[str(excluded)])
        supervised_tables=[]
        for index,path in enumerate(supervised_paths):
            table = f"ha_supervised_{index}"
            con.execute(f"CREATE TEMP TABLE {table} AS SELECT customer_id FROM read_parquet(?)",[str(path)])
            supervised_tables.append(table)
        rebuild_reserved_ids(con,data["cohort"]["salt"],users_count,train_count,supervised_tables,deadline)
        require(ordered_ids_digest(con,"ha_reserved","reservation_rank",deadline)==data["reservation"]["reserved_ordered_ids_sha256"], "Reserved ordered-ID digest mismatch")
        require(ordered_ids_digest(con,"ha_excluded","customer_id",deadline)==data["reservation"]["excluded_ordered_ids_sha256"], "Excluded ordered-ID digest mismatch")
        con.execute("CREATE TEMP TABLE ha_users AS SELECT * FROM read_parquet(?)",[str(collection/"users.parquet")])
        con.execute("CREATE TEMP TABLE ha_targets AS SELECT customer_id,article_id FROM read_parquet(?)",[str(collection/"targets.parquet")])
        con.execute("CREATE TEMP TABLE ha_candidates AS SELECT customer_id,article_id,label,full_candidate_count,query_weight FROM read_parquet(?)",[str(collection/"frame.parquet")])
        def count(sql,parameters=None):
            deadline.check()
            return con.execute(sql,parameters or []).fetchone()[0]
        require(count("SELECT count(*) FROM ha_users")==users_count and count("SELECT count(DISTINCT customer_id) FROM ha_users")==users_count, "Complete unique reserved collection Q required")
        require(count("""SELECT count(*) FROM ((SELECT customer_id,cohort_hash,reservation_rank FROM ha_users EXCEPT SELECT customer_id,cohort_hash,reservation_rank FROM ha_reserved)
            UNION ALL (SELECT customer_id,cohort_hash,reservation_rank FROM ha_reserved EXCEPT SELECT customer_id,cohort_hash,reservation_rank FROM ha_users))""")==0,
                "Collection Q differs from exact reserved IDs/order")
        require(count("SELECT count(*) FROM ha_users WHERE full_candidate_count IS NULL OR full_candidate_count<>120")==0, "Query denominator must be120")
        for table in ("ha_targets","ha_candidates"):
            require(count(f"SELECT count(*) FROM (SELECT customer_id,article_id,count(*) n FROM {table} GROUP BY ALL HAVING n<>1)")==0, "Duplicate cached pair")
            require(count(f"SELECT count(*) FROM {table} x WHERE customer_id IS NULL OR article_id IS NULL OR NOT EXISTS(SELECT 1 FROM ha_users u WHERE u.customer_id=x.customer_id)")==0, "Cached pair outside exact Q")
        con.execute("CREATE TEMP TABLE ha_sizes AS SELECT customer_id,count(*) n FROM ha_candidates GROUP BY customer_id")
        require(count("SELECT count(*) FROM ha_sizes")==users_count and count("SELECT count(*) FROM ha_sizes WHERE n<>120")==0, "Every query needs120 unique cached candidates")
        require(count("SELECT count(*) FROM ha_candidates WHERE full_candidate_count IS NULL OR full_candidate_count<>120 OR query_weight IS NULL OR NOT isfinite(query_weight) OR abs(query_weight-1.0/120)>1e-12 OR label IS NULL")==0, "Cached label/weight/denominator invalid")
        require(candidate_identity(con,"ha_candidates",deadline)==manifest["candidate_identity"], "Cached candidate key digest mismatch")
        rebuild_c0q120(con,manifest["anchor"],deadline)
        compare_source_candidates(con)
        con.execute("""CREATE TEMP TABLE ha_source_targets AS SELECT DISTINCT t.customer_id,t.article_id
            FROM transactions t JOIN ha_reserved q USING(customer_id)
            WHERE t.t_dat>=DATE '2020-09-16' AND t.t_dat<DATE '2020-09-23'""")
        require(count("""SELECT count(*) FROM ((SELECT * FROM ha_source_targets EXCEPT SELECT * FROM ha_targets)
            UNION ALL (SELECT * FROM ha_targets EXCEPT SELECT * FROM ha_source_targets))""")==0, "Cached fullY differs from independent source")
        require(count("SELECT count(*) FROM ha_candidates c WHERE c.label<>EXISTS(SELECT 1 FROM ha_targets t WHERE t.customer_id=c.customer_id AND t.article_id=c.article_id)")==0, "Cached candidate labels differ from fullY")
        users=[row[0] for row in con.execute("SELECT customer_id FROM ha_users ORDER BY customer_id").fetchall()]
        truth={user:set() for user in users}
        for user,article in con.execute("SELECT customer_id,article_id FROM ha_targets").fetchall():
            truth[user].add(article)
        coverage=dict(con.execute("SELECT c.customer_id,count(*) FROM ha_candidates c JOIN ha_targets t USING(customer_id,article_id) GROUP BY c.customer_id").fetchall())
        require(manifest["population"]==dict(candidate_rows=users_count*120,positive_rows=sum(coverage.values()),selected_queries=users_count,target_pairs=sum(map(len,truth.values()))), "Collection population aggregates disagree")
        validation_identity=dict(anchor=manifest["anchor"],manifest_sha256=report["collection"]["manifest_sha256"],qcy_identity=qcy,candidate_identity=manifest["candidate_identity"])
        for index,fit in enumerate(fits):
            deadline.check()
            arm,seed=("M" if index<2 else "E"),(2026,2027)[index%2]
            producer=read_json(fit/"report.json")
            require(producer.get("format")=="hm-auto-holdout-fit-v2" and producer.get("status")=="completed" and producer.get("fit_count")==1, "Completed locked custom-cohort fit required")
            require(producer.get("holdout_arm")==arm and producer.get("holdout_lock_sha256")==plan.sha256 and producer.get("cohort")==data["cohort"] and producer.get("reservation_manifest_sha256")==report["reservation_manifest_sha256"], "Fit reservation/arm/lock differs")
            features=dict(data["features"][arm],contract_digest=manifest["features"]["digest"])
            parameters=dict(data["hyperparameters"][arm],random_seed=seed)
            require(producer["features"]==features and producer["hyperparameters"]==parameters and producer["actual_trees"]==500, "Fit features/parameters/capacity differ")
            require(producer["training_user_limit"]==train_count and producer["negative_sample"]==20 and producer["sampling_seed"]==2026, "Fit training policy differs")
            require(producer["inputs"]==training+[validation_identity], "Fit training/validation inputs differ")
            require(producer["code"]==data["implementation"]["code"] and producer["runtime"]==data["implementation"]["runtime"], "Fit implementation/runtime differs")
            require(metric_math.canonical_digest(fit_identity_payload(producer))==producer["fit_identity"], "Fit identity payload differs")
            for name in ("model.cbm","query-metrics.parquet","predictions-top12.parquet"):
                require(metric_math.file_digest(fit/name,deadline)==producer["files"][name], "Saved fit artifact SHA256 differs")
            model=inspect_model(fit/"model.cbm")
            require(model["trees"]==500 and model["names"]==features["numeric"]+features["categorical"] and model["categorical"]==list(range(len(features["numeric"]),len(model["names"]))), "Saved model capacity/feature order differs")
            require(same_model_parameters(model["parameters"],producer["resolved_model_parameters"]), "Saved model resolved parameters differ from producer")
            require(all(model["parameters"].get(key)==parameters[key] for key in ("iterations","depth","l2_leaf_reg","random_seed","task_type","loss_function")), "Saved model core recipe differs from lock")
            con.execute("CREATE OR REPLACE TEMP TABLE ha_predictions AS SELECT customer_id,article_id,rank,score FROM read_parquet(?)",[str(fit/"predictions-top12.parquet")])
            require(count("SELECT count(*) FROM ha_predictions p WHERE customer_id IS NULL OR article_id IS NULL OR NOT EXISTS(SELECT 1 FROM ha_candidates c WHERE c.customer_id=p.customer_id AND c.article_id=p.article_id)")==0, "Prediction outside exact cached Q/C")
            predicted={user:[] for user in users}
            for user,article,rank,score in con.execute("SELECT customer_id,article_id,rank,score FROM ha_predictions ORDER BY customer_id,rank").fetchall():
                predicted[user].append((article,rank,score))
            values={}
            for user in users:
                deadline.check()
                values[user]=query_metrics(predicted[user],truth[user],120,coverage.get(user,0))
            cursor=con.execute("SELECT * FROM read_parquet(?)",[str(fit/"query-metrics.parquet")])
            columns=[item[0] for item in cursor.description]
            exported={}
            for raw in cursor.fetchall():
                row=dict(zip(columns,raw))
                user=row.pop("customer_id")
                require(user not in exported, "Duplicate producer metric query")
                exported[user]=row
            metric_math.check_export(values,exported)
            metrics=metric_math.aggregate_queries(values)
            require(set(metrics)==set(producer["validation_metrics"]) and all(metric_math.close(value,producer["validation_metrics"][key]) for key,value in metrics.items()), "Producer aggregate metrics disagree")
            population=producer["validation_population"]
            require(population["selected_queries"]==users_count and population["full_candidate_rows"]==users_count*120 and population["fit_rows"]==users_count*120 and population["positive_rows"]==sum(coverage.values()) and population["target_pairs"]==sum(map(len,truth.values())), "Producer validation population disagrees")
            filename=f"arm-{index:02d}-query-metrics.parquet"
            con.register("_audit_values",pd.DataFrame([dict(customer_id=user,**row) for user,row in values.items()]))
            con.sql("SELECT * FROM _audit_values ORDER BY customer_id").write_parquet(str(output/filename))
            report["fits"].append(dict(arm=index,fit_directory=fit.as_posix(),report_sha256=metric_math.file_digest(fit/"report.json",deadline),
                                       fit_identity=producer["fit_identity"],metrics=metrics,
                                       private_query_metrics=dict(file=filename,sha256=metric_math.file_digest(output/filename,deadline)),
                                       saved_model_metadata="PASS: fresh load,500trees,ordered feature names/categories,core recipe"))
        after=database.stat()
        require((source_stat.st_size,source_stat.st_mtime_ns)==(after.st_size,after.st_mtime_ns), "Source DB changed during audit")
        require(metric_math.file_digest(manifest_path,deadline)==report["collection"]["manifest_sha256"], "Collection manifest changed during audit")
        require(gate.load_lock(decision_lock,expected_lock_sha256).sha256==plan.sha256, "Decision lock changed during audit")
        report.update(source_rebuild="PASS: source7cohort exclusion union/exactreservedhashQ/fullY/independentC0-Q120",
                      checker_sha256=metric_math.file_digest(Path(__file__),deadline),
                      metric_formula_source_sha256=metric_math.file_digest(Path(metric_math.__file__),deadline),
                      resources=dict(threads=2,duckdb_memory="2GB",spill_limit="8GB",wall_seconds=wall_seconds))
        deadline.check()
        report["status"]="PASS"
    except Exception as error:
        report["status"]="FAIL"
        report["error"]=dict(type=type(error).__name__)
        if isinstance(error,(ValueError,TimeoutError)):
            report["error"]["check"]=str(error)
        raise
    finally:
        if timer is not None:
            timer.cancel()
        if con is not None:
            con.close()
        report["elapsed_seconds"]=round(time.monotonic()-deadline.started,3)
        (output/"report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8",newline="\n")
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-lock",type=Path,required=True)
    parser.add_argument("--expected-lock-sha256",required=True)
    parser.add_argument("--collection",type=Path,required=True)
    parser.add_argument("--fits",type=Path,nargs=4,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--wall-seconds",type=float,default=1800)
    args=parser.parse_args(argv)
    try:
        report=audit(args.decision_lock,args.expected_lock_sha256,args.collection,args.fits,args.output,args.wall_seconds)
    except Exception as error:
        print(json.dumps(dict(status="FAIL",error_type=type(error).__name__)))
        return 1
    print(json.dumps(dict(status=report["status"],elapsed_seconds=report["elapsed_seconds"])))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
