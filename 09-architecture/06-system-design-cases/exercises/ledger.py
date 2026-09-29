"""9.6 システム設計ケーススタディ — 演習4（★★★）: 複式簿記の元帳（ledger）

ケーススタディ 6（決済システム）の心臓部である **元帳** を実装します。

お金を扱うシステムでは、「残高」という 1 つの数値を上書きしてはいけません。すべてのお金の動きを、
借方（debit）と貸方（credit）が必ず一致する **仕訳（journal entry）** として追記し、残高はその合計として導きます。
こうすると、お金が「どこから来て、どこへ行ったか」が常に説明でき、合計が合わなければ即座に不具合に気づけます。

    口座の種類と「正常残高の側」:
        資産（ASSET）・費用（EXPENSE）            … 借方で増える（debit-normal）
        負債（LIABILITY）・純資産（EQUITY）・収益（REVENUE） … 貸方で増える（credit-normal）

    例: 利用者 alice が 10,000 円をチャージした（決済代行の口座にお金が入り、alice への支払い義務が増える）
        借方 決済代行の預け金（資産）   10,000 ／ 貸方 alice のウォレット残高（負債） 10,000

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 9.6

金額はすべて最小通貨単位の整数（円）。日時はタイムゾーン付きの datetime。
この元帳は「追記のみ」です。記帳済みの仕訳を変更・削除する操作はなく、誤りは取消の仕訳（reverse）で打ち消します。
"""
from __future__ import annotations

import bisect  # noqa: F401  演習4で使えます
import threading
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Sequence


# ---------------------------------------------------------------------------
# 例外 — 実装済み
# ---------------------------------------------------------------------------

class LedgerError(Exception):
    """元帳のエラーの基底クラス。"""


class InvalidPostingError(LedgerError):
    """仕訳の形が不正（行が 2 行未満、金額が不正、外部 ID がない、など）。"""


class UnbalancedEntryError(LedgerError):
    """借方の合計と貸方の合計が一致しない。"""


class UnknownAccountError(LedgerError):
    pass


class UnknownEntryError(LedgerError):
    pass


class CurrencyMismatchError(LedgerError):
    """1 つの仕訳に、通貨の異なる口座が混ざっている。"""


class InsufficientBalanceError(LedgerError):
    """マイナス残高を許さない口座の残高が負になる。"""


class IdempotencyConflictError(LedgerError):
    """同じ外部 ID で、別の内容の記帳が要求された。"""


class OutOfOrderError(LedgerError):
    """最後の仕訳より前の日時の記帳が要求された。"""


class AlreadyReversedError(LedgerError):
    pass


# ---------------------------------------------------------------------------
# 口座・仕訳の型 — Posting の検証以外は実装済み
# ---------------------------------------------------------------------------

