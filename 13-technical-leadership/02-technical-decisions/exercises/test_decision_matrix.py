"""13.2 技術的意思決定と設計レビュー — テスト

実行: python3 tools/check.py 13.2   （またはこのディレクトリで python3 -m unittest -v）
"""
import random
import unittest

from decision_matrix import (
    normalize,
    rank_stability,
    ranking,
    weight_flip_points,
    weighted_scores,
)

# 本文の例: ジョブキューの選定
# 案: 0 = PostgreSQL キュー, 1 = マネージドキュー, 2 = Kafka 自前運用
# 軸: 要件適合(1-5), 運用負荷(人時/月), 習熟期間(週), 月額費用(万円), 撤退コスト(人週)
EXAMPLE_SCORES = [
    [3, 4, 0.5, 3, 2],
    [4, 2, 2, 5, 4],
    [5, 30, 8, 25, 10],
]
EXAMPLE_DIRECTIONS = ["benefit", "cost", "cost", "cost", "cost"]
EXAMPLE_WEIGHTS = [0.35, 0.25, 0.15, 0.15, 0.10]


def with_weight(weights, k, t):
    """軸 k の重みを t にし、他の軸を比率を保って合計 1 - t にした重みを返す（テスト用）。"""
    total = sum(weights)
    w = [x / total for x in weights]
    scale = (1 - t) / (1 - w[k])
    return [t if j == k else wj * scale for j, wj in enumerate(w)]


class TestExercise1Normalize(unittest.TestCase):
    def test_minmax_benefit_and_cost(self):
        got = normalize([[1, 10], [3, 20], [5, 30]], ["benefit", "cost"])
        expected = [[0.0, 1.0], [0.5, 0.5], [1.0, 0.0]]
        for row_got, row_exp in zip(got, expected):
            for g, e in zip(row_got, row_exp):
                self.assertAlmostEqual(g, e)

    def test_minmax_is_default_and_best_is_one(self):
        got = normalize(EXAMPLE_SCORES, EXAMPLE_DIRECTIONS)
        # 要件適合（benefit）は Kafka が最良、運用負荷（cost）はマネージドキューが最良
        self.assertAlmostEqual(got[2][0], 1.0)
        self.assertAlmostEqual(got[0][0], 0.0)
        self.assertAlmostEqual(got[1][1], 1.0)
        self.assertAlmostEqual(got[2][1], 0.0)
        self.assertAlmostEqual(got[0][1], 26 / 28)
        for row in got:
            for x in row:
                self.assertTrue(0.0 <= x <= 1.0)

    def test_constant_column_is_all_one(self):
        got = normalize([[7, 1], [7, 2]], ["benefit", "benefit"])
        self.assertEqual([got[0][0], got[1][0]], [1.0, 1.0])
        got = normalize([[7, 1], [7, 2]], ["cost", "cost"])
        self.assertEqual([got[0][0], got[1][0]], [1.0, 1.0])

    def test_ratio_method(self):
        got = normalize([[2, 10], [4, 20]], ["benefit", "cost"], method="ratio")
        self.assertEqual(got, [[0.5, 1.0], [1.0, 0.5]])
        got = normalize(EXAMPLE_SCORES, EXAMPLE_DIRECTIONS, method="ratio")
        self.assertAlmostEqual(got[0][2], 1.0)       # 習熟期間 0.5 週が最良
        self.assertAlmostEqual(got[1][2], 0.25)      # 0.5 / 2
        self.assertAlmostEqual(got[2][3], 3 / 25)    # 月額費用 3 / 25

    def test_ratio_requires_positive_values(self):
        with self.assertRaises(ValueError):
            normalize([[0, 1], [2, 3]], ["benefit", "cost"], method="ratio")
        with self.assertRaises(ValueError):
            normalize([[1, -1], [2, 3]], ["benefit", "cost"], method="ratio")

    def test_does_not_modify_input(self):
        scores = [[1, 2], [3, 4]]
        normalize(scores, ["benefit", "cost"])
        self.assertEqual(scores, [[1, 2], [3, 4]])

    def test_invalid_inputs(self):
        cases = [
            ([], [], "minmax"),
            ([[]], [], "minmax"),
            ([[1, 2], [3]], ["benefit", "cost"], "minmax"),
            ([[1, 2], [3, 4]], ["benefit"], "minmax"),
            ([[1, 2], [3, 4]], ["benefit", "good"], "minmax"),
            ([[1, 2], [3, 4]], ["benefit", "cost"], "zscore"),
        ]
        for scores, directions, method in cases:
            with self.assertRaises(ValueError, msg=f"{scores}, {directions}, {method}"):
                normalize(scores, directions, method)

    def test_normalization_method_can_change_the_winner(self):
        # 本文のポイント: 同じデータ・同じ重みでも、正規化の方法だけで 1 位が入れ替わる
        minmax = weighted_scores(normalize(EXAMPLE_SCORES, EXAMPLE_DIRECTIONS, "minmax"), EXAMPLE_WEIGHTS)
        ratio = weighted_scores(normalize(EXAMPLE_SCORES, EXAMPLE_DIRECTIONS, "ratio"), EXAMPLE_WEIGHTS)
        self.assertEqual(ranking(minmax), [1, 0, 2])
        self.assertEqual(ranking(ratio), [0, 1, 2])


