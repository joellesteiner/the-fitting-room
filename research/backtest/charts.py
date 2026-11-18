"""Draw the three report figures from results/metrics.json."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).parent
RES = HERE / 'results'
LEARNED, ASSUMED, BASE = '#2a78d6', '#eb6834', '#8a8a85'
INK, MUTED, GRID, SURFACE = '#1f1f1d', '#5c5c57', '#e6e5e0', '#fcfcfb'

plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11, 'axes.edgecolor': GRID,
                     'axes.labelcolor': MUTED, 'xtick.color': MUTED, 'ytick.color': MUTED,
                     'text.color': INK, 'axes.titlesize': 13, 'axes.titleweight': 'bold'})


def frame(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)


def save(fig, name):
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    fig.savefig(RES / name, dpi=200, facecolor=SURFACE)
    plt.close(fig)


def sensor_chart(r):
    """P(tight) and P(loose) by true minus worn size, assumed against learned."""
    from model import ASSUMED_SENSOR
    xs = list(range(-2, 3))
    learned = {int(k): v for k, v in r['learned_sensor'].items()}
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    for ax, report, title in ((axes[0], 'tight', 'Chance the shopper says "too tight"'),
                              (axes[1], 'loose', 'Chance the shopper says "too loose"')):
        frame(ax)
        a = [ASSUMED_SENSOR[x][report] for x in xs]
        l = [learned[x][report] for x in xs]
        ax.plot(xs, a, color=ASSUMED, lw=2, ls='--', marker='o', ms=8, label='001 assumed')
        ax.plot(xs, l, color=LEARNED, lw=2, marker='o', ms=8, label='Learned from ModCloth')
        ax.text(xs[-1] + 0.12, a[-1], 'Assumed', color=MUTED, va='center', fontsize=10)
        ax.text(xs[-1] + 0.12, l[-1], 'Learned', color=MUTED, va='center', fontsize=10)
        ax.set_title(title, loc='left')
        ax.set_xticks(xs, ['2 sizes\ntoo big', '1 size\ntoo big', 'Right\nsize', '1 size\ntoo small', '2 sizes\ntoo small'])
        ax.set_xlim(-2.4, 2.9)
        ax.set_ylim(0, 1)
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    axes[0].legend(frameon=False, loc='upper left')
    save(fig, 'sensor_assumed_vs_learned.png')


def calibration_chart(r):
    fig, ax = plt.subplots(figsize=(5.6, 5.2))
    frame(ax)
    ax.plot([0, 1], [0, 1], color=BASE, lw=1, ls=':')
    ax.text(0.62, 0.70, 'Perfectly honest', color=MUTED, rotation=42, fontsize=10)
    for name, colour, ls in (('001 assumed model', ASSUMED, '--'), ('Learned model', LEARNED, '-')):
        pts = [p for p in r['reliability'][name] if p['n'] >= 20]
        ax.plot([p['mean_conf'] for p in pts], [p['accuracy'] for p in pts], color=colour, lw=2, ls=ls, marker='o', ms=8,
                label=f"{name.replace(' model', '')} (calibration error {r['size'][name]['ece']['mean']:.0%})")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel('Confidence the app states')
    ax.set_ylabel('How often that size was right')
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_title('Is the stated confidence honest?', loc='left')
    ax.legend(frameon=False, loc='upper left', fontsize=9.5)
    save(fig, 'calibration.png')


def coverage_chart(r):
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    frame(ax)
    for name, colour, ls in (('001 assumed model', ASSUMED, '--'), ('Learned model', LEARNED, '-')):
        pts = [p for p in r['coverage'][name] if p['coverage'] >= 0.02]
        ax.plot([p['coverage'] for p in pts], [p['accuracy'] for p in pts], color=colour, lw=2, ls=ls,
                marker='o', ms=6, label=name.replace(' model', ''))
    same = r['size']['Same size again']['exact']['mean']
    ax.scatter([1.0], [same], s=80, color=BASE, zorder=3, label='Same size again')
    learned = {p['threshold']: p for p in r['coverage']['Learned model']}[0.5]
    ax.annotate(f"50% bar: answers {learned['coverage']:.0%},\nright {learned['accuracy']:.0%} of the time",
                (learned['coverage'], learned['accuracy']), xytext=(0.30, 0.62), color=INK, fontsize=10,
                arrowprops={'arrowstyle': '-', 'color': MUTED, 'lw': 1})
    ax.set_xlim(0, 1.05)
    ax.set_ylim(0, 0.7)
    ax.set_xlabel('Share of shoppers the app gives a size to')
    ax.set_ylabel('Exact size accuracy')
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_title('Abstaining trades coverage for accuracy', loc='left')
    ax.legend(frameon=False, loc='lower right', fontsize=9.5)
    save(fig, 'coverage_vs_accuracy.png')


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(HERE))
    results = json.loads((RES / 'metrics.json').read_text())
    sensor_chart(results)
    calibration_chart(results)
    coverage_chart(results)
    print('charts written to', RES)
