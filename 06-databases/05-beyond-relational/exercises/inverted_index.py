"""6.5 データモデルの多様性とデータストアの選定 — 演習1: 転置インデックスと BM25

Elasticsearch / OpenSearch（中身は Apache Lucene）や PostgreSQL の全文検索の中心にある
転置インデックス（inverted index）と、検索結果の順位付けに広く使われる BM25 を実装します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 6.5
このディレクトリで、この演習だけを実行する:
    python3 -m unittest -v test_inverted_index

転置インデックス: 「語 → その語を含む文書の一覧（ポスティングリスト）」の索引。
本の巻末の索引と同じ発想で、語から文書を引く。

    文書 1: "SQL と インデックス"          語 "sql"   → [(1, 1), (3, 2)]   ← (文書 ID, 出現回数)
    文書 3: "SQL の SQL による SQL..."     語 "イン"   → [(1, 1)]

使ってはいけないもの: 全文検索のライブラリ（sqlite3 の FTS5 など）。
"""
from __future__ import annotations

import math  # noqa: F401  演習1-4 で使えます
import unicodedata  # noqa: F401  演習1-1 で使えます
from collections import Counter  # noqa: F401  演習1-2 で使えます

# ---------------------------------------------------------------------------
# 提供済み: 文字の種類の判定（変更しなくてよい）
# ---------------------------------------------------------------------------


def is_japanese_char(c: str) -> bool:
    """ひらがな・カタカナ（長音記号を含む）・漢字（CJK 統合漢字）・々〆 なら True。中黒「・」は False。"""
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
    """英数字など、単語を構成する文字（日本語の文字は除く）なら True。"""
    return c.isalnum() and not is_japanese_char(c)


# ---------------------------------------------------------------------------
# 演習1-1（★★☆）: トークナイザ
# ---------------------------------------------------------------------------

def tokenize(text: str) -> list[str]:
    """文字列をトークン（索引の単位となる語）の列に分ける。

    1. unicodedata.normalize("NFKC", text) で正規化し、lower() で小文字にする
       （全角英数字 → 半角、半角カナ → 全角 などがそろう。[1.1] の Unicode 正規化）。
    2. 先頭から順に、文字の種類が同じものの連続（ラン）に分ける:
       - is_word_char の連続 → そのまま 1 つのトークン（英単語や数字）
       - is_japanese_char の連続 → 長さ 1 ならそのまま、2 以上なら 2 文字ずつずらした
         文字 bi-gram（"天気予報" → "天気", "気予", "予報"）
       - それ以外（空白・記号）→ 区切りとして捨てる
    3. 出現順に返す（重複もそのまま）。

    >>> tokenize("Hello, World!")
    ['hello', 'world']
    >>> tokenize("東京都の天気")
    ['東京', '京都', '都の', 'の天', '天気']
    >>> tokenize("ＳＱＬ入門")
    ['sql', '入門']

    日本語の文章は単語の間に空白がないので、形態素解析（辞書で単語に区切る。Lucene の Kuromoji、
    MeCab、Sudachi など）か、この演習の n-gram が使われる。n-gram は辞書が要らず取りこぼしが
    少ない代わりに、「京都」で「東京都」がヒットするような誤りが起きる。
    """
    raise NotImplementedError("演習1-1: tokenize を実装してください")


# ---------------------------------------------------------------------------
# 演習1-2〜1-4: 転置インデックス
# ---------------------------------------------------------------------------

