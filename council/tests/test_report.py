"""council.report on synthetic JSON under /tmp/tlab-report-test-*: tables and rounding, placeholders for missing
artifacts, --check pass and fail, no writes, and an AST guard that the module reads no labels or tests."""
import ast
import contextlib
import io
import json
import re
import shutil
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from council import report as R

COLUMNS = [f'F{i}' for i in range(1, 13)] + [f'T{i}' for i in range(1, 5)] + ['PL'] + [f'E{i}' for i in range(1, 7)]


def _beta_block():
    out = {}
    for k, c in enumerate(COLUMNS):
        what = 'empty' if c.startswith('E') else 'placebo' if c == 'PL' else f'G{1 + k % 4}-{1 + k // 4}'
        out[c] = {'what': what, 'beta': 0.0001 * (k + 1) - 0.0011, 'se': 0.00041 + 0.00001 * k, 't': 0.31 * k - 2.3456}
    out['F1'] = {'what': 'G1-1', 'beta': 0.00123456, 'se': 0.00045678, 't': 2.7027}
    out['PL'] = {'what': 'placebo', 'beta': -0.00098765, 'se': 0.00040012, 't': -2.4684}
    return out


def plan_result(xfer=False):
    res = {'queries': 15605, 'users': 13958, 'beta': _beta_block(), 'se_empty': 0.00031234,
           'wy_harm': {**{f'F{i}': 0.5 + 0.01 * i for i in range(1, 13)}, 'PL': 0.0123},
           'wy_empty_max': 0.4321,
           'calibration': {'passed': True, 'sd_t': 0.61234, 'interval': [0.36671, 0.84765], 'p_wy_empty': 0.4321},
           'mechanism': [{'family': 'F1', 'twin': 'T1', 'beta': 0.00123456, 'beta_twin': 0.0002, 'diff': 0.00103456,
                          'se': 0.0004, 't': 2.5864, 't_family': 2.7027, 'class': 'ждёт C_val'},
                         {'family': 'F2', 'twin': 'T2', 'beta': -0.0003, 'beta_twin': 0.0001, 'diff': -0.0004,
                          'se': 0.0005, 't': -0.8, 't_family': -0.7, 'class': 'не различено'}],
           'twin_arm_family': 'F1'}
    if xfer:
        res |= {'D': [], 'subtraction': 'descriptive: power gate failed', 'power_gate': False}
    return res


def contrast(d, lo, hi, by, key='by_pair'):
    return {'d': d, 'ci95': [lo, hi], key: by}


VAL = {'queries': 34567, 'mean': {'path_Hr_full_val_s0': 0.14567, 'cval_ALLP_s0': 0.14789},
       'contrasts': {'SEL − H+r⁺ (главный, описательно)': contrast(0.00071, 0.00012, 0.00133, [0.0006, 0.0008]),
                     'H+r⁺ − H+r (кривая объёма)': contrast(-0.00052, -0.0011, 0.00004, [-0.0005, -0.00054])},
       'mechanism_c_val': {'F1': 0.00042}, 'mechanism_class': 'механизм установлен', 'twin_card': 'G1-1'}

H1 = {'delta': 0.00213, 'lower': 0.00106, 'upper': 0.00321, 'pairs_positive': 4, 'n_pairs': 4,
      'by_pair': [0.002, 0.0021, 0.0022, 0.0023], 'verdict': 'обыгрывает H+', 'n_boot': 2000, 'seed': 2026}
TEST_REES46 = {s: {'queries': q, 'mean': {'ctest_Hrp_s0': 0.15}, 'h1': H1,
                   'H+r⁺ − H+r': contrast(0.0011, 0.0002, 0.002, [0.001, 0.0012]),
                   'ALL_P − H+r': contrast(0.0031, 0.0021, 0.0041, [0.003, 0.0032])}
               for s, q in (('primary', 50001), ('all_16_days', 60002))}
TEST_XFER = {'test': 'повторный тест', 'selection_sha256': 'ab' * 32, 'queries': 7001, 'users': 6001,
             'mean': {'test-SEL-7': 0.2}, 'h1': H1 | {'verdict': 'не различено', 'lower': -0.0004},
             'contrasts': {'SEL − H+r': contrast(0.0015, 0.0005, 0.0025, [0.0014, 0.0016], 'by_seed')},
             'mechanism': {'family': 'F1', 'card': 'G1-1', 't_select': 2.5864, 'diff': 0.00103,
                           'repeat': {'delta': 0.0009, 'lower': 0.0001, 'upper': 0.0017, 'repeated': True},
                           'class': 'механизм установлен'}, 'cut': []}

