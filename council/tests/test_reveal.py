"""council.reveal on synthetic JSON under /tmp/tlab-reveal-test-*: H3 signs against beta-hat (share of beta > 0,
t counts, Spearman with exact and Monte Carlo permutation p, the degenerate constant-sign case), H2 seed SE from the
empty columns, H1' ratio with the delta-method interval, H14 importance (fit records only, the xfer sandbox names),
the schema of the committed REES46 prereg-0/1/2, the xfer layout (PL empty, fewer families), waiting lines,
--write touching only reveal.json, and an AST/grep guard that the module reads JSON only."""
import ast
import contextlib
import io
import json
import math
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from scipy import stats

from council import reveal as R

FAMS = {f'F{k + 1}': f'G{1 + k % 4}-{1 + k // 4}' for k in range(12)}
EMPTY = [f'E{i}' for i in range(1, 7)]
COLUMNS = list(FAMS) + [f'T{i}' for i in range(1, 5)] + ['PL'] + EMPTY
BETAS = [0.0012, -0.0004, 0.0003, 0.0009, -0.0011, 0.0002, 0.0006, -0.0001, 0.0015, -0.0007, 0.0004, 0.0001]
SIGNS = ['+', '-', '+', '+', '-', '+', '-', '+', '+', '-', '-', '+']
SE_EMPTY = 0.0003
SE_BOOT = 0.0002
REAL = R.ROOT / 'council' / 'runs' / 'rees46-2020'


def _write(path: Path, obj, jsonl=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = '\n'.join(json.dumps(r) for r in obj) + '\n' if jsonl else json.dumps(obj, ensure_ascii=False)
    path.write_text(text, encoding='utf-8')


def plan_result(betas=BETAS, se_empty=SE_EMPTY, se_boot=SE_BOOT, se_boot_other=None, columns=COLUMNS, empty=EMPTY,
                fams=FAMS):
    """beta per column; se = sqrt(se_boot^2 + se_empty^2) with se_boot of the empty columns `se_boot` and of the
    other columns `se_boot_other` (default the same)."""
    beta = {}
    other = se_boot if se_boot_other is None else se_boot_other
    for c in columns:
        b = betas[int(c[1:]) - 1] if c.startswith('F') and c not in empty else 0.0001 * (len(c) - 1)
        se = math.sqrt((se_boot if c in empty else other) ** 2 + se_empty ** 2)
        what = 'empty' if c in empty else fams.get(c, 'placebo' if c == 'PL' else 'tw')
        beta[c] = {'what': what, 'beta': b, 'se': se, 't': b / se}
    return {'queries': 100, 'users': 90, 'beta': beta, 'se_empty': se_empty}


def cards(signs=SIGNS, fams=FAMS):
    return {'cards': [{'id': cid, 'lens': cid.split('-')[0], 'name': cid, 'sign': s}
                      for (f, cid), s in zip(fams.items(), signs)] + [{'id': 'G9-9', 'lens': 'G9', 'sign': '-'}],
            'withdrawn': [], 'code_sha256': {}}


def card_columns(cid):
    lens, n = cid[1], cid.split('-')[1]
    return [f'f_x_c{lens}_fam{n}_a', f'f_x_c{lens}_fam{n}_b']


VAL = {'queries': 50, 'mean': {}, 'contrasts': {
    'SEL − H+r⁺ (главный, описательно)': {'d': 0.0001, 'ci95': [-0.0002, 0.0004], 'by_pair': [0.0, 0.0002]},
    'ALL_P − H+r (вклад совета)': {'d': 0.0012, 'ci95': [0.0004, 0.0020], 'by_pair': [0.0010, 0.0014]}}}


class Base(unittest.TestCase):
    dataset = 'rees46'

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='tlab-reveal-test-'))
        self.runs = R.runs_dir(self.dataset, self.root)
        self.runs.mkdir(parents=True)
        self.fits = self.root / 'fits' / 'runs.jsonl'

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def full(self, signs=SIGNS, betas=BETAS, val=True, **kw):
        _write(self.runs / 'prereg-0.json', {'select_queries_expected': 400,
                                             'rehearsal': {'se_boot': SE_BOOT, 'sd_t_interval': [0.36, 0.85]}})
        _write(self.runs / 'prereg-1.json', cards(signs))
        _write(self.runs / 'prereg-2.json', {'families': FAMS, 'empty': EMPTY, 'columns': COLUMNS})
        _write(self.runs / 'plan-result.json', plan_result(betas, **kw))
        _write(self.runs / 'curation.json', {'families': list(FAMS.values()),
                                             'columns': {cid: card_columns(cid) for cid in FAMS.values()}})
        if val:
            _write(self.runs / 'val.json', VAL)

    def run_reveal(self, ds=None):
        return R.reveal(ds or self.dataset, self.root, self.fits)


