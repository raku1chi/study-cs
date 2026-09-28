"""12.3 演習3: 注意機構 — テスト

実行: python3 tools/check.py 12.3   （またはこのディレクトリで python3 -m unittest -v test_attention）
"""
import math
import random
import unittest

from attention import (
    KVCache,
    causal_mask,
    layer_norm,
    matmul,
    merge_heads,
    multi_head_attention,
    scaled_dot_product_attention,
    sinusoidal_positional_encoding,
    softmax,
    split_heads,
    transpose,
)


def rand_matrix(rng, n, m):
    return [[rng.gauss(0, 1) for _ in range(m)] for _ in range(n)]


class MatrixAssertions(unittest.TestCase):
    def assertMatrixAlmostEqual(self, A, B, places=9, msg=None):
        self.assertEqual(len(A), len(B), msg)
        for ra, rb in zip(A, B):
            self.assertEqual(len(ra), len(rb), msg)
            for a, b in zip(ra, rb):
                self.assertAlmostEqual(a, b, places=places, msg=msg)


class TestBasics(MatrixAssertions):
    def test_matmul_and_transpose(self):
        A = [[1, 2, 3], [4, 5, 6]]
        B = [[1, 0], [0, 1], [1, 1]]
        self.assertEqual(matmul(A, B), [[4, 5], [10, 11]])
        self.assertEqual(transpose(A), [[1, 4], [2, 5], [3, 6]])
        with self.assertRaises(ValueError):
            matmul(A, A)
        with self.assertRaises(ValueError):
            matmul([[1, 2], [3]], B)

    def test_softmax(self):
        p = softmax([1.0, 2.0, 3.0])
        self.assertAlmostEqual(sum(p), 1.0)
        self.assertTrue(p[0] < p[1] < p[2])
        shifted = softmax([101.0, 102.0, 103.0])
        for a, b in zip(p, shifted):
            self.assertAlmostEqual(a, b, msg="定数を足しても結果は変わらない")
        big = softmax([1000.0, 1001.0, 1002.0])  # そのまま exp をとるとオーバーフローする
        self.assertAlmostEqual(sum(big), 1.0)
        self.assertEqual(softmax([0.0, -math.inf, 0.0]), [0.5, 0.0, 0.5])
        with self.assertRaises(ValueError):
            softmax([-math.inf, -math.inf])
        with self.assertRaises(ValueError):
            softmax([])

    def test_causal_mask(self):
        self.assertEqual(causal_mask(3), [[True, False, False], [True, True, False], [True, True, True]])

    def test_layer_norm(self):
        out = layer_norm([1.0, 2.0, 3.0, 10.0])
        mean = sum(out) / 4
        var = sum((v - mean) ** 2 for v in out) / 4
        self.assertAlmostEqual(mean, 0.0)
        self.assertAlmostEqual(var, 1.0, places=4)
        self.assertEqual(layer_norm([5.0, 5.0]), [0.0, 0.0])


class TestAttention(MatrixAssertions):
    def test_hand_computed_example(self):
        Q = [[1.0, 0.0]]
        K = [[1.0, 0.0], [0.0, 1.0]]
        V = [[1.0, 2.0], [3.0, 4.0]]
        out, w = scaled_dot_product_attention(Q, K, V)
        s = 1 / math.sqrt(2)  # スコアは [1/√2, 0]（√d_k = √2 で割る）
        w0 = math.exp(s) / (math.exp(s) + 1)
        self.assertAlmostEqual(w[0][0], w0)
        self.assertAlmostEqual(w[0][1], 1 - w0)
        self.assertAlmostEqual(out[0][0], w0 * 1 + (1 - w0) * 3)
        self.assertAlmostEqual(out[0][1], w0 * 2 + (1 - w0) * 4)

    def test_identical_keys_give_uniform_weights(self):
        K = [[0.3, -0.2]] * 4
        V = [[1.0], [2.0], [3.0], [6.0]]
        out, w = scaled_dot_product_attention([[5.0, 1.0]], K, V)
        self.assertMatrixAlmostEqual(w, [[0.25] * 4])
        self.assertAlmostEqual(out[0][0], 3.0, msg="重みが均等なら V の平均")

    def test_weights_are_distributions_and_shapes(self):
        rng = random.Random(0)
        Q, K, V = rand_matrix(rng, 2, 4), rand_matrix(rng, 5, 4), rand_matrix(rng, 5, 3)
        out, w = scaled_dot_product_attention(Q, K, V)  # クロスアテンション（長さが違ってよい）
        self.assertEqual((len(out), len(out[0])), (2, 3))
        self.assertEqual((len(w), len(w[0])), (2, 5))
        for row in w:
            self.assertAlmostEqual(sum(row), 1.0)
            self.assertTrue(all(x >= 0 for x in row))

    def test_causal_mask_blocks_future(self):
        rng = random.Random(1)
        X = rand_matrix(rng, 4, 3)
        _, w = scaled_dot_product_attention(X, X, X, mask=causal_mask(4))
        for i in range(4):
            for j in range(4):
                if j > i:
                    self.assertEqual(w[i][j], 0.0)
            self.assertAlmostEqual(sum(w[i]), 1.0)
        self.assertEqual(w[0][0], 1.0, "最初のトークンは自分自身だけを見る")

    def test_shape_errors(self):
        rng = random.Random(2)
        Q, K, V = rand_matrix(rng, 2, 4), rand_matrix(rng, 3, 4), rand_matrix(rng, 3, 2)
        with self.assertRaises(ValueError):
            scaled_dot_product_attention(Q, rand_matrix(rng, 3, 5), V)
        with self.assertRaises(ValueError):
            scaled_dot_product_attention(Q, K, rand_matrix(rng, 4, 2))
        with self.assertRaises(ValueError):
            scaled_dot_product_attention(Q, K, V, mask=causal_mask(3))