LLM_REES46 = [
    {'stage': 'wave1', 'role': 'G1', 'call': True, 'seconds': 1800.0, 'cost_usd': 1.2652, 'error': None},
    {'stage': 'wave1', 'role': 'G2', 'call': True, 'seconds': 1800.0, 'cost_usd': 1.2022, 'error': None},
    {'stage': 'cross', 'role': 'critic-G1', 'call': True, 'seconds': 360.0, 'cost_usd': 0.5, 'error': None},
]
LLM_XFER = [
    {'stage': 'wave1', 'role': 'G1', 'call': False, 'started': True, 'call_id': 'a'},
    {'stage': 'wave1', 'role': 'G1', 'call': True, 'call_id': 'a', 'seconds': 382.2, 'cost_usd': 0.93},
    {'stage': 'reference', 'role': 'rb1', 'call': False, 'started': True, 'call_id': 'b'},
    {'stage': 'reference', 'role': 'rb1', 'call': True, 'call_id': 'b', 'seconds': 323.4, 'cost_usd': 0.8149},
    {'stage': 'cross', 'role': 'critic-G1', 'call': False, 'started': True, 'call_id': 'c'},   # still running
]


def fit_record(name, peak, prepare=40, fit=220, predict=40):
    return {'name': name, 'spec': {'name': name}, 'peak_rss_gb': peak, 'started': '2026-10-22 00:00:00',
            'seconds': {'prepare': prepare, 'fit': fit, 'predict': predict, 'write': 0}}


QUEUE_XFER = [
    {'event': 'light-start', 'what': 'probe reference 641'},
    {'event': 'light-end', 'what': 'probe reference 641', 'ok': True, 'seconds': 40.0, 'peak_gb': 5.646},
    {'event': 'light-end', 'what': 'probe reference 611', 'ok': True, 'seconds': 37.6, 'peak_gb': 6.111},
    {'event': 'wait', 'what': 'fit path_select-Hr-2026', 'reason': 'lock held'},
    {'event': 'start', 'what': 'fit path_select-Hr-2026', 'pid': 1},
    {'event': 'end', 'what': 'fit path_select-Hr-2026', 'ok': True, 'seconds': 1800.0, 'peak_gb': 30.5},
    {'event': 'peak', 'what': 'fit path_select-Hr-2026', 'peak_gb': 12.34},
    {'event': 'end', 'what': 'fit plan-ALLP-1001', 'ok': True, 'seconds': 1800.0, 'peak_gb': 30.5},
    {'event': 'peak', 'what': 'fit plan-ALLP-1001', 'peak_gb': 14.06},
    {'event': 'end', 'what': 'compute', 'ok': False, 'seconds': 3600.0, 'peak_gb': 9.95},
    {'event': 'end', 'what': 'fit plan-ALLP-1002', 'ok': True, 'seconds': 60.0, 'peak_gb': 30.5},   # child failed:
    {'event': 'failed', 'what': 'plan-ALLP-1002', 'code': 1},                                      # end is ok
    {'event': 'stop', 'what': 'plan-ALLP-1003', 'reason': 'code changed'},
]


def _write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == '.jsonl':
        path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in obj), encoding='utf-8')
    else:
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding='utf-8')


def build_root(root: Path, full: bool = True):
    """A repository tree with the artifacts of REES46 and Tinkoff (full) or with the journals only."""
    rees = root / R.REES46_RUNS
    tink = root / 'council' / 'runs' / 'xfer-tinkoff'
    _write(rees / 'prereg-0.json', {'select_queries_expected': 15605, 'explore_queries': 15759, 'sigma_q': 0.0634373,
                                    'rehearsal': {'power': 0.5235, 'gate': False,
                                                  'sd_t_interval': [0.3667125, 0.8476492]}})
    _write(rees / 'llm.jsonl', LLM_REES46)
    _write(root / R.REES46_FITS, [fit_record('path_Hr_full_val_s0', 21.0, 83, 648, 79),
                                  fit_record('plan_r01', 99.9), fit_record('plan_r01', 19.2),   # the last one counts
                                  fit_record('plan_r02', 22.54),
                                  fit_record('cval_Hrp_s0', 23.1, 100, 700, 100),
                                  fit_record('cval_ALLP_s0', 23.96, 100, 800, 100)])
    _write(rees / 'memory.jsonl', [{'arm': 'Hrp', 'recipe': 'full_test', 'peak_rss_gb': 24.04,
                                    'seconds': {'prepare': 111, 'fit': 851}}])
    _write(tink / 'llm.jsonl', LLM_XFER)
    _write(tink / 'queue.jsonl', QUEUE_XFER)
    if full:
        _write(rees / 'plan-result.json', plan_result())
        _write(rees / 'selection.json', {'SEL': 'ALL_P', 'D': [], 'reason': 'prereg-0: power gate failed',
                                         'twin_arm': {'family': 'F1', 'card': 'G1-1',
                                                      'replace': ['council_g1_1', 'council_g1_1_tw']}})
        _write(rees / 'val.json', VAL)
        _write(rees / 'queue-plan.json', [{'name': 'plan_r01'}, {'name': 'plan_r02'}])
        _write(rees / 'queue-test.json', [{'name': 'ctest_Hrp_s0'}, {'name': 'ctest_ALLP_s0'}])
        _write(rees / 'queue-cval.json', [{'name': 'cval_Hrp_s0'}, {'name': 'cval_ALLP_s0'}, {'name': 'cval_TWIN_s0'}])
        _write(rees / 'test.json', TEST_REES46)
        _write(tink / 'prereg-0.json', {'select_queries_expected': 5000, 'explore_queries': 5100, 'sigma_q': 0.11,
                                        'power': 0.3149, 'gate': False, 'path_ok': True, 'peak_gb': 12.34,
                                        'rehearsal': {'power': 0.3149, 'gate': False, 'sd_t_interval': [0.4, 0.9]}})
        _write(tink / 'plan-result.json', plan_result(xfer=True))
        _write(tink / 'selection.json', {'SEL': 'ALL_P', 'D': [], 'nominated': [], 'reason': 'power gate failed',
                                         'confirmation': None, 'cut': [], 'cut_plan': False,
                                         'twin_arm': {'family': 'F1', 'card': 'G1-1', 'replace': ['a', 'b']}})
        _write(tink / 'test.json', TEST_XFER)


