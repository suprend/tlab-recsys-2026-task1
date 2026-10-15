from fractions import Fraction as F
from itertools import product
from math import log2
from pathlib import Path
import json
threshold=F(1,500)
sequences=known=unknown=retired=0
for N in range(1,7):
    for seq in product((-1,0,1),repeat=N):
        sequences+=1;truth=F(sum(seq),N)
        for n in range(N+1):
            S=sum(seq[:n]);M=N-n;lo=F(S-M,N);hi=F(S+M,N)
            assert lo<=truth<=hi;known+=1
            if hi<threshold:assert truth<threshold;retired+=1
            for R in range(M,6-n+1):
                ulo=F(S-R,n+R);uhi=F(S+R,n+R)
                assert ulo<=truth<=uhi;unknown+=1
assert (sequences,known,unknown,retired)==(1092,7107,9837,1287)
# Additional no-positive/undefined/tie/unequal-cluster boundaries, not author corpus.
zero_cases=0
for totalQ in range(7):
    for seq in product((None,-1,0,1),repeat=totalQ):
        positives=[v for v in seq if v is not None]
        truth=F(sum(positives),len(positives)) if positives else None
        for processed in range(totalQ+1):
            prefix=[v for v in seq[:processed] if v is not None];n=len(prefix);S=sum(prefix);R=totalQ-processed
            if n+R==0:assert truth is None;continue
            lo=F(S-R,n+R);hi=F(S+R,n+R)
            if truth is not None:assert lo<=truth<=hi
            if n==0 and R>0:assert (lo,hi)==(-1,1)
            zero_cases+=1
# Exact threshold equality must continue.
assert not (F(1,500)<threshold)
# Query-macro and user-macro must not be exchanged: one user2positive queries.
cluster_values=[[-1,-1],[1]]
query_macro=F(sum(map(sum,cluster_values)),sum(map(len,cluster_values)))
user_macro=sum((F(sum(v),len(v)) for v in cluster_values),F(0))/len(cluster_values)
assert query_macro==F(-1,3) and user_macro==0
N=73
harm=next(n for n in range(N+1) if F(N-2*n,N)<threshold)
zero=next(n for n in range(N+1) if F(N-n,N)<threshold)
assert (harm,zero)==(37,73)
# Discounted binary ranking ceiling and a genuine finite-point-vs-bootstrap example.
def disc(r):return sum(1/log2(j+1) for j in range(1,r+1))
O=1/(1+1/log2(3));assert abs(O-0.6131471927654584)<1e-14
h=(1/log2(16)-1/log2(21))/disc(19)
# q1 has m=h=19; W's positive ranks1..14 and16..20, oracle ranks1..19.
w=sum(1/log2(j+1) for j in [*range(1,15),*range(16,21)])/disc(19)
assert abs((1-w)-h)<1e-14
finiteH=h/2
boot=[0.0,h/2,h/2,h]
# Four equal-probability ordered user-resampling outcomes, linear empirical percentile.
x=.975*(len(boot)-1);lower=int(x);weight=x-lower;upper97=boot[lower]*(1-weight)+boot[lower+1]*weight
assert finiteH<float(threshold)<upper97<=h
p_undefined=F(99,100)**100
assert abs(float(p_undefined)-0.3660323412732292)<1e-14
# Feedback accounting is two dimensions: global physical callbacks vs recipients.
no_reuse={'fit_credits':4,'physical_starts':4,'computed_candidate_payloads':4,'computed_gate_payloads':1,'unique_computed_payloads':5,'policy_recipient_credits':6}
shared={'fit_credits':4,'physical_starts':3,'computed_candidate_payloads':3,'computed_gate_payloads':1,'unique_computed_payloads':4,'policy_recipient_credits':6}
fit_only_shared={'fit_credits':4,'physical_starts':3,'computed_candidate_payloads':4,'computed_gate_payloads':1,'unique_computed_payloads':5,'policy_recipient_credits':6}
assert no_reuse['unique_computed_payloads']==5 and shared['unique_computed_payloads']==4
# A full oracle scalar may expose target information; no row counts are invented as free metadata.
result={'kind':'invented stdlib arithmetic only; noDB/SQL/Y/model/native','A_reproduced':{'sequences':sequences,'known_prefix_checks':known,'unknown_completion_checks':unknown,'strict_retirement_certificates':retired,'all_pass':True},'A_extra_unknown_support_cases':zero_cases,'A_N73':{'strongharm_first_retire':harm,'zero_first_retire':zero},'estimands':{'query_macro':'-1/3','user_macro':'0'},'B_oracle_m2_h1':{'oracle_W':O,'true_headroom':0,'wrong_1_minus_W':1-O},'B_nonlinear_CI_counterexample':{'m_q1':19,'h_q1':19,'W_positive_ranks_q1':[*range(1,15),*range(16,21)],'q1_headroom':h,'q2_headroom':0,'finite_conditional_headroom':finiteH,'threshold':.002,'four_userbootstrap_headroom_draws':boot,'linear_empirical_percentile97_5':upper97,'finite_point_below_threshold_but_bootstrap_upper_above':True,'claim':'does not contradict authorfinitepointstop; disprovespopulation/CIextension'},'rare_user_undefined_probability':float(p_undefined),'feedback_accounting':{'no_shared_receipt':no_reuse,'fit_only_shared':fit_only_shared,'exact_shared_fit_and_feedback_receipt':shared},'nested_cost_minutes_sum':30+30+180,'limitations':'exact Fraction proofs for inventedbounded differences; floatingDCGexample is numeric illustration, notoutward-safe productioncertificate'}
Path('/tmp/tlab-wave008-skeptic-literal.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':'pass','author_counts':[sequences,known,unknown,retired],'extra_zero_support_checks':zero_cases,'finiteH':finiteH,'bootstrap_upper97_5':upper97,'undefinedprob':float(p_undefined),'feedback_unique_no_reuse':5,'feedback_unique_shared':4}))
