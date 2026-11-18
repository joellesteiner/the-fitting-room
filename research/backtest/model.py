"""Learned and assumed versions of the two probability tables the app relies on.

Prior: how far the size that fits the next pair sits from the size of the pair the
shopper owns, given how the owned pair felt. P(step | owned report).

Sensor: how a shopper reports fit, given the size they wore minus the size that truly
fits them. P(report | true size minus worn size). Keyed exactly as in the app.
"""
import math

from fitdata import REPORTS

MAX_STEP = 3      # prior support: up to three sizes either side of the owned size
MAX_DIFF = 2      # sensor support, matching the app's SENSOR keys

# The assumed sensor model shipped in the 001 prototype, kept for comparison.
ASSUMED_SENSOR = {
    -2: {'tight': 0.03, 'right': 0.07, 'loose': 0.90},
    -1: {'tight': 0.05, 'right': 0.15, 'loose': 0.80},
    0: {'tight': 0.15, 'right': 0.70, 'loose': 0.15},
    1: {'tight': 0.80, 'right': 0.15, 'loose': 0.05},
    2: {'tight': 0.90, 'right': 0.07, 'loose': 0.03},
}


def clip(x, limit):
    return max(-limit, min(limit, int(x)))


def learn_prior(pairs, alpha=1.0):
    """P(step | owned report) from pairs where the next pair was reported as right.

    In those pairs the next pair's size is the size that fits, so the step is observed.
    Laplace smoothing (alpha) keeps every step possible.
    """
    steps = range(-MAX_STEP, MAX_STEP + 1)
    table = {}
    fitted = pairs[pairs['report_b'] == 'right']
    for report in REPORTS:
        sub = fitted[fitted['report_a'] == report]
        counts = {s: alpha for s in steps}
        for d in (sub['rank_b'] - sub['rank_a']):
            counts[clip(d, MAX_STEP)] += 1
        total = sum(counts.values())
        table[report] = {s: c / total for s, c in counts.items()}
    return table


def learn_sensor(pairs, alpha=1.0):
    """P(report | true size minus worn size) from pairs where the owned pair fitted.

    The owned pair's size stands in for the shopper's true size, so
    true minus worn is rank_a minus rank_b. That stand in is noisy (sizing varies by
    brand), which widens the learned table; the backtest measures whether it still helps.
    """
    table = {}
    anchored = pairs[pairs['report_a'] == 'right']
    for d in range(-MAX_DIFF, MAX_DIFF + 1):
        counts = {r: alpha for r in REPORTS}
        diff = (anchored['rank_a'] - anchored['rank_b']).map(lambda x: clip(x, MAX_DIFF))
        for r in anchored.loc[diff == d, 'report_b']:
            counts[r] += 1
        total = sum(counts.values())
        table[d] = {r: c / total for r, c in counts.items()}
    return table


def counts_behind_sensor(pairs):
    """How many pairs support each sensor row, to flag thin cells."""
    anchored = pairs[pairs['report_a'] == 'right']
    diff = (anchored['rank_a'] - anchored['rank_b']).map(lambda x: clip(x, MAX_DIFF))
    return {int(d): int(n) for d, n in diff.value_counts().sort_index().items()}


def assumed_prior(spread=0.70, lean=0.15):
    """The 001 prototype's prior: chart rule shift (tight goes up one, loose down one),
    a small lean, and a discretised Gaussian of fixed width."""
    table = {}
    for report, shift in (('tight', 1 + lean), ('right', 0.0), ('loose', -1 - lean)):
        w = {s: math.exp(-((s - shift) ** 2) / (2 * spread ** 2)) for s in range(-MAX_STEP, MAX_STEP + 1)}
        total = sum(w.values())
        table[report] = {s: v / total for s, v in w.items()}
    return table


def naive_prior():
    """Buy the same size again, with certainty."""
    return {r: {s: 1.0 if s == 0 else 0.0 for s in range(-MAX_STEP, MAX_STEP + 1)} for r in REPORTS}


def size_belief(prior, rank_a, report_a, n_sizes):
    """Belief over the size that fits the next pair, clipped to the size scale."""
    belief = {}
    for step, p in prior[report_a].items():
        t = min(n_sizes - 1, max(0, rank_a + step))
        belief[t] = belief.get(t, 0.0) + p
    return belief


def report_probs(belief, worn_rank, sensor):
    """P(report on the next pair | its size), summed over the belief about true size."""
    out = {r: 0.0 for r in REPORTS}
    for t, p in belief.items():
        row = sensor[clip(t - worn_rank, MAX_DIFF)]
        for r in REPORTS:
            out[r] += p * row[r]
    total = sum(out.values())
    return {r: v / total for r, v in out.items()}