COSTS_TEMPLATE = '''| Этап | Время | Пик памяти |
|---|---|---|
| план: 48 подгонок `plan` | ⟨ждёт plan-result⟩ | ⟨ждёт plan-result⟩ |
| C_val: 9 новых подгонок `full_val`, H+r на 2026/0 — подгонка пути | ⟨ждёт val.json⟩ | ⟨ждёт val.json⟩ |
| C_test: 10 подгонок `full_test` | ⟨ждёт C_test, нужно «да»⟩ | ⟨ждёт C_test, нужно «да»⟩ |'''


def snapshot(root: Path) -> dict:
    return {str(p): (p.stat().st_mtime_ns, p.stat().st_size) for p in sorted(root.rglob('*'))}


def run_main(argv) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = R.main(argv)
    return code, out.getvalue()


class ReportCase(unittest.TestCase):
    full = True

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='tlab-report-test-', dir='/tmp'))
        build_root(self.root, self.full)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)


class FormatTest(unittest.TestCase):
    def test_rounding_and_signs(self):
        self.assertEqual(R.beta(0.00123456), '+0.0012')
        self.assertEqual(R.beta(-0.00098765), '−0.0010')
        self.assertEqual(R.beta(-0.00001), '0.0000')           # a rounded zero has no sign
        self.assertEqual(R.se(0.00045678), '0.0005')
        self.assertEqual(R.tval(-2.3456), '−2.35')
        self.assertEqual(R.pval(0.0123), '0.012')
        self.assertEqual(R.usd(16.750856), '16.75')
        self.assertEqual(R.gb(22.54), '22.5')
        self.assertEqual(R.hours(5400), '1.5')
        self.assertEqual(R.beta(None), '—')
        self.assertEqual(R.beta(float('nan')), '—')

    def test_numbers_skip_names_and_read_minus(self):
        got = R.numbers('| F12 | G3-4 | Rb1 | −0.0012 | [+0.0010, 0.0030] | 2026-10-22 | 15605 | $5.44 | 24.0 ГБ. |')
        self.assertEqual(got, [Decimal('-0.0012'), Decimal('0.001'), Decimal('0.003'), Decimal('15605'),
                               Decimal('5.44'), Decimal('24.0')])


