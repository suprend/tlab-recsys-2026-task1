"""One separately granted native LOAD/parameter capture; expected red, no fix."""
import time
ENTRY = time.monotonic()
import resource
import signal
resource.setrlimit(resource.RLIMIT_CPU, (15,15))
signal.alarm(30)
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import sys
import types

PROJECT = Path('/Users/mdpospelov/tlab-recsys-2026')
OP = '018-native-param-diagnostic-20261015-once'
OUT = Path('/private/tmp/tlab-' + OP)
REQUEST = Path('/tmp/tlab-development-whole018-request-candidate-v1.json')
REQUEST_SHA = '0d7d99a9a8fb2a1f9bfbf9375e57935f49f52ee48685ae92dbb7f66f5dc41ce9'
PREDICTIONS = PROJECT / 'scripts/heldout_predictions.py'
PREDICTIONS_SHA = 'e1b06b2aac68c59379d15298c39101ec02b6a176c26b13d4671f8e445de2851b'
CONTRACT = PROJECT / 'scripts/heldout_contract.py'
CONTRACT_SHA = 'fc50d11d3b6dfdc2906522472f5b66138424bc4586e7833b43c6fc4e6c4f1abc'
MODEL_SHA = 'a60a82894ed9385a7b4f38784e7ea34ed9476966557387924406f803343f2b2e'
RSS_CAP = 512 * 2**20
PROGRESS = dict(native_load_attempts=0,native_load_returns=0,native_parameter_calls=0,
                predict_attempts=0,fit_attempts=0,source_db_or_Y_opened=False,children_started=0)


def need(value,message):
    if not value: raise ValueError(message)


def telemetry():
    own=resource.getrusage(resource.RUSAGE_SELF);child=resource.getrusage(resource.RUSAGE_CHILDREN)
    return dict(CPU_seconds=own.ru_utime+own.ru_stime,wall_seconds=time.monotonic()-ENTRY,
        process_peak_RSS_bytes=own.ru_maxrss*(1 if sys.platform=='darwin' else 1024),
        child_CPU_seconds=child.ru_utime+child.ru_stime,child_peak_RSS=child.ru_maxrss)


def check():
    t=telemetry()
    need(t['CPU_seconds']<14 and t['wall_seconds']<28 and t['process_peak_RSS_bytes']<=RSS_CAP,
         'Separate diagnostic budget/cleanup reserve exhausted')
    need(t['child_CPU_seconds']==0 and t['child_peak_RSS']==0,'Diagnostic must never reap children')
    return t


def stable(path):
    value=path.stat();need(stat.S_ISREG(value.st_mode),'Regular immutable input required')
    return dict(device=value.st_dev,inode=value.st_ino,size=value.st_size,
                mtime_ns=value.st_mtime_ns,ctime_ns=value.st_ctime_ns)


def pin(path,expected,cap):
    before=stable(path);need(0<before['size']<=cap,'Bounded explicit input required')
    digest=hashlib.sha256()
    with path.open('rb') as handle:
        while True:
            check();raw=handle.read(1024*1024)
            if not raw:break
            digest.update(raw)
    need(stable(path)==before and digest.hexdigest()==expected,'Explicit original input bytes changed')
    return dict(path=str(path),sha256=expected,stat=before)


def write(name,value):
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    need(len(raw)<=262144,'Bounded diagnostic capture required')
    with (OUT/name).open('xb') as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())


class CapturedModel:
    def __init__(self,native):self.native=native;self.params=None
    def __getattr__(self,name):
        need(name in {'tree_count_','feature_names_','get_cat_feature_indices',
            'get_text_feature_indices','get_embedding_feature_indices'},'Unexpected native capability requested')
        return getattr(self.native,name)
    def get_all_params(self):
        need(PROGRESS['native_parameter_calls']==0,'No repeated native parameter read')
        PROGRESS['native_parameter_calls']+=1;check();self.params=self.native.get_all_params();check()
        return self.params


