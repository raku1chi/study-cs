"""12.3 深層学習とTransformer — 演習4: バイト単位の BPE トークナイザ（★★☆）

大規模言語モデルは、文字列を「トークン」の ID 列にしてから処理します。多くのモデルが使う
BPE（Byte Pair Encoding）を、UTF-8 のバイト列の上で実装します（GPT-2 以降のバイトレベル BPE と同じ考え方）。

    学習: 256 種類のバイトから始め、「最も頻繁に隣り合うペア」を 1 つの新しいトークンに併合する、
          を語彙が vocab_size になるまで繰り返す。併合した順番（ランク）を記録する。
    符号化: 文字列を UTF-8 のバイト列にし、学習した併合をランクの高い（早く学習した）順に適用する。
    復号: トークン ID をバイト列に戻して連結し、UTF-8 として解釈する。

バイトから始めるので、学習データになかった文字（絵文字・珍しい漢字）も必ず表現でき、
「未知語（unknown token）」が生じません。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 12.3
このディレクトリで直接実行する場合:
    python3 -m unittest -v test_bpe
"""
from __future__ import annotations

import re
from collections import Counter  # noqa: F401
from typing import Sequence

# GPT-2 の事前分割を標準ライブラリの re で近似した正規表現（実装済み）:
# 「前に空白を 1 つ伴う単語」「前に空白を伴う記号の並び」「空白」に分ける。
# 併合が単語の境界をまたがないようにするための前処理。
PRETOKENIZE_PATTERN = re.compile(r" ?\w+| ?[^\w\s]+|\s+(?!\S)|\s+")


def pretokenize(text: str) -> list[str]:
    """テキストを塊（chunk）に分ける（実装済み）。連結すると元のテキストに戻る。

    >>> pretokenize("Hello, world!")
    ['Hello', ',', ' world', '!']
    """
    return PRETOKENIZE_PATTERN.findall(text)


# ---------------------------------------------------------------------------
# 演習4a（★☆☆）: ペアの数え上げと併合
# ---------------------------------------------------------------------------

def count_pairs(chunks: dict[tuple[int, ...], int]) -> dict[tuple[int, int], int]:
    """{トークン ID の列: その塊の出現回数} から、隣り合うペアの出現回数を数える。

    >>> count_pairs({(1, 2, 3): 2, (2, 3): 1})
    {(1, 2): 2, (2, 3): 3}
    """
    raise NotImplementedError("演習4a: count_pairs を実装してください")


def merge_pair(ids: Sequence[int], pair: tuple[int, int], new_id: int) -> list[int]:
    """ids の中の pair を、左から重ならないように new_id に置き換えた新しいリストを返す。

    >>> merge_pair([1, 2, 3, 1, 2], (1, 2), 256)
    [256, 3, 256]
    >>> merge_pair([1, 1, 1], (1, 1), 256)
    [256, 1]
    """
    raise NotImplementedError("演習4a: merge_pair を実装してください")


# ---------------------------------------------------------------------------
# 演習4b（★★☆）: トークナイザ
# ---------------------------------------------------------------------------

class BPETokenizer:
    """バイトレベル BPE トークナイザ。

    属性:
        merges: {(id1, id2): 新しい id}。挿入順 = 学習した順（ランク）。新しい id は 256, 257, … と振る。
        vocab:  {id: その id が表すバイト列}。0〜255 は 1 バイトそのもの。
                併合でできた id のバイト列は、2 つの構成要素のバイト列の連結。
    """

    def __init__(self, merges: Sequence[tuple[int, int]] | None = None) -> None:
        """merges（学習済みの併合の列）から復元する。None なら併合なし（語彙 256）。

        ペアに未知の id が含まれていたら ValueError。
        """
        raise NotImplementedError("演習4b: BPETokenizer.__init__ を実装してください")

    @property
    def merge_list(self) -> list[tuple[int, int]]:
        """学習した順の併合のリスト。"""
        raise NotImplementedError("演習4b: merge_list を実装してください")

    @property
    def vocab_size(self) -> int:
        """語彙の大きさ（256 + 併合の数）。"""
        raise NotImplementedError("演習4b: vocab_size を実装してください")

    @classmethod
    def train(cls, text: str, vocab_size: int) -> "BPETokenizer":
        """text から語彙が vocab_size になるまで併合を学習する。

        1. pretokenize で塊に分け、各塊を UTF-8 のバイト列（int のタプル）にして出現回数を数える。
        2. vocab_size - 256 回まで繰り返す:
           - count_pairs で隣り合うペアを数える。ペアがなければ（すべての塊が 1 トークン）終了。
           - 最も頻度が高いペアを選ぶ。同数なら (id1, id2) が辞書順で最小のもの（決定的にするため）。
           - 新しい id を割り当て、すべての塊でそのペアを merge_pair する。
        vocab_size < 256 なら ValueError。
        """
        raise NotImplementedError("演習4b: BPETokenizer.train を実装してください")

    def encode(self, text: str) -> list[int]:
        """テキストをトークン ID の列にする。

        塊ごとに UTF-8 のバイト列から始め、「現在の列の隣り合うペアのうち、merges で最もランクの高い
        （最も早く学習した）もの」を併合する、を併合できるペアがなくなるまで繰り返す。
        （学習した併合を順番どおりに全部適用するのと同じ結果になる）
        """
        raise NotImplementedError("演習4b: encode を実装してください")

    def decode(self, ids: Sequence[int]) -> str:
        """ID の列をバイト列に戻して連結し、UTF-8 として解釈する。

        - 未知の ID があれば ValueError。
        - 任意の ID 列は UTF-8 として不完全なことがあるので、errors="replace" で復号する
          （不正な部分は置換文字 U+FFFD になる）。encode の結果を decode すれば元の文字列に戻る。
        """
        raise NotImplementedError("演習4b: decode を実装してください")

    def token_bytes(self, token_id: int) -> bytes:
        """ID が表すバイト列。未知の ID は ValueError。"""
        raise NotImplementedError("演習4b: token_bytes を実装してください")
