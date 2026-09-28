"""13.6 チームと組織の設計 — テスト（組織の規模の計算）

実行: python3 tools/check.py 13.6   （またはこのディレクトリで python3 -m unittest -v test_org_calc）
"""
import unittest

from org_calc import communication_paths, management_layers, management_overhead


class TestExercise1CommunicationPaths(unittest.TestCase):
    def test_small_values(self):
        self.assertEqual([communication_paths(n) for n in range(6)], [0, 0, 1, 3, 6, 10])

    def test_grows_quadratically(self):
        self.assertEqual(communication_paths(10), 45)
        self.assertEqual(communication_paths(50), 1225)
        self.assertEqual(communication_paths(100), 4950)

    def test_negative_is_error(self):
        with self.assertRaises(ValueError):
            communication_paths(-1)


class TestExercise1Layers(unittest.TestCase):
    def test_book_examples(self):
        self.assertEqual(management_layers(150, ic_span=7, manager_span=5), [22, 5, 1])
        self.assertEqual(management_layers(30, ic_span=7, manager_span=5), [5, 1])
        self.assertEqual(management_layers(80, ic_span=7, manager_span=5), [12, 3, 1])
        self.assertEqual(management_layers(500, ic_span=7, manager_span=5), [72, 15, 3, 1])

    def test_single_team(self):
        self.assertEqual(management_layers(6, ic_span=8, manager_span=5), [1])
        self.assertEqual(management_layers(8, ic_span=8, manager_span=5), [1])
        self.assertEqual(management_layers(9, ic_span=8, manager_span=5), [2, 1])

    def test_last_layer_is_one(self):
        for engineers in range(1, 300):
            layers = management_layers(engineers, ic_span=6, manager_span=4)
            self.assertEqual(layers[-1], 1, engineers)
            self.assertTrue(all(a >= b for a, b in zip(layers, layers[1:])), engineers)

    def test_invalid_arguments(self):
        for args in ((0, 7, 5), (10, 0, 5), (10, 7, 1)):
            with self.assertRaises(ValueError, msg=str(args)):
                management_layers(*args)


class TestExercise1Overhead(unittest.TestCase):
    def test_example(self):
        o = management_overhead(30, 7, 5, engineer_cost=1000, manager_cost=1300)
        self.assertEqual(o["managers"], 6)
        self.assertEqual(o["layers"], 2)
        self.assertAlmostEqual(o["people_ratio"], 6 / 36)
        self.assertAlmostEqual(o["cost_ratio"], 7800 / 37800)

    def test_wider_span_means_less_overhead(self):
        narrow = management_overhead(150, 4, 3, 1000, 1300)
        wide = management_overhead(150, 8, 6, 1000, 1300)
        self.assertGreater(narrow["managers"], wide["managers"])
        self.assertGreater(narrow["layers"], wide["layers"])
        self.assertGreater(narrow["cost_ratio"], wide["cost_ratio"])

    def test_zero_costs(self):
        o = management_overhead(10, 5, 5, 0, 0)
        self.assertEqual(o["cost_ratio"], 0.0)

    def test_negative_cost_is_error(self):
        with self.assertRaises(ValueError):
            management_overhead(10, 5, 5, -1, 100)
        with self.assertRaises(ValueError):
            management_overhead(10, 5, 5, 100, -1)


if __name__ == "__main__":
    unittest.main()