class TestH3(Base):
    def test_mixed_signs(self):
        self.full()
        h = self.run_reveal()['H3']
        x = [1 if s == '+' else -1 for s in SIGNS]
        a = h['all']
        self.assertFalse(h['degenerate'])
        self.assertIn('перестановочный p Spearman', h['note'])
        self.assertEqual(a['n'], 12)
        self.assertAlmostEqual(a['spearman'], stats.spearmanr(x, BETAS).statistic, places=12)
        self.assertEqual(a['agree'], sum(1 for s, b in zip(x, BETAS) if s * b > 0))
        pos = sum(1 for b in BETAS if b > 0)
        self.assertAlmostEqual(a['share_positive'], pos / 12)
        self.assertIn(f"{pos / 12:.2f}", h['note'])
        se = math.sqrt(SE_BOOT ** 2 + SE_EMPTY ** 2)
        self.assertEqual(a['n_t_above_2'], sum(1 for b in BETAS if b / se > 2))
        self.assertEqual(a['n_t_below_minus_2'], sum(1 for b in BETAS if b / se < -2))
        self.assertEqual(sorted(h['by_lens']), ['G1', 'G2', 'G3', 'G4'])
        self.assertTrue(all(b['n'] == 3 for b in h['by_lens'].values()))
        self.assertEqual(h['cards_from'], 'prereg-1.json')
        self.assertTrue(0 < a['perm_p'] <= 1)
        md = R.markdown(self.run_reveal())
        self.assertIn('знак совпал', md)

    def test_exact_permutation_p(self):
        # n = 3, x = (-1, 1, 1), y increasing: rho = sqrt(3)/2; 4 of the 6 orderings reach it in absolute value
        self.assertAlmostEqual(R.spearman([-1, 1, 1], [1, 2, 3]), math.sqrt(3) / 2, places=12)
        self.assertAlmostEqual(R.permutation_p([-1, 1, 1], [1, 2, 3]), 4 / 6, places=12)
        # n = 4, perfect monotone: 2 of 24 orderings reach |rho| = 1
        self.assertAlmostEqual(R.permutation_p([1, 2, 3, 4], [10, 20, 30, 40]), 2 / 24, places=12)

    def test_monte_carlo_permutation_p_is_seeded(self):
        x, y = list(range(10)), [v * v for v in range(10)]
        p1, p2 = R.permutation_p(x, y, n_perm=500), R.permutation_p(x, y, n_perm=500)
        self.assertEqual(p1, p2)
        self.assertAlmostEqual(p1, 1 / 501, places=12)

    def test_constant_sign_is_degenerate(self):
        self.full(signs=['+'] * 12)
        h = self.run_reveal()['H3']
        a = h['all']
        self.assertTrue(h['degenerate'])
        self.assertEqual(h['note'], 'H3 не проверяема: все знаки «+»; ниже только доля β̂ > 0')
        self.assertTrue(a['degenerate'])
        self.assertIsNone(a['spearman'])
        self.assertIsNone(a['perm_p'])
        self.assertNotIn('agree', a)
        k = sum(1 for b in BETAS if b > 0)
        self.assertAlmostEqual(a['p_share_vs_half'], stats.binomtest(k, 12, 0.5, alternative='greater').pvalue)
        md = R.markdown(self.run_reveal())
        self.assertIn('H3 не проверяема', md)
        self.assertIn('доля β̂ > 0 против 1/2', md)
        self.assertNotIn('знак совпал', md)
        self.assertNotIn('Spearman', md)

    def test_cards_fallback_and_unknown_sign(self):
        self.full()
        (self.runs / 'prereg-1.json').unlink()
        c = cards()
        c['cards'][0]['sign'] = '?'
        _write(self.runs / 'cards-final.json', {'replies': {}, **c})
        h = self.run_reveal()['H3']
        self.assertEqual(h['cards_from'], 'cards-final.json')
        self.assertEqual(h['no_sign'], ['F1'])
        self.assertEqual(h['all']['n'], 11)

    def test_families_fallback_to_curation_and_empty_families_skipped(self):
        self.full()
        (self.runs / 'prereg-2.json').unlink()
        pr = plan_result()
        pr['beta']['F12']['what'] = 'empty'
        _write(self.runs / 'plan-result.json', pr)
        h = self.run_reveal()['H3']
        self.assertEqual(h['all']['n'], 11)


