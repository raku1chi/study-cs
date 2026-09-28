"""7.4 合意と協調 — 演習: 2 相コミット（2PC）と、コーディネーター障害によるブロック

複数のデータベース（参加者）にまたがる更新を「全員コミットか、全員アボートか」にする古典的な方法が
2 相コミットです。この演習では、コーディネーターと参加者を（ネットワークを使わずに）メソッド呼び出しで
模擬し、障害を注入して次のことを確かめます。

    - NO が 1 票でもあれば、全員がアボートする（原子性）
    - 参加者が応答しなければ、タイムアウト = NO とみなしてアボートする
    - コーディネーターが PREPARE の後に落ちると、YES と約束した参加者は結果を知るまで何もできない（ブロック）
    - 決定をログに書いた時点（コミットポイント）の前後で、復旧時の振る舞いが変わる

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 7.4
このディレクトリで、この演習だけを実行することもできます:
    python3 -m unittest -v test_twopc

用語:
    - 永続ログ（log）: クラッシュしても残る記録。参加者は "PREPARED" / "COMMIT" / "ABORT"、
      コーディネーターは "COMMIT" / "ABORT"（決定）を追記する。
    - state: メモリ上の状態（INIT / PREPARED / COMMITTED / ABORTED）。クラッシュで失われ、recover でログから復元する。
"""
from __future__ import annotations

from typing import Sequence

INIT = "INIT"
PREPARED = "PREPARED"
COMMITTED = "COMMITTED"
ABORTED = "ABORTED"

COMMIT = "COMMIT"  # 決定・ログの記録に使う文字列
ABORT = "ABORT"

CRASH_POINTS = ("after_prepare", "after_decision", "during_decision")


class AtomicityViolation(Exception):
    """原子性に反する指示（コミット済みの参加者へのアボートなど）を受け取った。"""


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: 参加者
# ---------------------------------------------------------------------------


