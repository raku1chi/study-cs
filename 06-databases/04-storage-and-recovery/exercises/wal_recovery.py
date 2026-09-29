"""6.4 ストレージエンジンと障害回復 — 演習3: WAL による障害回復（ARIES の考え方）

クラッシュした時点の「ディスク上のページ」と「先行書き込みログ（WAL）」から、
コミットしたトランザクションの変更をすべて残し、コミットしていない変更をすべて取り消す
回復処理を実装します。IBM の ARIES（Mohan ほか, 1992）の 3 段階（分析・再実行・取り消し）を
簡略化したものです。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 6.4
このディレクトリで、この演習だけを実行する:
    python3 -m unittest -v test_wal_recovery

モデル（簡略化している点に注意）:
    - データベースは、名前の付いたページ（"P1" など）の集まり。各ページは 1 つの値を持つ。
    - ページは、最後に反映したログレコードの番号 page_lsn を持つ（ディスクに書かれたページの
      page_lsn を見れば、どの変更までが反映済みかが分かる）。
    - バッファの方針は STEAL / NO-FORCE: コミット前の変更を含むページがディスクに書かれることも
      あり（STEAL → 取り消しが必要）、コミットしてもページを書く必要はない（NO-FORCE → 再実行が必要）。
    - WAL の規則: ページをディスクに書く前に、そのページの変更のログレコードを必ず永続化する。
      コミットは、commit レコードが永続化されたら完了とする。

ログレコード（LogRecord）の種類:
    update      トランザクション txn がページ page の値を before から after に変えた
    commit      txn がコミットした
    abort       txn の中断（取り消し）を始めた
    clr         補償ログレコード（Compensation Log Record）。update（LSN = undoes）を取り消して、
                page の値を after に戻した。CLR は「再実行」されるだけで、取り消されることはない
    end         txn の後始末が完了した（取り消しの完了など）。これ以降、回復の対象にならない
    checkpoint  その時点の実行中のトランザクション（active）と、ディスクに未反映の変更を持つ
                ページとその recLSN（そのページを最初に汚した LSN）の組（dirty）を記録する

ページの初期値は Page(value=None, page_lsn=0)。disk_pages に存在しないページは初期値とみなす。
"""
from __future__ import annotations

import copy  # noqa: F401  演習3-4 で使えます
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# 提供済み: ログレコードとページ（変更しなくてよい）
# ---------------------------------------------------------------------------

KINDS = ("update", "commit", "abort", "clr", "end", "checkpoint")


@dataclass(frozen=True)
class LogRecord:
    """ログレコード。使わない欄は既定値のまま。"""

    lsn: int                                   # ログ順序番号（Log Sequence Number）。狭義に増加
    kind: str                                  # KINDS のいずれか
    txn: int | None = None
    page: str | None = None
    before: Any = None                         # update: 変更前の値（取り消し用）
    after: Any = None                          # update / clr: 変更後の値（再実行用）
    undoes: int | None = None                  # clr: 取り消した update の LSN
    active: tuple[int, ...] = ()               # checkpoint: 実行中のトランザクション
    dirty: tuple[tuple[str, int], ...] = ()    # checkpoint: (ページ, recLSN) の組


@dataclass
class Page:
    """ページ。value は値、page_lsn はこのページに最後に反映したログレコードの LSN。"""

    value: Any = None
    page_lsn: int = 0


@dataclass(frozen=True)
class Analysis:
    """分析の結果。winners はコミットした、losers は取り消すべきトランザクション。"""

    winners: frozenset[int]
    losers: frozenset[int]
    redo_lsn: int


def validate_log(log: Sequence[LogRecord]) -> None:
    """ログの形式を確かめる（提供済み）。不正なら ValueError。

    - LSN が 1 以上で狭義に増加している、種類が KINDS のいずれか、
      update / clr には txn と page、commit / abort / end には txn がある。
    """
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
# 演習3-1（★★☆）: 分析（analysis）
# ---------------------------------------------------------------------------