class TestH2(Base):
    def test_seed_se_from_empty_columns_only(self):
        self.full(se_boot_other=0.0009)          # families, twins and PL carry a larger bootstrap SE
        h = self.run_reveal()['H2']
        self.assertAlmostEqual(h['se_boot'], SE_BOOT, places=15)
        self.assertEqual(h['empty'], EMPTY)
        self.assertAlmostEqual(h['se_seed'], math.sqrt(SE_EMPTY ** 2 - SE_BOOT ** 2), places=15)
        self.assertAlmostEqual(h['ratio_empty_to_boot'], 1.5)
        self.assertAlmostEqual(h['share_of_variance_seed'], 1 - (SE_BOOT / SE_EMPTY) ** 2)
        self.assertEqual((h['n_empty'], h['df']), (6, 5))
        lo, hi = h['se_empty_ci95']
        self.assertAlmostEqual(lo, SE_EMPTY * math.sqrt(5 / stats.chi2.ppf(0.975, 5)))
        self.assertAlmostEqual(hi, SE_EMPTY * math.sqrt(5 / stats.chi2.ppf(0.025, 5)))
        self.assertLessEqual(h['se_seed_ci95'][0], h['se_seed'])
        self.assertGreaterEqual(h['se_seed_ci95'][1], h['se_seed'])
        self.assertEqual(h['rehearsal_se_boot'], SE_BOOT)
        self.assertAlmostEqual(h['rehearsal_se_boot_scaled'], SE_BOOT * 2)      # sqrt(400 / 100)
        self.assertIn('прогноз репетиции', R.markdown(self.run_reveal()))

    def test_root_mean_square_over_empties(self):
        self.full()
        pr = plan_result()
        for c, sb in zip(EMPTY, [0.0001, 0.0002, 0.0003, 0.0001, 0.0002, 0.0003]):
            pr['beta'][c]['se'] = math.sqrt(sb ** 2 + SE_EMPTY ** 2)
        _write(self.runs / 'plan-result.json', pr)
        h = self.run_reveal()['H2']
        self.assertAlmostEqual(h['se_boot'], math.sqrt((1 + 4 + 9) * 2 / 6) * 0.0001, places=15)

    def test_seed_se_floors_at_zero_and_prereg0_optional(self):
        self.full()
        _write(self.runs / 'plan-result.json', plan_result(se_empty=0.0001, se_boot=0.0002))
        (self.runs / 'prereg-0.json').unlink()
        h = self.run_reveal()['H2']
        self.assertEqual(h['se_seed'], 0.0)
        self.assertEqual(h['share_of_variance_seed'], 0.0)
        self.assertEqual(h['rehearsal_waiting'], '⟨ждёт prereg-0.json⟩')


