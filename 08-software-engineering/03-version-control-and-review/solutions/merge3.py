"""8.3 バージョン管理とコードレビュー — 解答例: 3 方向マージ（diff3）

仕様は exercises/merge3.py の docstring を参照してください。
テストのケースは、本物の git merge-file --diff3（Git 2.43）の出力と一致することを確かめてあります。
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 演習2-1: 最長共通部分列（LCS）
# ---------------------------------------------------------------------------

def lcs_pairs(a: list[str], b: list[str]) -> list[tuple[int, int]]:
    n, m = len(a), len(b)
    # L[i][j] = a[i:] と b[j:] の LCS の長さ（末尾に番兵の 0 の行・列を置く）
    L = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        row, below = L[i], L[i + 1]
        for j in range(m - 1, -1, -1):
            row[j] = below[j + 1] + 1 if a[i] == b[j] else max(below[j], row[j + 1])
    pairs = []
    i = j = 0
    while i < n and j < m:
        if a[i] == b[j]:
            pairs.append((i, j))
            i += 1
            j += 1
        elif L[i + 1][j] >= L[i][j + 1]:
            i += 1  # 同点なら a 側（削除）を先に進める
        else:
            j += 1
    return pairs


# ---------------------------------------------------------------------------
# 演習2-2: 3 方向マージ
# ---------------------------------------------------------------------------

@dataclass
class MergeResult:
    lines: list[str] = field(default_factory=list)
    conflicts: int = 0

    @property
    def clean(self) -> bool:
        return self.conflicts == 0


def merge3(
    base: list[str],
    ours: list[str],
    theirs: list[str],
    *,
    labels: tuple[str, str, str] = ("ours", "base", "theirs"),
) -> MergeResult:
    ma = dict(lcs_pairs(base, ours))
    mb = dict(lcs_pairs(base, theirs))
    result = MergeResult()
    o = a = t = 0
    while True:
        # 1. 安定したチャンク: base の行が ours・theirs の両方で「同じ並び」のまま対応している区間
        k = 0
        while o + k < len(base) and ma.get(o + k) == a + k and mb.get(o + k) == t + k:
            k += 1
        if k:
            result.lines.extend(base[o:o + k])
            o, a, t = o + k, a + k, t + k
            continue
        # 2. 不安定なチャンク: 次に 3 つすべてに残っている base の行 j までが、変更のあった区間
        j = next((j for j in range(o, len(base)) if j in ma and j in mb), None)
        if j is None:
            _resolve(result, base[o:], ours[a:], theirs[t:], labels)
            return result
        _resolve(result, base[o:j], ours[a:ma[j]], theirs[t:mb[j]], labels)
        o, a, t = j, ma[j], mb[j]


def _resolve(
    result: MergeResult, b: list[str], a: list[str], t: list[str], labels: tuple[str, str, str]
) -> None:
    if a == t:
        result.lines.extend(a)  # 変更なし、または両方が同じ変更をした
    elif a == b:
        result.lines.extend(t)  # 相手だけが変更した
    elif t == b:
        result.lines.extend(a)  # 自分だけが変更した
    else:
        ours_label, base_label, theirs_label = labels
        result.lines.append(f"<<<<<<< {ours_label}")
        result.lines.extend(a)
        result.lines.append(f"||||||| {base_label}")
        result.lines.extend(b)
        result.lines.append("=======")
        result.lines.extend(t)
        result.lines.append(f">>>>>>> {theirs_label}")
        result.conflicts += 1
