"""5.4 Webの仕組みとネットワーク構成 — 演習（lb）: ロードバランサの振り分けアルゴリズム

ロードバランサの中心は「次のリクエスト（接続）をどのバックエンドに送るか」を決める部分です。
この演習では、代表的な 4 つのアルゴリズムと、ヘルスチェック・コネクションドレインを実装します。
ネットワークの通信はせず、振り分けの判断だけを扱います。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 5.4
    python3 tools/check.py -v 5.4

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_lb

構成:
    - Backend: バックエンド 1 台の状態（実装済み）
    - 振り分けの戦略（RoundRobin など）: choose(candidates) で候補の中から 1 つを選ぶ
    - LoadBalancer: 候補（正常かつドレイン中でないもの）を絞り込み、戦略に選ばせ、接続数を数える
    - HealthChecker: ヘルスチェックの結果から、バックエンドの正常・異常を切り替える

戦略は「候補のリスト」だけを受け取り、LoadBalancer が acquire() のたびに、設定された順序のまま
正常な候補を渡します。候補のリストは空でないことが保証されます。
"""
from __future__ import annotations

import random  # noqa: F401
from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass
class Backend:
    """バックエンド 1 台（実装済み）。"""

    name: str
    weight: int = 1  # 重み（重み付きの戦略で使う。1 以上）
    healthy: bool = True  # ヘルスチェックで正常か
    draining: bool = False  # ドレイン中（新しい接続を送らない）か
    active_connections: int = 0  # 処理中の接続（リクエスト）の数


class NoAvailableBackend(RuntimeError):
    """振り分け先の候補が 1 つもない（実装済み）。"""


class Strategy(Protocol):
    """振り分けの戦略のインタフェース（実装済み）。"""

    def choose(self, candidates: Sequence[Backend]) -> Backend: ...


# ---------------------------------------------------------------------------
# 演習1（★★☆）: 振り分けのアルゴリズム
# ---------------------------------------------------------------------------

class RoundRobin:
    """順番に選ぶ。

    呼ばれた回数を数えるカウンタ c を持ち、candidates[c % len(candidates)] を選んでから c を 1 増やす。
    （候補が a, b, c なら a, b, c, a, b, …。b が異常になって候補が a, c になれば、そのまま a, c, a, c, … と続く）
    """

    def __init__(self) -> None:
        raise NotImplementedError("演習1: RoundRobin.__init__ を実装してください")

    def choose(self, candidates: Sequence[Backend]) -> Backend:
        raise NotImplementedError("演習1: RoundRobin.choose を実装してください")


class SmoothWeightedRoundRobin:
    """重みに比例して選ぶ、nginx の「なめらかな」重み付きラウンドロビン。

    各バックエンドに「現在の重み」（最初は 0。バックエンドの名前をキーにした辞書で持つ）を持たせ、
    choose のたびに次を行う:
        1. すべての候補について、現在の重み += 設定された重み（weight）。
           その合計（候補の weight の合計）を total とする。
        2. 現在の重みが最大の候補を選ぶ（同じなら候補のリストで先に現れたもの）。
        3. 選んだ候補の現在の重みから total を引く。

    重み {a: 5, b: 1, c: 1} なら a a b a c a a を繰り返す。単純に a を 5 回続けてから b, c とする
    方式と比べて、重いサーバーに負荷が連続して集中しない。

    >>> lb = LoadBalancer([Backend("a", 5), Backend("b", 1), Backend("c", 1)], SmoothWeightedRoundRobin())
    >>> names = []
    >>> for _ in range(7):
    ...     b = lb.acquire(); names.append(b.name); lb.release(b)
    >>> "".join(names)
    'aabacaa'
    """

    def __init__(self) -> None:
        raise NotImplementedError("演習1: SmoothWeightedRoundRobin.__init__ を実装してください")

    def choose(self, candidates: Sequence[Backend]) -> Backend:
        raise NotImplementedError("演習1: SmoothWeightedRoundRobin.choose を実装してください")


class LeastConnections:
    """処理中の接続が最も少ない候補を選ぶ（同数なら候補のリストで先に現れたもの）。

    処理時間がばらつくとき（長いリクエストと短いリクエストが混ざるとき）に、ラウンドロビンより偏りにくい。
    """

    def choose(self, candidates: Sequence[Backend]) -> Backend:
        raise NotImplementedError("演習1: LeastConnections.choose を実装してください")


