"""Render accepted aggregate validation curves."""
SUMMARY_SHA = 'a29181ba769356936afcc9c8833c3a0f7b1d1a466eb6f0b045f85513716aba74'
SOURCE_SHA = '9126386add408b9b4c76a626b8512cb78074f6570dd8b26937a12c49700cf26f'
TOLERANCE = 1e-12


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read_json(path, digest):
    import hashlib
    import json
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 1048576,
            'Only bounded accepted aggregate JSON is allowed')
    with path.open('rb') as stream:
        raw = stream.read(1048577)
    require(len(raw) <= 1048576 and hashlib.sha256(raw).hexdigest() == digest, 'Aggregate SHA differs')
    return json.loads(raw)


def validate(summary, source):
    import math
    require(set(source['curves']) == {'B', 'W'}, 'Exactly two accepted curves required')
    require(summary['full_curves']['checkpoints_per_arm'] == 1200 and
            summary['science_scope']['validation_positive_fullY_queries'] == 73 and
            summary['independent_calls']['checkpoints'] == source['calls']['checkpoints'] == 2400,
            'Accepted cohort/checkpoint metadata differs')
    proof = summary['verification']
    require(proof['curve_comparison_tolerance'] == TOLERANCE and
            0 <= proof['maximum_curve_absolute_difference'] <= TOLERANCE,
            'Accepted independent-versus-producer comparison witness differs')
    selected = {}
    for arm in ('B', 'W'):
        curve = source['curves'][arm]
        meta = summary['arms'][arm]
        require(type(curve) is list and len(curve) == 1200 and
                all(type(v) is float and math.isfinite(v) and 0 <= v <= 1 for v in curve),
                'Every original finite NDCG point is required')
        peak = max(curve)
        best = next(i + 1 for i, value in enumerate(curve) if value >= peak - TOLERANCE)
        require(type(meta['selected_trees']) is int and
                best == meta['selected_trees'] == source['arms'][arm]['selected_trees'] and
                meta['maximum_trained_trees'] == 1200 and meta['global_maximum_band_tolerance'] == TOLERANCE,
                'Global-band earliest selection differs')
        for actual, expected in ((curve[299], meta['same_fit_prefix300_NDCG20']),
                                 (curve[1199], meta['same_fit_prefix1200_NDCG20']),
                                 (peak, meta['independent_conditional_NDCG20']),
                                 (curve[best-1], source['arms'][arm]['evaluation']['conditional_macro_query']['ndcg'])):
            require(math.isfinite(expected) and abs(actual-expected) <= TOLERANCE,
                    'Accepted scalar/curve consistency differs')
        require(0 <= meta['max_independent_vs_producer_curve_absolute_difference'] <= TOLERANCE,
                'Accepted per-arm comparison witness differs')
        selected[arm] = best
    require(selected == {'B': 1189, 'W': 403} and summary['arms']['B']['distance_from_ceiling'] == 11,
            'Figure-specific accepted annotation metadata differs')
    return selected


