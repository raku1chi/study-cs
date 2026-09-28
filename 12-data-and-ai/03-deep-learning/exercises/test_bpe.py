"""12.3 演習4: BPE トークナイザ — テスト

実行: python3 tools/check.py 12.3   （またはこのディレクトリで python3 -m unittest -v test_bpe）
"""
import functools
import unittest

from bpe import BPETokenizer, count_pairs, merge_pair, pretokenize

CORPUS = (
    "the lower the slower, the lowest the slowest. "
    "low lower lowest; slow slower slowest! " * 20
    + "東京都の東京駅から東京タワーへ行く。東京は大きい。" * 10
)


def apply_merges_in_order(tokenizer, text):
    """テスト用の参照実装: 学習した順にすべての併合を順番に適用する。"""
    out = []
    for chunk in pretokenize(text):
        ids = list(chunk.encode("utf-8"))
        for pair in tokenizer.merge_list:
            new_id = tokenizer.merges[pair]
            i, merged = 0, []
            while i < len(ids):
                if i + 1 < len(ids) and (ids[i], ids[i + 1]) == pair:
                    merged.append(new_id)
                    i += 2
                else:
                    merged.append(ids[i])
                    i += 1
            ids = merged
        out.extend(ids)
    return out


@functools.lru_cache(maxsize=None)
def trained_tokenizer():
    """CORPUS で語彙 300 まで学習したトークナイザ（テスト間で使い回す）。"""
    return BPETokenizer.train(CORPUS, 300)


class TestPieces(unittest.TestCase):
    def test_count_pairs_uses_frequencies(self):
        counts = count_pairs({(1, 2, 3): 2, (2, 3): 1, (7,): 5})
        self.assertEqual(counts, {(1, 2): 2, (2, 3): 3})
        self.assertEqual(count_pairs({}), {})

    def test_merge_pair(self):
        self.assertEqual(merge_pair([1, 2, 3, 1, 2], (1, 2), 256), [256, 3, 256])
        self.assertEqual(merge_pair([1, 1, 1], (1, 1), 256), [256, 1], "左から重ならないように置き換える")
        self.assertEqual(merge_pair([1, 1, 1, 1], (1, 1), 256), [256, 256])
        self.assertEqual(merge_pair([5, 6], (1, 2), 256), [5, 6])
        self.assertEqual(merge_pair([], (1, 2), 256), [])


class TestTokenizer(unittest.TestCase):
    @property
    def tok(self):
        return trained_tokenizer()

    def test_first_merges_and_tie_breaking(self):
        tok = BPETokenizer.train("aaabdaaabac", 258)
        # (97,97) が 4 回で最多。次は (256,97) と (97,98) が 2 回で同数 → 小さい (97,98)
        self.assertEqual(tok.merge_list, [(97, 97), (97, 98)])
        self.assertEqual(tok.token_bytes(256), b"aa")
        self.assertEqual(tok.token_bytes(257), b"ab")

    def test_training_is_deterministic(self):
        self.assertEqual(BPETokenizer.train(CORPUS, 300).merge_list, BPETokenizer.train(CORPUS, 300).merge_list)

    def test_vocab(self):
        self.assertEqual(self.tok.vocab_size, 300)
        self.assertEqual(len(self.tok.merge_list), 44)
        self.assertEqual(self.tok.token_bytes(65), b"A")
        for pair, new_id in self.tok.merges.items():
            self.assertEqual(self.tok.token_bytes(new_id), self.tok.token_bytes(pair[0]) + self.tok.token_bytes(pair[1]))

    def test_round_trip(self):
        # 事前分割（実装済み）は文字を失わない。その上で encode → decode が元に戻ることを確かめる
        self.assertEqual(pretokenize("Hello, world!"), ["Hello", ",", " world", "!"])
        self.assertEqual(pretokenize("a  b"), ["a", " ", " b"])
        self.assertEqual(pretokenize("今日は晴れ。明日は雨"), ["今日は晴れ", "。", "明日は雨"])
        for text in ["", "the slowest lower", "未知の文字: 𠮷野家 😀 café", "  spaces\tand\nnewlines  ",
                     "東京タワーへ行く。", "zzzz qqqq"]:
            ids = self.tok.encode(text)
            self.assertTrue(all(i in self.tok.vocab for i in ids))
            self.assertEqual(self.tok.decode(ids), text)

    def test_compression_and_whole_word_tokens(self):
        ids = self.tok.encode(CORPUS)
        self.assertLess(len(ids), len(CORPUS.encode("utf-8")) / 3)
        self.assertEqual(len(self.tok.encode(" slowest")), 1, "頻出する単語は 1 トークンになる")
        self.assertEqual(len(self.tok.encode("東京")), 1, "日本語の頻出語も（バイト列の併合で）1 トークンになる")

    def test_encode_matches_sequential_merges(self):
        for text in [CORPUS[:300], "slowly lowering the lowest tower", "東京の東の京都"]:
            self.assertEqual(self.tok.encode(text), apply_merges_in_order(self.tok, text))

    def test_rebuild_from_merges(self):
        clone = BPETokenizer(self.tok.merge_list)
        self.assertEqual(clone.encode(CORPUS[:200]), self.tok.encode(CORPUS[:200]))

    def test_training_stops_when_nothing_to_merge(self):
        tok = BPETokenizer.train("abc", 300)
        self.assertEqual(tok.merge_list, [(97, 98), (256, 99)])
        self.assertEqual(tok.vocab_size, 258)
        self.assertLess(BPETokenizer.train(CORPUS, 1000).vocab_size, 1000, "異なる塊が少ないコーパスでは途中で止まる")

    def test_errors(self):
        with self.assertRaises(ValueError):
            BPETokenizer.train("abc", 255)
        with self.assertRaises(ValueError):
            self.tok.decode([10_000])
        with self.assertRaises(ValueError):
            self.tok.token_bytes(-1)
        with self.assertRaises(ValueError):
            BPETokenizer([(1000, 1001)])

    def test_decode_of_partial_character_uses_replacement(self):
        ids = list("東".encode("utf-8"))[:2]  # 3 バイトのうち 2 バイトだけ
        self.assertEqual(self.tok.decode(ids), "�")


if __name__ == "__main__":
    unittest.main()
