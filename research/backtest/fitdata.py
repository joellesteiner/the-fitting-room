"""Load ModCloth bottoms purchases and turn repeat buyers into owned and next pair examples.

ModCloth size codes are not evenly spaced (4, 6, 8, 10, 12, 15, 20 and so on), so each
code is mapped to its position on an ordered size scale. One step on that scale is
treated as one size step, the same unit the app uses for waist sizes.
"""
import itertools
import json

import pandas as pd

# ModCloth fit labels describe the garment, the app's reports describe how it felt.
REPORT = {'small': 'tight', 'fit': 'right', 'large': 'loose'}
REPORTS = ('tight', 'right', 'loose')


def load_bottoms(path):
    """Read the ModCloth JSON lines file and keep bottoms with a usable fit label."""
    with open(path, encoding='utf-8') as f:
        rows = [json.loads(line) for line in f if line.strip()]
    df = pd.DataFrame(rows)
    df = df[(df['category'] == 'bottoms') & df['fit'].isin(REPORT)].copy()
    df['report'] = df['fit'].map(REPORT)
    return df[['user_id', 'item_id', 'size', 'report']].reset_index(drop=True)


def size_scale(df, min_count=150):
    """Size codes common enough to place reliably, in ascending order."""
    counts = df['size'].value_counts()
    return sorted(int(s) for s in counts[counts >= min_count].index)


def add_rank(df, scale):
    """Position of each size code on the scale; rows with rare codes are dropped."""
    index = {s: i for i, s in enumerate(scale)}
    out = df[df['size'].isin(index)].copy()
    out['rank'] = out['size'].map(index).astype(int)
    return out


def make_pairs(df, max_pairs_per_user=20, seed=0):
    """Every ordered pair of two different purchases by the same shopper.

    Purchase A plays the pair the shopper already owns (its size and how it fitted).
    Purchase B plays the next pair. ModCloth has no purchase dates, so order is not
    known; both orders are used. Heavy buyers are capped so they cannot dominate.
    """
    out = []
    for user, g in df.groupby('user_id', sort=True):
        if len(g) < 2:
            continue
        rows = list(g[['item_id', 'rank', 'report']].itertuples(index=False))
        pairs = list(itertools.permutations(rows, 2))
        if len(pairs) > max_pairs_per_user:
            pick = pd.Series(range(len(pairs))).sample(max_pairs_per_user, random_state=seed + int(user) % 9973)
            pairs = [pairs[i] for i in sorted(pick)]
        for a, b in pairs:
            out.append({'user_id': user, 'item_a': a.item_id, 'rank_a': a.rank, 'report_a': a.report,
                        'item_b': b.item_id, 'rank_b': b.rank, 'report_b': b.report})
    return pd.DataFrame(out)
