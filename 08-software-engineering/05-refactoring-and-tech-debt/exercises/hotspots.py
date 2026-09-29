"""8.5 リファクタリングと技術的負債 — 演習1: ホットスポットと変更の結合の分析

技術的負債のうち、本当に「利子」を払っているのは、**頻繁に変更される** うえに **複雑な** コードです。
誰も触らない複雑なコードは、読みにくくても日々のコストはほとんど生みません。
この演習では、Git の履歴（どのファイルがどれだけ変更されたか）と、ソースコードの複雑さを
組み合わせて、改善の優先順位を決めるための分析を実装します（Adam Tornhill『Your Code as a
Crime Scene』の手法を単純化したもの）。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 8.5

入力のログは、次のコマンドの出力の形式です（テストでは exercises/data/hotspots/git_log.txt を使う）:
    git log --numstat --date=short --pretty=format:'--%h--%ad--%aN' --no-renames

    --663677a--2026-09-02--Alice          ← コミットの見出し: --<短い SHA>--<日付>--<作者>
    6	4	shop/billing/invoice.py         ← <追加行数>\\t<削除行数>\\t<パス>
    1	0	shop/notifications/email_templates.py
                                          ← コミットの間は空行
    --c3c95c1--2026-03-25--Carol
    -	-	assets/logo.png                ← バイナリファイルは行数の代わりに "-"

自分のリポジトリで試すには、上のコマンドの出力をファイルに保存して parse_log に渡します。

演習の構成:
    1-1 parse_log / churn           （★☆☆）ログの解析と、ファイルごとの変更量
    1-2 complexity / hotspots       （★★☆）複雑さ × 変更回数 = ホットスポット
    1-3 temporal_coupling           （★★☆）一緒に変更されるファイル（変更の結合）
"""
from __future__ import annotations

import ast  # noqa: F401  実装で使います
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class FileChange:
    path: str
    added: Optional[int]  # バイナリファイルなら None
    deleted: Optional[int]


@dataclass(frozen=True)
class Commit:
    sha: str
    date: date
    author: str
    changes: tuple[FileChange, ...]


@dataclass(frozen=True)
class Churn:
    revisions: int  # そのファイルを変更したコミットの数
    added: int  # 追加行数の合計（バイナリは 0 として数える）
    deleted: int


@dataclass(frozen=True)
class Hotspot:
    path: str
    revisions: int
    complexity: int
    score: int  # revisions × complexity


@dataclass(frozen=True)
class Coupling:
    a: str  # a < b（辞書順）
    b: str
    shared: int  # a と b の両方を変更したコミットの数
    degree: float  # shared / ((a の変更回数 + b の変更回数) / 2)


# ---------------------------------------------------------------------------
# 演習1-1（★☆☆）: ログの解析と変更量
# ---------------------------------------------------------------------------

def parse_log(text: str) -> list[Commit]:
    """上の形式のログを、出現順（git log なので新しい順）の Commit のリストにする。

    - "--" で始まる行がコミットの見出し。"--" を取り除いた残りを "--" で最大 2 回だけ分割し、
      SHA・日付（YYYY-MM-DD）・作者とする（作者名に "--" が含まれてもよいように）。
    - 見出しの後の、タブで区切られた 3 つの項目の行が変更（numstat）。行数が "-" なら None。
    - 空行は無視する。
    - 見出しより前に変更の行がある、項目の数が違う、行数が数字でも "-" でもない、日付が不正、
      などは ValueError（何行目かをメッセージに含めるとよい）。
    - 変更の行が 1 つもないコミット（マージコミットなど）も、changes が空のコミットとして含める。
    """
    raise NotImplementedError("演習1-1: parse_log を実装してください")


def churn(commits: Iterable[Commit], since: Optional[date] = None) -> dict[str, Churn]:
    """ファイルのパスごとの変更量を返す。since を指定したら、その日以降（その日を含む）のコミットだけを数える。"""
    raise NotImplementedError("演習1-1: churn を実装してください")


# ---------------------------------------------------------------------------
# 演習1-2（★★☆）: 複雑さとホットスポット
# ---------------------------------------------------------------------------

def complexity(source: str) -> int:
    """Python のソースコード全体の複雑さ = 1 + 分岐点の数。

    分岐点（ファイル全体のすべてのノードを数える。関数の中かどうかは問わない）:
        if / elif（If）、条件式（IfExp）、for / async for、while、except 節（ExceptHandler）、
        match の case（match_case）: 各 +1
        and / or（BoolOp）: 値の個数 − 1
        内包表記の for 節（comprehension）: 1 + その中の if の数
    構文エラーなら SyntaxError をそのまま送出してよい。

    メモ: 8.1 の演習の循環的複雑度を、ファイル単位に単純化したものです。
          ホットスポット分析では「相対的な大小」が分かれば十分で、行数を使うこともあります。
    """
    raise NotImplementedError("演習1-2: complexity を実装してください")


def hotspots(
    commits: Iterable[Commit],
    root: Path,
    since: Optional[date] = None,
    top: Optional[int] = None,
) -> list[Hotspot]:
    """ホットスポット（変更回数 × 複雑さ）を、score の降順（同点ならパスの昇順）で返す。

    - 対象は、churn(commits, since) に現れるファイルのうち、パスが ".py" で終わり、
      root の下に現在も存在するもの（削除されたファイル・Python 以外は除く）。
    - 構文エラーで解析できないファイルは除く。
    - top を指定したら、上位 top 件だけを返す。
    """
    raise NotImplementedError("演習1-2: hotspots を実装してください")


# ---------------------------------------------------------------------------
# 演習1-3（★★☆）: 変更の結合
# ---------------------------------------------------------------------------

def temporal_coupling(
    commits: Iterable[Commit],
    *,
    min_shared: int = 3,
    min_degree: float = 0.3,
    max_changeset_size: int = 30,
    since: Optional[date] = None,
) -> list[Coupling]:
    """一緒に変更されることが多いファイルの組を返す。

    - 対象のコミット: since 以降で、変更したファイル（重複を除く）の数が max_changeset_size 以下のもの。
      一括の整形のような巨大なコミットは、偶然の同時変更なので除く。
    - 各ファイルの変更回数と、各組（a < b）が同じコミットで変更された回数（shared）を、
      **対象のコミットだけで** 数える。
    - degree = shared / ((a の変更回数 + b の変更回数) / 2)
    - shared >= min_shared かつ degree >= min_degree の組だけを、
      degree の降順、shared の降順、a、b の昇順で返す。
    """
    raise NotImplementedError("演習1-3: temporal_coupling を実装してください")
