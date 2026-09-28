"""8.2 テスト戦略 — 演習3: テストダブル（fake・stub・spy）を作る

subscriptions.py の SubscriptionService は、リポジトリ（DB）・決済ゲートウェイ・時計に依存しています。
本物を使うと、テストは遅く（DB）、危険で（本物の決済）、日付に依存して不安定に（時計）なります。
そこで、テスト用の代役（テストダブル）を 3 つ作ります。

  3-1 InMemorySubscriptionRepository（fake）: 本物と同じ契約を満たす、軽量な実装
  3-2 FakeClock（fake）                     : テストが自由に進められる時計
  3-3 RecordingPaymentGateway（stub + spy） : 決まった結果を返し（stub）、呼び出しを記録する（spy）

偽物は「本物と同じように振る舞う」ことが命です。test_fakes.py の契約テスト（RepositoryContract）は、
**同じテストを本物（SQLite）と偽物の両方に対して実行** します。本物だけが通り、偽物が落ちるテストは、
偽物が本物と違う振る舞いをしている証拠です。最初から SQLite 版の契約テストが通っているのはそのためです。

後半のテスト（TestSubscriptionService...）は、あなたの偽物を使って SubscriptionService を検証します。
実時間の待ちも DB もなしに「30 日後」「猶予期間の 3 日後」を一瞬でテストできることを確かめてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 8.2
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional

from subscriptions import (  # noqa: F401  実装で使います
    DUE_STATUSES,
    DuplicateSubscriptionError,
    Subscription,
    SubscriptionNotFoundError,
)


# ---------------------------------------------------------------------------
# 演習3-1（★★☆）: インメモリのリポジトリ（fake）
# ---------------------------------------------------------------------------

class InMemorySubscriptionRepository:
    """subscriptions.SubscriptionRepository の契約を、dict だけで満たす偽物。

    契約（subscriptions.py の SubscriptionRepository の docstring と同じ）:
    - add(sub): 保存する。同じ id がすでにあれば DuplicateSubscriptionError。
    - get(sub_id): 保存されている値の **コピー** を返す。なければ None。
    - update(sub): 同じ id の値を置き換える。なければ SubscriptionNotFoundError。
    - list_due(now): status が DUE_STATUSES（ACTIVE か PAST_DUE）で current_period_end <= now のものを、
      (current_period_end, id) の昇順で返す（返す要素もコピー）。
    - timezone のない datetime を渡したら ValueError（add・update の current_period_end、list_due の now）。
    - 保存した後で、渡したオブジェクトや返されたオブジェクトを変更しても、保存内容は変わらない。

    ヒント: 偽物で最もよくあるバグは「受け取ったオブジェクトをそのまま保存し、そのまま返す」こと。
            本物の DB は値をコピーして保存するので、呼び出し側が後でオブジェクトを書き換えても
            DB の中身は変わりません。dataclasses.replace(sub) でコピーを作れます。
    """

    def __init__(self) -> None:
        raise NotImplementedError("演習3-1: InMemorySubscriptionRepository を実装してください")

    def add(self, sub: Subscription) -> None:
        raise NotImplementedError("演習3-1: add を実装してください")

    def get(self, sub_id: str) -> Optional[Subscription]:
        raise NotImplementedError("演習3-1: get を実装してください")

    def update(self, sub: Subscription) -> None:
        raise NotImplementedError("演習3-1: update を実装してください")

    def list_due(self, now: datetime) -> list[Subscription]:
        raise NotImplementedError("演習3-1: list_due を実装してください")


# ---------------------------------------------------------------------------
# 演習3-2（★☆☆）: テスト用の時計（fake）
# ---------------------------------------------------------------------------

class FakeClock:
    """テストから自由に進められる時計。subscriptions.Clock の契約（now() を持つ）を満たす。

    - FakeClock(start): start は timezone 付きの datetime。なければ ValueError。
    - now(): 現在の（偽の）時刻を返す。
    - advance(delta): 時刻を delta だけ進める。delta が負なら ValueError
      （時計が戻るのは多くの場合テストの書き間違い。戻したいときは set を使う）。
    - set(when): 時刻を when にする。timezone がなければ ValueError。
    """

    def __init__(self, start: datetime) -> None:
        raise NotImplementedError("演習3-2: FakeClock を実装してください")

    def now(self) -> datetime:
        raise NotImplementedError("演習3-2: now を実装してください")

    def advance(self, delta: timedelta) -> None:
        raise NotImplementedError("演習3-2: advance を実装してください")

    def set(self, when: datetime) -> None:
        raise NotImplementedError("演習3-2: set を実装してください")


# ---------------------------------------------------------------------------
# 演習3-3（★☆☆）: 決済ゲートウェイ（stub + spy）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Charge:
    """記録された課金の呼び出し 1 回分。"""

    user_id: str
    amount: int
    idempotency_key: str


class RecordingPaymentGateway:
    """subscriptions.PaymentGateway の契約（charge）を満たすテスト用の代役。

    - declined_users: 課金を拒否する（False を返す）ユーザー ID の集合。テストの途中で変更してよい
      （例: カードを更新したので、次からは成功する）。コンストラクタには任意の iterable を渡せる。
    - charges: charge の呼び出しを、呼ばれた順に Charge として記録したリスト（成功・失敗の両方）。
    - charge(user_id, amount, idempotency_key): 呼び出しを記録し、user_id が declined_users に
      含まれていれば False、それ以外は True を返す。
    """

    def __init__(self, declined_users: Iterable[str] = ()) -> None:
        raise NotImplementedError("演習3-3: RecordingPaymentGateway を実装してください")

    def charge(self, user_id: str, amount: int, idempotency_key: str) -> bool:
        raise NotImplementedError("演習3-3: charge を実装してください")