class TablesTest(ReportCase):
    def test_rees46_beta_table(self):
        t = R.render('rees46', 'beta', self.root)
        self.assertIn('| F1 | G1-1 | +0.0012 | 0.0005 | +2.70 | 0.510 |', t)
        self.assertIn('| PL | placebo | −0.0010 | 0.0004 | −2.47 | 0.012 |', t)
        self.assertRegex(t, r'\| E6 \| empty \| [^|]+ \| [^|]+ \| [^|]+ \| — \|')   # no WY p for an empty column
        self.assertIn('запросов 15605, пользователей 13958', t)
        self.assertIn('SE_empty = 0.0003', t)
        self.assertEqual(t.count('\n| '), len(COLUMNS) + 1)

    def test_small_se_plan_prints_six_decimals(self):
        res = plan_result()
        for b in res['beta'].values():
            b['beta'] /= 20; b['se'] /= 20
        res['se_empty'] /= 20
        res['mechanism'][0] |= {'beta': 0.000123456, 'se': 0.00004}
        _write(self.root / R.REES46_RUNS / 'plan-result.json', res)
        t = R.render('rees46', 'beta', self.root)
        self.assertIn('| F1 | G1-1 | +0.000062 | 0.000023 | +2.70 | 0.510 |', t)
        self.assertIn('SE_empty = 0.000016', t)
        self.assertIn('| F1 | T1 | +0.000123 | +0.000200 | +0.001035 | 0.000040 |', R.render('rees46', 'mechanism', self.root))
        self.assertEqual(R.plan_nd(plan_result()), 4)              # the usual plan keeps 4 decimals
        self.assertEqual(R.plan_nd({'beta': {}}), 4)                # nothing to judge by
        small = {c: {'se': 2e-5} for c in COLUMNS} | {'E6': {'se': None}, 'E5': {'se': float('nan')}}
        self.assertEqual(R.plan_nd({'beta': small}), 6)             # non-finite SE are skipped

    def test_rees46_calibration_mechanism_selection(self):
        t = {n: R.render('rees46', n, self.root) for n in R.PARTS}
        plan = R.tables('rees46', self.root)['plan']
        for n in R.PARTS:
            self.assertIn(t[n], plan)                              # plan = the four parts, in order
        self.assertIn('| 0.612 | [0.367, 0.848] | 0.432 | пройдена |', t['calibration'])
        self.assertIn('| F1 | T1 | +0.0012 | +0.0002 | +0.0010 | 0.0004 | +2.59 | +2.70 | ждёт C_val |', t['mechanism'])
        self.assertIn('Рука-близнец: F1', t['mechanism'])
        self.assertIn('| SEL | ALL_P |', t['selection'])
        self.assertIn('| D | пусто |', t['selection'])
        self.assertIn('| карточка близнеца | G1-1 |', t['selection'])

    def test_rees46_prereg(self):
        t = R.tables('rees46', self.root)['prereg']
        self.assertIn('| мощность плана | 0.52 |', t)
        self.assertIn('| гейт мощности (≥ 0.8) | не пройден |', t)
        self.assertIn('[0.367, 0.848]', t)
        self.assertIn('| σ_q | 0.0634 |', t)

    def test_rees46_val_contrasts_with_ci(self):
        t = R.tables('rees46', self.root)
        self.assertIn('| SEL − H+r⁺ (главный, описательно) | +0.0007 | [+0.0001, +0.0013] | +0.0006, +0.0008 |', t['cval'])
        self.assertIn('| H+r⁺ − H+r (кривая объёма) | −0.0005 | [−0.0011, 0.0000] | −0.0005, −0.0005 |', t['cval'])
        self.assertIn('C_val: запросов 34567', t['cval'])
        self.assertIn('F1 +0.0004): механизм установлен', t['cval'])
        self.assertIn('| cval_ALLP_s0 | 0.1479 |', t['cval-mean'])

    def test_rees46_test_two_slices(self):
        t = R.tables('rees46', self.root)['test']
        self.assertIn('| C_test (основной) | +0.0021 | +0.0011 | +0.0032 | 4/4 | обыгрывает H+ |', t)
        self.assertIn('| C_test (все 16 дней) |', t)
        self.assertIn('| ALL_P − H+r | +0.0031 | [+0.0021, +0.0041] | +0.0030, +0.0032 |', t)
        self.assertIn('C_test (основной) 50001', t)
        self.assertTrue(t.startswith('Запросов: '))                   # REES46 test.json has no `test` phrase
        self.assertIn('по парам зёрен', t)

    def test_xfer_tables(self):
        t = R.tables('tinkoff', self.root)
        self.assertNotIn('cval', t)
        self.assertIn(R.render('tinkoff', 'beta', self.root), t['plan'])
        self.assertIn('| мощность плана | 0.31 |', t['prereg'])
        self.assertIn('| пик пути и шума, ГБ | 12.3 |', t['prereg'])
        self.assertIn('D (номинированы планом): пусто', t['plan'])
        self.assertIn('| номинированы | пусто |', t['plan'])
        self.assertIn('| C_test | +0.0021 | −0.0004 | +0.0032 | 4/4 | не различено |', t['test'])
        self.assertIn('| SEL − H+r | +0.0015 | [+0.0005, +0.0025] | +0.0014, +0.0016 |', t['test'])
        self.assertIn('класс: механизм установлен', t['test'])
        self.assertIn('Класс до C_test', t['plan'])
        self.assertIn('| Контраст | Δ | 95% CI | по зёрнам |', t['test'])
        self.assertIn('| интервал SD t пустых (2.5–97.5%) (prereg-0, раскладка 12/4) | [0.400, 0.900] |', t['prereg'])
        self.assertIn('| план не запускался (cut_plan) | нет |', t['plan'])
        _write(self.root / 'council/runs/xfer-tinkoff/prereg-2.json', {'rehearsal': {'sd_t_interval': [0.41, 0.95]}})
        self.assertIn('| интервал SD t пустых (2.5–97.5%) (prereg-2) | [0.410, 0.950] |',
                      R.render('tinkoff', 'prereg', self.root))

    def test_xfer_cut_plan_without_plan_result(self):
        d = self.root / 'council/runs/xfer-tinkoff'
        (d / 'plan-result.json').unlink()
        sel = json.loads((d / 'selection.json').read_text()) | {'cut_plan': True, 'twin_arm': {'family': None}}
        _write(d / 'selection.json', sel)
        t = R.render('tinkoff', 'plan', self.root)
        self.assertTrue(t.startswith('План не запускался (cut_plan)'))
        self.assertIn('| план не запускался (cut_plan) | да |', t)
        self.assertIn('| SEL | ALL_P |', t)

    def test_rees46_stage_costs(self):
        t = R.tables('rees46', self.root)['costs']
        self.assertIn('| план: 2 подгонок `plan` | 0.2 ч | 22.5 ГБ |', t)          # plan_r01 last record: 19.2, not 99.9
        self.assertIn('| C_val: 3 новых подгонок `full_val`, H+r на 2026/0 — подгонка пути | 0.5 ч (записей 2 из 3) '
                      '| 24.0 ГБ |', t)
        self.assertIn('| C_test: 2 подгонок `full_test` | — (записей 0 из 2) | — |', t)
        self.assertNotIn('99.9', t)
        self.assertNotIn('16.75', t)                                    # LLM costs live in the llm table

    def test_rees46_llm_and_fits(self):
        t = R.tables('rees46', self.root)
        self.assertIn('| wave1 | 2 | 1.0 | 2.47 |', t['llm'])             # 1.2652 + 1.2022, summed directly
        self.assertIn('| всего | 3 | 1.1 | 2.97 |', t['llm'])
        self.assertIn('| plan | 2 | 0.2 | 22.5 |', t['fit-runs'])
        self.assertIn('| path | 1 | 0.2 | 21.0 |', t['fit-runs'])
        self.assertIn('| cval | 2 | 0.5 | 24.0 |', t['fit-runs'])
        self.assertIn('| всего | 5 | 0.9 | 24.0 |', t['fit-runs'])
        self.assertIn('| проба памяти Hrp (full_test) | 1 | 0.3 | 24.0 |', t['fit-runs'])
        self.assertNotIn('99.9', t['fit-runs'])

    def test_xfer_costs(self):
        t = R.tables('tinkoff', self.root)
        self.assertIn('| wave1 | 1 | 0.1 | 0.93 |', t['llm'])
        self.assertIn('| всего | 2 | 0.2 | 1.74 |', t['llm'])          # 0.93 + 0.8149; the started rows cost nothing
        self.assertIn('Начато без записи результата (идут или оборваны): 1.', t['llm'])
        c = t['costs']
        self.assertIn('| probe reference | 2 | 0.0 | 6.1 |', c)
        self.assertIn('| fit: path_select | 1 | 0.5 | 12.3 |', c)      # the fit record peak, not the queue lifetime peak
        self.assertIn('| fit: plan | 2 | 0.5 | 30.5 |', c)        # no `peak` event for the failed fit: its end peak
        self.assertIn('| compute | 1 | 1.0 | 9.9 |', c)
        self.assertIn('| тяжёлые шаги: всего | 4 | 2.0 | 30.5 |', c)
        self.assertIn('Ошибок и остановов (end/light-end не ok, failed, stop): 3.', c)   # compute end, failed, stop
        self.assertIn(R.LLM_NOTE, t['llm'])

    def test_broken_journal_line_is_skipped(self):
        p = self.root / R.REES46_RUNS / 'llm.jsonl'
        p.write_text(p.read_text() + '{"stage": "wave1", "cost_usd": 9')
        with contextlib.redirect_stderr(io.StringIO()) as err:
            t = R.tables('rees46', self.root)['llm']
        self.assertIn('| всего | 3 | 1.1 | 2.97 |', t)
        self.assertIn('broken', err.getvalue())

    def test_cli_prints_blocks_and_writes_nothing(self):
        before = snapshot(self.root)
        code, out = run_main(['rees46', '--root', str(self.root)])
        self.assertEqual(code, 0)
        self.assertIn('<!-- report:rees46:plan -->', out)
        self.assertEqual(out.count('<!-- /report -->'), len(R.TABLES['rees46']))
        code, out = run_main(['rees46', '--table', 'beta', '--root', str(self.root)])
        self.assertEqual(out.count('<!-- report:rees46:beta -->'), 1)
        code, out = run_main(['tinkoff', '--dry', '--table', 'costs', '--root', str(self.root)])
        self.assertEqual(code, 0)
        self.assertIn('Входы tinkoff', out)
        self.assertIn('### tinkoff: costs', out)
        self.assertNotIn('<!--', out)
        self.assertEqual(snapshot(self.root), before)