def main():
    import argparse
    import os
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--font-cache', type=Path, help='Optional bounded fontlist-v*.json cache')
    args = parser.parse_args()
    summary = read_json(args.summary, SUMMARY_SHA)
    source = read_json(args.source, SOURCE_SHA)
    require(args.source.resolve() == (args.summary.parent / summary['full_curves']['path']).resolve(),
            'Source must be the summary-linked accepted aggregate')
    selected = validate(summary, source)  # All stdlib checks precede plotting imports.
    literal = args.output_dir.expanduser().absolute()
    require(not literal.exists() and not literal.is_symlink(), 'Existing output must be preserved')
    out = literal.resolve()
    out.mkdir(mode=0o700)
    if args.font_cache is not None:
        font_cache = args.font_cache.expanduser().absolute()
        require(font_cache.is_file() and not font_cache.is_symlink() and
                font_cache.stat().st_size <= 1048576 and font_cache.match('fontlist-v*.json'),
                'Font cache must be a bounded regular fontlist-v*.json file, without symlinks')
        with font_cache.open('rb') as stream:
            cache_raw = stream.read(1048577)
        require(len(cache_raw) <= 1048576, 'Font cache exceeds 1 MiB')
        config = out / '.mplconfig'
        config.mkdir(mode=0o700)
        with (config / font_cache.name).open('xb') as stream:
            stream.write(cache_raw)
    os.environ['MPLCONFIGDIR'] = str(out / '.mplconfig')
    import matplotlib
    matplotlib.use('Agg', force=True)
    import matplotlib.pyplot as plt
    matplotlib.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11,
                                'axes.spines.top': False, 'axes.spines.right': False,
                                'path.simplify': False, 'pdf.fonttype': 42})
    colors = {'B': '#0072B2', 'W': '#D55E00'}
    curves = source['curves']
    fig, axes = plt.subplots(1, 2, figsize=(16, 10), dpi=100)
    try:
        fig.subplots_adjust(left=.075, right=.975, bottom=.255, top=.80, wspace=.19)
        fig.suptitle('Выбор числа деревьев по validation', y=.972, fontsize=22, weight='semibold')
        fig.text(.5, .925, 'Обе модели полностью обучены до 1200 деревьев', ha='center', fontsize=13)
        fig.text(.5, .892, 'Повторно использована validation 22–23.10.2019 · 73 запроса с непустым full Y',
                 ha='center', fontsize=12)
        for ax, start, title in zip(axes, (1, 250),
                ('Вся кривая: 1–1200', 'Увеличение: 250–1200 · отдельный масштаб Y')):
            for arm in ('B', 'W'):
                values = curves[arm]
                ax.plot(range(1, 1201), values, color=colors[arm], linewidth=1.35,
                        label=f'{arm}: выбранное k = {selected[arm]}')
                best = selected[arm]
                ax.scatter([best], [values[best-1]], marker='*', s=170, color=colors[arm],
                           edgecolors='white', linewidths=.7, zorder=5)
            ax.axvline(300, color='#666666', linestyle='--', linewidth=1.2, label='300 деревьев')
            ax.set_xlim(start, 1200)
            ax.set_title(title, fontsize=12.5, pad=14)
            ax.set_xlabel('Число деревьев, k', labelpad=11)
            ax.set_ylabel('Средний NDCG@20 по запросам\nс непустым full Y', labelpad=9)
            ax.grid(True, color='#D8DEE4', alpha=.70, linewidth=.65)
            ax.set_axisbelow(True)
        axes[0].set_ylim(0, .5)
        axes[0].legend(loc='lower left', framealpha=.95, fontsize=10)
        zoom_values = curves['B'][249:] + curves['W'][249:]
        axes[1].set_ylim(min(zoom_values)-.003, max(zoom_values)+.005)
        for arm, position in (('W', (.16, .955)), ('B', (.54, .11))):
            best = selected[arm]
            label = f'{arm}: k = {best}\nNDCG@20 = {curves[arm][best-1]:.6f}'.replace('.', ',')
            axes[1].annotate(label, xy=(best, curves[arm][best-1]), xytext=position,
                             textcoords='axes fraction', ha='left', va='top' if arm == 'W' else 'bottom',
                             color=colors[arm], fontsize=11, weight='semibold',
                             bbox=dict(boxstyle='round,pad=.4', facecolor='white', edgecolor=colors[arm], alpha=.96),
                             arrowprops=dict(arrowstyle='-', color=colors[arm], linewidth=1.1), zorder=6)
        caption = ('2400 зависимых validation-проверок · exploratory после исходного final reporting.\n'
                   'Это не независимое подтверждение качества и не доказательство экономии обучения: обе модели обучены до 1200.\n'
                   'B: 1189 — всего 11 деревьев до потолка; оптимум за пределами 1200 не установлен.')
        fig.text(.075, .17, caption, ha='left', va='top', fontsize=11, linespacing=1.8, color='#303840')
        for name, kind in (('adaptive-validation.png', 'png'), ('adaptive-validation.pdf', 'pdf')):
            with (out / name).open('xb') as stream:
                fig.savefig(stream, format=kind, dpi=100, facecolor='white')
        import json
        with (out / 'validation-checks.json').open('x') as stream:
            json.dump({'summary_sha256': SUMMARY_SHA, 'source_sha256': SOURCE_SHA,
                       'selected_trees': selected, 'points_per_arm': 1200, 'smoothing': False,
                       'producer_comparison': 'accepted producer aggregate curves read; independent comparison witness reused, no curve recomputation/model evaluation/refit',
                       'scope': 'accepted aggregate presentation only; zero ML fits'}, stream, indent=2)
            stream.write('\n')
    finally:
        plt.close(fig)


if __name__ == '__main__':
    main()
