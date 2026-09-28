"""8.2 テスト戦略 — 演習3 で使う「本物」のコード（完成しています。編集しないでください）

定期購入（サブスクリプション）の更新と失効を扱う小さなサービスです。

  - SqliteSubscriptionRepository: sqlite3 を使った本物のリポジトリ
  - SystemClock                 : 本物の時計
  - SubscriptionService         : 更新・失効のビジネスロジック（依存はすべてコンストラクタで受け取る）

演習3（fakes.py）では、このリポジトリと「同じ契約」を満たすインメモリの偽物（fake）と、
テスト用の時計・決済ゲートウェイを作り、SubscriptionService をネットワークも DB も
実時間の待ちもなしにテストできるようにします。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol

ACTIVE, PAST_DUE, CANCELED, EXPIRED = "active", "past_due", "canceled", "expired"
DUE_STATUSES = (ACTIVE, PAST_DUE)

# プラン: (1 期間の長さ, 1 期間の料金（円）)
PLANS = {
    "monthly": (timedelta(days=30), 980),
    "yearly": (timedelta(days=365), 9800),
}
GRACE_PERIOD = timedelta(days=3)  # 支払いに失敗してから失効するまでの猶予
MAX_FAILED_ATTEMPTS = 3  # この回数続けて失敗したら、猶予期間中でも失効させる


class DuplicateSubscriptionError(Exception):
    """同じ id のサブスクリプションがすでにある。"""


class SubscriptionNotFoundError(Exception):
    """指定した id のサブスクリプションがない。"""


class PaymentFailedError(Exception):
    """新規申し込み時の決済に失敗した。"""


@dataclass
class Subscription:
    id: str
    user_id: str
    plan: str  # PLANS のキー
    status: str  # ACTIVE / PAST_DUE / CANCELED / EXPIRED
    current_period_end: datetime  # 現在の期間の終わり（timezone 付き）
    auto_renew: bool = True  # False なら期間の終わりで失効する（解約予約）
    failed_attempts: int = 0  # 連続した決済失敗の回数


class SubscriptionRepository(Protocol):
    """リポジトリの契約（本物も偽物も、この振る舞いを守る）。

    - add(sub): 保存する。同じ id がすでにあれば DuplicateSubscriptionError。
    - get(sub_id): 保存されている値の **コピー** を返す。なければ None。
    - update(sub): 同じ id の値を置き換える。なければ SubscriptionNotFoundError。
    - list_due(now): status が ACTIVE か PAST_DUE で、current_period_end <= now のものを、
      (current_period_end, id) の昇順で返す。
    - timezone のない datetime を渡したら ValueError（add・update・list_due のすべて）。
    - 保存した後で、渡したオブジェクトや返されたオブジェクトを変更しても、保存内容は変わらない。
    """

    def add(self, sub: Subscription) -> None: ...

    def get(self, sub_id: str) -> Optional[Subscription]: ...

    def update(self, sub: Subscription) -> None: ...

    def list_due(self, now: datetime) -> list[Subscription]: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class PaymentGateway(Protocol):
    def charge(self, user_id: str, amount: int, idempotency_key: str) -> bool:
        """課金を試み、成功したら True、カードの拒否などで失敗したら False を返す。"""
        ...


# ---------------------------------------------------------------------------
# 本物の実装
# ---------------------------------------------------------------------------

def _require_aware(dt: datetime, what: str) -> None:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{what} には timezone 付きの datetime を指定してください: {dt!r}")


def _to_db(dt: datetime) -> str:
    # UTC に揃えた固定幅の文字列にすると、文字列の大小比較と時刻の前後が一致する
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def _from_db(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%f+00:00").replace(tzinfo=timezone.utc)


class SqliteSubscriptionRepository:
    """sqlite3 を使った本物のリポジトリ。path=":memory:" ならメモリ上の DB。"""

    def __init__(self, path: str = ":memory:"):
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS subscriptions (
                   id TEXT PRIMARY KEY,
                   user_id TEXT NOT NULL,
                   plan TEXT NOT NULL,
                   status TEXT NOT NULL,
                   current_period_end TEXT NOT NULL,
                   auto_renew INTEGER NOT NULL,
                   failed_attempts INTEGER NOT NULL
               )"""
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _row(sub: Subscription) -> tuple:
        _require_aware(sub.current_period_end, "current_period_end")
        return (sub.user_id, sub.plan, sub.status, _to_db(sub.current_period_end),
                int(sub.auto_renew), sub.failed_attempts, sub.id)

    @staticmethod
    def _from_row(row: tuple) -> Subscription:
        sub_id, user_id, plan, status, period_end, auto_renew, failed = row
        return Subscription(sub_id, user_id, plan, status, _from_db(period_end), bool(auto_renew), failed)

    def add(self, sub: Subscription) -> None:
        row = self._row(sub)
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO subscriptions (user_id, plan, status, current_period_end,"
                    " auto_renew, failed_attempts, id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    row,
                )
        except sqlite3.IntegrityError:
            raise DuplicateSubscriptionError(sub.id) from None

    def get(self, sub_id: str) -> Optional[Subscription]:
        row = self._conn.execute(
            "SELECT id, user_id, plan, status, current_period_end, auto_renew, failed_attempts"
            " FROM subscriptions WHERE id = ?",
            (sub_id,),
        ).fetchone()
        return self._from_row(row) if row else None

    def update(self, sub: Subscription) -> None:
        row = self._row(sub)
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE subscriptions SET user_id = ?, plan = ?, status = ?, current_period_end = ?,"
                " auto_renew = ?, failed_attempts = ? WHERE id = ?",
                row,
            )
        if cursor.rowcount == 0:
            raise SubscriptionNotFoundError(sub.id)

    def list_due(self, now: datetime) -> list[Subscription]:
        _require_aware(now, "now")
        rows = self._conn.execute(
            "SELECT id, user_id, plan, status, current_period_end, auto_renew, failed_attempts"
            " FROM subscriptions WHERE status IN (?, ?) AND current_period_end <= ?"
            " ORDER BY current_period_end, id",
            (*DUE_STATUSES, _to_db(now)),
        ).fetchall()
        return [self._from_row(row) for row in rows]


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# ビジネスロジック
# ---------------------------------------------------------------------------

