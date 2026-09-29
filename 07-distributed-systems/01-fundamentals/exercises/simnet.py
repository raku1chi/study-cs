"""7.1 分散システムの本質 — 演習: 決定的ネットワークシミュレータと「実質1回」の処理

分散システムのバグは「メッセージが遅れた」「消えた」「2 回届いた」「追い越した」といった、
めったに起きない組み合わせで表面化します。本物のネットワークでは再現が難しいので、
この演習では **乱数のシードだけで挙動が完全に決まる** ネットワークシミュレータを作り、
その上で「再送（at-least-once）＋ 重複排除（冪等な受信）＝ 実質1回（effectively-once）の処理」を実装します。
FoundationDB などが採用している決定的シミュレーションテスト（本文 8 節）の考え方の縮小版です。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 7.1
このディレクトリで、この演習だけを実行することもできます:
    python3 -m unittest -v test_simnet

制約:
    - 乱数は必ず Network.rng（random.Random(seed)）だけを使うこと。random モジュールの関数や
      time モジュールを直接使うと、実行が再現しなくなる。
    - 実時間は一切使わない。時刻は Network.now（シミュレーション上の時刻、単位は任意）だけ。
"""
from __future__ import annotations

import heapq  # noqa: F401  イベントキュー（優先度付きキュー）に使えます
import random  # noqa: F401  Network.rng = random.Random(seed) に使います
from dataclasses import dataclass
from typing import Any, Callable, Iterable

# ---------------------------------------------------------------------------
# 演習4（★★★）: 決定的な離散イベント・ネットワークシミュレータ
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Message:
    """ネットワーク上を運ばれるメッセージ。sent_at は送信した時点の Network.now。"""

    src: str
    dst: str
    payload: Any
    sent_at: float


class Network:
    """シード付き乱数で遅延・損失・複製・順序の入れ替わりを起こす、決定的なネットワーク。

    離散イベントシミュレーション: 「時刻 t にこれを実行する」というイベントを優先度付きキューに入れ、
    run() が時刻の早い順に取り出して実行する。実時間は待たない。

    属性:
        rng: random.Random(seed)。**すべての乱数はここから取る**。
        now: 現在のシミュレーション時刻（初期値 0.0）。
        stats: {"sent": 送信回数, "dropped": 失われた数, "duplicated": 複製された数, "delivered": 配送した数}
        log: 配送したメッセージの記録。(配送時刻, src, dst, payload) のリスト（配送順）。

    send(src, dst, payload) の規則:
        1. src と dst が register 済みでなければ ValueError。stats["sent"] を 1 増やす。
        2. src と dst が分断されている（partition 中で別グループ）か、rng.random() < drop_rate なら
           メッセージは失われる（stats["dropped"] += 1 で終了）。
        3. そうでなければ、rng.random() < duplicate_rate のとき 2 通、それ以外は 1 通を配送する
           （2 通なら stats["duplicated"] += 1）。
        4. 各コピーの遅延は rng.uniform(min_delay, max_delay) で独立に決め、
           時刻 now + 遅延 に「配送」イベントを予約する。→ 追い越しが自然に起きる。
        5. 配送イベントの実行時に src と dst が分断されていれば、そのコピーは失われる（dropped += 1）。
           そうでなければ stats["delivered"] += 1、log に追記し、dst のハンドラを Message で呼ぶ。

    同じ時刻のイベントは、予約した順（FIFO）に実行すること（通し番号をキーに加えるとよい）。
    シードが同じなら、何度実行しても log と stats が完全に一致しなければならない。

    ヒント: キューの要素は (時刻, 通し番号, コールバック) のタプルにすると heapq で扱える。
    ラムダでループ変数を捕まえるときは `lambda m=msg: ...` のように既定値で束縛する。
    """

    def __init__(
        self,
        seed: int = 0,
        *,
        min_delay: float = 1.0,
        max_delay: float = 10.0,
        drop_rate: float = 0.0,
        duplicate_rate: float = 0.0,
    ) -> None:
        """引数を検証して初期化する。

        0 <= min_delay <= max_delay でなければ ValueError。
        drop_rate・duplicate_rate が 0〜1 の範囲外なら ValueError。
        """
        raise NotImplementedError("演習4: Network.__init__ を実装してください")

    def register(self, node_id: str, handler: Callable[[Message], None]) -> None:
        """ノードを登録する。メッセージが届くと handler(Message) が呼ばれる。登録済みなら ValueError。"""
        raise NotImplementedError("演習4: Network.register を実装してください")

    def send(self, src: str, dst: str, payload: Any) -> None:
        """メッセージを送る（クラスの docstring の規則に従う）。すぐには届かない。"""
        raise NotImplementedError("演習4: Network.send を実装してください")

    def schedule(self, delay: float, callback: Callable[[], None]) -> None:
        """時刻 now + delay に callback() を実行するよう予約する（タイマー）。delay < 0 なら ValueError。"""
        raise NotImplementedError("演習4: Network.schedule を実装してください")

    def partition(self, *groups: Iterable[str]) -> None:
        """ネットワークを分断する。同じグループ内のノードどうしだけが通信できる。

        どのグループにも属さないノードは孤立する（自分自身への送信だけは常に届く）。
        新たに partition を呼ぶと、前の分断は置き換えられる。
        """
        raise NotImplementedError("演習4: Network.partition を実装してください")

    def heal(self) -> None:
        """分断を解消し、全ノードが通信できる状態に戻す。"""
        raise NotImplementedError("演習4: Network.heal を実装してください")

    def pending(self) -> int:
        """キューに残っているイベント数。"""
        raise NotImplementedError("演習4: Network.pending を実装してください")

    def run(self, until: float | None = None, max_events: int = 1_000_000) -> int:
        """イベントを時刻順に実行し、実行したイベント数を返す。

        - until が None ならキューが空になるまで。数値なら、時刻が until 以下のイベントだけを実行し、
          最後に now を until まで進める（イベントが残っていても）。
        - 実行するたびに now をそのイベントの時刻にする。コールバックの中で新しいイベントを予約してよい。
        - 実行数が max_events を超えたら RuntimeError（再送のバグなどによる無限ループの検出）。
        """
        raise NotImplementedError("演習4: Network.run を実装してください")