class TestH1p(Base):
    def test_ratio_and_delta_interval(self):
        self.full()
        h = self.run_reveal()["H1'"]
        s = sum(BETAS)
        se_s = math.sqrt(12 * (SE_BOOT ** 2 + SE_EMPTY ** 2))
        r = 0.0012 / s
        self.assertEqual(h['label'], 'отношение d(C_val) / Σβ̂ (S0-select)')
        self.assertAlmostEqual(h['sum_beta'], s, places=15)
        self.assertAlmostEqual(h['se_sum_beta_no_cov'], se_s, places=15)
        self.assertAlmostEqual(h['ratio'], r, places=12)
        self.assertAlmostEqual(h['ratio_by_pair'][1], 0.0014 / s, places=12)
        self.assertEqual(h['ratio_numerator_ci95'], sorted([0.0004 / s, 0.0020 / s]))
        se_d = 0.0016 / 3.92
        se_r = math.sqrt(se_d ** 2 + r ** 2 * se_s ** 2) / abs(s)
        ap = h['ratio_ci95_delta_approx']
        self.assertAlmostEqual(ap['se_ratio'], se_r, places=12)
        self.assertAlmostEqual(ap['ci95'][0], r - 1.96 * se_r, places=12)
        self.assertIn('S0-select', h['differs'])
        self.assertIn('перенос', h['differs'])
        md = R.markdown(self.run_reveal())
        self.assertIn('приближённо', md)
        self.assertNotIn('коэффициент сжатия', md)

    def test_no_delta_interval_when_the_denominator_is_not_distinguished(self):
        self.full()
        _write(self.runs / 'plan-result.json', plan_result(se_boot=1.0))     # |Σβ̂| << 2 SE
        h = self.run_reveal()["H1'"]
        self.assertTrue(h['sum_beta_within_2se'])
        self.assertIsNone(h['ratio_ci95_delta_approx'])
        self.assertIn('дельта-метод неприменим', R.markdown(self.run_reveal()))

    def test_waiting_without_val(self):
        self.full(val=False)
        self.assertEqual(self.run_reveal()["H1'"]['waiting'], '⟨ждёт val.json⟩')


class TestH14(Base):
    def test_no_data_and_run_files_not_scanned(self):
        self.full()
        _write(self.fits, [{'name': 'plan_r01', 'features': 300, 'cfg': {'depth': 6}}], jsonl=True)
        _write(self.runs / 'probes.json', {'importance': {card_columns('G1-1')[0]: 5.0}})
        h = self.run_reveal()['H14']
        self.assertEqual(h['status'], 'нет данных')
        self.assertEqual(h['scanned'], ['runs.jsonl'])
        self.assertIn('council/fit.py', h['why'])

    def test_unreadable_file_is_not_an_error(self):
        self.full()
        (self.runs / 'broken.json').write_text('{not json', encoding='utf-8')
        h = R.h14(R.Inputs('rees46', self.root, self.fits), files=('broken.json', 'x.parquet'))
        self.assertEqual(h['status'], 'нет данных')
        self.assertEqual(h['unreadable'], ['broken.json', 'x.parquet'])

    def test_importance_against_beta(self):
        self.full()
        recs = []
        for r in range(2):
            imp = {card_columns(cid)[0]: 10.0 * (k + 1) + r for k, cid in enumerate(FAMS.values())}
            recs.append({'name': f'plan_r0{r + 1}', 'feature_importance': imp})
        _write(self.fits, recs, jsonl=True)
        h = self.run_reveal()['H14']
        self.assertEqual((h['maps'], h['n']), (2, 12))
        self.assertAlmostEqual(h['families'][0]['importance'], 10.5)
        x = [10.0 * (k + 1) + 0.5 for k in range(12)]
        self.assertAlmostEqual(h['spearman'], stats.spearmanr(x, BETAS).statistic, places=12)

    def test_xfer_sandbox_names(self):
        self.assertEqual(R.column_names('f_x_c3_flow_net_slog'), ('f_x_c3_flow_net_slog', 'ag_c3_flow_net_slog'))
        self.assertEqual(R.column_names('other'), ('other',))
        self.full()
        imp = {'ag_c' + c[len('f_x_c'):]: float(k) for k, cid in enumerate(FAMS.values()) for c in card_columns(cid)}
        _write(self.fits, [{'name': 'plan-r01-1001', 'council_columns': list(imp), 'importance': imp}], jsonl=True)
        h = self.run_reveal()['H14']
        self.assertEqual(h['n'], 12)
        self.assertEqual(h['families'][3]['importance'], 6.0)


