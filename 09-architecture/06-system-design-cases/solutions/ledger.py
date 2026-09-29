"""9.6 システム設計ケーススタディ — 解答例: 複式簿記の元帳（ledger）

演習の仕様は exercises/ledger.py の docstring を参照してください。
"""
from __future__ import annotations

import bisect
import threading
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Sequence


class LedgerError(Exception):
    pass


class InvalidPostingError(LedgerError):
    pass


class UnbalancedEntryError(LedgerError):
    pass


class UnknownAccountError(LedgerError):
    pass


class UnknownEntryError(LedgerError):
    pass


class CurrencyMismatchError(LedgerError):
    pass


class InsufficientBalanceError(LedgerError):
    pass


class IdempotencyConflictError(LedgerError):
    pass


class OutOfOrderError(LedgerError):
    pass


class AlreadyReversedError(LedgerError):
    pass


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
    allow_negative: bool = True

    @property
    def normal_side(self) -> str:
        return "debit" if self.type in DEBIT_NORMAL else "credit"


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class Posting:
    account_id: str
    debit: int = 0
    credit: int = 0

    def __post_init__(self) -> None:
        if not _is_int(self.debit) or not _is_int(self.credit) or self.debit < 0 or self.credit < 0:
            raise InvalidPostingError(f"金額は 0 以上の整数です: {self}")
        if (self.debit > 0) == (self.credit > 0):
            raise InvalidPostingError(f"1 行は借方か貸方のどちらか一方だけに正の金額を持ちます: {self}")


@dataclass(frozen=True)
class JournalEntry:
    entry_id: str
    external_id: str
    occurred_at: datetime
    postings: tuple[Posting, ...]
    description: str = ""
    reverses: str | None = None


@dataclass(frozen=True)
class PostResult:
    entry: JournalEntry
    duplicate: bool


