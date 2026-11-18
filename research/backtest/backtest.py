"""Backtest the recommender on ModCloth shoppers it has never seen.

Two questions, both scored with five fold cross validation split by shopper, so no
shopper's purchases are used for both learning and testing:

1. Size: given the pair a shopper owns and how it felt, does the recommended size match
   the size of their next pair that they reported as right?
2. Fit: for the size they actually bought next, how well do the probabilities predict
   whether they reported it tight, right or loose?

Usage: python backtest.py path/to/modcloth_final_data.json [--write-app-model]
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

import fitdata
import model
from fitdata import REPORTS

HERE = Path(__file__).parent
OUT = HERE / 'results'
APP_MODEL = HERE.parent.parent / 'app' / 'model' / 'sensor_learned.json'
THRESHOLDS = [round(x, 2) for x in np.arange(0.0, 0.96, 0.05)]
BINS = np.linspace(0, 1, 11)


def size_scores(test, prior, n_sizes):
    """Top size, its confidence, and whether it matched, for pairs where B fitted."""
    fitted = test[test['report_b'] == 'right']
    rows = []
    for r in fitted.itertuples(index=False):
        belief = model.size_belief(prior, r.rank_a, r.report_a, n_sizes)
        top = max(belief, key=belief.get)
        rows.append({'conf': belief[top], 'exact': top == r.rank_b, 'within1': abs(top - r.rank_b) <= 1,
                     'p_true': belief.get(r.rank_b, 0.0)})
    return pd.DataFrame(rows)


def fit_scores(test, prior, sensor, n_sizes):
    """Predicted report probabilities for the size actually bought, and the outcome."""
    rows = []
    for r in test.itertuples(index=False):
        belief = model.size_belief(prior, r.rank_a, r.report_a, n_sizes)
        p = model.report_probs(belief, r.rank_b, sensor)
        rows.append({**{f'p_{k}': v for k, v in p.items()}, 'y': r.report_b})
    return pd.DataFrame(rows)


def fit_metrics(df):
    probs = df[[f'p_{r}' for r in REPORTS]].to_numpy()
    y = np.array([REPORTS.index(v) for v in df['y']])
    onehot = np.eye(3)[y]
    pred = probs.argmax(1)
    recalls = [float((pred[y == k] == k).mean()) if (y == k).any() else float('nan') for k in range(3)]
    return {'log_loss': float(-np.mean(np.log(np.clip(probs[np.arange(len(y)), y], 1e-12, 1)))),
            'brier': float(np.mean(np.sum((probs - onehot) ** 2, axis=1))),
            'macro_recall': float(np.nanmean(recalls)),
            'recall_tight': recalls[0], 'recall_right': recalls[1], 'recall_loose': recalls[2]}


def size_metrics(df):
    return {'exact': float(df['exact'].mean()), 'within1': float(df['within1'].mean()),
            'mean_conf': float(df['conf'].mean()),
            'log_loss': float(-np.mean(np.log(np.clip(df['p_true'], 1e-12, 1)))),
            'ece': ece(df)}


def ece(df):
    """Expected calibration error: average gap between stated confidence and accuracy."""
    idx = np.clip(np.digitize(df['conf'], BINS) - 1, 0, len(BINS) - 2)
    gap = 0.0
    for b in np.unique(idx):
        m = idx == b
        gap += m.mean() * abs(df.loc[m, 'conf'].mean() - df.loc[m, 'exact'].mean())
    return float(gap)


def coverage_curve(df):
    out = []
    for t in THRESHOLDS:
        kept = df[df['conf'] >= t]
        out.append({'threshold': t, 'coverage': len(kept) / len(df),
                    'accuracy': float(kept['exact'].mean()) if len(kept) else float('nan')})
    return out


def reliability(df):
    idx = np.clip(np.digitize(df['conf'], BINS) - 1, 0, len(BINS) - 2)
    return [{'bin_low': float(BINS[b]), 'mean_conf': float(df.loc[idx == b, 'conf'].mean()),
             'accuracy': float(df.loc[idx == b, 'exact'].mean()), 'n': int((idx == b).sum())}
            for b in np.unique(idx)]


def summarise(per_fold):
    keys = per_fold[0].keys()
    return {k: {'mean': float(np.mean([f[k] for f in per_fold])), 'sd': float(np.std([f[k] for f in per_fold]))}
            for k in keys}


def run(path, folds=5, write_app_model=False):
    raw = fitdata.load_bottoms(path)
    scale = fitdata.size_scale(raw)
    ranked = fitdata.add_rank(raw, scale)
    pairs = fitdata.make_pairs(ranked)
    n = len(scale)
    print(f'{len(raw)} bottoms rows, {len(ranked)} on the size scale {scale}')
    print(f"{pairs['user_id'].nunique()} repeat shoppers, {len(pairs)} owned and next pairs")

    size_runs = {'Same size again': [], '001 assumed model': [], 'Learned model': []}
    fit_runs = {'Class frequency baseline': [], '001 assumed model': [],
                'Learned prior, assumed sensor': [], 'Learned model': []}
    pooled = {'001 assumed model': [], 'Learned model': []}

    for k, (tr, te) in enumerate(GroupKFold(n_splits=folds).split(pairs, groups=pairs['user_id'])):
        train, test = pairs.iloc[tr], pairs.iloc[te]
        lp, ls = model.learn_prior(train), model.learn_sensor(train)
        ap, as_ = model.assumed_prior(), model.ASSUMED_SENSOR

        for name, prior in (('Same size again', model.naive_prior()), ('001 assumed model', ap), ('Learned model', lp)):
            s = size_scores(test, prior, n)
            size_runs[name].append(size_metrics(s))
            if name in pooled:
                pooled[name].append(s)

        freq = train['report_b'].value_counts(normalize=True)
        base = pd.DataFrame({**{f'p_{r}': [freq.get(r, 0.0)] * len(test) for r in REPORTS}, 'y': test['report_b'].to_numpy()})
        fit_runs['Class frequency baseline'].append(fit_metrics(base))
        fit_runs['001 assumed model'].append(fit_metrics(fit_scores(test, ap, as_, n)))
        fit_runs['Learned prior, assumed sensor'].append(fit_metrics(fit_scores(test, lp, as_, n)))
        fit_runs['Learned model'].append(fit_metrics(fit_scores(test, lp, ls, n)))
        print(f'fold {k + 1}/{folds} done')

    pooled = {k: pd.concat(v, ignore_index=True) for k, v in pooled.items()}
    full_prior, full_sensor = model.learn_prior(pairs), model.learn_sensor(pairs)
    results = {
        'data': {'bottoms_rows': len(raw), 'rows_on_scale': len(ranked), 'size_scale': scale,
                 'repeat_shoppers': int(pairs['user_id'].nunique()), 'pairs': len(pairs),
                 'pairs_next_fitted': int((pairs['report_b'] == 'right').sum()), 'folds': folds},
        'size': {k: summarise(v) for k, v in size_runs.items()},
        'fit': {k: summarise(v) for k, v in fit_runs.items()},
        'coverage': {k: coverage_curve(v) for k, v in pooled.items()},
        'reliability': {k: reliability(v) for k, v in pooled.items()},
        'learned_prior': {r: {str(s): round(p, 4) for s, p in t.items()} for r, t in full_prior.items()},
        'learned_sensor': {str(d): {r: round(p, 4) for r, p in t.items()} for d, t in full_sensor.items()},
        'sensor_support': model.counts_behind_sensor(pairs),
    }
    OUT.mkdir(exist_ok=True)
    (OUT / 'metrics.json').write_text(json.dumps(results, indent=2))
    if write_app_model:
        APP_MODEL.parent.mkdir(exist_ok=True)
        APP_MODEL.write_text(json.dumps({
            'description': 'P(report | true size minus worn size), learned from ModCloth bottoms repeat buyers. '
                           'Produced by research/backtest/backtest.py.',
            'source': 'Misra, Wan and McAuley (2018), ModCloth clothing fit dataset',
            'pairs_used': results['sensor_support'],
            'smoothing': 'Laplace, alpha = 1',
            'sensor': results['learned_sensor'],
        }, indent=2))
    return results


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('data')
    ap.add_argument('--folds', type=int, default=5)
    ap.add_argument('--write-app-model', action='store_true')
    a = ap.parse_args()
    res = run(a.data, a.folds, a.write_app_model)
    print(json.dumps({'size': res['size'], 'fit': res['fit'], 'sensor': res['learned_sensor'],
                      'support': res['sensor_support']}, indent=1))
