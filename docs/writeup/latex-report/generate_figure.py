from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[3]


def scores():
    """Read the selected submission at each stage, rather than duplicate its score."""
    def read(path, name):
        with (ROOT / path).open(encoding='utf-8', newline='') as handle:
            rows = list(csv.DictReader(line for line in handle if not line.startswith('#')))
        selected = [row for row in rows if row['fileName'] == name]
        if len(selected) != 1:
            raise ValueError(f'{path}: expected exactly one submission named {name}')
        return float(selected[0]['privateScore'])
    return [read('docs/otto-run/otto2-kaggle-scores.csv', 'f4all-lr10-it2000.csv.gz')] + [
        read('docs/otto3-run/otto3-kaggle-scores.csv', f'{iteration}-f4all-lr10-it2000.csv.gz')
        for iteration in ('i1', 'i2', 'i3')]


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FormatStrFormatter

    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'pdf.fonttype': 42})
    fig, ax = plt.subplots(figsize=(7.3, 2.05))
    x = [0, 1, 2, 3]
    y = scores()
    ax.plot(x, y, color='#245E8A', lw=2, marker='o', ms=6)
    for a,b in zip(x,y):
        ax.annotate(f'{b:.4f}', (a,b), xytext=(0,8), textcoords='offset points', ha='center', fontsize=10, fontweight='bold', color='#162D46')
    ax.set_xticks(x, ['Исходное решение\n(OTTO-2)', 'Итерация 1', 'Итерация 2', 'Итерация 3'])
    ax.set_ylim(.578, .601)
    ax.set_xlim(-.35, 3.35)
    ax.set_yticks([.580, .590, .600])
    ax.yaxis.set_major_formatter(FormatStrFormatter('%.3f'))
    ax.set_ylabel('Оценка Kaggle', color='#53616C')
    ax.grid(axis='y', color='#DFE5E9', lw=.6)
    ax.set_axisbelow(True)
    for k in ['top', 'right']: ax.spines[k].set_visible(False)
    for k in ['bottom', 'left']: ax.spines[k].set_color('#B9C3CC')
    ax.tick_params(axis='both', length=0, pad=6, colors='#53616C')
    fig.tight_layout(pad=.6)
    out = Path(__file__).parent / 'images' / 'otto-iterations.pdf'
    fig.savefig(out, bbox_inches='tight')


if __name__ == "__main__":
    main()
