"""13.6 チームと組織の設計 — 解答例: 変更の結合からチームの境界を提案する

演習の仕様は exercises/team_clustering.py の docstring を参照してください。
"""
from __future__ import annotations

from itertools import combinations

Pair = tuple[str, str]


# ---------------------------------------------------------------------------
# 演習2: 変更の結合と、チーム間の依存度
# ---------------------------------------------------------------------------

def change_coupling(commits: list[list[str]], components: list[str]) -> dict[Pair, int]:
    known = set(components)
    if len(known) != len(components):
        raise ValueError("components に重複があります")
    counts: dict[Pair, int] = {}
    for i, commit in enumerate(commits):
        touched = set(commit)
        unknown = touched - known
        if unknown:
            raise ValueError(f"コミット {i} に未知のコンポーネントがあります: {sorted(unknown)}")
        # 同じコミットで一緒に変更されたコンポーネントの組を 1 回ずつ数える
        for a, b in combinations(sorted(touched), 2):
            counts[(a, b)] = counts.get((a, b), 0) + 1
    return dict(sorted(counts.items()))


def _weight(coupling: dict[Pair, float], a: str, b: str) -> float:
    return coupling.get((a, b) if a < b else (b, a), 0.0)


def _team_of(teams: list[list[str]]) -> dict[str, int]:
    owner: dict[str, int] = {}
    for t, members in enumerate(teams):
        for c in members:
            if c in owner:
                raise ValueError(f"{c} が複数のチームに含まれています")
            owner[c] = t
    return owner


def dependency_score(teams: list[list[str]], coupling: dict[Pair, float]) -> float:
    owner = _team_of(teams)
    total = cross = 0.0
    for (a, b), w in coupling.items():
        if a not in owner or b not in owner:
            raise ValueError(f"どのチームにも属さないコンポーネントがあります: {a}, {b}")
        total += w
        if owner[a] != owner[b]:
            cross += w
    return cross / total if total > 0 else 0.0


# ---------------------------------------------------------------------------
# 演習3: 貪欲な凝集型クラスタリング
# ---------------------------------------------------------------------------

def _between(x: list[str], y: list[str], coupling: dict[Pair, float]) -> float:
    return sum(_weight(coupling, a, b) for a in x for b in y)


def _load(members: list[str], load: dict[str, float]) -> float:
    return sum(load[c] for c in members)


def _sorted_teams(clusters: list[list[str]]) -> list[list[str]]:
    return sorted((sorted(c) for c in clusters), key=lambda c: c[0])


def greedy_teams(
    components: list[str],
    coupling: dict[Pair, float],
    load: dict[str, float],
    max_load: float,
    target_teams: int | None = None,
) -> list[list[str]]:
    if not components or len(set(components)) != len(components):
        raise ValueError("components は空でない、重複のないリストにしてください")
    for c in components:
        if c not in load:
            raise ValueError(f"{c} の負荷が指定されていません")
        if load[c] > max_load:
            raise ValueError(f"{c} の負荷 {load[c]} が 1 チームの上限 {max_load} を超えています")
    if target_teams is not None and target_teams < 1:
        raise ValueError("target_teams は 1 以上にしてください")

    clusters = [[c] for c in sorted(components)]

    def done() -> bool:
        return target_teams is not None and len(clusters) <= target_teams

    def best_pair(score) -> tuple[int, int] | None:
        """容量の制約を満たす組のうち、score が最大の組を返す（score が None の組は候補にしない）。

        同点なら、2 つのクラスタの先頭の名前の組が辞書順で先の組を選ぶ（結果を決定的にするため）。
        """
        best = None  # (score, 名前の組, i, j)
        for i, j in combinations(range(len(clusters)), 2):
            if _load(clusters[i], load) + _load(clusters[j], load) > max_load:
                continue
            s = score(clusters[i], clusters[j])
            if s is None:
                continue
            names = (clusters[i][0], clusters[j][0])
            if best is None or s > best[0] or (s == best[0] and names < best[1]):
                best = (s, names, i, j)
        return None if best is None else (best[2], best[3])

    def merge(i: int, j: int) -> None:
        clusters[i] = sorted(clusters[i] + clusters[j])
        del clusters[j]
        clusters.sort(key=lambda c: c[0])

    def coupling_score(x: list[str], y: list[str]) -> float | None:
        w = _between(x, y, coupling)
        return w if w > 0 else None  # 結合のない組は第 1 段階では併合しない

    def small_load_score(x: list[str], y: list[str]) -> float:
        return -(_load(x, load) + _load(y, load))  # 負荷の合計が小さいほど高いスコア

    # 第 1 段階: 結合の強い組から順に併合する（チーム間の依存を最も大きく減らす併合を選ぶ）
    while not done():
        pair = best_pair(coupling_score)
        if pair is None:
            break
        merge(*pair)

    # 第 2 段階: target_teams に届かなければ、結合のないクラスタを、負荷の合計が小さい組から詰める
    while target_teams is not None and not done():
        pair = best_pair(small_load_score)
        if pair is None:
            break
        merge(*pair)

    return _sorted_teams(clusters)


# ---------------------------------------------------------------------------
# 演習4: 1 つずつ動かす局所探索による改善
# ---------------------------------------------------------------------------

def refine_teams(
    teams: list[list[str]],
    coupling: dict[Pair, float],
    load: dict[str, float],
    max_load: float,
) -> list[list[str]]:
    work = _sorted_teams([t for t in teams if t])
    _team_of(work)  # 重複の検査
    for t in work:
        if _load(t, load) > max_load:
            raise ValueError("負荷の上限を超えるチームがあります")

    while True:
        best = None  # (-利得, コンポーネント名, 移動先のチームの先頭の名前, 移動元の添字, 移動先の添字)
        for src, members in enumerate(work):
            for c in members:
                inside = sum(_weight(coupling, c, o) for o in members if o != c)
                for dst, other in enumerate(work):
                    if dst == src or _load(other, load) + load[c] > max_load:
                        continue
                    # c を動かすと、c と移動先の結合はチーム内に、c と移動元の結合はチーム間になる
                    gain = sum(_weight(coupling, c, o) for o in other) - inside
                    if gain <= 0:
                        continue
                    cand = (-gain, c, other[0], src, dst)
                    if best is None or cand[:3] < best[:3]:
                        best = cand
        if best is None:
            return work
        _, c, _, src, dst = best
        work[src] = [x for x in work[src] if x != c]
        work[dst] = work[dst] + [c]
        # 空になったチームは消し、並べ直して次の反復の同点の判定を決定的にする
        work = _sorted_teams([t for t in work if t])
