"""4.5 仮想化とコンテナ — 演習2・3: CFS 帯域制御（CPU クォータ）のシミュレーション

Kubernetes の CPU の limits や `docker run --cpus` は、Linux の cgroup の CFS 帯域制御
（cgroup v2 の cpu.max）で実現されています。「周期（period）ごとに、グループ全体で
クォータ（quota）分の CPU 時間まで」という仕組みで、クォータを使い切ると、次の周期の
始まりまでグループ内のすべてのスレッドが止められます（スロットリング）。

この仕組みを 1 ミリ秒単位でシミュレーションし、「CPU 使用率の平均は低いのに、遅延が
急に悪化する」現象を再現します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 4.5
このディレクトリで、このファイルのテストだけを実行する:
    python3 -m unittest -v test_cfs_quota

モデル（簡略化している点）:
    - 時間は 1 ミリ秒の刻みで進む。仕事（Burst）は start の時刻から実行可能になり、
      合計 work ミリ秒の CPU 時間を受け取ると完了する。1 つの仕事は 1 刻みに最大 1 ミリ秒ぶん走る
      （1 つのスレッドは同時に 2 つの CPU を使えない）。
    - グループが使える CPU は cpus 個。クォータの補充は、時刻が period の倍数になった瞬間に行う。
    - 実際のカーネルは、クォータを CPU ごとに少しずつ配る（スライス）など、もっと複雑に動く。
"""
from __future__ import annotations

from typing import NamedTuple, Sequence


class Burst(NamedTuple):
    name: str  # 仕事の名前（一意）
    start: int  # 実行可能になる時刻（ミリ秒、0 以上）
    work: int  # 必要な CPU 時間（ミリ秒、1 以上）


class CfsResult(NamedTuple):
    finish: dict[str, int]  # 仕事の名前 -> 完了時刻（ミリ秒）
    nr_periods: int  # 実行可能な仕事がいた周期の数
    nr_throttled: int  # クォータ不足で実行できない仕事が出た周期の数
    throttled_time: int  # 実行可能な仕事がいるのに、クォータが 0 で誰も動けなかった時間（ミリ秒）


def latencies(bursts: Sequence[Burst], result: CfsResult) -> dict[str, int]:
    """各仕事の遅延（完了時刻 - 開始時刻）を返す（実装済み）。"""
    return {b.name: result.finish[b.name] - b.start for b in bursts}


# ---------------------------------------------------------------------------
# 演習2（★★★）: CFS 帯域制御のシミュレーション
# ---------------------------------------------------------------------------

def simulate(bursts: Sequence[Burst], *, quota: int | None, period: int = 100, cpus: int = 4) -> CfsResult:
    """仕事の集まりを、クォータ付きで実行したときの結果を返す。

    時刻 t = 0, 1, 2, ... について、すべての仕事が完了するまで次を繰り返す:
      1. t が period の倍数なら、新しい周期の始まり。残りのクォータを quota に戻す。
      2. 実行可能な仕事（start <= t で、まだ完了していない）を集める。
      3. 同時に走らせたい数 want = min(実行可能な数, cpus)。
         quota が None（無制限）なら want 個走らせる。そうでなければ min(want, 残りのクォータ) 個。
         走らせる数が want より少ない刻みがあった周期は「スロットリングされた周期」。
         残りのクォータが 0 で、実行可能な仕事がいる刻みは throttled_time に 1 ミリ秒加える。
      4. 走らせる仕事は、CFS のように「これまでに受け取った CPU 時間が少ない順」に選ぶ
         （同点なら start の早い順、さらに同点なら入力の順）。
      5. 選んだ各仕事の残り時間を 1 減らし、クォータを 1 ずつ消費する。残りが 0 になった仕事は
         時刻 t + 1 に完了する。

    nr_periods は「実行可能な仕事が 1 つでもいた周期」の数（誰もいない周期は数えない）。
    period < 1、cpus < 1、quota が None でも 1 以上でもない、名前の重複、start < 0、work < 1 は ValueError。

    例（テストの一部）: 50 ms ずつの仕事 4 つを t=0 に始め、quota=100・period=100（CPU 1 個分）・cpus=4
    で動かすと、4 並列で走って 25 ms でクォータを使い切り、残り 75 ms は止められる。
    次の周期でまた 25 ms 走って完了するので、全員の完了時刻は 125（制限がなければ 50）。

    >>> r = simulate([Burst(f"T{i}", 0, 50) for i in range(4)], quota=100, period=100, cpus=4)
    >>> r.finish["T0"], r.nr_periods, r.nr_throttled, r.throttled_time
    (125, 2, 1, 75)
    """
    raise NotImplementedError("演習2: simulate を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: スロットリングを起こさない最小のクォータ
# ---------------------------------------------------------------------------

def min_quota_without_throttling(bursts: Sequence[Burst], *, period: int = 100, cpus: int = 4) -> int:
    """simulate(bursts, quota=q, period=period, cpus=cpus).nr_throttled == 0 となる最小の q を返す。

    bursts が空なら ValueError。

    >>> min_quota_without_throttling([Burst(f"T{i}", 0, 50) for i in range(4)], period=100, cpus=4)
    200

    ヒント: 1 から順に試しても正しく求まるが、次の性質に気づくと 1 回のシミュレーションで求まる。
    「スロットリングが一度も起きないなら、実行の様子は quota=None のときと完全に同じになる」。
    では、quota=None で動かしたときの何を見ればよいか？（答えは README の 6 節）
    """
    raise NotImplementedError("演習3: min_quota_without_throttling を実装してください")
