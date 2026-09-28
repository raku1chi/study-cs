"""8.4 CI/CDとリリースエンジニアリング — 解答例: セマンティックバージョニング（SemVer 2.0.0）

仕様は exercises/semver.py の docstring を参照してください。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional, Union

# semver.org が示している正規表現を、\d を [0-9] に変えて使う（\d は Unicode の数字にも一致するため）
NUM = r"0|[1-9][0-9]*"
PRE_ID = r"0|[1-9][0-9]*|[0-9]*[a-zA-Z-][0-9a-zA-Z-]*"
SEMVER_RE = re.compile(
    rf"({NUM})\.({NUM})\.({NUM})"
    rf"(?:-((?:{PRE_ID})(?:\.(?:{PRE_ID}))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?"
)
COMPARATOR_RE = re.compile(r"(\^|~|>=|<=|>|<|=)?(.+)")


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple[Union[int, str], ...] = ()
    build: tuple[str, ...] = ()

    def __str__(self) -> str:
        text = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            text += "-" + ".".join(str(p) for p in self.prerelease)
        if self.build:
            text += "+" + ".".join(self.build)
        return text


def parse(text: str) -> Version:
    m = SEMVER_RE.fullmatch(text) if isinstance(text, str) else None
    if m is None:
        raise ValueError(f"SemVer 2.0.0 の形式ではありません: {text!r}")
    major, minor, patch, pre, build = m.groups()
    prerelease = tuple(int(p) if p.isdigit() else p for p in pre.split(".")) if pre else ()
    return Version(int(major), int(minor), int(patch), prerelease, tuple(build.split(".")) if build else ())


def _as_version(v: Union[str, Version]) -> Version:
    return v if isinstance(v, Version) else parse(v)


def _cmp(x, y) -> int:
    return (x > y) - (x < y)


def _compare_prerelease(a: tuple, b: tuple) -> int:
    if not a or not b:
        # プレリリースのない版の方が高い（両方ないなら等しい）
        return _cmp(not a, not b)
    for x, y in zip(a, b):
        if x == y:
            continue
        if isinstance(x, int) and isinstance(y, int):
            return _cmp(x, y)
        if isinstance(x, int):
            return -1  # 数字だけの識別子は、英字を含む識別子より低い
        if isinstance(y, int):
            return 1
        return _cmp(x, y)  # ASCII の辞書順
    return _cmp(len(a), len(b))  # すべて等しければ、識別子の多い方が高い


def compare(a: Union[str, Version], b: Union[str, Version]) -> int:
    va, vb = _as_version(a), _as_version(b)
    core = _cmp((va.major, va.minor, va.patch), (vb.major, vb.minor, vb.patch))
    return core or _compare_prerelease(va.prerelease, vb.prerelease)  # ビルドメタデータは無視


# ---------------------------------------------------------------------------
# 範囲指定
# ---------------------------------------------------------------------------

Comparator = tuple[str, Version]  # (演算子, バージョン)。演算子は ">=" "<=" ">" "<" "="


def _expand(op: str, v: Version) -> list[Comparator]:
    """^ と ~ を、>= と < の組に展開する。上限の "-0" で次の版のプレリリースを除外する。"""
    if op == "^":
        if v.major > 0:
            upper = Version(v.major + 1, 0, 0, (0,))
        elif v.minor > 0:
            upper = Version(0, v.minor + 1, 0, (0,))
        else:
            upper = Version(0, 0, v.patch + 1, (0,))
        return [(">=", v), ("<", upper)]
    if op == "~":
        return [(">=", v), ("<", Version(v.major, v.minor + 1, 0, (0,)))]
    return [(op or "=", v)]


def _parse_set(text: str) -> list[Comparator]:
    tokens = text.split()
    if tokens == ["*"]:
        return [(">=", Version(0, 0, 0))]
    if not tokens:
        raise ValueError("空の比較子の集合があります")
    comparators: list[Comparator] = []
    for token in tokens:
        m = COMPARATOR_RE.fullmatch(token)
        if m is None:
            raise ValueError(f"不正な比較子です: {token!r}")
        op, version_text = m.groups()
        comparators.extend(_expand(op or "=", parse(version_text)))
    return comparators


def parse_range(range_expr: str) -> list[list[Comparator]]:
    if not isinstance(range_expr, str) or not range_expr.strip():
        raise ValueError(f"範囲指定が空です: {range_expr!r}")
    return [_parse_set(part) for part in range_expr.split("||")]


OPS = {
    "=": lambda c: c == 0,
    ">": lambda c: c > 0,
    ">=": lambda c: c >= 0,
    "<": lambda c: c < 0,
    "<=": lambda c: c <= 0,
}


def _satisfies_set(v: Version, comparators: list[Comparator]) -> bool:
    if not all(OPS[op](compare(v, target)) for op, target in comparators):
        return False
    if not v.prerelease:
        return True
    # プレリリースの版は、同じ MAJOR.MINOR.PATCH のプレリリースを含む比較子があるときだけ許す
    core = (v.major, v.minor, v.patch)
    return any(t.prerelease and (t.major, t.minor, t.patch) == core for _, t in comparators)


def satisfies(version: Union[str, Version], range_expr: str) -> bool:
    sets = parse_range(range_expr)  # 範囲指定が不正なら、版に関係なく ValueError
    v = _as_version(version)
    return any(_satisfies_set(v, s) for s in sets)


def max_satisfying(versions: Iterable[str], range_expr: str) -> Optional[str]:
    sets = parse_range(range_expr)
    best: Optional[str] = None
    for text in versions:
        v = parse(text)
        if any(_satisfies_set(v, s) for s in sets) and (best is None or compare(v, best) > 0):
            best = text
    return best
