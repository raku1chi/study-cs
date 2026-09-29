"""8.6 開発プロセスとドキュメンテーション — 演習3: ADR（アーキテクチャ決定記録）の管理ツール

ADR（Architecture Decision Record）は、重要な設計判断を「1 つの判断 = 1 つの短い Markdown ファイル」
として、番号付きでリポジトリに残す習慣です（Michael Nygard, 2011）。この演習では、ADR の作成・一覧・
状態の変更・置き換え（supersede）を行う小さなツールを作ります（Nat Pryce の adr-tools を参考にした）。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 8.6

ファイル名: "<4 桁の番号>-<スラッグ>.md"（例: 0003-use-postgresql.md）
ファイルの形式（new_adr が書き出すもの。{…} は置き換える）:

    # {番号}. {タイトル}

    - 日付: {YYYY-MM-DD}

    ## ステータス

    {ステータス}

    ## コンテキスト

    （この決定が必要になった背景、制約、検討した選択肢を書く）

    ## 決定

    （何をするか。「〜する」と能動態で書く）

    ## 結果

    （この決定によって、何が容易になり、何が困難になるか。良い面も悪い面も書く）

    （ファイルの末尾は改行 1 つで終わる。番号は見出しでは 4 桁にしない: "# 3. …"）

ステータスは STATUSES のいずれか。置き換えた・置き換えられた ADR では、ステータスの行の次に
空行を挟んで、相手へのリンクの行を 1 行置く:
    置き換え元: [ADR-0003 セッションをアプリケーションサーバーのメモリに保存する](0003-store-sessions-in-memory.md)
    置き換え先: [ADR-0005 セッションを Redis に保存する](0005-store-sessions-in-redis.md)
"""
from __future__ import annotations

import re  # noqa: F401  実装で使えます
import unicodedata  # noqa: F401  実装で使えます
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

STATUSES = ("提案中", "承認済み", "却下", "非推奨", "置き換え済み")


@dataclass(frozen=True)
class AdrInfo:
    number: int
    title: str
    status: str  # 「## ステータス」の後の、最初の空でない行
    path: Path


def slugify(title: str) -> str:
    """ファイル名用のスラッグ: NFKC で正規化して小文字にし、英数字 [a-z0-9] の連続を "-" でつなぐ。

    英数字が 1 文字もなければ "decision"。

    >>> slugify("Use PostgreSQL for the main DB")
    'use-postgresql-for-the-main-db'
    >>> slugify("ＰｏｓｔｇｒｅＳＱＬ を採用する")
    'postgresql'
    >>> slugify("認証方式の決定")
    'decision'
    """
    raise NotImplementedError("演習3: slugify を実装してください")


def new_adr(
    directory: Path, title: str, *, on: date, status: str = "提案中", slug: Optional[str] = None
) -> Path:
    """新しい ADR を作り、そのパスを返す。

    - 番号は、directory にある ADR の最大の番号 + 1（なければ 1）。欠番は埋めない。
    - directory がなければ作る。
    - title が空白だけ、または status が STATUSES にないなら ValueError。
    - slug を省略したら slugify(title)。
    """
    raise NotImplementedError("演習3: new_adr を実装してください")


def list_adrs(directory: Path) -> list[AdrInfo]:
    """directory の ADR（ファイル名が "<4 桁の数字>-….md" のもの）を番号順に返す。それ以外のファイルは無視する。

    タイトルは 1 行目の "# {番号}. " の後ろ、ステータスは「## ステータス」の後の最初の空でない行。
    """
    raise NotImplementedError("演習3: list_adrs を実装してください")


def set_status(directory: Path, number: int, status: str) -> None:
    """ADR のステータスの行を書き換える（例: 提案中 → 承認済み）。ほかの行は変えない。

    番号の ADR がなければ KeyError、status が STATUSES にないなら ValueError。
    """
    raise NotImplementedError("演習3: set_status を実装してください")


def supersede(directory: Path, old_number: int, new_title: str, *, on: date, slug: Optional[str] = None) -> Path:
    """old_number の ADR を置き換える新しい ADR を作り、そのパスを返す。

    - 新しい ADR: ステータス「承認済み」、その下に「置き換え元: [ADR-{旧番号 4 桁} {旧タイトル}]({旧ファイル名})」。
    - 古い ADR: ステータスを「置き換え済み」にし、その下に「置き換え先: [ADR-{新番号 4 桁} {新タイトル}]({新ファイル名})」。
    - 古い ADR がなければ KeyError、すでに「置き換え済み」なら ValueError。
    """
    raise NotImplementedError("演習3: supersede を実装してください")
