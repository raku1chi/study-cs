"""6.1 リレーショナルモデルとSQL — 演習3: 関数従属性と正規化

関数従属性（functional dependency, FD）から、属性閉包・候補キーを求め、
BCNF・第3正規形の違反を検出し、BCNF への分解を行います。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 6.1
このディレクトリで、この演習だけを実行する:
    python3 -m unittest -v test_normalize

表記:
    - 関数従属性 X → Y は、(左辺の属性の frozenset, 右辺の属性の frozenset) のタプルで表す（型 FD）。
    - parse_fds("A B -> C; C -> D") のように文字列から作れる（提供済み）。
    - 属性名は任意の文字列（日本語でもよい）。スキーマは属性名の集まり（文字列 "ABCD" も
      1 文字ずつの属性の集まりとして渡せる）。
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from itertools import combinations  # noqa: F401  演習3-2・3-4 で使えます

FD = tuple[frozenset[str], frozenset[str]]


# ---------------------------------------------------------------------------
# 提供済み: 関数従属性の読み取り（変更しなくてよい）
# ---------------------------------------------------------------------------

def parse_fds(text: str) -> list[FD]:
    """'A B -> C; C -> D' のような文字列を FD のリストにする。

    - FD どうしは ';' か改行で区切る。属性どうしは空白かカンマで区切る。
    - '->' がない・2 つ以上ある、左辺か右辺が空、のときは ValueError。

    >>> fds = parse_fds("A, B -> C; C -> D")
    >>> fds[1]
    (frozenset({'C'}), frozenset({'D'}))
    >>> [format_fd(f) for f in fds]
    ['A B -> C', 'C -> D']
    """
    fds: list[FD] = []
    for part in re.split(r"[;\n]", text):
        part = part.strip()
        if not part:
            continue
        if part.count("->") != 1:
            raise ValueError(f"'左辺 -> 右辺' の形ではありません: {part!r}")
        left, right = part.split("->")
        lhs = frozenset(a for a in re.split(r"[,\s]+", left.strip()) if a)
        rhs = frozenset(a for a in re.split(r"[,\s]+", right.strip()) if a)
        if not lhs or not rhs:
            raise ValueError(f"左辺と右辺には属性が 1 つ以上必要です: {part!r}")
        fds.append((lhs, rhs))
    return fds


def format_fd(fd: FD) -> str:
    """FD を 'A B -> C' の形の文字列にする（属性は名前順）。"""
    lhs, rhs = fd
    return f"{' '.join(sorted(lhs))} -> {' '.join(sorted(rhs))}"


def _check_schema(schema: Iterable[str], fds: Sequence[FD]) -> frozenset[str]:
    """スキーマを frozenset にする。空のスキーマや、スキーマ外の属性を含む FD は ValueError。"""
    attrs = frozenset(schema)
    if not attrs:
        raise ValueError("スキーマが空です")
    for lhs, rhs in fds:
        outside = (lhs | rhs) - attrs
        if outside:
            raise ValueError(f"関数従属性 {format_fd((lhs, rhs))} にスキーマ外の属性があります: {sorted(outside)}")
    return attrs


# ---------------------------------------------------------------------------
# 演習3-1（★★☆）: 属性閉包と超キー
# ---------------------------------------------------------------------------

def closure(attributes: Iterable[str], fds: Sequence[FD]) -> frozenset[str]:
    """属性集合 X の閉包 X⁺（FD の集合から、X によって決まるすべての属性）を返す。

    >>> fds = parse_fds("A -> B; B -> C; C D -> E")
    >>> sorted(closure({"A"}, fds))
    ['A', 'B', 'C']
    >>> sorted(closure({"A", "D"}, fds))
    ['A', 'B', 'C', 'D', 'E']

    ヒント: 結果を X で初期化し、「左辺がすべて結果に含まれる FD の右辺を加える」を、
    結果が増えなくなるまで繰り返す。
    """
    raise NotImplementedError("演習3-1: closure を実装してください")


def is_superkey(attributes: Iterable[str], schema: Iterable[str], fds: Sequence[FD]) -> bool:
    """attributes がスキーマ schema の超キー（閉包がスキーマ全体を含む）かどうか。

    - attributes にスキーマ外の属性があれば ValueError。
    - スキーマが空、または FD にスキーマ外の属性があれば ValueError（_check_schema を使える）。
    """
    raise NotImplementedError("演習3-1: is_superkey を実装してください")


# ---------------------------------------------------------------------------
# 演習3-2（★★★）: 候補キー
# ---------------------------------------------------------------------------

def candidate_keys(schema: Iterable[str], fds: Sequence[FD]) -> list[frozenset[str]]:
    """すべての候補キー（極小の超キー）を返す。

    - 並び順: 属性数の少ない順、同数なら sorted(キー) の辞書順。
    - FD が 1 つもなければ、スキーマ全体が唯一の候補キー。
    - スキーマのエラーは is_superkey と同じく ValueError。

    >>> [sorted(k) for k in candidate_keys("ABCD", parse_fds("A -> B; B -> C; C -> A"))]
    [['A', 'D'], ['B', 'D'], ['C', 'D']]

    ヒント（総当たりを速くする工夫）:
    - どの FD の右辺（自明でない部分）にも現れない属性は、必ずすべての候補キーに入る。
    - 右辺にだけ現れ、左辺に現れない属性は、どの候補キーにも入らない。
    - 残りの属性の組み合わせを、小さい順に試す。見つかったキーを含む集合は極小ではない。
    """
    raise NotImplementedError("演習3-2: candidate_keys を実装してください")


# ---------------------------------------------------------------------------
# 演習3-3（★★☆）: BCNF と第3正規形の違反の検出
# ---------------------------------------------------------------------------

def bcnf_violations(schema: Iterable[str], fds: Sequence[FD]) -> list[FD]:
    """BCNF に違反する FD を、与えられた順に返す。

    BCNF: 自明でないすべての FD X → Y について、X が超キーであること。
    - 各違反は (X, Y − X)（右辺から自明な部分を除いたもの）の形で返す。
    - 自明な FD（Y ⊆ X）は違反にならない。
    - 元のスキーマについては、与えられた FD だけを調べれば十分であることが知られている。

    >>> fds = parse_fds("学生 科目 -> 教員; 教員 -> 科目")
    >>> [format_fd(v) for v in bcnf_violations(["学生", "科目", "教員"], fds)]
    ['教員 -> 科目']
    """
    raise NotImplementedError("演習3-3: bcnf_violations を実装してください")


def third_nf_violations(schema: Iterable[str], fds: Sequence[FD]) -> list[FD]:
    """第3正規形（3NF）に違反する FD を、与えられた順に返す。

    3NF: 自明でないすべての FD X → A について、X が超キーであるか、
    A がキー属性（いずれかの候補キーに含まれる属性。prime attribute）であること。
    - 各違反は (X, 違反している右辺の属性の集合) の形で返す。右辺のうち、自明な属性と
      キー属性は除く。X が超キーの FD と、除いた結果が空になる FD は含めない。

    >>> fds = parse_fds("学生 科目 -> 教員; 教員 -> 科目")
    >>> third_nf_violations(["学生", "科目", "教員"], fds)   # 科目はキー属性なので 3NF は満たす
    []
    """
    raise NotImplementedError("演習3-3: third_nf_violations を実装してください")


# ---------------------------------------------------------------------------
# 演習3-4（★★★ 発展）: BCNF 分解
# ---------------------------------------------------------------------------

def bcnf_decompose(schema: Iterable[str], fds: Sequence[FD]) -> list[frozenset[str]]:
    """スキーマを、無損失（lossless-join）な BCNF のスキーマの集まりに分解する。

    アルゴリズム:
      1. 分解待ちのスキーマ R を 1 つ取り出す。
      2. R の中に BCNF 違反 X → Y があれば、R を (X ∪ Y) と (R − Y) に分けて分解待ちに戻す。
         なければ R を結果に加える。
      3. 分解待ちがなくなるまで繰り返す。
    注意: 分解後の R では、与えられた FD だけでなく、そこから導かれる FD を R に射影したもの
    を調べる必要がある。R の部分集合 X ごとに closure(X) ∩ R を計算するとよい
    （X ⊊ closure(X) ∩ R ⊊ R なら、X → (closure(X) ∩ R) − X が違反）。

    - 結果は、他の断片に真に含まれる断片を除き、sorted(断片) の辞書順に並べる。
    - 結果が一意になるよう、違反の X は「属性数の少ない順、同数なら sorted の辞書順」で
      最初に見つかったものを使うとよい（テストは結果の性質で確かめるので、必須ではない）。

    >>> fds = parse_fds("学生 科目 -> 教員; 教員 -> 科目")
    >>> [sorted(f) for f in bcnf_decompose(["学生", "科目", "教員"], fds)]
    [['学生', '教員'], ['教員', '科目']]
    """
    raise NotImplementedError("演習3-4: bcnf_decompose を実装してください")
