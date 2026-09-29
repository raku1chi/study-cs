"""6.5 データモデルの多様性とデータストアの選定 — 演習1 解答例: 転置インデックスと BM25

演習の仕様は exercises/inverted_index.py の docstring を参照してください。
"""
from __future__ import annotations

import math
import unicodedata
from collections import Counter

# ---------------------------------------------------------------------------
# 提供済み: 文字の種類の判定（スタブと同じ）
# ---------------------------------------------------------------------------


def is_japanese_char(c: str) -> bool:
    code = ord(c)
    if c == "・":  # 中黒は区切りとして扱う
        return False
    return (
        0x3040 <= code <= 0x309F      # ひらがな
        or 0x30A0 <= code <= 0x30FF   # カタカナ（長音記号 ー を含む）
        or 0x4E00 <= code <= 0x9FFF   # CJK 統合漢字
        or c in "々〆"
    )


def is_word_char(c: str) -> bool:
    return c.isalnum() and not is_japanese_char(c)


# ---------------------------------------------------------------------------
# 演習1-1: トークナイザ
# ---------------------------------------------------------------------------

def tokenize(text: str) -> list[str]:
    # 全角英数字や半角カナを揃え（NFKC）、大文字・小文字を区別しない
    text = unicodedata.normalize("NFKC", text).lower()
    tokens: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if is_word_char(c):
            j = i
            while j < n and is_word_char(text[j]):
                j += 1
            tokens.append(text[i:j])  # 英語などは、空白や記号で区切られた単語をそのまま使う
            i = j
        elif is_japanese_char(c):
            j = i
            while j < n and is_japanese_char(text[j]):
                j += 1
            run = text[i:j]
            if len(run) == 1:
                tokens.append(run)
            else:
                # 日本語は単語の区切りがないので、2 文字ずつずらして切り出す（文字 bi-gram）
                tokens.extend(run[k:k + 2] for k in range(len(run) - 1))
            i = j
        else:
            i += 1  # 記号や空白は区切り
    return tokens


# ---------------------------------------------------------------------------
# 演習1-2〜1-4: 転置インデックス・ブール検索・BM25
# ---------------------------------------------------------------------------

class InvertedIndex:
    def __init__(self, k1: float = 1.2, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._postings: dict[str, dict[int, int]] = {}  # 語 → {文書 ID: 出現回数}
        self._doc_len: dict[int, int] = {}              # 文書 ID → トークン数

    # --- 演習1-2: 索引の構築 ----------------------------------------------------

    def add(self, doc_id: int, text: str) -> None:
        if doc_id in self._doc_len:
            raise ValueError(f"文書 {doc_id} はすでに登録されています")
        tokens = tokenize(text)
        self._doc_len[doc_id] = len(tokens)
        for term, tf in Counter(tokens).items():
            self._postings.setdefault(term, {})[doc_id] = tf

    def postings(self, term: str) -> list[tuple[int, int]]:
        return sorted(self._postings.get(term, {}).items())

    @property
    def doc_count(self) -> int:
        return len(self._doc_len)

    @property
    def avgdl(self) -> float:
        return sum(self._doc_len.values()) / len(self._doc_len) if self._doc_len else 0.0

    def doc_length(self, doc_id: int) -> int:
        return self._doc_len[doc_id]

    # --- 演習1-3: ブール検索 ----------------------------------------------------

    def _docs(self, term: str) -> set[int]:
        return set(self._postings.get(term, {}))

    def search_boolean(self, must: str = "", should: str = "", must_not: str = "") -> list[int]:
        must_terms = list(dict.fromkeys(tokenize(must)))
        should_terms = list(dict.fromkeys(tokenize(should)))
        if not must_terms and not should_terms:
            raise ValueError("must か should に、少なくとも 1 つの語が必要です")
        result: set[int] | None = None
        if must_terms:
            # AND: 出現する文書の少ない語から順に積集合をとると、途中の集合が小さく保たれる
            for term in sorted(must_terms, key=lambda t: len(self._postings.get(t, {}))):
                docs = self._docs(term)
                result = docs if result is None else result & docs
                if not result:
                    return []
        if should_terms:
            any_docs: set[int] = set()
            for term in should_terms:
                any_docs |= self._docs(term)  # OR: 和集合
            result = any_docs if result is None else result & any_docs
        for term in tokenize(must_not):
            result -= self._docs(term)  # NOT: 差集合
        return sorted(result)

    # --- 演習1-4: BM25 ----------------------------------------------------------

    def idf(self, term: str) -> float:
        n_docs = self.doc_count
        n_t = len(self._postings.get(term, {}))
        # Lucene などで使われる、負にならない形の IDF
        return math.log(1 + (n_docs - n_t + 0.5) / (n_t + 0.5))

    def score(self, query: str, doc_id: int) -> float:
        dl = self._doc_len[doc_id]
        avgdl = self.avgdl
        total = 0.0
        for term in dict.fromkeys(tokenize(query)):  # クエリ中の同じ語は 1 回だけ数える
            tf = self._postings.get(term, {}).get(doc_id, 0)
            if tf == 0:
                continue
            # tf が増えても k1 + 1 倍で頭打ちになり（飽和）、長い文書ほど tf の効きが弱まる（b）
            norm = tf + self.k1 * (1 - self.b + self.b * dl / avgdl)
            total += self.idf(term) * tf * (self.k1 + 1) / norm
        return total

    def search(self, query: str, k: int = 10) -> list[tuple[int, float]]:
        if k <= 0:
            raise ValueError("k は 1 以上にしてください")
        candidates: set[int] = set()
        for term in dict.fromkeys(tokenize(query)):
            candidates |= self._docs(term)  # 語を 1 つでも含む文書だけを採点する
        scored = [(doc_id, self.score(query, doc_id)) for doc_id in candidates]
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:k]