class TestXferLayout(Base):
    dataset = 'tinkoff'

    def layout(self, n_fams):
        fams = {f'F{k + 1}': f'G{1 + k % 4}-{1 + k // 4}' for k in range(n_fams)}
        empty = [c for c in COLUMNS if c in set(list(FAMS)[n_fams:]) | set(EMPTY) | {'PL'}]
        _write(self.runs / 'prereg-0.json', {'select_queries_expected': 100, 'rehearsal': {'se_boot': SE_BOOT}})
        _write(self.runs / 'prereg-1.json', cards(['+'] * n_fams, fams))
        _write(self.runs / 'prereg-2.json', {'families': fams, 'empty': empty, 'columns': COLUMNS,
                                             'placebo': None})
        _write(self.runs / 'plan-result.json', plan_result(columns=COLUMNS, empty=empty, fams=fams))
        return fams, empty

    def test_twelve_families_pl_empty(self):
        _, empty = self.layout(12)
        res = self.run_reveal()
        self.assertEqual((res['H2']['n_empty'], res['H2']['df']), (7, 6))
        self.assertIn('PL', res['H2']['empty'])
        self.assertAlmostEqual(res['H2']['se_empty_ci95'][0], SE_EMPTY * math.sqrt(6 / stats.chi2.ppf(0.975, 6)))
        self.assertEqual(res['H3']['all']['n'], 12)
        self.assertNotIn('PL', [r['column'] for r in res['H3']['families']])
        self.assertEqual(res["H1'"], {'status': 'не применимо', 'why': 'в контракте xfer нет C_val'})
        self.assertIn("не применимо (в контракте xfer нет C_val)", R.markdown(res))

    def test_fewer_families(self):
        fams, empty = self.layout(10)
        res = self.run_reveal()
        self.assertEqual(res['H2']['n_empty'], 9)
        self.assertEqual([r['column'] for r in res['H3']['families']], list(fams))
        self.assertEqual(sorted(res['H3']['by_lens']), ['G1', 'G2', 'G3', 'G4'])
        self.assertEqual(res['H3']['by_lens']['G1']['n'], 3)
        self.assertEqual(res['H3']['by_lens']['G4']['n'], 2)


@unittest.skipUnless((REAL / 'prereg-2.json').exists(), 'committed REES46 preregs absent')
class TestCommittedRees46Schema(Base):
    """The committed prereg-0/1/2 and curation of REES46 (read as JSON, copied to /tmp) with a synthetic
    plan-result laid out on prereg-2."""

    def test_schema(self):
        for name in ('prereg-0.json', 'prereg-1.json', 'prereg-2.json', 'curation.json'):
            shutil.copy(REAL / name, self.runs / name)
        pre = json.loads((self.runs / 'prereg-2.json').read_text(encoding='utf-8'))
        p0 = json.loads((self.runs / 'prereg-0.json').read_text(encoding='utf-8'))
        pr = plan_result(columns=pre['columns'], empty=pre['empty'], fams=pre['families'])
        pr['queries'] = p0['select_queries_expected']
        _write(self.runs / 'plan-result.json', pr)
        res = self.run_reveal()
        h3 = res['H3']
        self.assertEqual(h3['cards_from'], 'prereg-1.json')
        self.assertEqual(h3['all']['n'], len(pre['families']))
        self.assertEqual(h3['no_sign'], [])
        self.assertEqual({r['card'] for r in h3['families']}, set(pre['families'].values()))
        self.assertEqual(sorted(h3['by_lens']), list(R.LENSES))
        if {c['sign'] for c in json.loads((REAL / 'prereg-1.json').read_text(encoding='utf-8'))['cards']} == {'+'}:
            self.assertTrue(h3['degenerate'])
        h2 = res['H2']
        self.assertEqual(h2['n_empty'], len(pre['empty']))
        self.assertEqual(h2['rehearsal_se_boot'], p0['rehearsal']['se_boot'])
        self.assertAlmostEqual(h2['rehearsal_se_boot_scaled'], p0['rehearsal']['se_boot'])
        self.assertEqual(res["H1'"]['waiting'], '⟨ждёт val.json⟩')


