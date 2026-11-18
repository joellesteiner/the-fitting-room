"""Unit tests for the backtest building blocks. They use small synthetic data, so they run
without the ModCloth file."""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fitdata  # noqa: E402
import model  # noqa: E402


def pairs(rows):
    return pd.DataFrame(rows, columns=['user_id', 'item_a', 'rank_a', 'report_a', 'item_b', 'rank_b', 'report_b'])


class Pairs(unittest.TestCase):
    def test_every_ordered_pair_from_one_shopper(self):
        df = pd.DataFrame({'user_id': [1, 1, 1, 2], 'item_id': [10, 11, 12, 13], 'rank': [3, 4, 5, 2],
                           'report': ['right', 'tight', 'loose', 'right']})
        p = fitdata.make_pairs(df)
        self.assertEqual(len(p), 6)                 # 3 x 2 orders for shopper 1, none for shopper 2
        self.assertTrue((p['item_a'] != p['item_b']).all())

    def test_heavy_buyers_are_capped(self):
        df = pd.DataFrame({'user_id': [1] * 8, 'item_id': range(8), 'rank': range(8), 'report': ['right'] * 8})
        self.assertEqual(len(fitdata.make_pairs(df, max_pairs_per_user=20)), 20)

    def test_rare_sizes_dropped_and_ranked(self):
        df = pd.DataFrame({'size': [4] * 200 + [8] * 200 + [9] * 3})
        scale = fitdata.size_scale(df)
        self.assertEqual(scale, [4, 8])
        self.assertEqual(sorted(fitdata.add_rank(df, scale)['rank'].unique()), [0, 1])


class Tables(unittest.TestCase):
    def test_prior_rows_sum_to_one(self):
        p = pairs([(1, 1, 3, 'tight', 2, 4, 'right'), (1, 2, 4, 'right', 1, 3, 'tight')])
        for row in model.learn_prior(p).values():
            self.assertAlmostEqual(sum(row.values()), 1.0)

    def test_prior_learns_the_observed_step(self):
        p = pairs([(u, 1, 3, 'tight', 2, 4, 'right') for u in range(50)])
        prior = model.learn_prior(p)
        self.assertEqual(max(prior['tight'], key=prior['tight'].get), 1)

    def test_sensor_learns_direction(self):
        # Owned pair fitted at rank 4. Next pair one size smaller is reported tight.
        p = pairs([(u, 1, 4, 'right', 2, 3, 'tight') for u in range(50)])
        sensor = model.learn_sensor(p)
        self.assertEqual(max(sensor[1], key=sensor[1].get), 'tight')
        for row in sensor.values():
            self.assertAlmostEqual(sum(row.values()), 1.0)

    def test_belief_is_clipped_to_the_scale(self):
        belief = model.size_belief(model.assumed_prior(), 0, 'loose', 5)
        self.assertGreaterEqual(min(belief), 0)
        self.assertAlmostEqual(sum(belief.values()), 1.0)

    def test_report_probabilities_sum_to_one(self):
        belief = model.size_belief(model.assumed_prior(), 3, 'right', 8)
        self.assertAlmostEqual(sum(model.report_probs(belief, 3, model.ASSUMED_SENSOR).values()), 1.0)


if __name__ == '__main__':
    unittest.main()