class TestMultiHead(MatrixAssertions):
    def test_split_and_merge(self):
        X = [[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]]
        heads = split_heads(X, 3)
        self.assertEqual(heads, [[[1, 2], [7, 8]], [[3, 4], [9, 10]], [[5, 6], [11, 12]]])
        self.assertEqual(merge_heads(heads), X)
        with self.assertRaises(ValueError):
            split_heads(X, 4)

    def test_single_head_equals_plain_attention(self):
        rng = random.Random(3)
        X = rand_matrix(rng, 5, 4)
        Wq, Wk, Wv, Wo = (rand_matrix(rng, 4, 4) for _ in range(4))
        expected = matmul(scaled_dot_product_attention(matmul(X, Wq), matmul(X, Wk), matmul(X, Wv))[0], Wo)
        self.assertMatrixAlmostEqual(multi_head_attention(X, Wq, Wk, Wv, Wo, 1), expected)

    def test_heads_are_independent(self):
        rng = random.Random(4)
        X = rand_matrix(rng, 3, 4)
        Wq, Wk, Wv, Wo = (rand_matrix(rng, 4, 4) for _ in range(4))
        identity = [[float(i == j) for j in range(4)] for i in range(4)]
        out = multi_head_attention(X, Wq, Wk, Wv, identity, 2)
        Q, K, V = matmul(X, Wq), matmul(X, Wk), matmul(X, Wv)
        h0 = scaled_dot_product_attention([r[:2] for r in Q], [r[:2] for r in K], [r[:2] for r in V])[0]
        self.assertMatrixAlmostEqual([r[:2] for r in out], h0)

    def test_causal_output_does_not_depend_on_future_tokens(self):
        rng = random.Random(5)
        X = rand_matrix(rng, 6, 4)
        Ws = [rand_matrix(rng, 4, 4) for _ in range(4)]
        base = multi_head_attention(X, *Ws, n_heads=2, causal=True)
        X2 = [row[:] for row in X]
        X2[4] = [9.0, -9.0, 9.0, -9.0]  # 位置 4 以降を書き換える
        X2[5] = [0.0, 1.0, 2.0, 3.0]
        changed = multi_head_attention(X2, *Ws, n_heads=2, causal=True)
        self.assertMatrixAlmostEqual(base[:4], changed[:4], msg="過去の位置の出力は未来のトークンに影響されない")
        self.assertNotEqual(base[4], changed[4])
        non_causal = multi_head_attention(X2, *Ws, n_heads=2, causal=False)
        self.assertNotEqual(multi_head_attention(X, *Ws, n_heads=2)[0], non_causal[0])


class TestPositionalEncodingAndCache(MatrixAssertions):
    def test_positional_encoding_values(self):
        pe = sinusoidal_positional_encoding(50, 8)
        self.assertEqual((len(pe), len(pe[0])), (50, 8))
        self.assertEqual(pe[0], [0.0, 1.0] * 4)
        self.assertAlmostEqual(pe[7][0], math.sin(7))
        self.assertAlmostEqual(pe[7][1], math.cos(7))
        self.assertAlmostEqual(pe[7][2], math.sin(7 / 10000 ** (2 / 8)))
        self.assertAlmostEqual(pe[7][7], math.cos(7 / 10000 ** (6 / 8)))
        self.assertTrue(all(-1.0 <= v <= 1.0 for row in pe for v in row))

    def test_dot_product_depends_only_on_offset(self):
        pe = sinusoidal_positional_encoding(40, 16)
        dot = lambda a, b: sum(x * y for x, y in zip(a, b))  # noqa: E731
        for k in (1, 3, 7):
            vals = [dot(pe[p], pe[p + k]) for p in range(0, 30)]
            for v in vals:
                self.assertAlmostEqual(v, vals[0], msg="内積は相対位置 k だけで決まる")

    def test_kv_cache_matches_full_causal_attention(self):
        rng = random.Random(6)
        Q, K, V = rand_matrix(rng, 5, 4), rand_matrix(rng, 5, 4), rand_matrix(rng, 5, 3)
        full, full_w = scaled_dot_product_attention(Q, K, V, mask=causal_mask(5))
        cache = KVCache()
        for i in range(5):
            cache.append(K[i], V[i])  # 新しいトークンの K, V を追加するだけ
            out, w = cache.attend(Q[i])
            self.assertEqual(len(cache), i + 1)
            for a, b in zip(out, full[i]):
                self.assertAlmostEqual(a, b)
            for a, b in zip(w, full_w[i][: i + 1]):
                self.assertAlmostEqual(a, b)

    def test_kv_cache_errors(self):
        cache = KVCache()
        with self.assertRaises(ValueError):
            cache.attend([1.0, 2.0])
        cache.append([1.0, 2.0], [3.0])
        with self.assertRaises(ValueError):
            cache.append([1.0], [3.0])


if __name__ == "__main__":
    unittest.main()
