"""Read-only historical016 model-choice consumer; no target or model API.

The fixed external acceptance anchor is not regenerated or self-issued here.
Full pin streaming is paid work: call only inside a caller-owned guarded budget.
This is supplied-artifact replay authority, not a fresh-source bootstrap.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from scripts import heldout_contract as h

ROOT=Path(__file__).resolve().parents[1]
ACCEPTANCE_SHA256='7e6130ca15f5af8fccdb18849916896bd087ab37e03659afe078abe45bf83cbe'
RUN_ID='e1a63fa2c156d87b014b27b1d421bec5ebb35aefcde623f4c0c3d1ce2e636110'
SCOPE='reviewed_fixed_procedure_feature_program_models'
PROOFS=['docs/backlog-reviews/tlab016-feature-program-model-aggregate.json',
        'docs/backlog-reviews/tlab016-feature-program-model-verification.md',
        'docs/backlog-reviews/tlab016-feature-program-model-oracle.md']


def _local(name):
    h.ref(dict(path=name,sha256='0'*64))
    path=(ROOT/name).resolve();path.relative_to(ROOT.resolve());return path


def _read(path,check):
    check()
    with Path(path).open('rb') as f:raw=f.read(8*2**20+1)
    h.need(len(raw)<=8*2**20,'Bounded choice metadata exceeded')
    def unique(pairs):
        result={}
        for k,v in pairs:h.need(k not in result,'Duplicate choice JSON key');result[k]=v
        return result
    value=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite choice metadata')))
    check();return value,hashlib.sha256(raw).hexdigest()


def _read_ref(value,check,observed):
    h.ref(value);body,digest=_read(_local(value['path']),check)
    h.need(digest==value['sha256'],'Choice metadata differs from bound reference')
    h.need(value['path'] not in observed or observed[value['path']]==digest,'Choice snapshot changed')
    observed[value['path']]=digest;return body


def _merge(*mappings):
    result={}
    for mapping in mappings:
        h.need(type(mapping) is dict,'Exact pin map required')
        for name,digest in mapping.items():
            h.ref(dict(path=name,sha256=digest));h.need(name not in result or result[name]==digest,'Conflicting choice pin');result[name]=digest
    return result


def _pins(mapping,check):
    for name,digest in mapping.items():
        check();value=hashlib.sha256()
        with _local(name).open('rb') as f:
            while part:=f.read(4*2**20):check();value.update(part)
        h.need(value.hexdigest()==digest,'Choice input/output/authority changed');check()


def _markers(directory,report):
    for name in ['report.failed.json','observer/evidence.failed.json','observer/oracle.log.cleanup-failed.json']:
        h.need(not (directory/name).exists(),'Known failed model/observer cannot supply frozen W')
    for child in report['children']:
        worker=_local(child['report']['path']).parent
        h.need(not (worker/'report.failed.json').exists() and not (directory/'logs'/(child['worker_report']['candidate_id']+'.log.cleanup-failed.json')).exists(),
               'Known failed successful worker/cleanup cannot supply frozen choice')


def verify_choice(acceptance_path,*,check=lambda:None):
    """Authenticate exact438 closure plus acceptance, return B/W-only snapshot.

    No raw formulas, native training weights, fits, model predictions, private Y
    or bootstrap are recalculated. Historical failed source status stays failed.
    The caller must separately pin this consumer/code in its new measured plan.
    """
    path=Path(acceptance_path).resolve();path.relative_to(ROOT.resolve());name=path.relative_to(ROOT.resolve()).as_posix()
    a,actual=_read(path,check);h.need(actual==ACCEPTANCE_SHA256,'External438 acceptance anchor differs')
    h.keys(a,{'version','approved','scope','run_id','fingerprints','selected_spec','external_lifetime','external_admission','proof_limits','heldout_targets_opened','source_failed_invocation_preserved'},'model acceptance')
    h.need(type(a['version']) is int and a['version']==1 and a['approved'] is True and a['scope']==SCOPE and a['run_id']==RUN_ID,'Accepted model scope/identity differs')
    h.need(a['heldout_targets_opened'] is False and a['source_failed_invocation_preserved'] is True,'Historical/heldout boundary differs')
    pins=a['fingerprints'];h.need(type(pins) is dict and len(pins)==438,'Exact complete historical model closure required')
    observed={name:actual};life=_read_ref(a['external_lifetime'],check,observed);admission=_read_ref(a['external_admission'],check,observed)
    report=_read_ref(life['owner_report'],check,observed);directory=_local(life['owner_report']['path']).parent
    d=directory.relative_to(ROOT.resolve()).as_posix()
    def bound(suffix):
        key=d+'/'+suffix;h.need(key in pins,'Mandatory model receipt pin absent');return _read_ref(dict(path=key,sha256=pins[key]),check,observed)
    manifest=bound('run.json');producer=bound('producer-report.json');proposal=bound('proposal.json');winner=bound('winner.json')
    identity=manifest['identity'];observer=_read_ref(report['observer']['evidence'],check,observed)
    h.need(h.digest(identity)==RUN_ID==manifest['run_id']==producer['run_id']==report['run_id']==observer['run_id'],'Bound model identity differs')
    h.need(identity==proposal['identity'] and proposal['run_id']==RUN_ID,'Original proposal detached')
    h.need(report['status']=='model_outputs_verified_pending_external_acceptance' and report['fit_attempt_count']==producer['fit_attempt_count']==4
           and report['sum_metric_looks']==producer['sum_metric_looks']==4 and report['observer_calls']==1,'Original4fits/4looks/1observer differs')
    for value in [report,producer]:
        h.need(value['active_slot'] is None and value['unknown_live_fit'] is False and value['unknown_metric_looks'] is False and value['heldout_labels_opened'] is False,'Unknown counts or heldout access')
    h.need(observer['status']=='verified' and observer['fit_attempt_count']==observer['observer_refits']==observer['source_regenerations']==0
           and observer['checked_slots']==['I1','I2','R1','R2'],'Successful zero-fit original observer required')
    # Semantically reviewed output evidence is externally anchored; exact refs
    # and saved-array replay are not reissued by fresh hashes in this consumer.
    h.need(winner==producer['winner']==report['winner'],'Producer winner receipt differs')
    h.need(winner['candidate_id']==a['selected_spec']['candidate_id']=='R2' and identity['slots']['R2']['bundle_id']=='L05','Accepted choice differs')
    h.need(len(identity['fingerprints'])==374 and len(manifest['outputs'])==46 and len(report['observer']['authority_pins'])==12,'Mandatory historical input/output authority sets differ')
    extras=[d+'/'+n for n in ['proposal.json','run.json','report.json','producer-report.json','winner.json','external-time.log','external-lifetime.json','external-admission.json']]+PROOFS
    h.need(all(k in pins for k in extras),'Model proof/lifetime pin omitted')
    expected=_merge(identity['fingerprints'],manifest['outputs'],report['observer']['authority_pins'],{k:pins[k] for k in extras})
    h.need(expected==pins,'Acceptance has missing or extra historical closure')
    h.need(life['explicitly_reaped_exit_code']==0 and life['production_and_oracle_cpu_upper_seconds']==1694.75
           and life['charged_owner_wall_upper_seconds']==882.31 and life['conservative_job_peak_rss_bytes']<8*2**30,'Reaped full-lifetime gate differs')
    h.need(admission['total_study_with_admission_cpu_upper_seconds']==1704.75 and admission['refits']==admission['oracle_retries']==0,'Paid external admission differs')
    _markers(directory,report)
    spec=a['selected_spec'];h.need(spec['population']==26000 and spec['trained_iterations']==spec['scoring_prefix']==300
           and spec['depth']==6 and spec['l2_leaf_reg']==30,'Inherited B procedure differs')
    base=dict(model=dict(path=identity['baseline']['model_path'],sha256=pins[identity['baseline']['model_path']]),
              feature_names=identity['feature_names'],trained_iterations=300,scoring_prefix=300,population=26000,effective_parameters=identity['native_reference'])
    chosen=dict(model=spec['model'],feature_names=spec['feature_names'],trained_iterations=300,scoring_prefix=300,population=26000,effective_parameters=spec['native_effective_parameters'])
    h.need(chosen['model']['path']==winner['model_path'] and chosen['model']['sha256']==pins[winner['model_path']], 'Chosen CBM detached')
    h.need(chosen['feature_names']==winner['feature_names']==identity['slots']['R2']['feature_names'] and chosen['feature_names'][:41]==base['feature_names'],'Chosen exact3 order differs')
    h.need(spec['physical_delta']==identity['slots']['R2']['physical_delta'] and len(spec['physical_delta'])==3,'Chosen physical closure differs')
    h.model(base);h.model(chosen);h.need(h.canonical(base['effective_parameters'])==h.canonical(chosen['effective_parameters']),'Matched native effective parameters differ')
    def pinned_ref(key):h.need(key in pins,'Choice authority pin absent');return dict(path=key,sha256=pins[key])
    authority=dict(control=pinned_ref(identity['control_acceptance']),automation=dict(path=name,sha256=actual),
        source=pinned_ref(identity['source_acceptance']),selector=pinned_ref(identity['selector_path']),pool=pinned_ref('configs/features/automation-pool.json'))
    choice=dict(candidate_id='R2',models=dict(B=base,W=chosen),authority_refs=authority)
    for value in observed.values():h.need(type(value) is str,'Bound snapshots required')
    _pins(pins,check);_pins(observed,check);_markers(directory,report);check()
    return dict(authenticated_choice=deepcopy(choice),pins=_merge(pins,observed),acceptance=dict(path=name,sha256=actual),
                manifest=deepcopy(manifest),report=deepcopy(report),external_lifetime=deepcopy(life),external_admission=deepcopy(admission),
                selected_spec=deepcopy(spec),proof_limits=a['proof_limits'],source_formula_replay=False,model_prediction_replay=False)