def main():
    need(len(sys.argv)==1 and sys.flags.isolated==1 and sys.flags.dont_write_bytecode==1,
         'Fixed one-shot isolated entry required')
    need(sys.version_info[:2]==(3,12) and sys.platform=='darwin','Bound accepted interpreter required')
    need(not OUT.exists() and not OUT.is_symlink(),'Diagnostic namespace consumed; no retry')
    OUT.mkdir(mode=0o700)
    write('consumed.json',dict(op_id=OP,status='consumed_once_no_retry',bounds=dict(CPU_seconds=15,
          wall_seconds=30,process_peak_RSS_bytes=RSS_CAP),original600_episode_closed=True))
    pins={};wrapped=None;error=None
    try:
        check();pins['request']=pin(REQUEST,REQUEST_SHA,262144)
        request=json.loads(REQUEST.read_bytes());spec=request['models']['B']
        need(spec['model']['sha256']==MODEL_SHA,'Only fixed original B model allowed')
        model_path=PROJECT/spec['model']['path']
        need(not spec['model']['path'].startswith('/') and model_path.resolve().is_relative_to(PROJECT),
             'Explicit original project-relative B required')
        pins['protected_predictions']=pin(PREDICTIONS,PREDICTIONS_SHA,262144)
        pins['contract']=pin(CONTRACT,CONTRACT_SHA,262144)
        # Compile exact original function AST nodes only, avoiding unrelated
        # inference/native-SQL imports. No original function body is rewritten.
        original=ast.parse(PREDICTIONS.read_bytes(),filename=str(PREDICTIONS))
        selected=[node for node in original.body if isinstance(node,ast.FunctionDef)
                  and node.name in {'_same','verify_model'}]
        need([node.name for node in selected]==['_same','verify_model'],'Exact protected functions missing')
        contract=types.ModuleType('diagnostic_original_contract')
        exec(compile(CONTRACT.read_bytes(),str(CONTRACT),'exec',dont_inherit=True),contract.__dict__)
        functions=types.ModuleType('diagnostic_original_verify_model')
        functions.__dict__.update(h=contract,math=math,struct=struct)
        exec(compile(ast.Module(body=selected,type_ignores=[]),str(PREDICTIONS),'exec',dont_inherit=True),functions.__dict__)
        pins['model_before']=pin(model_path,MODEL_SHA,64*2**20)
        check()
        from catboost import CatBoostClassifier
        check();native=CatBoostClassifier();PROGRESS['native_load_attempts']+=1
        native.load_model(str(model_path));PROGRESS['native_load_returns']+=1;check()
        wrapped=CapturedModel(native)
        try:functions.verify_model(wrapped,spec)
        except Exception as caught:error=dict(type=type(caught).__name__,message=str(caught))
        if wrapped.params is None:wrapped.get_all_params()
        check();pins['model_after']=pin(model_path,MODEL_SHA,64*2**20)
        for name,path,digest in [('request',REQUEST,REQUEST_SHA),('protected_predictions',PREDICTIONS,PREDICTIONS_SHA),('contract',CONTRACT,CONTRACT_SHA)]:
            need(pin(path,digest,262144)==pins[name],'Protected metadata/source changed during capture')
        same_symptom=error==dict(type='ValueError',message='Native effective parameter differs')
        write('capture.json',dict(version=1,op_id=OP,status='expected_red_reproduced' if same_symptom else
            'different_failure_captured' if error else 'unexpected_green',
            original_verify_error=error,expected_spec=spec,actual_params=wrapped.params,
            native_metadata=dict(tree_count=native.tree_count_,feature_names=native.feature_names_,
                cat_features=native.get_cat_feature_indices(),text_features=native.get_text_feature_indices(),
                embedding_features=native.get_embedding_feature_indices()),
            exact_protected_AST_functions=['_same','verify_model'],pins=pins,progress=PROGRESS,
            telemetry=check(),source_acceptance_issued=False,fix_applied=False))
        write('body-receipt.json',dict(op_id=OP,status='capture_complete_expected_red' if same_symptom else
            'capture_complete_different_failure' if error else 'capture_complete_green',
            telemetry=telemetry(),progress=PROGRESS,full_exit_profile_pending=True))
        if error:
            print(('EXPECTED_RED ' if same_symptom else 'DIFFERENT_FAILURE ')+error['type']+': '+error['message'])
            return 1 if same_symptom else 2
        print('UNEXPECTED_GREEN original verify_model accepted fixed B');return 0
    except BaseException as caught:
        try:write('failure.json',dict(op_id=OP,status='failed_consumed_no_retry',error_type=type(caught).__name__,
            error=str(caught),pins=pins,progress=PROGRESS,telemetry=telemetry()))
        except BaseException as secondary:print('Diagnostic receipt unknown: '+str(secondary),file=sys.stderr)
        print('DIAGNOSTIC_FAILURE '+type(caught).__name__+': '+str(caught),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