# ---------------------------------------------------------------------------
# 演習5（★★★）: at-least-once 配信（再送と ACK）と冪等な受信側
# ---------------------------------------------------------------------------


class ReliableSender:
    """ACK が返るまで同じメッセージを再送する送信側（at-least-once）。

    - 生成時に net.register(node_id, self.on_message) で自分を登録する。
    - send(dst, body) はメッセージ ID を f"{node_id}-{連番}"（連番は 1 から）で決め、
      ペイロード {"type": "DATA", "id": ID, "body": body} を送って ID を返す。
    - 送るたびに retry_interval 後のタイマーを予約し、その時点で ACK が来ていなければ再送する。
      **再送でも同じ ID を使う**（受信側はこの ID で重複を見分ける）。
    - 送信回数（最初の送信を含む）が max_attempts に達した後のタイマーで、まだ ACK がなければ諦めて
      failed に入れる。これは「相手が処理しなかった」ことを意味しない（ACK だけが失われたかもしれない）。
    - {"type": "ACK", "id": ID} を受け取ったら、その ID を pending から除いて acked に入れる。
      pending にない ID の ACK（重複して届いた ACK や、諦めた後に届いた ACK）は無視する。

    属性:
        pending: {ID: (dst, body)} — ACK 待ち
        attempts: {ID: 送信した回数}
        acked: ACK を受け取った ID の集合
        failed: 諦めた ID の集合

    retry_interval <= 0 または max_attempts < 1 なら ValueError。

    実務メモ: 実際の再送は、間隔を指数的に伸ばし、ランダムなゆらぎ（ジッター）を加えるのが定石（7.5 参照）。
    """

    def __init__(
        self,
        net: Network,
        node_id: str,
        *,
        retry_interval: float = 30.0,
        max_attempts: int = 10,
    ) -> None:
        raise NotImplementedError("演習5: ReliableSender.__init__ を実装してください")

    def send(self, dst: str, body: Any) -> str:
        """body を dst に確実に届けるよう試み、メッセージ ID を返す。"""
        raise NotImplementedError("演習5: ReliableSender.send を実装してください")

    def on_message(self, msg: Message) -> None:
        """ネットワークから届いたメッセージ（ACK）を処理する。"""
        raise NotImplementedError("演習5: ReliableSender.on_message を実装してください")


class IdempotentReceiver:
    """メッセージ ID で重複を除き、各メッセージをちょうど 1 回だけ処理する受信側。

    - 生成時に net.register(node_id, self.on_message) で自分を登録する。
    - DATA を受け取ったら:
        1. 初めて見る ID なら seen に加え、body を processed に追加し、process が与えられていれば
           process(body) を呼ぶ。
        2. 見たことのある ID なら duplicates を 1 増やす（処理はしない）。
        3. **どちらの場合も** 送信元に {"type": "ACK", "id": ID} を返す。
    - DATA 以外のメッセージは無視する。

    なぜ重複にも ACK を返すのか: 最初の ACK がネットワークで失われると、送信側は再送を続ける。
    重複を黙って捨てるだけでは、送信側はいつまでも「届いていない」と判断してしまう。

    属性: processed（処理した body のリスト、処理順）、seen（処理済み ID の集合）、duplicates（捨てた重複の数）
    """

    def __init__(
        self,
        net: Network,
        node_id: str,
        process: Callable[[Any], None] | None = None,
    ) -> None:
        raise NotImplementedError("演習5: IdempotentReceiver.__init__ を実装してください")

    def on_message(self, msg: Message) -> None:
        """ネットワークから届いたメッセージ（DATA）を処理する。"""
        raise NotImplementedError("演習5: IdempotentReceiver.on_message を実装してください")