class PlaceholderTest(ReportCase):
    full = False

    def test_missing_artifacts_give_placeholders(self):
        t = R.tables('rees46', self.root)
        for name, w in (('plan', '⟨ждёт plan-result⟩'), ('cval', '⟨ждёт val.json⟩'), ('cval-mean', '⟨ждёт val.json⟩'),
                        ('test', '⟨ждёт C_test, нужно «да»⟩')):
            self.assertEqual(t[name], w)
        for name in R.PARTS[:3]:
            self.assertEqual(R.render('rees46', name, self.root), '⟨ждёт plan-result⟩')
        self.assertEqual(R.render('rees46', 'selection', self.root), '⟨ждёт selection.json⟩')
        self.assertIn('| мощность плана | 0.52 |', t['prereg'])
        x = R.tables('tinkoff', self.root)
        self.assertEqual(x['prereg'], '⟨ждёт prereg-0.json⟩')
        self.assertEqual(x['test'], '⟨ждёт C_test, нужно «да»⟩')

    def test_costs_block_while_waiting_is_the_report_template(self):
        self.assertEqual(R.tables('rees46', self.root)['costs'], COSTS_TEMPLATE)
        p = self.root / 'doc.md'
        p.write_text('<!-- report:rees46:plan -->\n⟨ждёт plan-result⟩\n<!-- /report -->\n\n'
                     '<!-- report:rees46:cval -->\n⟨ждёт val.json⟩\n<!-- /report -->\n\n'
                     f'<!-- report:rees46:costs -->\n{COSTS_TEMPLATE}\n<!-- /report -->\n', encoding='utf-8')
        code, out = run_main(['--check', '--doc', str(p), '--root', str(self.root)])
        self.assertEqual(code, 0, out)

    def test_dataset_without_a_directory(self):
        t = R.tables('sber', self.root)
        self.assertEqual(t['prereg'], '⟨ждёт prereg-0.json⟩')
        self.assertEqual(t['llm'], '⟨ждёт llm.jsonl⟩')
        self.assertEqual(t['costs'], '⟨ждёт queue.jsonl⟩')
        code, out = run_main(['sber', '--dry', '--root', str(self.root)])
        self.assertEqual(code, 0)
        self.assertIn('llm.jsonl: нет', out)