class AccountType(Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


DEBIT_NORMAL = frozenset({AccountType.ASSET, AccountType.EXPENSE})


@dataclass(frozen=True)
class Account:
    account_id: str
    type: AccountType
    currency: str = "JPY"
    allow_negative: bool = True   # False の口座（利用者のウォレットなど）は残高が負になってはいけない

    @property
    def normal_side(self) -> str:
        """"debit"（借方で増える）か "credit"（貸方で増える）。"""
        return "debit" if self.type in DEBIT_NORMAL else "credit"


@dataclass(frozen=True)
class Posting:
    """仕訳の 1 行。借方（debit）か貸方（credit）の、どちらか一方だけが正の金額。

    検証（違反は InvalidPostingError）: debit と credit はどちらも 0 以上の int（bool は不可）で、
    ちょうど一方だけが正であること（両方 0、両方正はだめ）。
    """

    account_id: str
    debit: int = 0
    credit: int = 0

    def __post_init__(self) -> None:
        raise NotImplementedError("演習4: Posting の検証を実装してください")


@dataclass(frozen=True)
class JournalEntry:
    entry_id: str               # 元帳が振る連番の ID: "je_000001", "je_000002", ...
    external_id: str            # 呼び出し側が指定する冪等キー（決済代行のイベント ID など）
    occurred_at: datetime
    postings: tuple[Posting, ...]
    description: str = ""
    reverses: str | None = None  # 取消の仕訳なら、取り消した仕訳の entry_id


@dataclass(frozen=True)
class PostResult:
    entry: JournalEntry
    duplicate: bool   # True なら、同じ外部 ID の再送だったので何も記帳していない


# ---------------------------------------------------------------------------
# 演習4（★★★）: 元帳
# ---------------------------------------------------------------------------

class Ledger:
    """複式簿記の元帳。すべての操作は self._lock の中で行い、複数のスレッドから呼ばれても整合を保つこと。

    open_account(account_id, type, *, currency="JPY", allow_negative=True) -> Account
        口座を開く。同じ ID が既にあれば LedgerError。
    account(account_id) -> Account
        なければ UnknownAccountError。
    post(external_id, postings, occurred_at, description="") -> PostResult
        仕訳を記帳する。次の順に検査し、1 つでも違反があれば何も変更せずに例外を送出する。
        1. external_id が空 → InvalidPostingError
        2. 同じ external_id が記帳済み: postings（行の順序は問わない）・occurred_at・description が
           すべて同じなら、何もせず PostResult(既存の仕訳, duplicate=True)。違えば IdempotencyConflictError
        3. occurred_at がタイムゾーンなし → InvalidPostingError
        4. occurred_at が最後の仕訳の occurred_at より前 → OutOfOrderError（同時刻は可）
        5. 行が 2 行未満 → InvalidPostingError。知らない口座 → UnknownAccountError
        6. 口座の通貨がそろっていない → CurrencyMismatchError
        7. 借方の合計 ≠ 貸方の合計 → UnbalancedEntryError
        8. allow_negative=False の口座の残高（正常残高の側で見た値）が負になる → InsufficientBalanceError
        成功したら entry_id を連番で振り（je_000001 から）、PostResult(新しい仕訳, duplicate=False) を返す。
    reverse(entry_id, external_id, occurred_at) -> PostResult
        entry_id の仕訳の借方と貸方を入れ替えた仕訳を、reverses=entry_id として記帳する
        （description は "取消: " + 元の description）。元の仕訳は消さない。
        - 同じ external_id が「この entry_id の取消」として記帳済みなら、PostResult(それ, duplicate=True)
          （occurred_at は比べない）。別の仕訳に使われていれば IdempotencyConflictError
        - 知らない entry_id → UnknownEntryError。取消の仕訳をさらに取り消そうとした → InvalidPostingError
        - 取消済み → AlreadyReversedError
        - 記帳の検査（時刻の順序、マイナス残高の禁止など）は post と同じ
    balance(account_id, as_of=None) -> int
        正常残高の側で見た残高（資産なら 借方 − 貸方、負債なら 貸方 − 借方）。
        as_of を指定したら、occurred_at が as_of 以前（同時刻を含む）の仕訳だけで計算した残高。
        仕訳は時刻順に追記されるので、口座ごとの履歴を二分探索（bisect）すれば O(log n) で求まる。
    statement(account_id) -> list[(entry_id, occurred_at, 増減, 記帳後の残高)]
        その口座に関わる仕訳の履歴（記帳順）。増減・残高は正常残高の側で見た値。
        1 つの仕訳に同じ口座の行が複数あれば、1 件にまとめる。
    entry(entry_id) -> JournalEntry
        なければ UnknownEntryError。
    trial_balance() -> (借方の総額, 貸方の総額)
        全仕訳の借方と貸方の総額（複式簿記では、常に一致する）。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def open_account(self, account_id: str, type: AccountType, *, currency: str = "JPY",
                     allow_negative: bool = True) -> Account:
        raise NotImplementedError("演習4: Ledger.open_account を実装してください")

    def account(self, account_id: str) -> Account:
        raise NotImplementedError("演習4: Ledger.account を実装してください")

    def post(self, external_id: str, postings: Sequence[Posting], occurred_at: datetime,
             description: str = "") -> PostResult:
        raise NotImplementedError("演習4: Ledger.post を実装してください")

    def reverse(self, entry_id: str, external_id: str, occurred_at: datetime) -> PostResult:
        raise NotImplementedError("演習4: Ledger.reverse を実装してください")

    def balance(self, account_id: str, as_of: datetime | None = None) -> int:
        raise NotImplementedError("演習4: Ledger.balance を実装してください")

    def statement(self, account_id: str) -> list[tuple[str, datetime, int, int]]:
        raise NotImplementedError("演習4: Ledger.statement を実装してください")

    def entry(self, entry_id: str) -> JournalEntry:
        raise NotImplementedError("演習4: Ledger.entry を実装してください")

    def trial_balance(self) -> tuple[int, int]:
        raise NotImplementedError("演習4: Ledger.trial_balance を実装してください")
