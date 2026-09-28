"""12.3 深層学習とTransformer — 演習4: バイト単位の BPE トークナイザ（解答例）

演習の仕様は exercises/bpe.py の docstring を参照してください。
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Sequence

# GPT-2 の事前分割を標準ライブラリの re で近似した正規表現（実装済み）:
# 「前に空白を 1 つ伴う単語」「前に空白を伴う記号の並び」「空白」に分ける
PRETOKENIZE_PATTERN = re.compile(r" ?\w+| ?[^\w\s]+|\s+(?!\S)|\s+")


def pretokenize(text: str) -> list[str]:
    return PRETOKENIZE_PATTERN.findall(text)


# ---------------------------------------------------------------------------
# 演習4a: ペアの数え上げと併合
# ---------------------------------------------------------------------------

def count_pairs(chunks: dict[tuple[int, ...], int]) -> dict[tuple[int, int], int]:
    counts: dict[tuple[int, int], int] = {}
    for ids, freq in chunks.items():
        for pair in zip(ids, ids[1:]):
            counts[pair] = counts.get(pair, 0) + freq  # 同じ塊が freq 回出てくるので重みを掛ける
    return counts


def merge_pair(ids: Sequence[int], pair: tuple[int, int], new_id: int) -> list[int]:
    out: list[int] = []
    i = 0
    while i < len(ids):
        if i + 1 < len(ids) and ids[i] == pair[0] and ids[i + 1] == pair[1]:
            out.append(new_id)  # 左から重ならないように置き換える（"aaa" → "Xa"）
            i += 2
        else:
            out.append(ids[i])
            i += 1
    return out


# ---------------------------------------------------------------------------
# 演習4b: トークナイザ
# ---------------------------------------------------------------------------

class BPETokenizer:
    def __init__(self, merges: Sequence[tuple[int, int]] | None = None) -> None:
        self.merges: dict[tuple[int, int], int] = {}
        # 基本の語彙は 256 種類のバイト。どんな文字列も UTF-8 のバイト列なので「未知語」が生じない
        self.vocab: dict[int, bytes] = {i: bytes([i]) for i in range(256)}
        for pair in merges or ():
            self._add_merge(tuple(pair))

    def _add_merge(self, pair: tuple[int, int]) -> int:
        a, b = pair
        if a not in self.vocab or b not in self.vocab:
            raise ValueError(f"未知のトークン ID を含むペアです: {pair}")
        new_id = 256 + len(self.merges)
        self.merges[(a, b)] = new_id
        self.vocab[new_id] = self.vocab[a] + self.vocab[b]
        return new_id

    @property
    def merge_list(self) -> list[tuple[int, int]]:
        return list(self.merges)  # dict は挿入順（= 学習した順）を保つ

    @property
    def vocab_size(self) -> int:
        return len(self.vocab)

    @classmethod
    def train(cls, text: str, vocab_size: int) -> "BPETokenizer":
        if vocab_size < 256:
            raise ValueError("vocab_size は 256 以上")
        tokenizer = cls()
        # 同じ塊（単語）は何度出てきても 1 回だけ持ち、頻度を重みとして使う
        chunks: Counter = Counter(tuple(chunk.encode("utf-8")) for chunk in pretokenize(text))
        for _ in range(vocab_size - 256):
            counts = count_pairs(chunks)
            if not counts:
                break  # すべての塊が 1 トークンになった
            # 最も頻度の高いペア。同数なら ID の組が辞書順で最小のもの（決定的にするため）
            best = min(counts, key=lambda p: (-counts[p], p))
            new_id = tokenizer._add_merge(best)
            merged: Counter = Counter()
            for ids, freq in chunks.items():
                merged[tuple(merge_pair(ids, best, new_id))] += freq
            chunks = merged
        return tokenizer

    def encode(self, text: str) -> list[int]:
        out: list[int] = []
        for chunk in pretokenize(text):
            ids = list(chunk.encode("utf-8"))
            while len(ids) >= 2:
                # 学習で早く作られた（順位の高い）ペアから順に併合する
                candidates = set(zip(ids, ids[1:]))
                pair = min(candidates, key=lambda p: self.merges.get(p, float("inf")))
                if pair not in self.merges:
                    break
                ids = merge_pair(ids, pair, self.merges[pair])
            out.extend(ids)
        return out

    def decode(self, ids: Sequence[int]) -> str:
        try:
            data = b"".join(self.vocab[i] for i in ids)
        except KeyError as exc:
            raise ValueError(f"未知のトークン ID です: {exc.args[0]}") from None
        # 任意の ID 列は UTF-8 として不完全なこともあるので、置換文字で補う
        return data.decode("utf-8", errors="replace")

    def token_bytes(self, token_id: int) -> bytes:
        if token_id not in self.vocab:
            raise ValueError(f"未知のトークン ID です: {token_id}")
        return self.vocab[token_id]