class CheckTest(ReportCase):
    def doc(self, text):
        p = self.root / 'docs' / 'report.md'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        return p

    def check(self, text, *extra):
        return run_main(['--check', '--doc', str(self.doc(text)), '--root', str(self.root), *extra])

    def test_generated_blocks_pass(self):
        text = '# Отчёт\n\nПроза 0.5 вне блоков не сверяется.\n\n' + R.blocks('rees46', self.root) + '\n\n' + \
               R.blocks('tinkoff', self.root, 'costs') + '\n'
        code, out = self.check(text)
        self.assertEqual(code, 0, out)
        self.assertIn('ok report:rees46:plan', out)
        self.assertIn('check: ok', out)

    def test_ordinary_words_may_change_vocabulary_and_numbers_may_not(self):
        block = R.blocks('rees46', self.root, 'calibration')
        self.assertTrue(block.startswith('<!-- report:rees46:calibration -->'))
        code, out = self.check(block.replace('калибровка', 'итог').replace('интервал репетиции', 'интервал'))
        self.assertEqual(code, 0, out)
        code, out = self.check(block.replace('пройдена', 'не пройдена'))
        self.assertEqual(code, 1)
        self.assertIn('vocabulary: 1 in the document, 1 generated; first difference at 1: не пройдена != пройдена', out)
        code, out = self.check(R.blocks('rees46', self.root, 'test').replace('обыгрывает H+', 'уступает', 1))
        self.assertEqual(code, 1)
        code, out = self.check(R.blocks('rees46', self.root, 'selection').replace('| SEL | ALL_P |', '| SEL | ALL_P minus D |'))
        self.assertEqual(code, 1)
        code, out = self.check(block.replace('0.612', '0.613'))
        self.assertEqual(code, 1)
        self.assertIn('MISMATCH report:rees46:calibration', out)
        self.assertIn('0.613 != 0.612', out)
        self.assertIn('+++ generated report:rees46:calibration', out)

    def test_stale_placeholder_fails(self):
        code, out = self.check('<!-- report:rees46:cval -->\n⟨ждёт val.json⟩\n<!-- /report -->\n')
        self.assertEqual(code, 1)
        self.assertIn('MISMATCH report:rees46:cval', out)
        code, out = self.check('<!-- report:rees46:selection -->\n⟨ждёт selection.json⟩\n<!-- /report -->\n')
        self.assertEqual(code, 1)                                    # selection.json exists: the placeholder is stale
        self.assertIn('waiting lines: 1 in the document, 0 generated', out)

    def test_waiting_words_must_match(self):
        shutil.rmtree(self.root / 'council' / 'runs' / 'xfer-tinkoff')
        code, out = self.check('<!-- report:tinkoff:test -->\n⟨ждёт test.json⟩\n<!-- /report -->\n')
        self.assertEqual(code, 1)                                    # generated: ⟨ждёт C_test, нужно «да»⟩

    def test_no_blocks_fail(self):
        code, out = self.check('# Отчёт без блоков\n')
        self.assertEqual(code, 1)
        self.assertIn('no report blocks', out)
        code, out = self.check(R.blocks('rees46', self.root, 'prereg'), 'sber')
        self.assertEqual(code, 1)
        self.assertIn('no report blocks of sber', out)

    def test_unknown_table_and_unclosed_block_fail(self):
        code, out = self.check('<!-- report:rees46:nope -->\n1\n<!-- /report -->\n')
        self.assertEqual(code, 1)
        self.assertIn('unknown block report:rees46:nope', out)
        code, out = self.check('<!-- report:tinkoff:cval -->\n<!-- /report -->\n')
        self.assertEqual(code, 1)                                    # xfer has no C_val table
        code, out = self.check(R.blocks('rees46', self.root, 'prereg') + '\n<!-- report:rees46:beta -->\n| 1 |\n')
        self.assertEqual(code, 1)
        self.assertIn('opening markers', out)

    def test_placeholder_blocks_pass_while_waiting(self):
        shutil.rmtree(self.root / 'council' / 'runs' / 'xfer-tinkoff')
        code, out = self.check(R.blocks('tinkoff', self.root, 'test'))
        self.assertEqual(code, 0, out)

    def test_dataset_filter(self):
        bad = R.blocks('rees46', self.root, 'prereg').replace('0.52', '0.99')
        code, _ = self.check(bad + '\n\n' + R.blocks('tinkoff', self.root, 'prereg'), 'tinkoff')
        self.assertEqual(code, 0)