class SubscriptionService:
    def __init__(self, repo: SubscriptionRepository, payments: PaymentGateway, clock: Clock):
        self._repo = repo
        self._payments = payments
        self._clock = clock

    def subscribe(self, sub_id: str, user_id: str, plan: str) -> Subscription:
        """申し込み。最初の期間の料金をすぐに課金し、成功したら ACTIVE で保存する。"""
        if plan not in PLANS:
            raise ValueError(f"不明なプランです: {plan!r}")
        length, price = PLANS[plan]
        now = self._clock.now()
        if not self._payments.charge(user_id, price, idempotency_key=f"{sub_id}:initial"):
            raise PaymentFailedError(f"{sub_id}: 最初の決済に失敗しました")
        sub = Subscription(sub_id, user_id, plan, ACTIVE, now + length)
        self._repo.add(sub)
        return sub

    def cancel(self, sub_id: str) -> None:
        """解約予約。現在の期間の終わりまでは使え、その後に失効する。"""
        sub = self._repo.get(sub_id)
        if sub is None:
            raise SubscriptionNotFoundError(sub_id)
        sub.auto_renew = False
        self._repo.update(sub)

    def process_due(self) -> list[tuple[str, str]]:
        """期限が来たサブスクリプションを処理し、(id, 出来事) の一覧を返す。1 日 1 回の実行を想定。

        出来事: "renewed"（更新）/ "payment_failed"（決済失敗・猶予期間中）/ "expired"（失効）
        """
        now = self._clock.now()
        events = []
        for sub in self._repo.list_due(now):
            events.append((sub.id, self._process_one(sub, now)))
        return events

    def _process_one(self, sub: Subscription, now: datetime) -> str:
        if not sub.auto_renew:
            sub.status = EXPIRED
            self._repo.update(sub)
            return "expired"
        length, price = PLANS[sub.plan]
        attempt = sub.failed_attempts + 1
        key = f"{sub.id}:{sub.current_period_end.isoformat()}:{attempt}"
        if self._payments.charge(sub.user_id, price, idempotency_key=key):
            # 更新後の期間は「現在の期間の終わり」から数える（支払いが遅れても無料期間は生じない）
            sub.current_period_end += length
            sub.status, sub.failed_attempts = ACTIVE, 0
            self._repo.update(sub)
            return "renewed"
        sub.failed_attempts = attempt
        if attempt >= MAX_FAILED_ATTEMPTS or now >= sub.current_period_end + GRACE_PERIOD:
            sub.status = EXPIRED
            self._repo.update(sub)
            return "expired"
        sub.status = PAST_DUE
        self._repo.update(sub)
        return "payment_failed"