class TestOutput(Base):
    def test_everything_missing_gives_waiting_lines(self):
        res = self.run_reveal()
        for k in ('H3', 'H2', "H1'"):
            self.assertIn('⟨ждёт', res[k]['waiting'])
        self.assertEqual(res['H14']['status'], 'нет данных')
        md = R.markdown(res)
        self.assertEqual(len(re.findall('⟨ждёт', md)), 3)
        R.reveal('sber', self.root, self.fits)          # no runs directory at all: still no error

    def test_markdown_full(self):
        self.full()
        md = R.markdown(self.run_reveal())
        for head in ('## H3', '## H2', "## H1'", '## H14'):
            self.assertIn(head, md)
        self.assertNotIn('⟨ждёт', md)
        self.assertIn('| G4 |', md)

    def test_write_touches_only_reveal_json(self):
        self.full()
        _write(self.fits, [{'name': 'x'}], jsonl=True)
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with contextlib.redirect_stdout(io.StringIO()) as out:
            R.main(['rees46'], root=self.root, fits=self.fits)
        self.assertEqual({p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}, before)
        self.assertIn('## H3', out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            R.main(['rees46', '--write'], root=self.root, fits=self.fits)
        after = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(set(after) - set(before), {self.runs / 'reveal.json'})
        self.assertEqual({p: after[p] for p in before}, before)
        res = json.loads((self.runs / 'reveal.json').read_text(encoding='utf-8'))
        self.assertEqual(res['H3']['all']['n'], 12)
        with contextlib.redirect_stdout(io.StringIO()):     # rerun: reveal.json itself is not an input
            R.main(['rees46', '--write'], root=self.root, fits=self.fits)
        self.assertEqual(json.loads((self.runs / 'reveal.json').read_text(encoding='utf-8')), res)

    def test_reader_refuses_other_suffixes(self):
        for name in ('x.parquet', 'x.csv', 'x.txt'):
            with self.assertRaises(ValueError):
                R._read_json(self.root / name)


FORBIDDEN = ('broker', 'y_select', 'c_val', 'c_test', 'final_labels', 'open_labels', 'sealed', 'duckdb',
             'read_parquet')


class TestGuard(unittest.TestCase):
    src = Path(R.__file__).read_text(encoding='utf-8')
    tree = ast.parse(src)

    def test_no_forbidden_names_in_source(self):
        for word in FORBIDDEN:
            self.assertNotIn(word, self.src, word)

    def test_imports(self):
        mods = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                mods |= {a.name.split('.')[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                mods.add((node.module or '').split('.')[0])
                for a in node.names:
                    self.assertNotIn(a.name, FORBIDDEN)
        self.assertLessEqual(mods, {'__future__', 'argparse', 'itertools', 'json', 'math', 'sys', 'pathlib', 'numpy',
                                    'scipy'})

    def test_identifiers(self):
        for node in ast.walk(self.tree):
            name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None
            if name is not None:
                self.assertNotIn(name.lower(), FORBIDDEN)

    def test_reads_only_in_the_json_reader(self):
        readers = {'read_text', 'read_bytes', 'open', 'load', 'loadtxt', 'genfromtxt', 'fromfile', 'read_csv',
                   'read_json', 'read_table', 'read_pickle', 'read_feather'}
        allowed = {'_read_json'}
        for fn in ast.walk(self.tree):
            if not isinstance(fn, ast.FunctionDef):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    f = node.func
                    name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
                    if name in readers:
                        self.assertIn(fn.name, allowed, f'{fn.name} calls {name}')

    def test_reader_suffixes_and_file_constants(self):
        self.assertEqual(R.READABLE, ('.json', '.jsonl'))
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for ext in re.findall(r'\.([a-z]{2,8})\b', node.value):
                    if re.search(rf'[\w-]\.{ext}\b', node.value) and ext in {'parquet', 'csv', 'pkl', 'npy', 'npz',
                                                                              'feather', 'arrow', 'cbm', 'db'}:
                        self.fail(f'file constant {node.value!r}')

    def test_writes_only_reveal_json(self):
        writes = [node for node in ast.walk(self.tree) if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Attribute) and node.func.attr in {'write_text', 'write_bytes',
                                                                                 'mkdir', 'unlink', 'rename',
                                                                                 'touch', 'rmdir', 'symlink_to'}]
        self.assertEqual([w.func.attr for w in writes], ['write_text'])
        for node in ast.walk(self.tree):      # str.replace only (two string arguments), never Path.replace(target)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'replace':
                self.assertEqual(len(node.args), 2)
        self.assertEqual(R.OUT_NAME, 'reveal.json')


if __name__ == '__main__':
    unittest.main()