class BoundaryTest(unittest.TestCase):
    FORBIDDEN = {'broker', 'y_select', 'c_val', 'c_test', 'final_labels', 'open_labels', 'sealed'}

    def setUp(self):
        self.tree = ast.parse(Path(R.__file__).read_text(encoding='utf-8'))

    def test_no_forbidden_import_or_call(self):
        used = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    used |= set(a.name.split('.')) | {a.asname or ''}
            elif isinstance(node, ast.ImportFrom):
                used |= set((node.module or '').split('.')) | {a.name for a in node.names}
            elif isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                used.add(node.attr)
            elif isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute)):
                used.add(getattr(node.func, 'id', None) or node.func.attr)
        self.assertEqual(used & self.FORBIDDEN, set())

    def test_imports_nothing_that_reads_data(self):
        mods = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                mods |= {a.name.split('.')[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                mods.add((node.module or '').split('.')[0])
        self.assertEqual(mods & {'council', 'task1', 'scripts', 'duckdb', 'pandas', 'pyarrow', 'numpy'}, set())

    def test_no_path_to_labels_or_parquet(self):
        consts = [n.value for n in ast.walk(self.tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        for s in consts:
            self.assertNotIn('sealed', s)
            self.assertNotIn('.parquet', s)
            self.assertNotIn('reads.jsonl', s)


    def test_reads_only_allowlisted_json_and_writes_nothing(self):
        allowed = {'prereg-0.json', 'prereg-2.json', 'plan-result.json', 'selection.json', 'val.json', 'test.json',
                   'llm.jsonl', 'memory.jsonl', 'runs.jsonl', 'queue.jsonl', 'queue-plan.json', 'queue-cval.json',
                   'queue-test.json'}
        consts = [n.value for n in ast.walk(self.tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        named = {m for c in consts for m in re.findall(r'[\w.-]+\.jsonl?(?!\w)', c)}
        self.assertLessEqual(named, allowed)
        for c in consts:
            self.assertNotIn('duckdb', c.lower())
        calls = {getattr(n.func, 'id', None) or getattr(n.func, 'attr', None)
                 for n in ast.walk(self.tree) if isinstance(n, ast.Call)}
        attrs = {n.attr for n in ast.walk(self.tree) if isinstance(n, ast.Attribute)}
        writes = {'open', 'write_text', 'write_bytes', 'mkdir', 'unlink', 'rename', 'touch', 'rmdir', 'remove',
                  'system', 'popen', 'run'}
        self.assertEqual((calls | attrs) & writes, set())        # files are read with Path.read_text only
        self.assertIn('read_text', attrs)


def _cells(text: str) -> list[list[str]]:
    """Body rows of every markdown table in a text: lines '| ...' except a header (the line before '|---')."""
    lines = text.splitlines()
    return [[c.strip() for c in line.strip('|').split(' | ')] for i, line in enumerate(lines)
            if line.startswith('| ') and not (i + 1 < len(lines) and lines[i + 1].startswith('|---'))]


class WriterContractTest(unittest.TestCase):
    """JSON produced by the real pure functions of the writers (council.xfer.plan.estimate, design.calibrate,
    design.mechanism through estimate, design.h1, design.confirm, plan._contrast, xfer.plan._contrast,
    mechanism_repeat, mechanism_class, twin_arm) renders without a dash in the key cells."""

    @classmethod
    def setUpClass(cls):
        import numpy as np
        import pandas as pd
        from council import design as D, plan as P
        from council.xfer import plan as XP
        cls.root = Path(tempfile.mkdtemp(prefix='tlab-report-test-', dir='/tmp'))
        rng = np.random.default_rng(7)
        n_q = 300
        qids = pd.Index([f'q{i}:u{i % 120}' for i in range(n_q)], name='qid')
        users = D.users_of(qids)
        eff = np.zeros(len(D.COLUMNS))
        eff[D.COLUMNS.index('F1')], eff[D.COLUMNS.index('PL')] = 0.02, -0.02
        base = rng.normal(0.15, 0.05, (n_q, 1))
        y = pd.DataFrame(base + D.matrix() @ eff + rng.normal(0, 0.01, (n_q, 48)), index=qids,
                         columns=[f'plan-r{r}' for r in range(1, 49)])
        fams = {f'F{k}': f'G{1 + (k - 1) % 4}-{1 + (k - 1) // 4}' for k in range(1, 13)}
        pre2 = {'families': fams, 'twins': {f'T{k}': {'family': f'F{k}', 'card': fams[f'F{k}']} for k in range(1, 5)},
                'empty': [f'E{k}' for k in range(1, 7)]}
        res = XP.estimate(y, pre2, (0.3, 1.2))
        tw = XP.twin_arm(pre2, res['mechanism'])

        def col(shift, name):
            return pd.Series(base[:, 0] + shift + rng.normal(0, 0.01, n_q), index=qids, name=name)

        conf = D.confirm([col(0, 'a7'), col(0, 'a11')], [col(0.002, 'm7'), col(0.002, 'm11')], groups=users, n_boot=200)
        sel = {'SEL': 'ALL_P', 'D': [], 'nominated': res['D'], 'reason': 'power gate failed', 'confirmation': conf,
               'twin_arm': tw, 'cut': [], 'cut_plan': False}
        arms = {'Hrp': 0.0, 'SEL': 0.003, 'Hr': -0.001, 'TWIN': 0.001, 'Rb1': 0.0, 'Rb2': 0.0005, 'ALLP': 0.003}
        yt = pd.DataFrame({f'test-{a}-{s}': col(sh, '') for a, sh in arms.items() for s in (7, 11, 13, 17)})
        fit = [f'test-SEL-{s}' for s in (7, 11)]
        rep = XP.mechanism_repeat(yt, fit, [f'test-TWIN-{s}' for s in (7, 11)], 1.0, n_boot=200)
        row = [m for m in res['mechanism'] if m['family'] == tw['family']][0]
        xtest = {'test': XP.REPEATED, 'queries': n_q, 'users': 120,
                 'h1': D.h1([yt[f'test-Hrp-{s}'] for s in (7, 11, 13, 17)], [yt[f'test-SEL-{s}'] for s in (7, 11, 13, 17)],
                            groups=users, n_boot=200),
                 'contrasts': {'SEL − H+r': XP._contrast(yt, ['test-Hr-7', 'test-Hr-11'], fit, users)},
                 'mechanism': {'family': tw['family'], 'card': tw['card'], 't_select': row['t'], 'diff': row['diff'],
                               'repeat': rep, 'class': XP.mechanism_class(row, rep['repeated'])}}
        yr = yt.rename(columns=lambda c: c.replace('test-', 'ctest_').replace('-7', '_s0').replace('-11', '_s1')
                       .replace('-13', '_s2').replace('-17', '_s3'))
        rslice = {'queries': n_q, 'h1': D.h1([yr[f'ctest_Hrp_s{i}'] for i in range(4)],
                                             [yr[f'ctest_ALLP_s{i}'] for i in range(4)], groups=users, n_boot=200),
                  'ALL_P − H+r': P._contrast(yr, ['ctest_Hr_s0', 'ctest_Hr_s1'], ['ctest_ALLP_s0', 'ctest_ALLP_s1'], users)}
        val = {'queries': n_q, 'mean': {c: float(yr[c].mean()) for c in yr.columns[:3]},
               'contrasts': {'SEL − H+r⁺': P._contrast(yr, ['ctest_Hrp_s0', 'ctest_Hrp_s1'],
                                                       ['ctest_ALLP_s0', 'ctest_ALLP_s1'], users)}}

        def put(rel, obj):    # the writers' own serialization: json.dumps(..., default=float)
            path = cls.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=float), encoding='utf-8')

        for d in ('council/runs/xfer-tinkoff', R.REES46_RUNS):
            put(f'{d}/plan-result.json', res)
            put(f'{d}/selection.json', sel)
        put('council/runs/xfer-tinkoff/test.json', xtest)
        put(f'{R.REES46_RUNS}/test.json', {'primary': rslice, 'all_16_days': rslice})
        put(f'{R.REES46_RUNS}/val.json', val)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_plan_cells(self):
        for ds in ('rees46', 'tinkoff'):
            beta = _cells(R.render(ds, 'beta', self.root))
            self.assertEqual(len(beta), 23)
            for r in beta:
                self.assertNotIn('—', r[2:5], (ds, r))
                if r[0].startswith('F') or r[0] == 'PL':
                    self.assertNotEqual(r[5], '—', (ds, r))
            for name in ('calibration', 'mechanism'):
                rows = _cells(R.render(ds, name, self.root))
                self.assertTrue(rows)
                for r in rows:
                    self.assertNotIn('—', r, (ds, name, r))
            self.assertNotIn('Рука-близнец: нет', R.render(ds, 'mechanism', self.root))
        sel = R.render('tinkoff', 'selection', self.root)
        self.assertRegex(sel, r'подтверждение D \| Δ = [+−]\d\.\d{4}, SE = \d\.\d{4}, t = [+−]?\d+\.\d{2}, (да|нет)')

    def test_test_and_cval_cells(self):
        for ds, name in (('tinkoff', 'test'), ('rees46', 'test'), ('rees46', 'cval'), ('rees46', 'cval-mean')):
            t = R.render(ds, name, self.root)
            rows = _cells(t)
            self.assertTrue(rows, (ds, name))
            for r in rows:
                self.assertNotIn('—', r, (ds, name, r))
            self.assertNotIn('None', t)
        x = R.render('tinkoff', 'test', self.root)
        self.assertRegex(x, r'SEL − близнец на C_test [+−]\d\.\d{4} \[[+−]?\d\.\d{4}, [+−]?\d\.\d{4}\]')
        self.assertTrue(any(v in x for v in ('механизм установлен', 'не различено', 'форма без механизма')))


if __name__ == '__main__':
    unittest.main()