class InvertedIndex:
    """転置インデックス。

    提供済みの属性（使っても、自分の設計に変えてもよい）:
        _postings: {語: {文書 ID: 出現回数}}
        _doc_len: {文書 ID: トークン数}
    """

    def __init__(self, k1: float = 1.2, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._postings: dict[str, dict[int, int]] = {}
        self._doc_len: dict[int, int] = {}

    # -----------------------------------------------------------------------
    # 演習1-2（★☆☆）: 索引の構築
    # -----------------------------------------------------------------------

    def add(self, doc_id: int, text: str) -> None:
        """文書を索引に加える。同じ doc_id がすでにあれば ValueError。

        文書の長さ（トークン数）も記録する（BM25 で使う）。トークンが 0 個の文書も登録できる。
        """
        raise NotImplementedError("演習1-2: add を実装してください")

    def postings(self, term: str) -> list[tuple[int, int]]:
        """語のポスティングリスト [(文書 ID, 出現回数), ...] を文書 ID の昇順で返す。なければ []。"""
        raise NotImplementedError("演習1-2: postings を実装してください")

    @property
    def doc_count(self) -> int:
        """登録した文書の数 N。"""
        raise NotImplementedError("演習1-2: doc_count を実装してください")

    @property
    def avgdl(self) -> float:
        """文書の長さ（トークン数）の平均。文書がなければ 0.0。"""
        raise NotImplementedError("演習1-2: avgdl を実装してください")

    def doc_length(self, doc_id: int) -> int:
        """文書の長さ（トークン数）。"""
        raise NotImplementedError("演習1-2: doc_length を実装してください")

    # -----------------------------------------------------------------------
    # 演習1-3（★★☆）: ブール検索
    # -----------------------------------------------------------------------

    def search_boolean(self, must: str = "", should: str = "", must_not: str = "") -> list[int]:
        """ブール検索。条件に合う文書 ID を昇順で返す。

        それぞれの引数の文字列を tokenize() した語について（Elasticsearch の bool クエリと同じ名前）:
          - must: すべての語を含む（AND）
          - should: いずれかの語を含む（OR）。must と両方あるときは、must を満たし、かつ should の
            いずれかを含む文書
          - must_not: どの語も含まない（NOT）
        must と should の両方が語を含まなければ ValueError。

        ヒント: AND は、ポスティングリストの短い（出現する文書の少ない）語から順に積集合をとると、
        途中の集合が小さく保たれて速い。

        日本語の語は bi-gram に分かれるので、must="データベース" は「デー」「ータ」「タベ」「ベー」「ース」を
        すべて含む文書になる（位置を見ないので、厳密な語句の一致ではない）。
        """
        raise NotImplementedError("演習1-3: search_boolean を実装してください")

    # -----------------------------------------------------------------------
    # 演習1-4（★★★）: BM25 による順位付け
    # -----------------------------------------------------------------------

    def idf(self, term: str) -> float:
        """逆文書頻度 IDF(t) = ln(1 + (N − n(t) + 0.5) / (n(t) + 0.5))。

        N は文書数、n(t) は語 t を含む文書の数。まれな語ほど大きい。（この形は、多くの文書に現れる
        語でも負にならない。Lucene などで使われている）
        """
        raise NotImplementedError("演習1-4: idf を実装してください")

    def score(self, query: str, doc_id: int) -> float:
        """文書 doc_id の、query に対する BM25 のスコア。

            score(D, Q) = Σ_{t ∈ Q} IDF(t) × tf(t, D) × (k1 + 1) / (tf(t, D) + k1 × (1 − b + b × |D| / avgdl))

        - Q は query を tokenize() した語の集合（同じ語が複数回あっても 1 回だけ数える）。
        - tf(t, D) は文書 D での語 t の出現回数、|D| は文書の長さ、avgdl は平均の長さ。
        - tf が 0 の語は 0 を足す。
        """
        raise NotImplementedError("演習1-4: score を実装してください")

    def search(self, query: str, k: int = 10) -> list[tuple[int, float]]:
        """query の語を 1 つ以上含む文書を BM25 のスコアで順位付けし、上位 k 件を返す。

        戻り値は [(文書 ID, スコア), ...]。スコアの降順、同点なら文書 ID の昇順。
        k が 0 以下なら ValueError。該当がなければ []。
        """
        raise NotImplementedError("演習1-4: search を実装してください")
