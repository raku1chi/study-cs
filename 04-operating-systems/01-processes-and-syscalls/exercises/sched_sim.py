"""4.1 プロセス・スレッド・システムコール — 演習: CPU スケジューリングシミュレータ

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 4.1          # 合格数を表示
    python3 tools/check.py -v 4.1       # 各テストの結果を詳しく表示

このディレクトリで、このファイルのテストだけを実行することもできます:
    python3 -m unittest -v test_sched_sim

モデル（簡略化している点）:
    - 時刻・到着時刻・CPU 時間はすべて整数（単位は問わない。ミリ秒と思えばよい）。
    - CPU は 1 個。プロセスは I/O をせず、到着したら完了まで CPU だけを使う。
    - スケジュールは「区間（Slice）」のリスト（タイムライン、ガントチャート）で表す。
      タイムラインは時刻 0 から隙間なく並び、CPU が空いている区間は name=IDLE(None)、
      コンテキストスイッチの区間は name=SWITCH で表す。
    - 隣り合う同じ名前の区間は 1 つに結合する（add_slice() を使えば自動で結合される）。

同点の扱い（テストはこの規約で答え合わせをします）:
    - 同じ時刻に到着したプロセスは、入力リストでの順番が先のものを先に扱う。

補助関数 validate_processes()・add_slice()・format_gantt() は実装済みです。自由に使ってください。
"""
from __future__ import annotations

import heapq  # noqa: F401  SJF・SRTF で使えます
from collections import deque  # noqa: F401  ラウンドロビン・MLFQ で使えます
from typing import NamedTuple, Sequence

IDLE = None  # CPU が空いている区間の名前
SWITCH = "<cs>"  # コンテキストスイッチに使われた区間の名前


class Process(NamedTuple):
    name: str
    arrival: int  # 到着時刻（実行可能になった時刻）
    burst: int  # 必要な CPU 時間


class Slice(NamedTuple):
    start: int
    end: int
    name: str | None  # プロセス名、SWITCH、または IDLE(None)


class Metrics(NamedTuple):
    completion: int  # 完了時刻
    turnaround: int  # ターンアラウンド時間 = 完了時刻 - 到着時刻
    waiting: int  # 待ち時間 = ターンアラウンド時間 - burst
    response: int  # 応答時間 = 初めて実行された時刻 - 到着時刻


class Averages(NamedTuple):
    turnaround: float
    waiting: float
    response: float


# ---------------------------------------------------------------------------
# 補助関数（実装済み）
# ---------------------------------------------------------------------------

def validate_processes(procs: Sequence[Process]) -> None:
    """プロセスの一覧を検査し、不正なら ValueError を送出する。

    - 名前は空でない文字列で、重複せず、SWITCH と同じでないこと
    - arrival は 0 以上の整数、burst は 1 以上の整数であること
    """
    names = set()
    for p in procs:
        if not isinstance(p.name, str) or not p.name or p.name == SWITCH:
            raise ValueError(f"プロセス名が不正です: {p.name!r}")
        if p.name in names:
            raise ValueError(f"プロセス名が重複しています: {p.name!r}")
        names.add(p.name)
        if not isinstance(p.arrival, int) or p.arrival < 0:
            raise ValueError(f"{p.name}: arrival は 0 以上の整数: {p.arrival!r}")
        if not isinstance(p.burst, int) or p.burst < 1:
            raise ValueError(f"{p.name}: burst は 1 以上の整数: {p.burst!r}")


def add_slice(timeline: list[Slice], start: int, end: int, name: str | None) -> None:
    """タイムラインの末尾に区間 [start, end) を追加する。

    長さ 0 の区間は無視し、直前の区間と同じ名前で連続していれば結合する。

    >>> tl = []
    >>> add_slice(tl, 0, 2, "A"); add_slice(tl, 2, 3, "A"); add_slice(tl, 3, 4, "B")
    >>> tl
    [Slice(start=0, end=3, name='A'), Slice(start=3, end=4, name='B')]
    """
    if end <= start:
        return
    if timeline and timeline[-1].name == name and timeline[-1].end == start:
        timeline[-1] = Slice(timeline[-1].start, end, name)
    else:
        timeline.append(Slice(start, end, name))


