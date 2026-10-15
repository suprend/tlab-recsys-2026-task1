"""Exactly one fixed6000-Q metadata/price Logloss50 development ablation.

External source acceptances and exact executionapproval are required. The
global experiment claim is consumed before matrix/Pool preparation, even if
that preparation fails. Frozen008 control is never refitted here.
"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np

from scripts import metadata_price_collection as c
from scripts import metadata_price_features as m
from scripts import model_data as d
from scripts import train_baselines as b
from scripts.protocol_manifest import _read_json,_keys,_hashes,canonical_json,sha256_file
from scripts.ranking_metrics import evaluate,paired_user_bootstrap

ROOT=Path(__file__).resolve().parents[1]
ROLE='metadata_price_single_ablation'
LIMITS=dict(wall_seconds=1200,max_process_cpu_seconds=900,rss_bytes=8*2**30,threads=2,allowed_fit_attempts=1)
PROOFS=('docs/backlog-reviews/tlab008-smoke-output-verification.md',
        'docs/backlog-reviews/tlab008-smoke-aggregate.json','docs/backlog-reviews/tlab008-output-oracle.md')
CODE=(*c.CODE,'scripts/model_data.py','scripts/metadata_ablation.py','scripts/ranking_metrics.py')
CLAIM='artifacts/fit-claims/tlab009-single-ablation.json'
RECALL_FLOOR=.5792133072407045
NDCG_FLOOR=.41444755081727774
NDCG_TOLERANCE=1e-12


def failure_decision(error):
    if isinstance(error,(TimeoutError,MemoryError)):
        return dict(retain_metadata_block=False,feature_choice='base41',reason='resource_failed_single_attempt_no_replacement')
    return dict(retain_metadata_block=False,feature_choice='stop_for_integrity_or_API_review_no_replacement')


class AblationAudit(c.ExecutionAudit):
    """Local failure policy also covers the shared audit's terminal writes.

    The accepted full-export audit is immutable. Failed persistence below is
    best effort; its small tail is measured by the external parent ledger.
    """
    def __exit__(self,kind,error,traceback):
        if error is not None:self.report['decision']=failure_decision(error)
        try:return super().__exit__(kind,error,traceback)
        except BaseException as terminal:
            self.report.update(status='failed',decision=failure_decision(terminal),
                terminal_decision_receipt_tail='best_effort_local_failure_persistence_charged_to_parent_process_ledger')
            paths=[self.directory/'report.json']
            marker=self.directory/'report.failed.json'
            if marker.exists():paths.append(marker)
            for path in paths:
                try:c._atomic_json(path,self.report)
                except Exception as secondary:
                    self.report.setdefault('secondary_errors',[]).append(dict(stage='ablation_terminal_policy_persistence',
                        error_type=type(secondary).__name__,error=str(secondary)))
                    try:marker.write_text(canonical_json(self.report)+'\n')
                    except Exception as final:
                        self.report['secondary_errors'].append(dict(stage='ablation_terminal_policy_fallback',
                            error_type=type(final).__name__,error=str(final)))
            raise # Keep the first terminal exception and consumed claim.


def verify_control(path,config_path,train_path,selection_path,*,check=lambda:None):
    approval=_read_json(path)
    _keys(approval,{'version','approved','scope','run_id','fingerprints'},'008 control acceptance')
    if type(approval['version']) is not int or approval['version']!=1 or approval['approved'] is not True or approval['scope']!='reviewed_cpu_smoke_control':
        raise ValueError('Independent008 control acceptance required')
    _hashes({'run_id':approval['run_id']},'008 control ID')
    expected,_,_=b.prepare_fit_plan(config_path,train_path,selection_path,check=check)
    if expected['run_id']!=approval['run_id']:raise ValueError('008control is not the unchanged actual base plan')
    directory=ROOT/'artifacts/training'/approval['run_id']
    run_name=c.relative(directory/'run.json');report_name=c.relative(directory/'report.json')
    for name in [run_name,report_name]:
        if name not in approval['fingerprints']:raise ValueError('Missing008control manifest/report pin')
        c.verify_pins({name:approval['fingerprints'][name]},check)
    manifest,report=_read_json(directory/'run.json'),_read_json(directory/'report.json')
    if (manifest['run_id']!=expected['run_id'] or manifest['identity']!=expected['identity']
            or report.get('run_id')!=expected['run_id'] or report.get('status')!='complete_produced_unreviewed'
            or report.get('config')!=expected['identity']['config'] or report.get('fit_attempt_count')!=2
            or [a.get('method') for a in report.get('fit_attempts',[])]!=['Logloss','PairLogit']):
        raise ValueError('008control actual execution differs from accepted plan')
    ref=manifest['fit_approval'];claim_name='artifacts/fit-claims/'+approval['run_id']+'.json'
    required=c.merge_pins(expected['identity']['fingerprints'],{run_name:approval['fingerprints'][run_name],
        report_name:approval['fingerprints'][report_name],ref['path']:ref['sha256']})
    fixed_outputs={c.relative(directory/(method+suffix)) for method in ['Logloss','PairLogit'] for suffix in ['.cbm','-scores.npz']}
    outputs={}
    for attempt in report['fit_attempts']:
        if attempt['status']!='complete' or attempt['tree_count']!=50 or attempt['checkpoint_iterations']!=50:
            raise ValueError('008control requires exactly two accepted50tree outputs')
        outputs=c.merge_pins(outputs,attempt['artifacts'])
    if set(outputs)!=fixed_outputs:raise ValueError('008control output scope differs')
    for name in [claim_name,*PROOFS]:
        if name not in approval['fingerprints']:raise ValueError('Missing008control claim/proof pin')
        required=c.merge_pins(required,{name:approval['fingerprints'][name]})
    required=c.merge_pins(required,outputs)
    if required!=approval['fingerprints']:raise ValueError('008control acceptance must have exact actual input/output/proof scope')
    c.verify_pins(required,check)
    execution=_read_json(c.local(ref['path']))
    if (type(execution.get('version')) is not int or execution.get('approved') is not True
            or execution!=dict(version=1,approved=True,scope='cpu_smoke_two_fits',run_id=approval['run_id'],fingerprints=expected['identity']['fingerprints'])):
        raise ValueError('008control executionapproval differs')
    claim=_read_json(c.local(claim_name))
    if type(claim.get('version')) is not int or claim!=dict(version=1,run_id=approval['run_id'],allowed_fit_attempts=2,fit_approval=ref,
        output_directory=c.relative(directory),report=report_name):raise ValueError('008control consumed claim differs')
    control=report['fit_attempts'][0]
    metrics=control['metrics']['conditional_macro_query']
    if metrics['ndcg']!=NDCG_FLOOR or metrics['recall']!=RECALL_FLOOR+.002:
        raise ValueError('008control metrics differ from predeclared retention reference')
    return dict(manifest=manifest,report=report,control=control,
                score_path=directory/'Logloss-scores.npz',pins=c.merge_pins(required,{c.relative(path):sha256_file(path)}))


def prepare_plan(config_path,train_path,selection_path,metadata_acceptance,control_acceptance,*,check=lambda:None):
    config,digest=b._config_snapshot(config_path)
    if (config['iterations'],config['depth'],config['learning_rate'],config['l2_leaf_reg'],config['random_seed'],
        config['training_query_cap'],config['k'])!=(50,6,.05,3,2026,6000,20):
        raise ValueError('Single009ablation must keep the accepted008 settings')
    train=c.verify_collection_strict(train_path,check=check);selection=c.verify_collection_strict(selection_path,check=check)
    b.validate_training_phases(train,selection,LIMITS)
    export=c.verify_accepted_export(metadata_acceptance,check=check)
    if export['manifest']['identity']['collections']!={role:collection['plan']['collection_id'] for role,collection in [('train',train),('selection',selection)]}:
        raise ValueError('Metadata export is not bound to the same base collections')
    control=verify_control(control_acceptance,config_path,train_path,selection_path,check=check)
    if control['manifest']['identity']['config']!=config or sha256_file(config_path)!=digest:
        raise ValueError('Config snapshot changed or differs from008control')
    pins=c.merge_pins(train['pins'],selection['pins'],export['pins'],control['pins'],{c.relative(config_path):digest})
    for name in CODE:pins=c.merge_pins(pins,{name:sha256_file(c.local(name))});check()
    identity=dict(version=1,role=ROLE,limits=deepcopy(LIMITS),config=config,fingerprints=pins,
        control_run_id=control['manifest']['run_id'],metadata_run_id=export['manifest']['run_id'],
        acceptance_refs=dict(train=c.relative(train_path),selection=c.relative(selection_path),metadata=c.relative(metadata_acceptance),control=c.relative(control_acceptance)),
        numeric_features=[*b.numeric_feature_names(train['feature_columns']),*m.NUMERIC],categorical_features=list(m.NOMINAL),
        query_selection='same008_bottom_sha256_query_id_then_id_6000_train_all4000_selection',
        retention=dict(recall20_min=RECALL_FLOOR,ndcg20_reference=NDCG_FLOOR,ndcg20_strict_improvement_tolerance=NDCG_TOLERANCE,
            tie='base41',resource_failure='base41_no_replacement',integrity_or_API_failure='stop'),
        environment=environment_snapshot(),one_hot_max_size=4096,no_CTR_fallback=True)
    if len(identity['numeric_features'])!=56:raise ValueError('Actual009ablation needs fixed56numeric+3nominal schema')
    return dict(run_id=hashlib.sha256(canonical_json(identity).encode()).hexdigest(),identity=identity),dict(train=train,selection=selection,export=export,control=control)


def environment_snapshot():
    import pandas
    import tomllib
    from importlib.metadata import version
    result=b.environment_snapshot()
    packages=tomllib.loads((ROOT/'uv.lock').read_text())['package']
    locked=[p['version'] for p in packages if p['name']=='pandas']
    if locked!=[pandas.__version__] or version('pandas')!=pandas.__version__:
        raise ValueError('Loaded/installed pandas differs from locked chunk transport')
    result['loaded_packages']['pandas']=pandas.__version__
    return result


def consume_claim(manifest,audit):
    path=c.local(CLAIM);path.parent.mkdir(parents=True,exist_ok=True)
    claim=dict(version=1,scope=ROLE,run_id=manifest['run_id'],allowed_fit_attempts=1,
        consumed_before='matrix_Pool_fit_preparation',output_directory=c.relative(audit.directory))
    with path.open('x') as handle:handle.write(canonical_json(claim)+'\n')
    audit.report['fit_budget_claim']=CLAIM
    audit.report['preparation_consumes_single_attempt']=True


def features_data(data):
    from catboost import FeaturesData
    if data.categorical is None:raise ValueError('009model needs the accepted nominal block')
    return FeaturesData(num_feature_data=data.x,cat_feature_data=data.categorical,
        num_feature_names=data.feature_names,cat_feature_names=data.categorical_names)


def fit_once(train,config,audit):
    from catboost import CatBoostClassifier,Pool
    _,_,_,_,weights,summary=b.group_accounting(train)
    if np.unique(train.y).size!=2:raise ValueError('Observed train labels need both classes')
    cardinality=m.validate_train_cardinality(train.categorical)
    params=dict(loss_function='Logloss',iterations=50,depth=6,learning_rate=.05,l2_leaf_reg=3,
        random_seed=2026,thread_count=2,task_type='CPU',boosting_type='Plain',bootstrap_type='No',
        leaf_estimation_method='Newton',leaf_estimation_iterations=10,leaf_estimation_backtracking='AnyImprovement',
        random_strength=1,boost_from_average=False,one_hot_max_size=4096,verbose=False,
        allow_writing_files=False,use_best_model=False)
    pool=Pool(features_data(train),label=train.y,weight=weights,thread_count=2)
    model=CatBoostClassifier(**params);audit.guard();callback=b._BudgetCallback(audit.guard)
    audit.report['fit_attempt_count']+=1
    if audit.report['fit_attempt_count']!=1:raise ValueError('Single009fit count exceeded')
    model.fit(pool,callbacks=[callback])
    if callback.failure is not None:raise callback.failure
    audit.guard()
    if model.tree_count_!=50:raise ValueError('Single009fit did not reach fixed50trees')
    summary.update(trained_rows=len(train.group),encoded_train_cardinality=cardinality,row_weight='1/|Cq|',explicit_pairs=0)
    return model,summary


def validate_model(model,control_params,json_path):
    actual=model.get_all_params()
    keys=['loss_function','iterations','depth','learning_rate','l2_leaf_reg','random_seed','task_type','boosting_type',
        'bootstrap_type','leaf_estimation_method','leaf_estimation_iterations','leaf_estimation_backtracking',
        'random_strength','boost_from_average','use_best_model','border_count','nan_mode','rsm']
    if any(actual.get(k)!=control_params.get(k) for k in keys) or actual.get('one_hot_max_size')!=4096:
        raise ValueError('Actual009effective parameters differ from008control/fixedonehot')
    model.save_model(str(json_path),format='json');body=_read_json(json_path)
    if body.get('features_info',{}).get('ctrs') or any(split.get('split_type')=='OnlineCtr'
        for tree in body.get('oblivious_trees',[]) for split in (tree.get('splits') or [])):
        raise ValueError('Actual009model contains forbidden CTR')
    if len(body.get('oblivious_trees',[]))!=50:raise ValueError('Saved009model does not have50trees')
    return actual


def retention(metrics):
    values=metrics['conditional_macro_query']
    if not np.isfinite([values['recall'],values['ndcg']]).all():raise ValueError('Undefined retention metrics')
    keep=values['recall']>=RECALL_FLOOR and values['ndcg']>NDCG_FLOOR+NDCG_TOLERANCE
    return dict(retain_metadata_block=bool(keep),feature_choice='base41_plus_metadata18' if keep else 'base41',
        interpretation='development screening; no confirmation or general superiority claim',
        recall20=values['recall'],ndcg20=values['ndcg'],recall_floor=RECALL_FLOOR,ndcg_reference=NDCG_FLOOR,tie_tolerance=NDCG_TOLERANCE)


def run(config_path,train_path,selection_path,metadata_acceptance,control_acceptance,*,execution_approval):
    from catboost import Pool
    with AblationAudit(ROOT/'artifacts/metadata-ablation',seconds=LIMITS['wall_seconds'],scope=ROLE,
        cpu_seconds=LIMITS['max_process_cpu_seconds']) as audit:
        try:
            manifest,inputs=audit.stage('verify_all_accepted_data_control_and_plan',lambda:prepare_plan(config_path,train_path,selection_path,
                metadata_acceptance,control_acceptance,check=audit.guard))
            audit.identify(manifest,execution_approval)
            audit.stage('consume_global_single_attempt_before_preparation',lambda:consume_claim(manifest,audit))
            config=manifest['identity']['config'];audit.report.update(limits=LIMITS,labels_loaded=True)
            matrices={}
            for role,max_queries,max_rows in [('train',6000,1320000),('selection',None,880000)]:
                legacy=audit.stage(role+'_unchanged008_reference',lambda:b.prepare_dataset(inputs[role],max_queries=max_queries,max_rows=max_rows,check=audit.guard))
                base=audit.stage(role+'_chunked_base',lambda:d.prepare_model_data(inputs[role],max_queries=max_queries,max_rows=max_rows,check=audit.guard))
                audit.stage(role+'_exact_base_equivalence',lambda:d.assert_base_equivalent(base,legacy));del base
                mixed=audit.stage(role+'_mixed',lambda:d.prepare_model_data(inputs[role],max_queries=max_queries,max_rows=max_rows,
                    metadata_paths=inputs['export']['refs'][role],check=audit.guard))
                audit.stage(role+'_exact_mixed_base_equivalence',lambda:d.assert_base_equivalent(mixed,legacy));del legacy
                matrices[role]=mixed
            train,selection=matrices['train'],matrices['selection']
            if (len(train.queries)!=6000 or len(selection.queries)!=4000 or train.feature_names!=selection.feature_names
                    or train.feature_names!=manifest['identity']['numeric_features']
                    or train.categorical_names!=manifest['identity']['categorical_features']
                    or selection.categorical_names!=train.categorical_names):
                raise ValueError('Actual009matrix population/schema differs from fixed008comparison')
            with np.load(inputs['control']['score_path'],allow_pickle=False) as saved:
                if set(saved.files)!={'group','product_id','raw_score'} or not np.array_equal(saved['group'],selection.group) or not np.array_equal(saved['product_id'],selection.items):
                    raise ValueError('008saved scores do not cover exact same selection keys')
                control_scores=np.array(saved['raw_score'],copy=True)
            control_rows=audit.stage('saved008_control_rankings',lambda:b.rankings(selection,control_scores))
            control_metrics=audit.stage('saved008_external_fullY_metrics',lambda:asdict(evaluate(control_rows,20)))
            if control_metrics!=inputs['control']['control']['metrics']:raise ValueError('Saved008fullY metric replay differs from accepted reference')
            model,population=audit.stage('one_Logloss50_fit',lambda:fit_once(train,config,audit))
            if audit.report['fit_attempt_count']!=1:raise ValueError('Actual single009fit count differs from one')
            if model.feature_names_!=train.feature_names+train.categorical_names:
                raise ValueError('Actual009model feature order differs from frozen plan')
            json_path=audit.directory/'Logloss.json'
            params=audit.stage('actual50trees_parameters_noCTR',lambda:validate_model(model,inputs['control']['control']['actual_model_parameters'],json_path))
            pool=audit.stage('selection_Pool',lambda:Pool(features_data(selection),thread_count=2))
            scores=audit.stage('predict_selection',lambda:model.predict(pool,prediction_type='RawFormulaVal',thread_count=2))
            rows=audit.stage('rank_full_candidate_set',lambda:b.rankings(selection,scores))
            metrics=audit.stage('external_fullY_four_estimands',lambda:asdict(evaluate(rows,20)))
            comparison=audit.stage('paired_user_bootstrap_screening',lambda:asdict(paired_user_bootstrap(rows,control_rows,20,
                replicates=config['bootstrap_replicates'],seed=config['random_seed'])))
            model_path=audit.directory/'Logloss.cbm';score_path=audit.directory/'Logloss-scores.npz'
            audit.stage('save_CBM',lambda:model.save_model(str(model_path)))
            audit.stage('save_exact_scores',lambda:np.savez_compressed(score_path,group=selection.group,product_id=selection.items,raw_score=np.asarray(scores)))
            outputs={c.relative(p):sha256_file(p) for p in [model_path,score_path,json_path]}
            audit.manifest['outputs']=outputs
            audit.report.update(training=population,preparation={r:v.preparation for r,v in matrices.items()},
                feature_names=train.feature_names,categorical_names=train.categorical_names,actual_model_parameters=params,
                metrics=metrics,comparison=comparison,decision=retention(metrics),artifacts=outputs)
            audit.stage('final_actual_input_pins',lambda:c.verify_pins(c.merge_pins(manifest['identity']['fingerprints'],{
                audit.manifest['execution_approval']['path']:audit.manifest['execution_approval']['sha256']}),audit.guard))
            audit.report['status']='complete_produced_unreviewed'
        except (TimeoutError,MemoryError) as error:
            audit.report['decision']=failure_decision(error)
            raise
        except BaseException as error:
            audit.report['decision']=failure_decision(error)
            raise
    print(json.dumps(dict(run_id=audit.report['run_id'],status=audit.report['status'],decision=audit.report['decision'])),flush=True)
    return audit.report


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['config','train','selection','metadata','control','execution-approval']:parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args()
    run(args.config,args.train,args.selection,args.metadata,args.control,execution_approval=args.execution_approval)


if __name__=='__main__':main()
