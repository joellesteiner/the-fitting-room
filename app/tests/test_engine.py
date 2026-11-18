import unittest
from recommendation_engine import recommend, report, rank, update_belief, prior_belief, WAIST, CATALOG, SIZES

RIGID = 'classic straight leg rigid non stretch jeans'


class Engine(unittest.TestCase):
    # Software behaviour
    def test_catalogue(self): self.assertGreaterEqual(len(CATALOG), 5)
    def test_size_changes(self): self.assertNotEqual(recommend(27, 0, 'regular', RIGID)['size'], recommend(31, 0, 'regular', RIGID)['size'])
    def test_intent_changes(self): self.assertNotEqual(recommend(28, 0, 'fitted', RIGID)['rule_size'], recommend(28, 0, 'relaxed', RIGID)['rule_size'])
    def test_boundary(self): self.assertEqual(recommend(24, 2, 'fitted', RIGID)['rule_size'], 'W24')
    def test_high_boundary(self): self.assertEqual(recommend(34, -2, 'oversized', RIGID)['rule_size'], 'W34')
    def test_mismatch(self):
        with self.assertRaisesRegex(ValueError, 'jeans only'): recommend(28, 0, 'regular', 'cotton summer dress')
    def test_missing(self):
        with self.assertRaises(ValueError): recommend(28, 0, 'regular', '')
    def test_bad_size(self):
        with self.assertRaises(ValueError): recommend(99, 0, 'regular', RIGID)
    def test_source(self): self.assertTrue(recommend(28, 0, 'regular', RIGID)['source'].startswith('https://www.levi.com/'))
    def test_top_retrieval(self): self.assertEqual(rank('ribcage super high rise ankle jeans')[0][0]['id'], 'ribcage')

    # Sizing direction (the bug the slide 9 example describes)
    def test_tight_never_sizes_down(self):
        for s in SIZES:
            for intent in ('fitted', 'regular', 'relaxed'):
                self.assertGreaterEqual(recommend(s, -2, intent, RIGID)['size_num'], s)
    def test_tight_goes_up_loose_goes_down(self):
        self.assertGreater(recommend(28, -2, 'regular', RIGID)['size_num'], recommend(28, 2, 'regular', RIGID)['size_num'])

    # Bayesian belief
    def test_belief_sums_to_one(self):
        b = recommend(28, -2, 'regular', RIGID)['belief']
        self.assertAlmostEqual(sum(b.values()), 1, places=3)
    def test_demo_case_confident(self):
        r = recommend(28, -2, 'regular', RIGID)
        self.assertEqual((r['decision'], r['size']), ('recommend', 'W29'))
        self.assertAlmostEqual(r['confidence'], 0.557, places=2)
    def test_abstain_different_cut(self): self.assertEqual(recommend(28, -2, 'regular', 'ribcage super high rise ankle straight jeans')['decision'], 'abstain')
    def test_abstain_oversized(self): self.assertEqual(recommend(28, 0, 'oversized', RIGID)['decision'], 'abstain')
    def test_abstain_weak_match(self): self.assertEqual(recommend(28, 0, 'regular', 'something comfy')['decision'], 'abstain')
    def test_tight_report_moves_belief_up(self):
        r = recommend(28, -2, 'regular', RIGID)
        u = report(r['belief'], 29, 'tight')
        self.assertEqual(u['size'], 'W30')
        self.assertAlmostEqual(u['confidence'], 0.671, places=2)
    def test_right_report_raises_confidence(self):
        r = recommend(28, -2, 'regular', RIGID)
        self.assertGreater(report(r['belief'], 29, 'right')['confidence'], r['confidence'])
    def test_bayes_matches_hand_calculation(self):
        prior = {s: 0 for s in SIZES}; prior.update({28: 0.15, 29: 0.60, 30: 0.25})
        post, _ = update_belief(prior, 29, 'tight')
        self.assertAlmostEqual(post[30], 0.2 / 0.2975, places=4)
    def test_bad_report_rejected(self):
        with self.assertRaises(ValueError): update_belief(prior_belief(29, 0.7, 0), 29, 'massive')


if __name__ == '__main__':
    unittest.main()
