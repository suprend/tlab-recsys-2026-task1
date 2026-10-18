"""Fixed contrasts of audited per-query AP; no models, scores or raw sources.

Model/seed AP values are averaged within each query BEFORE resampling users.
This is a mean of model metrics, not an ensemble of prediction scores.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import threading
import time

from scripts import hm_result_audit as audit_math

ROOT=Path(__file__).resolve().parents[1]
HEX=re.compile(r"[0-9a-f]{64}\Z")
ARM=re.compile(r"arm-[0-9]{2,}\Z")
FIELDS=("targets","candidate_count","covered","ap12")


def require(condition,message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,"Duplicate JSON property")
            result[key]=value
        return result
    def reject(value):
        raise ValueError("Nonfinite JSON constant")
    return json.loads(Path(path).read_text(encoding="utf-8"),object_pairs_hook=pairs,parse_constant=reject)


def digest(path,deadline):
    return audit_math.file_digest(Path(path),deadline)


def require_hash(value):
    require(isinstance(value,str) and bool(HEX.fullmatch(value)),"Expected full lowercase SHA256")
    return value


def parse_spec(spec):
    require(isinstance(spec,dict) and set(spec)=={"audit_report_sha256","contrasts"},"Spec requires audit_report_sha256 and contrasts only")
    require_hash(spec["audit_report_sha256"])
    contrasts=spec["contrasts"]
    require(isinstance(contrasts,list) and bool(contrasts),"Nonempty predeclared contrasts required")
    names=set()
    for contrast in contrasts:
        require(isinstance(contrast,dict) and set(contrast)=={"name","positive","negative"},"Unexpected contrast schema")
        name=contrast["name"]
        require(isinstance(name,str) and bool(name.strip()) and name not in names,"Unique nonempty contrast names required")
        names.add(name)
        for group in ("positive","negative"):
            identifiers=contrast[group]
            require(isinstance(identifiers,list) and bool(identifiers) and all(isinstance(a,str) for a in identifiers),"Each contrast group needs arm identifiers")
            require(len(set(identifiers))==len(identifiers),"Duplicate arm within contrast group")
            require(all(a in ("recency","popularity") or ARM.fullmatch(a) for a in identifiers),"Invalid arm identifier")
        require(not set(contrast["positive"]) & set(contrast["negative"]),"Positive and negative groups must be disjoint")
    return contrasts


def artifact_path(audit_dir,name):
    require(isinstance(name,str) and bool(name),"Private metrics filename required")
    path=Path(name)
    require(not path.is_absolute(),"Private metrics filename must be relative")
    result=(audit_dir/path).resolve()
    require(result.is_relative_to(audit_dir) and result!=audit_dir,"Private metrics path escapes audit directory")
    return result


def inventory(report):
    require(report.get("format")=="hm-independent-result-audit-v1" and report.get("status")=="PASS","Completed PASS independent audit required")
    collection=report["collection"]
    for field in ("qcy_identity","candidate_identity","manifest_sha256"):
        require_hash(collection[field])
    require_hash(report["checker_sha256"])
    arms={}
    require(isinstance(report["fits"],list) and bool(report["fits"]),"Audited fit arms required")
    for fit in report["fits"]:
        number=fit["arm"]
        require(type(number) is int and number>=0,"Nonnegative integer fit arm required")
        name=f"arm-{number:02d}"
        require(name not in arms,"Duplicate audited arm identifier")
        require_hash(fit["fit_identity"])
        require_hash(fit["report_sha256"])
        arms[name]=fit
    heuristics=report.get("heuristics",{})
    if heuristics.get("status")=="evaluated":
        for method in ("recency","popularity"):
            require(method in heuristics,"Evaluated heuristic inventory incomplete")
            arms[method]=heuristics[method]
    return arms


def read_queries(connection,path,deadline):
    cursor=connection.execute("SELECT customer_id,targets,candidate_count,covered,ap12 FROM read_parquet(?) ORDER BY customer_id",[str(path)])
    require(cursor.description[0][1]=="VARCHAR","Customer IDs must preserve VARCHAR values")
    result={}
    while rows:=cursor.fetchmany(8192):
        deadline.check()
        for user,targets,candidates,covered,ap in rows:
            require(isinstance(user,str) and user not in result,"Null or duplicate per-query customer ID")
            require(all(type(n) is int for n in (targets,candidates,covered)),"Query populations must be integer counts")
            require(targets>=0 and candidates>0 and 0<=covered<=min(targets,candidates),"Invalid query counts or coverage")
            require(isinstance(ap,(int,float)) and math.isfinite(ap) and 0<=ap<=1,"AP must be finite in [0,1]")
            require(targets>0 or ap==0,"Empty-target AP must be zero")
            ceiling=min(covered,12)/min(targets,12) if targets else 0
            require(ap<=ceiling+1e-12,"AP exceeds candidate oracle ceiling")
            result[user]=dict(targets=targets,candidate_count=candidates,covered=covered,ap12=float(ap))
    require(bool(result),"Nonempty per-query population required")
    return result


def validate_same_population(arms):
    reference=next(iter(arms.values()))
    for values in arms.values():
        require(set(reference)==set(values),"Contrast arms must have exact same customer IDs")
        require(all(tuple(reference[u][field] for field in FIELDS[:-1])==tuple(values[u][field] for field in FIELDS[:-1]) for u in reference),"Contrast arms must have identical targets, candidate counts and coverage")


def group_queries(names,arms):
    users=sorted(next(iter(arms.values())))
    return {user:dict(targets=arms[names[0]][user]["targets"],
        ap12=math.fsum(arms[name][user]["ap12"] for name in names)/len(names)) for user in users}


def compute_contrasts(contrasts,arms,deadline=None):
    validate_same_population(arms)
    require(all(name in arms for contrast in contrasts for group in ("positive","negative") for name in contrast[group]),"Spec references an unavailable audited arm")
    results=[]
    for contrast in contrasts:
        positive=group_queries(contrast["positive"],arms)
        negative=group_queries(contrast["negative"],arms)
        results.append(dict(name=contrast["name"],positive=contrast["positive"],negative=contrast["negative"],
            **audit_math.paired_bootstrap(negative,positive,deadline,draws=2000,seed=2026)))
    return results


def run(audit_dir,spec_path,output,wall_seconds=120):
    import duckdb
    deadline=audit_math.Deadline(wall_seconds)
    require(wall_seconds<=1800,"Wall limit must not exceed1800 seconds")
    audit_dir=Path(audit_dir).resolve();spec_path=Path(spec_path).resolve();output=Path(output).resolve()
    allowed=(ROOT/"artifacts").resolve()
    require(output!=allowed and output.is_relative_to(allowed),"New output must be inside checkout artifacts/")
    output.mkdir(parents=True,exist_ok=False)
    report=dict(format="hm-fixed-ap-contrasts-v1",status="running",
        interpretation="Per-query mean AP over models/seeds, then paired positive-user bootstrap; not a score ensemble or user-by-seed pooled sample",
        bootstrap=dict(draws=2000,seed=2026,unit="positive query",interval="percentile95"))
    connection=timer=None
    try:
        spec_sha=digest(spec_path,deadline);spec=read_json(spec_path);contrasts=parse_spec(spec)
        audit_path=audit_dir/"report.json"
        audit_sha=digest(audit_path,deadline)
        require(audit_sha==spec["audit_report_sha256"],"Audit report SHA256 differs from fixed spec")
        source=read_json(audit_path);available=inventory(source)
        requested=sorted({name for c in contrasts for group in ("positive","negative") for name in c[group]})
        require(set(requested)<=set(available),"Spec references an unavailable audited arm")
        connection=duckdb.connect(":memory:")
        connection.execute("SET threads=2");connection.execute("SET memory_limit='2GB'")
        timer=threading.Timer(max(0,deadline.expires-time.monotonic()),connection.interrupt)
        timer.daemon=True;timer.start()
        arms={};inputs={}
        for name in requested:
            artifact=available[name]["private_query_metrics"]
            path=artifact_path(audit_dir,artifact["file"])
            expected=require_hash(artifact["sha256"])
            require(digest(path,deadline)==expected,"Per-query metrics artifact SHA256 mismatch")
            arms[name]=read_queries(connection,path,deadline)
            inputs[name]=dict(file=artifact["file"],sha256=expected)
            if name.startswith("arm-"):
                inputs[name]["fit_identity"]=available[name]["fit_identity"]
        validate_same_population(arms)
        reference=next(iter(arms.values()));positive_users=[u for u in reference if reference[u]["targets"]>0]
        for name,values in arms.items():
            claimed=available[name]["metrics"]
            observed=math.fsum(values[u]["ap12"] for u in positive_users)/len(positive_users) if positive_users else None
            require(claimed["queries"]==len(values) and claimed["positive_queries"]==len(positive_users),"Audited aggregate population mismatch")
            require(audit_math.close(observed,claimed["map_at_12_conditional"]),"Audited aggregate AP mismatch")
        report.update(audit_report_sha256=audit_sha,spec_sha256=spec_sha,spec=spec,
            collection_provenance={key:source["collection"][key] for key in ("anchor","qcy_identity","candidate_identity","manifest_sha256")},
            checker_sha256=source["checker_sha256"],inputs=inputs,
            implementation_sha256=digest(Path(__file__),deadline),
            bootstrap_source_sha256=digest(Path(audit_math.__file__),deadline),
            queries=len(reference),positive_queries=len(positive_users),
            arm_mean_ap={name:{"conditional":math.fsum(v[u]["ap12"] for u in positive_users)/len(positive_users) if positive_users else None,
                               "all_query_empty_zero":math.fsum(row["ap12"] for row in v.values())/len(v)} for name,v in arms.items()},
            contrasts=compute_contrasts(contrasts,arms,deadline),
            resources=dict(threads=2,duckdb_memory="2GB",wall_seconds=wall_seconds))
        require(digest(audit_path,deadline)==audit_sha and digest(spec_path,deadline)==spec_sha,"Audit report or spec changed during analysis")
        for name,artifact in inputs.items():
            require(digest(artifact_path(audit_dir,artifact["file"]),deadline)==artifact["sha256"],"Per-query artifact changed during analysis")
        deadline.check();report["status"]="completed"
    except Exception as exc:
        report["status"]="failed";report["error"]={"type":type(exc).__name__,"check":str(exc) if isinstance(exc,(ValueError,TimeoutError)) else "Artifact processing failed"}
        raise
    finally:
        if timer is not None:timer.cancel()
        if connection is not None:connection.close()
        report["elapsed_seconds"]=round(time.monotonic()-deadline.started,3)
        (output/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n")
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir",required=True,type=Path)
    parser.add_argument("--spec",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--wall-seconds",type=float,default=120)
    args=parser.parse_args(argv)
    try:report=run(args.audit_dir,args.spec,args.output,args.wall_seconds)
    except Exception as exc:
        print(json.dumps({"status":"failed","error_type":type(exc).__name__}));return 1
    print(json.dumps({"status":report["status"],"output":args.output.resolve().as_posix()}));return 0


if __name__=="__main__":
    raise SystemExit(main())
