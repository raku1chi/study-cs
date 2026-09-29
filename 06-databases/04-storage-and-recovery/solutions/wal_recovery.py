"""6.4 ストレージエンジンと障害回復 — 演習3 解答例: WAL による障害回復

演習の仕様は exercises/wal_recovery.py の docstring を参照してください。
"""
from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# 提供済み: ログレコードとページ（スタブと同じ）
# ---------------------------------------------------------------------------

KINDS = ("update", "commit", "abort", "clr", "end", "checkpoint")


@dataclass(frozen=True)
class LogRecord:
    lsn: int
    kind: str
    txn: int | None = None
    page: str | None = None
    before: Any = None
    after: Any = None
    undoes: int | None = None
    active: tuple[int, ...] = ()
    dirty: tuple[tuple[str, int], ...] = ()


@dataclass
class Page:
    value: Any = None
    page_lsn: int = 0


@dataclass(frozen=True)
class Analysis:
    winners: frozenset[int]
    losers: frozenset[int]
    redo_lsn: int


def validate_log(log: Sequence[LogRecord]) -> None:
    prev = 0
    for rec in log:
        if rec.kind not in KINDS:
            raise ValueError(f"不明なレコードの種類です: {rec.kind!r}")
        if rec.lsn <= prev:
            raise ValueError(f"LSN は 1 以上で、狭義に増加する必要があります: {rec.lsn}")
        if rec.kind in ("update", "clr") and (rec.txn is None or rec.page is None):
            raise ValueError(f"LSN {rec.lsn}: update / clr には txn と page が必要です")
        if rec.kind in ("commit", "abort", "end") and rec.txn is None:
            raise ValueError(f"LSN {rec.lsn}: {rec.kind} には txn が必要です")
        prev = rec.lsn


# ---------------------------------------------------------------------------
# 演習3-1: 分析（analysis）
# ---------------------------------------------------------------------------

def analyze(log: Sequence[LogRecord]) -> Analysis:
    validate_log(log)
    ckpt_at = max((i for i, r in enumerate(log) if r.kind == "checkpoint"), default=None)
    if ckpt_at is None:
        start, active = 0, set()
        redo_lsn = log[0].lsn if log else 1
    else:
        ckpt = log[ckpt_at]
        start, active = ckpt_at + 1, set(ckpt.active)
        # チェックポイントの時点で汚れていたページの、最も古い recLSN から再実行すれば足りる。
        # それより前の更新は、ディスクのページに反映済みであることが（チェックポイントが）保証している
        redo_lsn = min([ckpt.lsn, *(rec_lsn for _, rec_lsn in ckpt.dirty)])
    committed: set[int] = set()
    ended: set[int] = set()
    for rec in log[start:]:
        if rec.txn is None:
            continue
        active.add(rec.txn)
        if rec.kind == "commit":
            committed.add(rec.txn)
        elif rec.kind == "end":
            ended.add(rec.txn)
    # コミットもしておらず、取り消しも完了していない（end がない）ものが「敗者」
    losers = active - committed - ended
    return Analysis(frozenset(committed), frozenset(losers), redo_lsn)


# ---------------------------------------------------------------------------
# 演習3-2: 再実行（redo）
# ---------------------------------------------------------------------------

def redo(log: Sequence[LogRecord], pages: dict[str, Page], redo_lsn: int) -> list[int]:
    applied: list[int] = []
    for rec in log:
        if rec.lsn < redo_lsn or rec.kind not in ("update", "clr"):
            continue
        page = pages.setdefault(rec.page, Page())
        # 「歴史の再現」: 勝者か敗者かを問わず、ページにまだ反映されていない変更をすべて適用する。
        # page_lsn >= LSN なら、その変更はすでにディスクのページに含まれているので飛ばす
        if page.page_lsn < rec.lsn:
            page.value = rec.after
            page.page_lsn = rec.lsn
            applied.append(rec.lsn)
    return applied


# ---------------------------------------------------------------------------
# 演習3-3: 取り消し（undo）
# ---------------------------------------------------------------------------

def undo(log: Sequence[LogRecord], pages: dict[str, Page], losers: frozenset[int] | set[int]) -> list[LogRecord]:
    # 以前の取り消し（通常時のアボートや、途中で落ちた回復）で、すでに補償済みの更新は飛ばす
    compensated = {r.undoes for r in log if r.kind == "clr"}
    todo = sorted(
        (r for r in log if r.kind == "update" and r.txn in losers and r.lsn not in compensated),
        key=lambda r: r.lsn,
        reverse=True,  # 新しい変更から順に取り消す
    )
    next_lsn = (log[-1].lsn if log else 0) + 1
    new: list[LogRecord] = []
    for rec in todo:
        # 取り消しそのものもログに記録する（CLR）。CLR は再実行だけされ、取り消されることはない。
        # 回復の途中でまたクラッシュしても、CLR を見れば「どこまで取り消したか」が分かる
        clr = LogRecord(next_lsn, "clr", txn=rec.txn, page=rec.page, after=rec.before, undoes=rec.lsn)
        page = pages.setdefault(rec.page, Page())
        page.value = rec.before
        page.page_lsn = next_lsn
        new.append(clr)
        next_lsn += 1
    for txn in sorted(losers):
        new.append(LogRecord(next_lsn, "end", txn=txn))
        next_lsn += 1
    return new


# ---------------------------------------------------------------------------
# 演習3-4: 回復の全体
# ---------------------------------------------------------------------------

def recover(log: Sequence[LogRecord], disk_pages: Mapping[str, Page]) -> tuple[dict[str, Page], list[LogRecord]]:
    validate_log(log)
    last_lsn = log[-1].lsn if log else 0
    for name, page in disk_pages.items():
        if page.page_lsn > last_lsn:
            # WAL の規則（ページより先にログを書く）が破られている。ログにない変更がページにあるので、
            # 取り消すことも正しく再実行することもできない
            raise ValueError(f"ページ {name} の page_lsn {page.page_lsn} がログの末尾 {last_lsn} より新しい")
    pages = copy.deepcopy(dict(disk_pages))
    analysis = analyze(log)
    redo(log, pages, analysis.redo_lsn)
    new_records = undo(log, pages, analysis.losers)
    return pages, new_records