class TestExercise2Scores(unittest.TestCase):
    def test_weighted_scores_example(self):
        got = weighted_scores([[1.0, 0.0], [0.0, 1.0]], [3, 1])
        self.assertAlmostEqual(got[0], 0.75)
        self.assertAlmostEqual(got[1], 0.25)

    def test_worked_example_scores(self):
        n = normalize(EXAMPLE_SCORES, EXAMPLE_DIRECTIONS, "minmax")
        got = weighted_scores(n, EXAMPLE_WEIGHTS)
        for g, e in zip(got, [0.632, 0.756, 0.350]):
            self.assertAlmostEqual(g, e, places=3)

    def test_weights_are_normalized_internally(self):
        n = [[0.2, 0.9, 0.4], [0.8, 0.1, 0.5]]
        a = weighted_scores(n, [2, 1, 1])
        b = weighted_scores(n, [0.5, 0.25, 0.25])
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y)

    def test_zero_weight_criterion_is_ignored(self):
        got = weighted_scores([[1.0, 0.0], [0.0, 1.0]], [1, 0])
        self.assertEqual(got, [1.0, 0.0])

    def test_invalid_weights(self):
        n = [[0.1, 0.2], [0.3, 0.4]]
        for weights in ([1, -1], [0, 0], [1], [1, 1, 1]):
            with self.assertRaises(ValueError, msg=str(weights)):
                weighted_scores(n, weights)

    def test_ranking_orders_by_score_descending(self):
        self.assertEqual(ranking([0.2, 0.9, 0.5]), [1, 2, 0])
        self.assertEqual(ranking([0.1]), [0])

    def test_ranking_ties_keep_input_order(self):
        self.assertEqual(ranking([0.5, 0.7, 0.7]), [1, 2, 0])
        self.assertEqual(ranking([0.3, 0.3, 0.3]), [0, 1, 2])


class TestExercise3FlipPoints(unittest.TestCase):
    def test_two_alternatives_closed_form(self):
        got = weight_flip_points([[1.0, 0.0], [0.0, 1.0]], [0.6, 0.4])
        self.assertEqual(len(got), 2)
        for item in got:
            self.assertIsNotNone(item)
            t, b = item
            self.assertAlmostEqual(t, 0.5)
            self.assertEqual(b, 1)

    def test_worked_example_ratio(self):
        # 比率で正規化すると PostgreSQL キュー（0）が僅差の 1 位で、どの軸も少し動かすだけで入れ替わる
        n = normalize(EXAMPLE_SCORES, EXAMPLE_DIRECTIONS, "ratio")
        got = weight_flip_points(n, EXAMPLE_WEIGHTS)
        expected_t = [0.429, 0.289, 0.118, 0.087, 0.048]
        for k, (item, t_exp) in enumerate(zip(got, expected_t)):
            self.assertIsNotNone(item, f"軸 {k}")
            t, b = item
            self.assertAlmostEqual(t, t_exp, places=3, msg=f"軸 {k}")
            self.assertEqual(b, 1, f"軸 {k}: 入れ替わる相手はマネージドキュー")

    def test_worked_example_minmax_has_unflippable_criterion(self):
        n = normalize(EXAMPLE_SCORES, EXAMPLE_DIRECTIONS, "minmax")
        got = weight_flip_points(n, EXAMPLE_WEIGHTS)
        self.assertIsNone(got[1], "運用負荷はマネージドキューが最良なので、重みを上げても下げても 1 位は変わらない")
        t, b = got[0]
        self.assertAlmostEqual(t, 0.135, places=3)
        self.assertEqual(b, 0)

    def test_dominant_alternative_never_flips(self):
        n = [[1.0, 1.0, 0.9], [0.5, 0.2, 0.8], [0.0, 0.7, 0.1]]
        self.assertEqual(weight_flip_points(n, [1, 1, 1]), [None, None, None])

    def test_full_weight_criterion_is_none(self):
        n = [[1.0, 0.0], [0.0, 1.0]]
        got = weight_flip_points(n, [1, 0])
        self.assertIsNone(got[0], "他の軸の重みがすべて 0 なら比率を保って配り直せない")
        t, b = got[1]
        self.assertAlmostEqual(t, 0.5)
        self.assertEqual(b, 1)

    def test_flip_point_is_a_tie_and_crossing_changes_winner(self):
        n = normalize(EXAMPLE_SCORES, EXAMPLE_DIRECTIONS, "ratio")
        base_winner = ranking(weighted_scores(n, EXAMPLE_WEIGHTS))[0]
        for k, item in enumerate(weight_flip_points(n, EXAMPLE_WEIGHTS)):
            t, b = item
            tied = weighted_scores(n, with_weight(EXAMPLE_WEIGHTS, k, t))
            self.assertAlmostEqual(tied[base_winner], tied[b], places=9, msg=f"軸 {k}")
            step = 1e-6 if t > EXAMPLE_WEIGHTS[k] else -1e-6
            beyond = weighted_scores(n, with_weight(EXAMPLE_WEIGHTS, k, t + step))
            self.assertEqual(ranking(beyond)[0], b, f"軸 {k}: 同点を越えると入れ替わる")

    def test_matches_brute_force_search(self):
        rng = random.Random(2026)
        steps = 1000
        for trial in range(25):
            n_alt, n_crit = rng.randint(2, 4), rng.randint(2, 4)
            scores = [[rng.uniform(1, 10) for _ in range(n_crit)] for _ in range(n_alt)]
            directions = [rng.choice(["benefit", "cost"]) for _ in range(n_crit)]
            weights = [rng.uniform(0.05, 1.0) for _ in range(n_crit)]
            n = normalize(scores, directions)
            total = sum(weights)
            w = [x / total for x in weights]
            base_winner = ranking(weighted_scores(n, w))[0]
            got = weight_flip_points(n, weights)
            for k in range(n_crit):
                best = None
                for s in range(steps + 1):
                    t = s / steps
                    winner = ranking(weighted_scores(n, with_weight(w, k, t)))[0]
                    if winner != base_winner:
                        d = abs(t - w[k])
                        if best is None or d < best[0]:
                            best = (d, t, winner)
                if best is None:
                    # 格子の間で入れ替わる極端な場合を除き、None になるはず
                    if got[k] is not None:
                        self.assertLess(abs(got[k][0] - w[k]), 2 / steps, f"試行 {trial} 軸 {k}")
                    continue
                self.assertIsNotNone(got[k], f"試行 {trial} 軸 {k}: 総当たりでは入れ替わりがある")
                self.assertAlmostEqual(got[k][0], best[1], delta=2 / steps, msg=f"試行 {trial} 軸 {k}")
                self.assertEqual(got[k][1], best[2], f"試行 {trial} 軸 {k}")


