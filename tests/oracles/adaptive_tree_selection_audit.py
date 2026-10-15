"""Inert independent zero-fit verifier; Root owns runtime/lifetime acceptance."""
import hashlib
import math
from pathlib import Path
import resource
import sys
import time

ADAPTER_SHA = 'cb24a4143c1093c7e07b2dfbb7fa021bc8530ab9448188eb22a696164220c8c4'
REPORT_SHA = 'e62b1f47d6db808f6f5235f63a1b207970ac2f8487c09d9273902c4fbc864a9b'
RECIPE_SHA = '3a26fed3bee450cb7ce4b658816386c14cbd2c4133a18bdaa39ae058e5b560ec'
PRODUCER_SHA = '4adcde3add3bf878a16831c109b8dc3ee141932dbb7c50ab663adc8e6ad2ecf6'
REQUEST_SHA = '6ffe3c7a82854fca25446faf8a580dce83c03584c7f37a81d63d1684b76049a7'
INPUT_ACCEPTANCE_SHA = '6dfe06d94140e5231574cd76718a61df2b0fd16dfc3e74a0698544a4948d7db6'
MATRIX_RESULT_SHA = '0a4a8fac03de95ca147ddc7f5ba1e62c60ae12bb78d220753094cb930664a75a'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def verify(output, *, export_root, project_root, scratch_directory, adapter_raw, accepted_matrix_result_raw,
           inventory_raw, expected_inventory_sha, observed_raw, expected_observed_sha, check):
    """Return pending evidence only; no fits, producer imports or persistence."""
    need(callable(check), 'Mandatory external whole-lifetime guard required')
    outer = check; wall = time.monotonic(); cpu = time.process_time(); calls = dict(loads=0, streams=0, predicts=0, checkpoints=0)
    def check():
        outer(); r = resource.getrusage(resource.RUSAGE_SELF)
        peak = r.ru_maxrss if sys.platform == 'darwin' else r.ru_maxrss*1024
        need(time.monotonic()-wall < 800 and time.process_time()-cpu < 600 and peak <= 12*2**30, 'Verifier reserve exceeded')
        need(calls['loads'] <= 4 and calls['streams'] <= 2 and calls['predicts'] <= 4 and calls['checkpoints'] <= 2400, 'Native replay cap exceeded')
    check(); need(type(adapter_raw) is bytes and len(adapter_raw) <= 128*1024
                  and hashlib.sha256(adapter_raw).hexdigest() == ADAPTER_SHA, 'Exact accepted helper snapshot required')
    A = {'__name__': 'adaptive_independent_helpers'}; exec(compile(adapter_raw, '<accepted-V3-helper>', 'exec'), A)
    parse = A['strict_json']; same = None
    need(all(type(v) is str and A['re'].fullmatch('[a-f0-9]{64}',v) for v in (expected_inventory_sha,expected_observed_sha)), 'Mandatory external SHA pins required')
    inventory = parse(inventory_raw, expected_inventory_sha); observed = parse(observed_raw, expected_observed_sha)
    accepted_matrix = parse(accepted_matrix_result_raw,MATRIX_RESULT_SHA)['matrix_proofs']
    need(set(observed) == {'version','scope','driver_sha256','request_sha256','accepted_input_authority_sha256','output_directory','inventory_sha256','invocation','terminal'}, 'Exact external observation required')
    need(observed['version'] == 1 and type(observed['version']) is int and observed['scope'] == 'observed_adaptive_tree_study_completion'
         and observed['driver_sha256'] == PRODUCER_SHA and observed['request_sha256'] == REQUEST_SHA
         and observed['accepted_input_authority_sha256'] == INPUT_ACCEPTANCE_SHA and observed['inventory_sha256'] == expected_inventory_sha
         and Path(observed['output_directory']).resolve() == Path(output).resolve(), 'Observed source/output binding differs')
    inv = observed['invocation']; terminal = observed['terminal']
    need(set(inv) == {'argv','cwd','fresh_output_observed','standalone_no_backend_substitution','closed_native_environment_observed'}
         and type(inv['argv']) is list and all(type(x) is str for x in inv['argv']) and '-c' not in inv['argv']
         and all(inv[k] is True for k in ('fresh_output_observed','standalone_no_backend_substitution','closed_native_environment_observed'))
         and type(inv['cwd']) is str and Path(inv['cwd']).is_absolute(), 'Truthful concrete standalone invocation required')
    need(set(terminal) == {'closed','exit_code','external_record'} and terminal['closed'] is True
         and type(terminal['exit_code']) is int and terminal['exit_code'] == 0 and type(terminal['external_record']) is str
         and terminal['external_record'], 'Actual terminal0 witness required')
    files = A['BoundFiles'](output, inventory, check); con = None; primary = None
    try:
        expected = {'consumed.json','request.json','recipe.json','accepted-report.json','report.json','both-fits-complete.json'}
        expected.update(arm+suffix for arm in ('B','W') for suffix in ('.fit-consumed.json','.full-1200.cbm','.validation-consumed.json','.curve.json','.selected.cbm','.selected-scores.npz'))
        need(set(inventory) == expected, 'Exact new output closure differs')
        request_raw = files.raw('request.json'); request = parse(request_raw)
        need(hashlib.sha256(request_raw).hexdigest() == observed['request_sha256'] and request['driver']['sha256'] == PRODUCER_SHA, 'Request/source binding differs')
        recipe_raw = files.raw('recipe.json'); accepted_raw = files.raw('accepted-report.json')
        need(hashlib.sha256(recipe_raw).hexdigest() == RECIPE_SHA and hashlib.sha256(accepted_raw).hexdigest() == REPORT_SHA, 'Accepted original inputs differ')
        recipe = parse(recipe_raw); original = parse(accepted_raw); report = files.body('report.json'); consumed = files.body('consumed.json')
        need(report['status'] == 'complete_produced_pending_independent_review' and report['fit_attempts'] == 2
             and report['dependent_validation_checkpoints'] == 2400 and report['exploratory'] is True
             and report['heldout_confirmed'] is False and report['final_used'] is False and report['native_early_stopping'] is False
             and report['best_within_range'] == [1,1200] and report['independent_acceptance_issued'] is False
             and report['full_external_tail_accepted'] is False and report['request_sha256'] == observed['request_sha256'], 'Completed exploratory scope differs')
        need(consumed == dict(request_sha256=observed['request_sha256'], max_fits=2, max_validation_checkpoints=2400,
                             retry=False, independent_acceptance_issued=False), 'Exactly one consumed two-fit attempt required')
        project = Path(project_root).resolve(strict=True); exports = Path(export_root).resolve(strict=True)
        need(exports == project/'artifacts/reproduction/public-frozen-bw-once' and not Path(export_root).is_symlink()
             and files.root == project/request['output_path'] and not files.root.is_relative_to(exports), 'Fixed separate export/output namespaces required')
        argv = inv['argv']; positions = [i for i,v in enumerate(argv) if v == 'scripts.adaptive_tree_selection' or v.endswith('/scripts/adaptive_tree_selection.py')]
        need(len(positions) == 1 and len(argv[positions[0]+1:]) == 6, 'Exact standalone adaptive producer entry required')
        tail = argv[positions[0]+1:]; need(set(tail[::2]) == {'--request','--expected-request-sha','--output'}, 'Exact observed arguments required')
        args = dict(zip(tail[::2],tail[1::2])); cwd = Path(inv['cwd'])
        need(cwd.resolve() == project and (cwd/args['--output']).resolve() == files.root
             and args['--expected-request-sha'] == REQUEST_SHA
             and (cwd/args['--request']).resolve() == project/'configs/studies/adaptive-tree-selection-oct2019-once.json', 'Observed request/output paths differ')
        files.bind_external(project/'scripts/adaptive_tree_selection.py',request['driver'],snapshot=True)
        files.bind_external(cwd/args['--request'],A['byte_ref'](request_raw),snapshot=True)
        for name,ref in request['accepted_source_pins'].items():
            A['relative'](name); files.bind_external(project/name,ref,snapshot=True)
        def local(name):
            A['relative'](name); path = exports/name; p = path
            while p != exports:
                need(not p.is_symlink(), 'Export symlink forbidden'); p = p.parent
            need(path.is_file() and path.resolve().is_relative_to(exports), 'Accepted export path differs'); return path
        files.bind_external(local('report.json'), A['byte_ref'](accepted_raw), snapshot=True)
        files.bind_external(local('recipe.json'), A['byte_ref'](recipe_raw), snapshot=True)
        sources = {kind:files.bind_external(project/name, ref, snapshot=True) for kind,(name,ref) in A['INDEPENDENT'].items() if kind in ('model','native')}
        M = A['load_core'](sources['model'], 'model'); N = A['load_core'](sources['native'], 'native'); same = M['same']
        same(report['driver'],request['driver']); same(report['accepted_report'],A['byte_ref'](accepted_raw)); same(report['dependencies'],original['dependencies'])
        complete = files.body('both-fits-complete.json')
        need(set(complete) == {'completed_fits','full_models','validation_checkpoints_started','telemetry','producer_statement_not_independent_proof'}
             and type(complete['completed_fits']) is int and complete['completed_fits'] == 2
             and type(complete['validation_checkpoints_started']) is int and complete['validation_checkpoints_started'] == 0
             and complete['producer_statement_not_independent_proof'] is True, 'Bound producer completion statement required; not native provenance proof')
        same(complete['full_models'],{arm:inventory[arm+'.full-1200.cbm'] for arm in ('B','W')}); same(report['both_fits_complete'],inventory['both-fits-complete.json'])
        collections = {}
        for phase, days in (('train',range(8,21)),('selection',range(22,24))):
            rows = original['data_exports'][phase]; need(len(rows) == len(days), 'Exact development day cover required')
            refs = {k:[] for k in ('queries','features','candidates','labels')}; extras = []
            for row,day in zip(rows,days):
                prefix = f'{phase}/2019-10-{day:02}'; name = prefix+'/manifest.json'
                need(row['manifest']['path'] == name and set(row['exports']) == {'queries','candidates','base','extra','labels'}, 'Exact day/export kinds required')
                manifest = parse(files.bind_external(local(name), {k:row['manifest'][k] for k in ('sha256','bytes')}, snapshot=True))
                need(manifest['queries'] == 2000 and manifest['label_blind_Q_C_F_frozen_before_Y'] is True, 'Accepted query manifest differs')
                for kind,pin in row['exports'].items():
                    name = prefix+'/'+kind+'.parquet'; ref = {k:pin[k] for k in ('sha256','bytes')}
                    need(pin['path'] == name and manifest['files'][kind] == dict(path=kind+'.parquet',**ref), 'Accepted export binding differs')
                    files.bind_external(local(name),ref)
                    (extras if kind == 'extra' else refs['features' if kind == 'base' else kind]).append(name)
            collections[phase] = dict(phase={'role':phase},refs=refs,extra_paths=extras)
        from importlib.metadata import version
        need(list(sys.version_info[:2]) == recipe['environment']['python_major_minor'] and
             {n:version(n) for n in recipe['environment']['packages']} == recipe['environment']['packages'], 'Exact native environment required')
        import duckdb
        import numpy as np
        from catboost import CatBoostClassifier
        need(CatBoostClassifier.__module__ == 'catboost.core', 'Concrete native models required')
        scratch = Path(scratch_directory).resolve(strict=True)
        need(scratch.is_dir() and not Path(scratch_directory).is_symlink() and not any(scratch.iterdir())
             and not scratch.is_relative_to(files.root) and not scratch.is_relative_to(exports), 'Fresh external scratch required')
        con = duckdb.connect(':memory:',config={'threads':'2','memory_limit':'2GB','max_temp_directory_size':'8GiB','temp_directory':str(scratch)})
        expected_params = A['deepcopy'](recipe['effective_parameters']); expected_params['iterations'] = 1200
        constructor = A['deepcopy'](recipe['constructor_parameters']); constructor['iterations'] = 1200
        def load(arm, suffix, trees):
            calls['loads'] += 1; check(); model = CatBoostClassifier(); model.load_model(str(files.local(arm+suffix)),format='cbm'); check()
            need(type(model.tree_count_) is int and model.tree_count_ == trees and model.feature_names_ == recipe['feature_names'][arm]
                 and model.get_cat_feature_indices() == model.get_text_feature_indices() == model.get_embedding_feature_indices() == [], 'Exact native model schema/tree count differs')
            N['native_equal'](model.get_all_params(), expected_params); return model
        own = {}; canonical = {}; curves = {}; base = {}
        for arm in ('B','W'):
            summary = report['arms'][arm]; fit = files.body(arm+'.fit-consumed.json'); canonical[arm] = {}
            need(fit['arm'] == arm and fit['attempt'] == (1 if arm == 'B' else 2) and type(fit['attempt']) is int
                 and fit['constructor_parameters'] == constructor, 'Exactly two fixed constructor slots required')
            for phase in ('train','selection'):
                c = collections[phase]; delta = [dict(name=n,dtype='BIGINT') for n in recipe['extra_feature_names']] if arm == 'W' else []
                data = M['read_matrix'](con,c,recipe['feature_names']['B'],local=local,cap=26000 if phase == 'train' else None,
                                       extra_paths=c['extra_paths'] if delta else None,delta=delta,check=check)
                need(len(data.queries) == (26000 if phase == 'train' else 4000) and len(data.items) == (5317058 if phase == 'train' else 817149), 'Full matrix support differs')
                weights,accounting = M['group_weights'](data); identity = A['own_identity'](data,check)
                if phase == 'train':
                    identity['weights'] = A['raw_array_ref'](weights,check); same(accounting,fit['accounting']); same(identity,fit['train']); same(accounting,summary['accounting'])
                same(identity,original['comparison'][arm][phase]); same(identity,summary[phase])
                shared = {k:identity[k] for k in ('queries_sha256','group','items','y','base41')}
                if arm == 'B': base[phase] = shared
                else: same(shared,base[phase])
                canonical[arm][phase] = M['matrix_proof'](data,weights=weights if phase == 'train' else None,check=check)
                same(canonical[arm][phase],accepted_matrix[arm][phase])
                if phase == 'train': del data,weights; A['gc'].collect(); check(); continue
                full = load(arm,'.full-1200.cbm',1200); positive = [i for i,q in enumerate(data.queries) if q[3]]
                need(len(positive) == 73 and sum(len(q[3]) for q in data.queries) == 96, 'Every full-Y-positive query required')
                remap = np.full(len(data.queries),-1,dtype=np.int32); remap[positive] = np.arange(len(positive),dtype=np.int32)
                rows = np.flatnonzero(remap[data.group] >= 0)
                small = M['Matrix']([data.queries[i] for i in positive],remap[data.group[rows]],data.items[rows],data.x[rows],data.y[rows],data.feature_names)
                need(len(rows) > 0,'Accepted positive selection support unexpectedly empty')
                same(files.body(arm+'.validation-consumed.json'),dict(max_checkpoints=1200,both_fits_complete=inventory['both-fits-complete.json'],final_used=False))
                calls['streams'] += 1; check(); curve = []
                for scores in full.staged_predict(small.x,prediction_type='RawFormulaVal',ntree_start=0,ntree_end=1200,eval_period=1,thread_count=2):
                    calls['checkpoints'] += 1; check(); need(len(curve) < 1200,'Extra native staged prefix')
                    value = M['summarize'](small.queries,M['rankings'](small,scores))[0]['conditional_macro_query']['ndcg']
                    need(type(value) is float and math.isfinite(value), 'Finite independent checkpoint required'); curve.append(value)
                need(len(curve) == 1200,'Complete1..1200 curve required'); peak = max(curve)
                best = min(i+1 for i,value in enumerate(curve) if value >= peak-1e-12)
                same(files.body(arm+'.curve.json'),dict(ndcg=curve,selected_trees=best,maximum_ndcg=peak,tie_tolerance=1e-12,
                     projection=dict(fullY_positive_queries=73,candidate_rows=len(rows)),full_model=inventory[arm+'.full-1200.cbm'],metric='conditional_macro_query.ndcg@20'))
                need(type(summary['selected_trees']) is int and summary['selected_trees'] == best,'Independent best tree differs')
                selected = load(arm,'.selected.cbm',best)
                calls['predicts'] += 1; check(); prefix_scores = np.asarray(full.predict(data.x,ntree_end=best,prediction_type='RawFormulaVal',thread_count=2),dtype=np.float64); check()
                calls['predicts'] += 1; check(); selected_scores = np.asarray(selected.predict(data.x,prediction_type='RawFormulaVal',thread_count=2),dtype=np.float64); check()
                saved = A['saved_scores'](files.raw(arm+'.selected-scores.npz',maximum=32*2**20),data,np,check=check)
                need(np.allclose(prefix_scores,selected_scores,rtol=0,atol=1e-12) and np.allclose(selected_scores,saved,rtol=0,atol=1e-12), 'Selected/full-prefix/saved scores differ')
                ranked = M['rankings'](data,selected_scores); need(ranked == M['rankings'](data,prefix_scores) == M['rankings'](data,saved),'Full key/rank replay differs')
                evaluation,_,_ = M['summarize'](data.queries,ranked); same(evaluation,summary['evaluation'])
                need(abs(evaluation['conditional_macro_query']['ndcg']-curve[best-1]) <= 1e-12,'Compact/full primary differs')
                for key,suffix in (('full_model','.full-1200.cbm'),('selected_model','.selected.cbm'),('scores','.selected-scores.npz'),('curve','.curve.json')):
                    same(summary[key],inventory[arm+suffix])
                need(summary['validation_checkpoints'] == 1200,'Complete saved checkpoint count required')
                same(float(np.max(np.abs(prefix_scores-selected_scores))),summary['max_raw_score_difference'])
                own[arm] = dict(selected_trees=best,evaluation=evaluation); curves[arm] = curve
                del data,weights,full,selected,small,rows,remap,prefix_scores,selected_scores,saved,ranked; A['gc'].collect(); check()
        need(calls == dict(loads=4,streams=2,predicts=4,checkpoints=2400),'Exact zero-fit native replay closure differs')
        check(); return dict(status='checked_pending_external_lifetime_acceptance',arms=own,curves=curves,matrix_proofs=canonical,
                             calls=calls,verifier_fits=0,heldout_confirmed=False,external_acceptance_required=True,
                             output_inventory_sha256=expected_inventory_sha,observed_run_sha256=expected_observed_sha)
    except BaseException as error:
        primary = error; raise
    finally:
        for name,action in (('connection_close',lambda:con.close() if con is not None else None),('bound_byte_repin',files.repin),('resource_tail',check)):
            try: action()
            except BaseException as error:
                if primary is None: primary = error
                else:
                    try: primary.add_note(name+' secondary '+type(error).__name__)
                    except BaseException: pass
        if primary is not None: raise primary.with_traceback(primary.__traceback__)