def analyze(log: Sequence[LogRecord]) -> Analysis:
    """ログを調べ、勝者・敗者と、再実行を始める LSN を求める。

    - 最後の checkpoint レコードを探す。あれば、その active を出発点にし、その次のレコードから
      末尾まで調べる。なければ、空の集合から始めてログ全体を調べる。
    - 調べる範囲で txn を持つレコードに現れたトランザクションを、実行中の集合に加える。
      commit があれば勝者（winners）。end があれば後始末が済んでいる。
    - 敗者（losers）= 実行中の集合 − 勝者 − end のあるトランザクション
      （abort を始めたが end のないトランザクションも敗者。取り消しを続ける必要がある）。
    - redo_lsn: checkpoint があれば、その LSN と、dirty にある recLSN の最小値。
      なければ、ログの最初の LSN（ログが空なら 1）。
    - 最初に validate_log(log) を呼ぶこと。
    """
    raise NotImplementedError("演習3-1: analyze を実装してください")


# ---------------------------------------------------------------------------
# 演習3-2（★★☆）: 再実行（redo）
# ---------------------------------------------------------------------------

def redo(log: Sequence[LogRecord], pages: dict[str, Page], redo_lsn: int) -> list[int]:
    """LSN >= redo_lsn の update と clr を、ログの順に再実行する（pages をその場で書き換える）。

    - 勝者か敗者かを問わず、すべての変更を再実行する（「歴史の再現」。敗者の変更は次の undo で
      取り消す）。
    - ページの page_lsn がレコードの LSN 以上なら、その変更は反映済みなので飛ばす。
      そうでなければ value = after、page_lsn = LSN にする（pages にないページは Page() を作る）。
    - 戻り値: 実際に適用したレコードの LSN のリスト（昇順）。
    """
    raise NotImplementedError("演習3-2: redo を実装してください")


# ---------------------------------------------------------------------------
# 演習3-3（★★★）: 取り消し（undo）
# ---------------------------------------------------------------------------

def undo(log: Sequence[LogRecord], pages: dict[str, Page], losers: frozenset[int] | set[int]) -> list[LogRecord]:
    """敗者の変更を、新しいものから順に取り消し、追加したログレコードを返す（pages を書き換える）。

    - ログ中の clr の undoes に現れる update は、すでに取り消し済みなので飛ばす
      （通常時のアボートや、途中でクラッシュした前回の回復で取り消したもの）。
    - 残った敗者の update を LSN の降順に処理する。それぞれについて CLR
      LogRecord(lsn=次の LSN, kind="clr", txn=..., page=..., after=update の before, undoes=update の LSN)
      を作り、ページの value を before に、page_lsn を CLR の LSN にする。
      「次の LSN」は、ログの最後の LSN + 1 から始めて 1 ずつ増やす。
    - 最後に、敗者ごとに（番号の昇順で）LogRecord(lsn=次の LSN, kind="end", txn=...) を作る。
    - 戻り値: 作った CLR と end のリスト（LSN の昇順）。

    敗者の変更は、最後の checkpoint より前にあることもある（長いトランザクション）。
    取り消しでは、checkpoint より前も含めてログ全体を見ること。
    """
    raise NotImplementedError("演習3-3: undo を実装してください")


# ---------------------------------------------------------------------------
# 演習3-4（★★☆）: 回復の全体
# ---------------------------------------------------------------------------

def recover(log: Sequence[LogRecord], disk_pages: Mapping[str, Page]) -> tuple[dict[str, Page], list[LogRecord]]:
    """クラッシュ後の回復: 分析 → 再実行 → 取り消し。

    - disk_pages を書き換えないこと（deepcopy してから作業する）。
    - ディスクのページの page_lsn がログの最後の LSN より大きければ ValueError
      （WAL の規則が破られており、ログにない変更がページに含まれている）。
    - 戻り値: (回復後のページ, 回復中に追加したログレコード)

    回復の途中で再びクラッシュしても、「元のログ + それまでに追加できたログ」と、その時点の
    ディスクのページから recover をやり直せば、同じ結果になること（冪等性）。
    """
    raise NotImplementedError("演習3-4: recover を実装してください")