def format_gantt(timeline: Sequence[Slice]) -> str:
    """タイムラインを、プロセスごとの行を持つ文字のガントチャートにする（デバッグ用）。

    >>> print(format_gantt([Slice(0, 2, "A"), Slice(2, 3, "B"), Slice(3, 4, "A")]))
    A |██·█|
    B |··█·|
       0〜4（1 文字 = 1 単位時間）
    """
    if not timeline:
        return "(空)"
    total = timeline[-1].end
    rows: dict[str, list[str]] = {}
    for s in timeline:
        label = "idle" if s.name is IDLE else ("cs" if s.name == SWITCH else s.name)
        rows.setdefault(label, ["·"] * total)
        for t in range(s.start, s.end):
            rows[label][t] = "█"
    width = max(len(label) for label in rows)
    lines = [f"{label:<{width}} |{''.join(cells)}|" for label, cells in rows.items()]
    lines.append(f"{'':<{width}}  0〜{total}（1 文字 = 1 単位時間）")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 演習1a（★☆☆）: 評価指標の計算
# ---------------------------------------------------------------------------

def compute_metrics(procs: Sequence[Process], timeline: Sequence[Slice]) -> dict[str, Metrics]:
    """タイムラインから、プロセスごとの評価指標を計算する。

    戻り値は {プロセス名: Metrics} の辞書。各指標の定義は Metrics のコメントを参照。
    IDLE と SWITCH の区間は、どのプロセスの実行時間にも数えない。

    次のいずれかに当てはまるタイムラインは不正なので ValueError を送出する:
    - 長さが 0 以下の区間がある / 区間が時刻順に並んでいない・重なっている
    - procs にないプロセス名がある / プロセスが到着時刻より前に実行されている
    - あるプロセスの実行時間の合計が burst と一致しない（一度も実行されない場合を含む）
    procs 自体が不正な場合も ValueError（validate_processes を使うとよい）。

    例（テキスト『Operating System Concepts』の SRTF の例）:
    >>> procs = [Process("P1", 0, 8), Process("P2", 1, 4)]
    >>> tl = [Slice(0, 1, "P1"), Slice(1, 5, "P2"), Slice(5, 12, "P1")]
    >>> compute_metrics(procs, tl)["P1"]
    Metrics(completion=12, turnaround=12, waiting=4, response=0)
    """
    raise NotImplementedError("演習1a: compute_metrics を実装してください")


def average(metrics: dict[str, Metrics]) -> Averages:
    """全プロセスのターンアラウンド時間・待ち時間・応答時間の平均を返す。

    metrics が空なら ValueError。
    """
    raise NotImplementedError("演習1a: average を実装してください")


# ---------------------------------------------------------------------------
# 演習1b（★★☆）: FIFO・SJF・SRTF
# ---------------------------------------------------------------------------

def fifo(procs: Sequence[Process]) -> list[Slice]:
    """FIFO（先着順、FCFS）: 到着順に、各プロセスを完了まで走らせる。

    - 到着順が同じなら入力の順。
    - 実行可能なプロセスがいなければ、次の到着まで IDLE の区間を入れる。
    - procs が空なら [] を返す。不正な procs は ValueError。

    >>> fifo([Process("A", 0, 3), Process("B", 1, 2)])
    [Slice(start=0, end=3, name='A'), Slice(start=3, end=5, name='B')]
    """
    raise NotImplementedError("演習1b: fifo を実装してください")


def sjf(procs: Sequence[Process]) -> list[Slice]:
    """SJF（最短ジョブ優先、非プリエンプティブ）。

    CPU が空いた時点で到着済みのプロセスのうち burst が最小のものを選び、完了まで走らせる
    （途中で短いプロセスが到着しても横取りしない）。
    同点は (burst, arrival, 入力の順) の小さい方を優先する。

    ヒント: heapq に (burst, arrival, index) を入れると、同点の規則まで自然に表せる。
    """
    raise NotImplementedError("演習1b: sjf を実装してください")