class PowerOfTwoChoices:
    """ランダムに 2 つ選び、処理中の接続が少ない方を選ぶ（Power of Two Choices）。

    - 候補が 1 つならそれを返す。
    - そうでなければ、**self.rng.sample(list(candidates), 2) を 1 回だけ呼んで** 2 つ（x, y の順）を選び、
      y の接続数が x より少なければ y、そうでなければ x を返す。
      （テストは同じシードの乱数で同じ手順を再現して、選ばれるものを比べます）

    全体を調べる最小接続数と違い、2 つを比べるだけなので、多数のロードバランサが古い情報を見ながら
    並行して振り分けても、全員が同じ 1 台に殺到しにくい。それでいて、完全なランダムより偏りを
    大幅に小さくできることが知られている。
    """

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def choose(self, candidates: Sequence[Backend]) -> Backend:
        raise NotImplementedError("演習1: PowerOfTwoChoices.choose を実装してください")


# ---------------------------------------------------------------------------
# 演習1（★★☆）: ロードバランサ本体（ヘルスチェックとコネクションドレイン）
# ---------------------------------------------------------------------------

class LoadBalancer:
    """バックエンドの一覧と戦略を持ち、接続の割り当てと解放を管理する。

    - __init__: backends が空、名前が重複、weight < 1 のものがあれば ValueError。
    - backend(name): 名前で Backend を返す。なければ KeyError。
    - eligible(): 新しい接続を受けてよい候補（healthy かつ draining でないもの）を、設定の順に返す。
    - acquire(): 候補がなければ NoAvailableBackend。あれば strategy.choose(候補) で選び、
      その active_connections を 1 増やして返す。
    - release(backend): Backend または名前を受け取り、active_connections を 1 減らす。
      0 のものを解放しようとしたら ValueError、知らない名前なら KeyError。
    - set_health(name, healthy): 正常・異常を切り替える。
    - drain(name) / undrain(name): ドレインを開始・解除する。ドレイン中は新しい接続を送らないが、
      処理中の接続はそのまま終わるのを待つ（デプロイやスケールインで安全に取り外すため）。
    - is_drained(name): ドレイン中で、処理中の接続が 0 なら True（取り外してよい）。
    """

    def __init__(self, backends: Sequence[Backend], strategy: Strategy) -> None:
        raise NotImplementedError("演習1: LoadBalancer.__init__ を実装してください")

    def backend(self, name: str) -> Backend:
        raise NotImplementedError("演習1: LoadBalancer.backend を実装してください")

    def eligible(self) -> list[Backend]:
        raise NotImplementedError("演習1: LoadBalancer.eligible を実装してください")

    def acquire(self) -> Backend:
        raise NotImplementedError("演習1: LoadBalancer.acquire を実装してください")

    def release(self, backend: Backend | str) -> None:
        raise NotImplementedError("演習1: LoadBalancer.release を実装してください")

    def set_health(self, name: str, healthy: bool) -> None:
        raise NotImplementedError("演習1: LoadBalancer.set_health を実装してください")

    def drain(self, name: str) -> None:
        raise NotImplementedError("演習1: LoadBalancer.drain を実装してください")

    def undrain(self, name: str) -> None:
        raise NotImplementedError("演習1: LoadBalancer.undrain を実装してください")

    def is_drained(self, name: str) -> bool:
        raise NotImplementedError("演習1: LoadBalancer.is_drained を実装してください")


class HealthChecker:
    """ヘルスチェックの結果（成功・失敗）を記録し、連続した回数で状態を切り替える。

    - 正常なバックエンドは、fall 回 **連続して** 失敗したら異常（healthy=False）にする。
    - 異常なバックエンドは、rise 回 **連続して** 成功したら正常に戻す。
    - 成功すれば失敗の連続回数は 0 に、失敗すれば成功の連続回数は 0 に戻る。
    - rise や fall が 1 未満なら ValueError。

    1 回の失敗ですぐに外し、1 回の成功ですぐに戻すと、一時的な揺らぎで振り分けが暴れる
    （フラッピング）ので、このような「ヒステリシス」を持たせるのが定石です（HAProxy の rise / fall）。
    """

    def __init__(self, lb: LoadBalancer, *, rise: int = 2, fall: int = 3) -> None:
        raise NotImplementedError("演習1: HealthChecker.__init__ を実装してください")

    def record(self, name: str, ok: bool) -> None:
        raise NotImplementedError("演習1: HealthChecker.record を実装してください")
