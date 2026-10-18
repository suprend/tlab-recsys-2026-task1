"""Exploratory, no-fit H&M retrieval diagnosis on September 2 only.

Input is the local hm_eda typed DuckDB. All writes are temporary relations or
a new local output directory. Labels end September 9; no validation/final read.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import sys
import time

POLICIES = ("C0", "C0-Q120", "C1-Q120")
LATEST_ANCHOR = date(2020, 9, 2)
LATEST_HISTORY_ANCHOR = date(2020, 9, 16)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8*1024*1024),b""):
            digest.update(block)
    return digest.hexdigest()


def create_candidates(connection, anchor, user_limit, seed=2026):
    """Return a lazy relation of candidates, ranks and source attribution.

    Q120 policies use global refill across the observed90d catalog, with zero
    buyers7d allowed, to make their size exactly120. C0 preserves the pilot's
    top100 actually bought7d union recent20. Sibling/type sources deduplicate
    and exclude all user90d purchases and earlier candidates before quotas.
    """
    cutoff = date.fromisoformat(anchor) if isinstance(anchor,str) else anchor
    if cutoff > LATEST_HISTORY_ANCHOR:
        raise ValueError("History builder cannot read anchors after 2020-09-16")
    if user_limit < 1:
        raise ValueError("user_limit must be positive")
    anchor = cutoff.isoformat()
    for name in ("context","history","users","items","recent","sibling","preferred","type_candidates","initial","candidates"):
        connection.execute(f"DROP TABLE IF EXISTS temp.hm_r_{name}")
    connection.execute("CREATE TEMP TABLE hm_r_context AS SELECT ?::DATE anchor",[anchor])
    connection.execute("""CREATE TEMP TABLE hm_r_history AS
        SELECT * FROM transactions WHERE t_dat >= ?::DATE-INTERVAL '90 days' AND t_dat < ?::DATE
    """,[anchor,anchor])
    connection.execute("""CREATE TEMP TABLE hm_r_users AS
        SELECT DISTINCT customer_id FROM hm_r_history
        ORDER BY sha256(customer_id || ':' || ?),customer_id LIMIT ?
    """,[str(seed),user_limit])
    if connection.execute("SELECT count(*)-count(DISTINCT article_id) FROM articles").fetchone()[0]:
        raise ValueError("Duplicate article metadata IDs")
    connection.execute(f"""CREATE TEMP TABLE hm_r_items AS
        WITH counts AS (
          SELECT article_id,count(DISTINCT customer_id) FILTER(
            WHERE t_dat >= DATE '{anchor}'-INTERVAL '7 days') buyers7
          FROM hm_r_history GROUP BY article_id
        ) SELECT c.*,a.product_code,a.product_type_no,
          row_number() OVER(ORDER BY buyers7 DESC,c.article_id) global_rank
          FROM counts c LEFT JOIN articles a USING(article_id)
    """)
    if connection.execute("SELECT count(*) FROM hm_r_items").fetchone()[0] < 120:
        raise ValueError("Observed90d catalog has fewer than120 articles")
    connection.execute("""CREATE TEMP TABLE hm_r_recent AS
        SELECT customer_id,article_id,source_rank FROM (
          SELECT h.customer_id,h.article_id,row_number() OVER(
            PARTITION BY h.customer_id ORDER BY max(t_dat) DESC,h.article_id) source_rank
          FROM hm_r_history h JOIN hm_r_users USING(customer_id)
          GROUP BY h.customer_id,h.article_id) WHERE source_rank<=20
    """)
    # A user may have bought many older siblings. The bounded per-product
    # list therefore allows all observed purchases plus20 novel candidates.
    # Deduplication by candidate occurs BEFORE the20-sibling quota.
    connection.execute("""CREATE TEMP TABLE hm_r_sibling AS
      WITH seen_per_user AS (
        SELECT h.customer_id,i.product_code,count(DISTINCT h.article_id) n
        FROM hm_r_history h JOIN hm_r_users USING(customer_id)
        JOIN hm_r_items i USING(article_id) GROUP BY h.customer_id,i.product_code
      ), bounds AS (SELECT product_code,max(n) max_seen FROM seen_per_user GROUP BY product_code),
      pruned AS (
        SELECT i.* FROM hm_r_items i LEFT JOIN bounds b USING(product_code)
        WHERE i.product_code IS NOT NULL AND trim(i.product_code)<>''
        QUALIFY row_number() OVER(PARTITION BY i.product_code ORDER BY buyers7 DESC,i.article_id)<=20+coalesce(b.max_seen,0)
      ), joined AS (
        SELECT r.customer_id,i.article_id,i.buyers7,min(r.source_rank) seed_rank
        FROM hm_r_recent r JOIN hm_r_items seed USING(article_id)
        JOIN pruned i ON seed.product_code=i.product_code
        WHERE NOT EXISTS(SELECT 1 FROM hm_r_recent earlier
          WHERE earlier.customer_id=r.customer_id AND earlier.article_id=i.article_id)
        AND NOT EXISTS(SELECT 1 FROM hm_r_history old
          WHERE old.customer_id=r.customer_id AND old.article_id=i.article_id)
        GROUP BY r.customer_id,i.article_id,i.buyers7
      ) SELECT customer_id,article_id,seed_rank,row_number() OVER(
        PARTITION BY customer_id ORDER BY seed_rank,buyers7 DESC,article_id) source_rank
      FROM joined QUALIFY source_rank<=20
    """)
    connection.execute("""CREATE TEMP TABLE hm_r_preferred AS
        SELECT h.customer_id,a.product_type_no,count(*) tx90,
          row_number() OVER(PARTITION BY h.customer_id
            ORDER BY count(*) DESC,a.product_type_no) preference_rank
        FROM hm_r_history h JOIN hm_r_users USING(customer_id)
        JOIN articles a USING(article_id) WHERE a.product_type_no IS NOT NULL
          AND trim(a.product_type_no)<>'' AND trim(a.product_type_no)<>'-1'
          AND (a.product_type_name IS NULL OR lower(trim(a.product_type_name))<>'unknown')
        GROUP BY h.customer_id,a.product_type_no QUALIFY preference_rank<=2
    """)
    # For each preferred type retain20 after removing all observed purchases
    # and at most20 novel sibling candidates. No borrowing between types.
    connection.execute("""CREATE TEMP TABLE hm_r_type_candidates AS
      WITH seen_per_user AS (
        SELECT h.customer_id,i.product_type_no,count(DISTINCT h.article_id) n
        FROM hm_r_history h JOIN hm_r_users USING(customer_id)
        JOIN hm_r_items i USING(article_id) GROUP BY h.customer_id,i.product_type_no
      ), bounds AS (SELECT product_type_no,max(n) max_seen FROM seen_per_user GROUP BY product_type_no),
      pruned AS (
        SELECT i.* FROM hm_r_items i LEFT JOIN bounds b USING(product_type_no)
        WHERE i.product_type_no IS NOT NULL AND trim(i.product_type_no)<>'' AND trim(i.product_type_no)<>'-1'
        QUALIFY row_number() OVER(PARTITION BY i.product_type_no ORDER BY buyers7 DESC,i.article_id)<=40+coalesce(b.max_seen,0)
      ), joined AS (
        SELECT p.customer_id,i.article_id,i.buyers7,p.preference_rank FROM hm_r_preferred p
        JOIN pruned i USING(product_type_no)
        WHERE NOT EXISTS(SELECT 1 FROM hm_r_recent r
          WHERE r.customer_id=p.customer_id AND r.article_id=i.article_id)
        AND NOT EXISTS(SELECT 1 FROM hm_r_sibling s
          WHERE s.customer_id=p.customer_id AND s.article_id=i.article_id)
        AND NOT EXISTS(SELECT 1 FROM hm_r_history old
          WHERE old.customer_id=p.customer_id AND old.article_id=i.article_id)
      ), per_type AS (
        SELECT *,row_number() OVER(PARTITION BY customer_id,preference_rank ORDER BY buyers7 DESC,article_id) type_rank
        FROM joined QUALIFY type_rank<=20
      ) SELECT customer_id,article_id,preference_rank,type_rank,row_number() OVER(
        PARTITION BY customer_id ORDER BY preference_rank,type_rank,article_id) source_rank FROM per_type
    """)
    connection.execute("""CREATE TEMP TABLE hm_r_initial AS
      SELECT p.policy,r.customer_id,r.article_id,'recent' AS source,r.source_rank,1 priority
      FROM hm_r_recent r CROSS JOIN (VALUES ('C0'),('C0-Q120'),('C1-Q120')) p(policy)
      UNION ALL SELECT 'C1-Q120',customer_id,article_id,'sibling',source_rank,2 FROM hm_r_sibling
      UNION ALL SELECT 'C1-Q120',customer_id,article_id,'type',source_rank,3 FROM hm_r_type_candidates
    """)
    connection.execute("""CREATE TEMP TABLE hm_r_candidates AS
      WITH global_pool AS (
        SELECT * FROM hm_r_items WHERE global_rank<=200
      ), global_unseen AS (
        SELECT p.policy,u.customer_id,g.article_id,'global' AS source,g.global_rank source_rank,4 priority,
          row_number() OVER(PARTITION BY p.policy,u.customer_id ORDER BY g.global_rank) refill_rank
        FROM hm_r_users u CROSS JOIN (VALUES ('C0'),('C0-Q120'),('C1-Q120')) p(policy)
        CROSS JOIN global_pool g
        WHERE (p.policy<>'C0' OR (g.global_rank<=100 AND g.buyers7>0))
        AND NOT EXISTS(SELECT 1 FROM hm_r_initial i WHERE i.policy=p.policy
          AND i.customer_id=u.customer_id AND i.article_id=g.article_id)
      ), selected AS (
        SELECT * FROM hm_r_initial UNION ALL
        SELECT g.policy,g.customer_id,g.article_id,g.source,g.source_rank,g.priority FROM global_unseen g
        WHERE g.policy='C0' OR g.refill_rank<=120-(SELECT count(*) FROM hm_r_initial i
          WHERE i.policy=g.policy AND i.customer_id=g.customer_id)
      ), ranked AS (
        SELECT policy,customer_id,article_id,source,source_rank,
          row_number() OVER(PARTITION BY policy,customer_id ORDER BY priority,source_rank,article_id) candidate_rank
        FROM selected)
      SELECT r.*,s.seed_rank,p.preference_rank preferred_type_rank,p.type_rank
      FROM ranked r
      LEFT JOIN (SELECT *, 'sibling' AS source FROM hm_r_sibling) s
        ON r.source=s.source AND r.customer_id=s.customer_id AND r.article_id=s.article_id
      LEFT JOIN (SELECT *, 'type' AS source FROM hm_r_type_candidates) p
        ON r.source=p.source AND r.customer_id=p.customer_id AND r.article_id=p.article_id
    """)
    invalid = connection.execute("""SELECT count(*) FROM (
        SELECT policy,customer_id,count(*) n,count(DISTINCT article_id) unique_n
        FROM hm_r_candidates GROUP BY policy,customer_id)
        WHERE n<>unique_n OR (policy<>'C0' AND n<>120) OR (policy='C0' AND n>120)
    """).fetchone()[0]
    if invalid:
        raise RuntimeError("Candidate deduplication/size invariant failed")
    return connection.sql("SELECT * FROM hm_r_candidates ORDER BY policy,customer_id,candidate_rank")


def collect_diagnostics(connection,anchor):
    """Aggregate metrics plus a temporary paired-user table; fullY never truncated."""
    cutoff = date.fromisoformat(anchor)
    if cutoff > LATEST_ANCHOR:
        raise ValueError("Anchor after development diagnostic boundary")
    built_anchor=connection.execute("SELECT anchor FROM hm_r_context").fetchone()[0]
    if built_anchor!=cutoff:
        raise ValueError("Diagnostic anchor differs from built history/candidates")
    connection.execute("DROP TABLE IF EXISTS temp.hm_r_targets")
    connection.execute("""CREATE TEMP TABLE hm_r_targets AS
      SELECT DISTINCT t.customer_id,t.article_id,
        EXISTS(SELECT 1 FROM hm_r_history h WHERE h.customer_id=t.customer_id
          AND h.article_id=t.article_id) repeat90
      FROM transactions t JOIN hm_r_users USING(customer_id)
      WHERE t.t_dat>=?::DATE AND t.t_dat<?::DATE+INTERVAL '7 days'
    """,[anchor,anchor])
    connection.execute("DROP TABLE IF EXISTS temp.hm_r_paired")
    connection.execute("""CREATE TEMP TABLE hm_r_paired AS
      WITH q AS (SELECT u.customer_id,p.policy FROM hm_r_users u CROSS JOIN
          (VALUES ('C0'),('C0-Q120'),('C1-Q120')) p(policy)), counts AS (
        SELECT q.policy,q.customer_id,count(t.article_id) targets,
          count(t.article_id) FILTER(WHERE c.article_id IS NOT NULL) covered,
          count(t.article_id) FILTER(WHERE t.repeat90) repeat_targets,
          count(t.article_id) FILTER(WHERE t.repeat90 AND c.article_id IS NOT NULL) repeat_covered,
          count(t.article_id) FILTER(WHERE NOT t.repeat90) new90_targets,
          count(t.article_id) FILTER(WHERE NOT t.repeat90 AND c.article_id IS NOT NULL) new90_covered
        FROM q LEFT JOIN hm_r_targets t USING(customer_id)
        LEFT JOIN hm_r_candidates c ON c.policy=q.policy AND c.customer_id=q.customer_id AND c.article_id=t.article_id
        GROUP BY q.policy,q.customer_id)
      SELECT *,CASE WHEN targets>0 THEN least(covered,12)::DOUBLE/least(targets,12) ELSE 0 END oracle_ap12,
        CASE WHEN targets>0 THEN covered::DOUBLE/targets ELSE 0 END target_coverage,
        (covered>0)::INTEGER any_covered FROM counts
    """)
    def records(sql):
        cursor=connection.execute(sql)
        columns=[d[0] for d in cursor.description]
        return [dict(zip(columns,row)) for row in cursor.fetchall()]
    summary = records("""SELECT policy,count(*) queries,count(*) FILTER(WHERE targets>0) positive_queries,
       count(*) FILTER(WHERE targets=0) empty_target_queries,sum(targets) target_pairs,
       avg(oracle_ap12) FILTER(WHERE targets>0) oracle_ap12_conditional,
       avg(oracle_ap12) oracle_ap12_all_queries_empty_zero,
       avg(target_coverage) FILTER(WHERE targets>0) target_coverage_macro_conditional,
       sum(covered)::DOUBLE/nullif(sum(targets),0) target_coverage_micro,
       avg(any_covered) FILTER(WHERE targets>0) query_coverage_conditional,
       sum(repeat_targets) repeat90_target_pairs,sum(repeat_covered)::DOUBLE/nullif(sum(repeat_targets),0) repeat90_target_coverage_micro,
       sum(new90_targets) new_to_observed90d_target_pairs,
       sum(new90_covered)::DOUBLE/nullif(sum(new90_targets),0) new_to_observed90d_target_coverage_micro
       FROM hm_r_paired GROUP BY policy ORDER BY policy""")
    sizes = records("""SELECT policy,min(n) min_candidates,max(n) max_candidates,avg(n) mean_candidates,
       sum(n) candidate_rows FROM (SELECT policy,customer_id,count(*) n FROM hm_r_candidates
       GROUP BY policy,customer_id) GROUP BY policy ORDER BY policy""")
    sources = records("""SELECT policy,source,count(*) AS rows,count(DISTINCT customer_id) users,
       max(source_rank) max_source_rank FROM hm_r_candidates GROUP BY policy,source ORDER BY policy,source""")
    overlap = records("""WITH sizes AS (SELECT policy,customer_id,count(*) n FROM hm_r_candidates GROUP BY policy,customer_id),
      pairs AS (SELECT a.policy left_policy,b.policy right_policy,a.customer_id,a.n left_n,b.n right_n
        FROM sizes a JOIN sizes b USING(customer_id) WHERE a.policy<b.policy),
      ints AS (SELECT a.policy left_policy,b.policy right_policy,a.customer_id,count(*) intersection_n
        FROM hm_r_candidates a JOIN hm_r_candidates b USING(customer_id,article_id)
        WHERE a.policy<b.policy GROUP BY a.policy,b.policy,a.customer_id)
      SELECT p.left_policy,p.right_policy,avg(coalesce(i.intersection_n,0)) mean_intersection,
        avg(coalesce(i.intersection_n,0)::DOUBLE/(p.left_n+p.right_n-coalesce(i.intersection_n,0))) mean_jaccard,
        avg(p.left_n-coalesce(i.intersection_n,0)) mean_left_only,
        avg(p.right_n-coalesce(i.intersection_n,0)) mean_right_only
      FROM pairs p LEFT JOIN ints i USING(left_policy,right_policy,customer_id)
      GROUP BY p.left_policy,p.right_policy ORDER BY p.left_policy,p.right_policy""")
    type_quotas=records("""SELECT policy,preferred_type_rank,sum(n) AS rows,
      max(n) max_per_query FROM (SELECT policy,preferred_type_rank,customer_id,count(*) n
      FROM hm_r_candidates WHERE source='type' GROUP BY policy,preferred_type_rank,customer_id)
      GROUP BY policy,preferred_type_rank ORDER BY policy,preferred_type_rank""")
    # One paired resampling unit is a complete positive query. The comparison
    # was declared before observing outcomes; no policy/model selection here.
    import numpy as np
    deltas=np.asarray([row[0] for row in connection.execute("""
      SELECT c1.oracle_ap12-c0.oracle_ap12 FROM hm_r_paired c1 JOIN hm_r_paired c0 USING(customer_id)
      WHERE c1.policy='C1-Q120' AND c0.policy='C0-Q120' AND c1.targets>0 ORDER BY c1.customer_id
    """).fetchall()],dtype=float)
    bootstrap={"comparison":"C1-Q120 minus C0-Q120", "metric":"oracle_ap12_conditional",
               "unit":"positive query","draws":2000,"seed":2026,"queries":len(deltas),
               "mean_delta":float(deltas.mean()) if len(deltas) else None,"percentile_95":None,
               "interpretation":"exploratory descriptive interval; no significance claim"}
    if len(deltas):
        rng=np.random.default_rng(2026)
        means=[]
        for _ in range(20):
            means.extend(deltas[rng.integers(0,len(deltas),size=(100,len(deltas)))].mean(axis=1))
        bootstrap["percentile_95"]=[float(x) for x in np.quantile(means,[0.025,0.975])]
    return dict(metrics=summary,candidate_sizes=sizes,source_attribution=sources,type_quotas=type_quotas,
        overlap=overlap,primary_paired_bootstrap=bootstrap,
        eligible_users=connection.execute("SELECT count(DISTINCT customer_id) FROM hm_r_history").fetchone()[0],
        selected_users=connection.execute("SELECT count(*) FROM hm_r_users").fetchone()[0],
        catalog90d=connection.execute("SELECT count(*) FROM hm_r_items").fetchone()[0])


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--anchor",default="2020-09-02")
    parser.add_argument("--users",type=int,default=20000)
    parser.add_argument("--wall-seconds",type=int,default=1800)
    args=parser.parse_args(argv)
    if args.anchor!="2020-09-02":
        parser.error("CLI diagnostic is predeclared for September2 only")
    if min(args.users,args.wall_seconds)<1:
        parser.error("Positive users/wall limits required")
    args.output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic()
    report=dict(status="running",anchor=args.anchor,horizon_days=7,requested_users=args.users,seed=2026,
        purpose="Exploratory candidate-retrieval diagnosis, no model fit or significance claim",
        protocol={
          "history":"[anchor-90d,anchor)","Q":"historyeligible SHA256(customer_id + ':2026') ascending, ID tie",
          "C0":"pilot global100 bought7d UNION recent20; recent attribution precedes global",
          "C0-Q120":"recent20 then global refill120",
          "C1-Q120":"recent20; up to20 novel90 product_code siblings by earliest seed rank,buyers7 DESC,ID; up to20 novel90 from EACH top2 preferred types by tx90, no borrowing; global refill120",
          "unseen":"sibling/type exclude all user prior90d purchases and all earlier-source candidates; global refill may repeat",
          "preferred_type_ties":"tx90 DESC then complete product_type_no string ASC",
          "type_candidate_ties":"within each type buyers7 DESC, article ID ASC; source presentation preference rank then type rank",
          "invalid_metadata":"product_code nonNULL/nonempty; preferred types nonNULL/nonempty/not '-1', name not trim/casefold Unknown",
          "prune_bound":"perproduct20+max cohort-user distinct past product purchases; pertype40+max cohort-user distinct past type purchases",
          "global_refill":"90d observed catalog sorted buyers7 DESC,ID ASC, including zero7buyers; pool200",
          "source_quota":"deduplicate then anti-join preceding sources before cap",
          "repeat_definition":"seen in observed prior90d; new90 does not mean lifetime new",
          "article_metadata":"static snapshot assumption; no mutable customer metadata",
          "oracle":"min(coveredY,12)/min(fullY,12), conditional positive queries; all-query empty-zero also",
        },caveats=["No ranking fit, validation or final evaluation; candidate ordering is a retrieval policy, not model quality.",
                  "Single cohort and week; descriptive paired differences do not establish significance.",
                  "Fixed Q120 makes candidate count comparable; source composition still differs.",
                  "Phase wall checks do not interrupt a running SQL statement; use external timeout."])
    con=None
    def save():
        (args.output/"report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8",newline="\n")
        (args.output/"report.md").write_text("# H&M retrieval diagnostic\n\nStatus: **"+report["status"]+"**\n\n```json\n"+json.dumps(report,indent=2,ensure_ascii=False)+"\n```\n",encoding="utf-8",newline="\n")
    def phase(name):
        report["phase"]=name
        if time.monotonic()-started>args.wall_seconds:
            raise TimeoutError("Declared wall limit exceeded")
        save()
    try:
        import duckdb
        phase("source_identity")
        report["source"]=dict(database=args.database.resolve().as_posix(),sha256=file_sha256(args.database),bytes=args.database.stat().st_size)
        report["runtime"]=dict(python=sys.version,platform=platform.platform(),duckdb=importlib.metadata.version("duckdb"),script_sha256=file_sha256(Path(__file__)),wall_seconds=args.wall_seconds,threads=2,memory_limit="4GB")
        phase("candidates")
        if shutil.disk_usage(args.output).free < 10*1024**3:
            raise OSError("Need at least10GiB free for8GB spill plus outputs/reserve")
        con=duckdb.connect(str(args.database.resolve()),read_only=True)
        con.execute("SET threads=2")
        con.execute("SET memory_limit='4GB'")
        con.execute("SET temp_directory = ?", [str((args.output/"sql-temp").resolve())])
        con.execute("SET max_temp_directory_size='8GB'")
        report["runtime"].update(spill_limit="8GB",minimum_free_disk_gib=10,
                                 temp_directory=(args.output/"sql-temp").resolve().as_posix())
        create_candidates(con,args.anchor,args.users)
        phase("coverage_diagnostics")
        report["diagnostics"]=collect_diagnostics(con,args.anchor)
        phase("private_paired_arrays")
        # IDs and paired per-user arrays stay in this ignored, local output.
        con.sql("SELECT * FROM hm_r_paired ORDER BY customer_id,policy").write_parquet(str(args.output/"paired-user-coverage.parquet"))
        con.sql("SELECT * FROM hm_r_candidates ORDER BY policy,customer_id,candidate_rank").write_parquet(str(args.output/"private-candidate-sources.parquet"))
        phase("derived_identities")
        cohort_digest=hashlib.sha256()
        for (customer,) in con.execute("SELECT customer_id FROM hm_r_users ORDER BY customer_id").fetchall():
            cohort_digest.update((customer+"\n").encode("utf-8"))
        candidate_digests={policy:hashlib.sha256() for policy in POLICIES}
        cursor=con.execute("SELECT policy,customer_id,article_id FROM hm_r_candidates ORDER BY policy,customer_id,article_id")
        while rows:=cursor.fetchmany(10000):
            for policy,customer,article in rows:
                candidate_digests[policy].update((customer+"\t"+article+"\n").encode("utf-8"))
            if time.monotonic()-started>args.wall_seconds:
                raise TimeoutError("Declared wall limit exceeded during identity hashing")
        report["derived_identity"]={
            "cohort_sha256":cohort_digest.hexdigest(),
            "cohort_serialization":"customer_id ASC, UTF8 ID + LF",
            "candidate_sha256":{policy:digest.hexdigest() for policy,digest in candidate_digests.items()},
            "candidate_serialization":"per policy customer_id/article_id ASC, UTF8 customer TAB article LF",
            "artifacts":{name:{"bytes":(args.output/name).stat().st_size,"sha256":file_sha256(args.output/name)}
                         for name in ("paired-user-coverage.parquet","private-candidate-sources.parquet")},
        }
        phase("complete")
        report["status"]="completed"
    except Exception as exc:
        report["status"]="failed"
        report["error"]={"type":type(exc).__name__,"message":str(exc)}
    finally:
        if con is not None:
            con.close()
        report["elapsed_seconds"]=round(time.monotonic()-started,3)
        save()
    print(json.dumps({"status":report["status"],"report":(args.output/"report.json").resolve().as_posix()}))
    return 0 if report["status"]=="completed" else 1


if __name__=="__main__":
    raise SystemExit(main())
