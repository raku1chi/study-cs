"""6.1 リレーショナルモデルとSQL — 演習3 解答例: 関数従属性と正規化

演習の仕様は exercises/normalize.py の docstring を参照してください。
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from itertools import combinations

FD = tuple[frozenset[str], frozenset[str]]


# ---------------------------------------------------------------------------
# 提供済み: 関数従属性の読み取り（スタブと同じ）
# ---------------------------------------------------------------------------

def parse_fds(text: str) -> list[FD]:
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
    lhs, rhs = fd
    return f"{' '.join(sorted(lhs))} -> {' '.join(sorted(rhs))}"


def _check_schema(schema: Iterable[str], fds: Sequence[FD]) -> frozenset[str]:
    attrs = frozenset(schema)
    if not attrs:
        raise ValueError("スキーマが空です")
    for lhs, rhs in fds:
        outside = (lhs | rhs) - attrs
        if outside:
            raise ValueError(f"関数従属性 {format_fd((lhs, rhs))} にスキーマ外の属性があります: {sorted(outside)}")
    return attrs


# ---------------------------------------------------------------------------
# 演習3-1: 属性閉包
# ---------------------------------------------------------------------------

def closure(attributes: Iterable[str], fds: Sequence[FD]) -> frozenset[str]:
    # X⁺ を求める定番のアルゴリズム:
    # 「左辺がすべて結果に含まれる FD があれば、右辺を結果に加える」を、何も増えなくなるまで繰り返す。
    # （反射律・増加律・推移律を機械的に適用しているのと同じ）
    result = set(attributes)
    changed = True
    while changed:
        changed = False
        for lhs, rhs in fds:
            if lhs <= result and not rhs <= result:
                result |= rhs
                changed = True
    return frozenset(result)


def is_superkey(attributes: Iterable[str], schema: Iterable[str], fds: Sequence[FD]) -> bool:
    attrs = frozenset(attributes)
    all_attrs = _check_schema(schema, fds)
    if not attrs <= all_attrs:
        raise ValueError(f"スキーマにない属性です: {sorted(attrs - all_attrs)}")
    # X が超キー ⇔ X⁺ がスキーマ全体を含む
    return closure(attrs, fds) >= all_attrs


# ---------------------------------------------------------------------------
# 演習3-2: 候補キー
# ---------------------------------------------------------------------------

def candidate_keys(schema: Iterable[str], fds: Sequence[FD]) -> list[frozenset[str]]:
    attrs = _check_schema(schema, fds)
    lhs_attrs = frozenset().union(*(lhs for lhs, _ in fds))
    rhs_attrs = frozenset().union(*(rhs - lhs for lhs, rhs in fds))  # 自明な部分は除く
    # どの FD の右辺（自明でない部分）にも現れない属性は、他から決まらないので必ずキーに入る。
    core = attrs - rhs_attrs
    # 右辺にだけ現れる属性は、他の属性から決まるのでキーには決して入らない。
    # 両方に現れる属性だけが「入るかもしれない」候補になる。
    middle = sorted((lhs_attrs & rhs_attrs) - core)
    keys: list[frozenset[str]] = []
    # 小さい組み合わせから順に試す。見つかったキーを含む集合は極小でないので飛ばす。
    for size in range(len(middle) + 1):
        for extra in combinations(middle, size):
            candidate = core | frozenset(extra)
            if any(k <= candidate for k in keys):
                continue
            if closure(candidate, fds) >= attrs:
                keys.append(candidate)
    return sorted(keys, key=lambda k: (len(k), sorted(k)))


# ---------------------------------------------------------------------------
# 演習3-3: BCNF と第3正規形の違反の検出
# ---------------------------------------------------------------------------

def bcnf_violations(schema: Iterable[str], fds: Sequence[FD]) -> list[FD]:
    attrs = _check_schema(schema, fds)
    violations: list[FD] = []
    for lhs, rhs in fds:
        nontrivial = rhs - lhs
        # BCNF: 自明でないすべての X → Y について、X が超キーであること
        if nontrivial and not closure(lhs, fds) >= attrs:
            violations.append((lhs, nontrivial))
    return violations


def third_nf_violations(schema: Iterable[str], fds: Sequence[FD]) -> list[FD]:
    attrs = _check_schema(schema, fds)
    prime = frozenset().union(*candidate_keys(attrs, fds))  # いずれかの候補キーに含まれる属性
    violations: list[FD] = []
    for lhs, rhs in fds:
        if closure(lhs, fds) >= attrs:
            continue  # 左辺が超キーなら問題ない
        # 3NF: 左辺が超キーでなくても、右辺が「キー属性（prime）」なら許される。BCNF との違いはここだけ
        bad = (rhs - lhs) - prime
        if bad:
            violations.append((lhs, bad))
    return violations


# ---------------------------------------------------------------------------
# 演習3-4（発展）: BCNF 分解
# ---------------------------------------------------------------------------

def _find_violation(fragment: frozenset[str], fds: Sequence[FD]) -> tuple[frozenset[str], frozenset[str]] | None:
    """fragment 上に射影した従属性の中から BCNF 違反 X → Y を 1 つ探す（無ければ None）。

    分解後の断片では、元の FD の集合 F だけを調べるのでは足りない。F から導かれる従属性
    （F⁺）を断片に射影したものを調べる必要がある。ここでは断片の部分集合 X ごとに
    X⁺ ∩ 断片 を計算する（属性数に対して指数的だが、演習の規模なら十分速い）。
    """
    ordered = sorted(fragment)
    for size in range(1, len(ordered)):
        for combo in combinations(ordered, size):
            x = frozenset(combo)
            implied = closure(x, fds) & fragment
            if implied != x and implied != fragment:  # 自明でなく、かつ X は断片の超キーでない
                return x, implied - x
    return None


def bcnf_decompose(schema: Iterable[str], fds: Sequence[FD]) -> list[frozenset[str]]:
    attrs = _check_schema(schema, fds)
    done: set[frozenset[str]] = set()
    todo = [attrs]
    while todo:
        fragment = todo.pop()
        violation = _find_violation(fragment, fds)
        if violation is None:
            done.add(fragment)
            continue
        x, y = violation
        # X → Y で分解する: (X ∪ Y) と (R − Y)。共通部分 X は X ∪ Y のキーなので、
        # この 2 つを自然結合すると元に戻る（無損失分解）。
        todo.append(x | y)
        todo.append(fragment - y)
    # 他の断片に含まれる断片は冗長なので取り除く
    result = [f for f in done if not any(f < g for g in done)]
    return sorted(result, key=lambda f: sorted(f))
