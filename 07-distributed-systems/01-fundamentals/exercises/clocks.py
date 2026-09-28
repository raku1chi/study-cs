"""7.1 分散システムの本質 — 演習: 論理時計（Lamport 時計・ベクトル時計）

分散システムには「全員が共有する正確な時計」がありません。そこで、物理的な時刻の代わりに
「どのイベントがどのイベントの原因になりえたか（happened-before 関係）」で順序を扱います。
この演習では、その道具である Lamport 時計とベクトル時計を実装し、実行トレースから
イベントの因果関係と「並行な書き込み」を見つけます。

各クラス・関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 7.1          # 7.1 章の全演習
    python3 tools/check.py -v 7.1       # 詳しい出力

このディレクトリで、この演習だけを実行することもできます:
    python3 -m unittest -v test_clocks

用語:
    - イベント: ノード上で起きる出来事。ローカル処理（local）、メッセージ送信（send）、受信（recv）の 3 種類。
    - a → b（a happened-before b）: 次のいずれかで定まる関係の推移閉包。
        1. a と b が同じノードのイベントで、a が先に起きた
        2. a がメッセージの送信で、b がそのメッセージの受信
    - a ∥ b（並行, concurrent）: a → b でも b → a でもない。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# 演習1（★☆☆）: Lamport 時計
# ---------------------------------------------------------------------------


class LamportClock:
    """1 つのノードが持つ Lamport 時計（整数のカウンタ）。

    規則（Lamport, 1978）:
        1. ローカルイベントや送信の前に、カウンタを 1 進める。
        2. 送信するメッセージには、進めた後のカウンタの値を添える。
        3. 受信したら、カウンタを max(自分の値, メッセージの値) + 1 にする。

    こうすると「a → b ならば L(a) < L(b)」（時計条件）が必ず成り立つ。
    ただし逆（L(a) < L(b) ならば a → b）は成り立たない。

    >>> c = LamportClock()
    >>> c.tick(), c.send(), c.receive(10), c.time
    (1, 2, 11, 11)
    """

    def __init__(self) -> None:
        raise NotImplementedError("演習1: LamportClock.__init__ を実装してください（初期値は 0）")

    @property
    def time(self) -> int:
        """現在のカウンタの値（読むだけで、進めない）。"""
        raise NotImplementedError("演習1: LamportClock.time を実装してください")

    def tick(self) -> int:
        """ローカルイベント: カウンタを 1 進め、進めた後の値を返す。"""
        raise NotImplementedError("演習1: LamportClock.tick を実装してください")

    def send(self) -> int:
        """送信イベント: カウンタを 1 進め、メッセージに添える値（進めた後の値）を返す。"""
        raise NotImplementedError("演習1: LamportClock.send を実装してください")

    def receive(self, remote_time: int) -> int:
        """受信イベント: カウンタを max(自分, remote_time) + 1 にして、その値を返す。

        remote_time が負なら ValueError。
        """
        raise NotImplementedError("演習1: LamportClock.receive を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: ベクトル時計
# ---------------------------------------------------------------------------


class Ordering(Enum):
    """2 つのベクトル時計の比較結果。"""

    BEFORE = "before"  # self → other（self が因果的に先）
    AFTER = "after"  # other → self
    CONCURRENT = "concurrent"  # どちらも相手を知らない（並行）
    EQUAL = "equal"  # 同じ


class VectorClock:
    """不変（immutable）なベクトル時計。

    「ノード名 → そのノードで起きたイベントのうち、知っている数」の対応表。
    表にないノードは 0 とみなす。0 の要素は持たない形に正規化すること
    （VectorClock({"A": 0, "B": 2}) と VectorClock({"B": 2}) は等しく、ハッシュ値も等しい）。

    increment と merge は **新しい VectorClock を返し、自分自身は変更しない**。
    不変にしておくと、イベントごとの時計をそのまま保存・比較できる。

    >>> a = VectorClock().increment("A")          # {A:1}
    >>> b = a.increment("B")                        # {A:1, B:1}
    >>> a.compare(b)
    <Ordering.BEFORE: 'before'>
    >>> VectorClock({"A": 1}).compare(VectorClock({"B": 1}))
    <Ordering.CONCURRENT: 'concurrent'>

    ヒント: 比較は「すべての要素で <=」「すべての要素で >=」の 2 つを調べれば 4 通りに分類できる。
    """

    def __init__(self, entries: Mapping[str, int] | None = None) -> None:
        """entries をコピーして保持する。負の値や整数でない値は ValueError。"""
        raise NotImplementedError("演習2: VectorClock.__init__ を実装してください")

    def get(self, node: str) -> int:
        """node の要素の値（表になければ 0）。"""
        raise NotImplementedError("演習2: VectorClock.get を実装してください")

    def increment(self, node: str) -> VectorClock:
        """node の要素を 1 増やした新しい時計を返す。"""
        raise NotImplementedError("演習2: VectorClock.increment を実装してください")

    def merge(self, other: VectorClock) -> VectorClock:
        """要素ごとの最大値をとった新しい時計を返す。"""
        raise NotImplementedError("演習2: VectorClock.merge を実装してください")

    def compare(self, other: VectorClock) -> Ordering:
        """self と other の因果関係を返す（EQUAL / BEFORE / AFTER / CONCURRENT）。"""
        raise NotImplementedError("演習2: VectorClock.compare を実装してください")

    def to_dict(self) -> dict[str, int]:
        """0 でない要素だけを、ノード名の昇順に並べた dict で返す（コピー）。"""
        raise NotImplementedError("演習2: VectorClock.to_dict を実装してください")

    def __eq__(self, other: object) -> bool:
        raise NotImplementedError("演習2: VectorClock.__eq__ を実装してください")

    def __hash__(self) -> int:
        raise NotImplementedError("演習2: VectorClock.__hash__ を実装してください")

    def __repr__(self) -> str:
        return "VectorClock(...)"  # 実装したら f"VectorClock({self.to_dict()})" などにするとデバッグしやすい


# ---------------------------------------------------------------------------
# 演習3（★★☆）: トレースの解析 — 因果順序と並行な書き込みの検出
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Event:
    """トレース（実行記録）の 1 イベント。

    - name: イベント名（トレース内で一意）
    - node: イベントが起きたノード
    - kind: "local" / "send" / "recv"
    - msg: send と recv のときのメッセージ ID（local では None）

    トレースは「実際に起きた順」に並んだ Event のリストとして与えられる。
    """

    name: str
    node: str
    kind: str = "local"
    msg: str | None = None


def lamport_timestamps(trace: Sequence[Event]) -> dict[str, int]:
    """トレースの各イベントに Lamport 時刻を割り当て、{イベント名: 時刻} を返す。

    ノードごとに LamportClock を 1 つ持ち、local と send では tick()、
    recv では送信時の時刻を使って receive() する。

    次のようなトレースは不正として ValueError を送出する:
        - イベント名の重複、kind が 3 種類以外
        - send / recv に msg がない、local に msg がある
        - 同じメッセージ ID の 2 回目の送信、同じメッセージの 2 回目の受信
        - まだ送信されていないメッセージの受信

    >>> t = [Event("a1", "A", "send", "m"), Event("b1", "B"), Event("b2", "B", "recv", "m")]
    >>> lamport_timestamps(t)
    {'a1': 1, 'b1': 1, 'b2': 2}
    """
    raise NotImplementedError("演習3: lamport_timestamps を実装してください")


def vector_timestamps(trace: Sequence[Event]) -> dict[str, VectorClock]:
    """トレースの各イベントにベクトル時計を割り当て、{イベント名: VectorClock} を返す。

    - local / send: そのノードの時計の自分の要素を 1 増やす
    - recv: 送信時の時計と merge してから、自分の要素を 1 増やす
    - 不正なトレースは lamport_timestamps と同じ条件で ValueError

    >>> t = [Event("a1", "A", "send", "m"), Event("b1", "B"), Event("b2", "B", "recv", "m")]
    >>> {k: v.to_dict() for k, v in vector_timestamps(t).items()}
    {'a1': {'A': 1}, 'b1': {'B': 1}, 'b2': {'A': 1, 'B': 2}}
    """
    raise NotImplementedError("演習3: vector_timestamps を実装してください")


def lamport_total_order(trace: Sequence[Event]) -> list[str]:
    """Lamport 時刻による全順序でイベント名を並べる。

    (Lamport 時刻, ノード名) の昇順。同じノードのイベントが同じ Lamport 時刻を持つことはないので、
    この組で全てのイベントの順序が一意に決まる。この全順序は因果関係と矛盾しない
    （a → b なら a が先に来る）が、並行なイベントの順序は「任意に決めたもの」にすぎない。
    """
    raise NotImplementedError("演習3: lamport_total_order を実装してください")


def concurrent_pairs(
    trace: Sequence[Event], names: Iterable[str] | None = None
) -> list[tuple[str, str]]:
    """names のイベントのうち、互いに並行なペアをすべて返す。

    - names が None ならトレースの全イベントが対象。
    - 各ペア (a, b) は、トレース上で a が b より前に現れる順で並べる。
      リスト全体も、a のトレース上の位置 → b の位置の順に並べる。
    - names にトレースにない名前があれば KeyError。

    用途: 同じキーへの書き込みイベントを names に渡すと「どれが並行な書き込み（競合）か」が分かる。
    並行な書き込みは、どちらが「後」とも言えないため、上書きで片方を捨てるとデータが失われる（7.2 参照）。

    ヒント: vector_timestamps で時計を求め、compare が CONCURRENT のペアを集める。
    """
    raise NotImplementedError("演習3: concurrent_pairs を実装してください")