class Participant:
    """2PC の参加者（例: 在庫データベース、決済データベース）。

    属性: name, vote（PREPARE に YES と答えるか）, crash_before_vote（PREPARE を受け取った瞬間に落ちるか）,
          up（稼働中か。初期値 True）, log（永続ログ。初期値 []）, state（初期値 INIT）

    - prepare() -> bool | None:
        * 停止中なら None（応答なし）。
        * crash_before_vote なら crash() して None。
        * すでに INIT 以外なら、同じ答えを返す（PREPARED・COMMITTED なら True、ABORTED なら False）。ログは増やさない。
        * vote が True なら、**先に** ログに "PREPARED" を追記して state = PREPARED にし、True を返す
          （「言われたら必ずコミットできる」ことを永続化してから約束する）。
        * vote が False なら、ログに "ABORT" を追記して state = ABORTED にし、False を返す。
    - commit() -> bool: 停止中なら False（届かない）。COMMITTED なら何もせず True（冪等）。
        PREPARED なら "COMMIT" を追記して COMMITTED にし True。それ以外（INIT・ABORTED）なら AtomicityViolation。
    - abort() -> bool: 停止中なら False。ABORTED なら何もせず True。COMMITTED なら AtomicityViolation。
        それ以外なら "ABORT" を追記して ABORTED にし True。
    - crash(): up = False、state = None（メモリ上の状態は失われる。ログは残る）。
    - recover(): up = True。ログの最後の記録から state を復元する:
        "PREPARED" → PREPARED（in-doubt: 結果を知るまで自分では決められない）、"COMMIT" → COMMITTED、
        "ABORT" → ABORTED。ログが空なら（YES と約束する前に落ちたので）"ABORT" を追記して ABORTED。
    - outcome() -> str | None: ログの最後が "COMMIT" なら COMMITTED、"ABORT" なら ABORTED、それ以外は None。
    """

    def __init__(self, name: str, vote: bool = True, crash_before_vote: bool = False) -> None:
        raise NotImplementedError("演習1: Participant.__init__ を実装してください")

    def prepare(self) -> bool | None:
        raise NotImplementedError("演習1: Participant.prepare を実装してください")

    def commit(self) -> bool:
        raise NotImplementedError("演習1: Participant.commit を実装してください")

    def abort(self) -> bool:
        raise NotImplementedError("演習1: Participant.abort を実装してください")

    def crash(self) -> None:
        raise NotImplementedError("演習1: Participant.crash を実装してください")

    def recover(self) -> None:
        raise NotImplementedError("演習1: Participant.recover を実装してください")

    def outcome(self) -> str | None:
        raise NotImplementedError("演習1: Participant.outcome を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: コーディネーター
# ---------------------------------------------------------------------------


class Coordinator:
    """2PC のコーディネーター。crash_at で、指定した地点でクラッシュさせられる。

    crash_at は None か CRASH_POINTS のいずれか（それ以外は ValueError）:
        "after_prepare"   : 投票を集めた後、決定をログに書く前に落ちる
        "after_decision"  : 決定をログに書いた後、誰にも伝える前に落ちる
        "during_decision" : 決定を最初の参加者にだけ伝えた後に落ちる

    属性: participants, crash_at, up（初期値 True）, log（決定の永続ログ。初期値 []）

    - run() -> str:
        1. フェーズ 1: 全参加者の prepare() を **順に全員分** 呼んで投票を集める。None（応答なし）は NO とみなす。
        2. 全員が True なら決定は COMMIT、そうでなければ ABORT。
        3. crash_at == "after_prepare" なら up = False にして "CRASHED" を返す。
        4. 決定をログに追記する（これがコミットポイント）。crash_at == "after_decision" なら落ちて "CRASHED"。
        5. フェーズ 2: 参加者の順に commit() / abort() で決定を伝える（停止中の参加者には届かない）。
           crash_at == "during_decision" なら、最初の参加者に伝えた直後に落ちて "CRASHED"。
        6. COMMIT なら COMMITTED、ABORT なら ABORTED を返す。
    - decision() -> str | None: ログにある決定（"COMMIT" / "ABORT"）。なければ None。
    - finish(): ログに決定があれば、稼働中で、まだ結果（outcome）を持たない参加者全員にその決定を伝える。
    - recover() -> str: up = True。ログに決定がなければ "ABORT" を追記する（presumed abort: 決定を書く前に
      落ちたのだから、誰もコミットしていないはず）。そして finish() を呼び、COMMITTED / ABORTED を返す。
    """

    def __init__(self, participants: Sequence[Participant], crash_at: str | None = None) -> None:
        raise NotImplementedError("演習2: Coordinator.__init__ を実装してください")

    def decision(self) -> str | None:
        raise NotImplementedError("演習2: Coordinator.decision を実装してください")

    def run(self) -> str:
        raise NotImplementedError("演習2: Coordinator.run を実装してください")

    def finish(self) -> None:
        raise NotImplementedError("演習2: Coordinator.finish を実装してください")

    def recover(self) -> str:
        raise NotImplementedError("演習2: Coordinator.recover を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: ブロックの検出と、参加者どうしの協調的な終了
# ---------------------------------------------------------------------------


def in_doubt(participants: Sequence[Participant]) -> list[str]:
    """YES と約束した（ログの最後が "PREPARED"）が、結果をまだ知らない参加者の名前を昇順で返す。

    停止中の参加者も、ログで判断して含める。これらの参加者はロックを握ったまま待つしかない。
    """
    raise NotImplementedError("演習3: in_doubt を実装してください")


def is_atomic(participants: Sequence[Participant]) -> bool:
    """結果（outcome）が COMMITTED の参加者と ABORTED の参加者が混在していなければ True。"""
    raise NotImplementedError("演習3: is_atomic を実装してください")


def cooperative_termination(participants: Sequence[Participant]) -> str | None:
    """コーディネーターが停止中に、稼働中の参加者どうしで結果を問い合わせて決着をつける。

    稼働中の参加者を調べて:
        - 誰かの outcome が COMMITTED なら、決定は "COMMIT"（COMMIT は全員の YES の後にしか決まらない）
        - そうでなく、誰かの outcome が ABORTED か、ログが空（まだ投票していない）なら、決定は "ABORT"
          （その参加者は YES と言っていないので、コーディネーターが COMMIT を決めたはずがない）
        - どちらでもなければ（稼働中の全員が PREPARED）、誰も結果を知らないので None を返す（ブロック）
    決定できたら、稼働中でログの最後が "PREPARED" の参加者にその決定を伝え、ログが空の稼働中の参加者は
    abort() する。そして決定（"COMMIT" / "ABORT"）を返す。

    考えてみよう: 稼働中の全員が PREPARED のとき、なぜ「多数決」で決めてはいけないのか。
    """
    raise NotImplementedError("演習3: cooperative_termination を実装してください")