class TestExercise4Stability(unittest.TestCase):
    def test_frequencies_sum_to_one(self):
        n = normalize(EXAMPLE_SCORES, EXAMPLE_DIRECTIONS, "ratio")
        freq = rank_stability(n, EXAMPLE_WEIGHTS, spread=0.3, trials=500, seed=1)
        self.assertEqual(len(freq), 3)
        self.assertAlmostEqual(sum(freq), 1.0)

    def test_zero_spread_gives_certain_winner(self):
        n = normalize(EXAMPLE_SCORES, EXAMPLE_DIRECTIONS, "ratio")
        self.assertEqual(rank_stability(n, EXAMPLE_WEIGHTS, spread=0.0, trials=50), [1.0, 0.0, 0.0])

    def test_dominant_alternative_always_wins(self):
        n = [[1.0, 1.0, 0.9], [0.5, 0.2, 0.8], [0.0, 0.7, 0.1]]
        self.assertEqual(rank_stability(n, [1, 1, 1], spread=0.9, trials=300, seed=7), [1.0, 0.0, 0.0])

    def test_close_call_is_split(self):
        # 比率で正規化した本文の例は僅差なので、重みを ±30% 揺らすと 1 位が割れる
        n = normalize(EXAMPLE_SCORES, EXAMPLE_DIRECTIONS, "ratio")
        freq = rank_stability(n, EXAMPLE_WEIGHTS, spread=0.3, trials=2000, seed=1)
        self.assertTrue(0.55 < freq[0] < 0.95, freq)
        self.assertTrue(0.05 < freq[1] < 0.45, freq)
        self.assertEqual(freq[2], 0.0)

    def test_robust_result_stays_robust(self):
        n = normalize(EXAMPLE_SCORES, EXAMPLE_DIRECTIONS, "minmax")
        freq = rank_stability(n, EXAMPLE_WEIGHTS, spread=0.3, trials=1000, seed=1)
        self.assertEqual(freq[1], 1.0)

    def test_reproducible_with_same_seed(self):
        n = normalize(EXAMPLE_SCORES, EXAMPLE_DIRECTIONS, "ratio")
        a = rank_stability(n, EXAMPLE_WEIGHTS, spread=0.4, trials=300, seed=42)
        b = rank_stability(n, EXAMPLE_WEIGHTS, spread=0.4, trials=300, seed=42)
        self.assertEqual(a, b)

    def test_invalid_arguments(self):
        n = [[1.0, 0.0], [0.0, 1.0]]
        for kwargs in ({"spread": -0.1}, {"spread": 1.0}, {"trials": 0}):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                rank_stability(n, [1, 1], **kwargs)
        with self.assertRaises(ValueError):
            rank_stability(n, [1, -1])


if __name__ == "__main__":
    unittest.main()