class Ledger:
    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._entries: list[JournalEntry] = []
        self._by_id: dict[str, JournalEntry] = {}
        self._by_external: dict[str, JournalEntry] = {}
        self._reversed_by: dict[str, str] = {}
        self._balances: dict[str, int] = {}
        # 口座ごとの履歴: (発生時刻, 仕訳 ID, 増減, 残高)。発生時刻の順に追記されるので二分探索できる
        self._history: dict[str, list[tuple[datetime, str, int, int]]] = {}
        self._times: dict[str, list[datetime]] = {}
        self._lock = threading.Lock()

    # --- 口座 -------------------------------------------------------------------

    def open_account(self, account_id: str, type: AccountType, *, currency: str = "JPY",
                     allow_negative: bool = True) -> Account:
        with self._lock:
            if account_id in self._accounts:
                raise LedgerError(f"口座 {account_id} は既にあります")
            account = Account(account_id, type, currency, allow_negative)
            self._accounts[account_id] = account
            self._balances[account_id] = 0
            self._history[account_id] = []
            self._times[account_id] = []
            return account

    def account(self, account_id: str) -> Account:
        try:
            return self._accounts[account_id]
        except KeyError:
            raise UnknownAccountError(account_id) from None

    # --- 記帳 -------------------------------------------------------------------

    @staticmethod
    def _signed(account: Account, posting: Posting) -> int:
        # 口座の「正常残高の側」で見た増減。資産・費用は借方で増え、負債・純資産・収益は貸方で増える
        delta = posting.debit - posting.credit
        return delta if account.normal_side == "debit" else -delta

    def post(self, external_id: str, postings: Sequence[Posting], occurred_at: datetime,
             description: str = "") -> PostResult:
        with self._lock:
            return self._post(external_id, tuple(postings), occurred_at, description, reverses=None)

    def _post(self, external_id: str, postings: tuple[Posting, ...], occurred_at: datetime,
              description: str, reverses: str | None) -> PostResult:
        if not external_id:
            raise InvalidPostingError("external_id が必要です")
        existing = self._by_external.get(external_id)
        if existing is not None:
            # 冪等性: 同じ外部 ID の再送は、内容が同じなら何もせず既存の仕訳を返す
            same = (
                sorted(existing.postings, key=_posting_key) == sorted(postings, key=_posting_key)
                and existing.occurred_at == occurred_at
                and existing.description == description
                and existing.reverses == reverses
            )
            if not same:
                raise IdempotencyConflictError(f"外部 ID {external_id} は別の内容で記帳済みです")
            return PostResult(existing, duplicate=True)

        # --- 検証（すべて通るまで何も変更しない） ---
        if occurred_at.utcoffset() is None:
            raise InvalidPostingError("発生時刻はタイムゾーン付きで指定してください")
        if self._entries and occurred_at < self._entries[-1].occurred_at:
            raise OutOfOrderError("元帳は追記のみ。過去の時点への記帳は、訂正の仕訳を今の時点で起こす")
        if len(postings) < 2:
            raise InvalidPostingError("仕訳には 2 行以上が必要です")
        accounts = []
        for p in postings:
            if not isinstance(p, Posting):
                raise InvalidPostingError(f"Posting ではありません: {p!r}")
            accounts.append(self.account(p.account_id))
        if len({a.currency for a in accounts}) != 1:
            raise CurrencyMismatchError("1 つの仕訳の口座はすべて同じ通貨である必要があります")
        total_debit = sum(p.debit for p in postings)
        total_credit = sum(p.credit for p in postings)
        if total_debit != total_credit:
            raise UnbalancedEntryError(f"借方 {total_debit} と貸方 {total_credit} が一致しません")

        deltas: dict[str, int] = {}
        for account, p in zip(accounts, postings):
            deltas[account.account_id] = deltas.get(account.account_id, 0) + self._signed(account, p)
        for account_id, delta in deltas.items():
            account = self._accounts[account_id]
            new_balance = self._balances[account_id] + delta
            if not account.allow_negative and new_balance < 0:
                raise InsufficientBalanceError(
                    f"{account_id} の残高が不足します（現在 {self._balances[account_id]}、変動 {delta}）"
                )

        # --- 適用 ---
        entry = JournalEntry(f"je_{len(self._entries) + 1:06d}", external_id, occurred_at, postings,
                             description, reverses)
        self._entries.append(entry)
        self._by_id[entry.entry_id] = entry
        self._by_external[external_id] = entry
        for account_id, delta in deltas.items():
            self._balances[account_id] += delta
            self._history[account_id].append((occurred_at, entry.entry_id, delta, self._balances[account_id]))
            self._times[account_id].append(occurred_at)
        if reverses is not None:
            self._reversed_by[reverses] = entry.entry_id
        return PostResult(entry, duplicate=False)

    def reverse(self, entry_id: str, external_id: str, occurred_at: datetime) -> PostResult:
        with self._lock:
            existing = self._by_external.get(external_id)
            if existing is not None:
                # 取消の再送: 同じ仕訳の取消なら結果を返す（発生時刻は再送のたびに変わりうるので比べない）
                if existing.reverses == entry_id:
                    return PostResult(existing, duplicate=True)
                raise IdempotencyConflictError(f"外部 ID {external_id} は別の仕訳に使われています")
            original = self._by_id.get(entry_id)
            if original is None:
                raise UnknownEntryError(entry_id)
            if original.reverses is not None:
                raise InvalidPostingError("取消の仕訳を取り消すことはできません（必要なら新しい仕訳を起こす）")
            if entry_id in self._reversed_by:
                raise AlreadyReversedError(f"{entry_id} は {self._reversed_by[entry_id]} で取り消し済みです")
            # 元の仕訳は消さない。借方と貸方を入れ替えた仕訳を追記して打ち消す
            swapped = tuple(Posting(p.account_id, debit=p.credit, credit=p.debit) for p in original.postings)
            return self._post(external_id, swapped, occurred_at, f"取消: {original.description}", entry_id)

    # --- 照会 -------------------------------------------------------------------

    def balance(self, account_id: str, as_of: datetime | None = None) -> int:
        with self._lock:
            self.account(account_id)
            if as_of is None:
                return self._balances[account_id]
            # as_of 以前（同時刻を含む）の最後の記帳の残高。履歴は時刻順なので二分探索で O(log n)
            i = bisect.bisect_right(self._times[account_id], as_of)
            return self._history[account_id][i - 1][3] if i else 0

    def statement(self, account_id: str) -> list[tuple[str, datetime, int, int]]:
        with self._lock:
            self.account(account_id)
            return [(entry_id, at, delta, running) for at, entry_id, delta, running in self._history[account_id]]

    def entry(self, entry_id: str) -> JournalEntry:
        try:
            return self._by_id[entry_id]
        except KeyError:
            raise UnknownEntryError(entry_id) from None

    def trial_balance(self) -> tuple[int, int]:
        with self._lock:
            debits = sum(p.debit for e in self._entries for p in e.postings)
            credits = sum(p.credit for e in self._entries for p in e.postings)
            return debits, credits


def _posting_key(p: Posting) -> tuple[str, int, int]:
    return (p.account_id, p.debit, p.credit)