def srtf(procs: Sequence[Process]) -> list[Slice]:
    """SRTF（残り時間最短優先、プリエンプティブ版 SJF。STCF とも呼ぶ）。

    常に「残り CPU 時間」が最小のプロセスを走らせる。新しいプロセスが到着して、
    その burst が実行中のプロセスの残り時間より **真に小さい** ときだけ横取りする。
    同点は (残り時間, arrival, 入力の順) の小さい方を優先する（同点では横取りしない）。

    ヒント: 判断をやり直す必要があるのは「プロセスの到着」と「プロセスの完了」の時刻だけ。
    1 単位時間ずつ進めても正しく実装できるが、イベントの時刻だけを追うと効率がよい。
    """
    raise NotImplementedError("演習1b: srtf を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: ラウンドロビン（コンテキストスイッチのコスト付き）
# ---------------------------------------------------------------------------

def round_robin(procs: Sequence[Process], quantum: int, switch_cost: int = 0) -> list[Slice]:
    """ラウンドロビン: 実行可能キュー（FIFO）の先頭を最大 quantum だけ走らせ、終わらなければ末尾へ戻す。

    規約（テストはこの規約で答え合わせをします）:
    - プロセスは到着した時刻にキューの末尾へ入る（同時到着は入力の順）。
    - 時刻 t にタイムスライスを使い切ったプロセスは、**時刻 t までに到着したプロセスを
      キューに入れた後で** 末尾に戻す（新しく来た方が先に並ぶ）。
    - switch_cost > 0 のとき、あるプロセスの実行の直後に **別の** プロセスを走らせる場合、
      その間に長さ switch_cost の SWITCH 区間を入れる。次のときは入れない:
        * 同じプロセスが続けて走る（キューにほかに誰もいない）とき
        * CPU がアイドルだった後にプロセスを走らせるとき
      SWITCH 区間の間に到着したプロセスも、到着時刻にキューの末尾へ入る。
    - quantum < 1、switch_cost < 0 は ValueError。

    >>> round_robin([Process("A", 0, 4), Process("B", 2, 2)], 2)
    [Slice(start=0, end=2, name='A'), Slice(start=2, end=4, name='B'), Slice(start=4, end=6, name='A')]
    """
    raise NotImplementedError("演習2: round_robin を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★★）: 多段フィードバックキュー（MLFQ）
# ---------------------------------------------------------------------------

def mlfq(
    procs: Sequence[Process],
    quanta: Sequence[int] = (2, 4, 8),
    boost_interval: int | None = None,
) -> list[Slice]:
    """簡略化した MLFQ（Multi-Level Feedback Queue）。

    優先度レベルは 0〜len(quanta)-1 で、0 が最高。各レベルに FIFO のキューがある。
    quanta[i] は、レベル i にいる間に使える CPU 時間の合計（割り当て、allotment）。

    時間は 1 単位ずつ進め、各時刻 t で次の (1)〜(6) をこの順に行う:
      (1) 時刻 t に到着したプロセスを、レベル 0 のキューの末尾に入れる（同時到着は入力の順）。
      (2) 実行中のプロセスが現在のレベルの割り当てを使い切っていたら、1 つ下のレベルへ
          下げて（最下段ならそのまま）使用量を 0 に戻し、そのレベルのキューの末尾に入れる。
      (3) boost_interval が指定され、t > 0 かつ t が boost_interval の倍数なら「優先度ブースト」:
          キューにいる全プロセスを、レベル 0 のキューへ「レベル 0 の順 → レベル 1 の順 → …」
          の順で移し、使用量を 0 に戻す。実行中のプロセスがいれば、それもレベル 0・使用量 0 にする
          （実行は続ける）。
      (4) 実行中のプロセスより高いレベル（番号が小さい）のキューが空でなければ横取りする:
          実行中のプロセスは、使用量を保ったまま自分のレベルのキューの末尾に入る。
      (5) 実行中のプロセスがいなければ、最も高いレベルの空でないキューの先頭を選ぶ。
          誰もいなければ、次の到着まで IDLE の区間を入れて時刻を進める。
      (6) 選んだプロセスを 1 単位時間実行する（残り時間 -1、使用量 +1）。残り時間が 0 なら完了。

    quanta が空、1 未満の値を含む、boost_interval が 1 未満のときは ValueError。

    確認用の性質: quanta が 1 段だけ（例: (q,)）なら、round_robin(procs, q) と同じ結果になる。

    >>> mlfq([Process("A", 0, 6), Process("B", 1, 1)], quanta=(1, 2, 4))
    [Slice(start=0, end=1, name='A'), Slice(start=1, end=2, name='B'), Slice(start=2, end=7, name='A')]
    """
    raise NotImplementedError("演習3: mlfq を実装してください")
