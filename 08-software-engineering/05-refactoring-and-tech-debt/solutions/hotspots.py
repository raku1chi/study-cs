"""8.5 リファクタリングと技術的負債 — 解答例: ホットスポットと変更の結合の分析

仕様は exercises/hotspots.py の docstring を参照してください。
"""
from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
from datetime import date
from itertools import combinations
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class FileChange:
    path: str
    added: Optional[int]
    deleted: Optional[int]


@dataclass(frozen=True)
class Commit:
    sha: str
    date: date
    author: str
    changes: tuple[FileChange, ...]


@dataclass(frozen=True)
class Churn:
    revisions: int
    added: int
    deleted: int


@dataclass(frozen=True)
class Hotspot:
    path: str
    revisions: int
    complexity: int
    score: int


@dataclass(frozen=True)
class Coupling:
    a: str
    b: str
    shared: int
    degree: float


# ---------------------------------------------------------------------------
# 演習1-1: ログの解析と変更量
# ---------------------------------------------------------------------------

def _count(field: str, lineno: int) -> Optional[int]:
    if field == "-":
        return None  # バイナリファイル
    if not field.isdigit():
        raise ValueError(f"{lineno} 行目: 追加・削除の行数が不正です: {field!r}")
    return int(field)


def parse_log(text: str) -> list[Commit]:
    commits: list[Commit] = []
    header: Optional[tuple[str, date, str]] = None
    changes: list[FileChange] = []

    def flush() -> None:
        if header is not None:
            commits.append(Commit(*header, tuple(changes)))

    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        if line.startswith("--"):
            flush()
            parts = line[2:].split("--", 2)  # 作者名に "--" が含まれても壊れないように、分割は 2 回まで
            if len(parts) != 3:
                raise ValueError(f"{lineno} 行目: コミットの見出しの形式が不正です: {line!r}")
            sha, day, author = parts
            try:
                parsed_day = date.fromisoformat(day)
            except ValueError:
                raise ValueError(f"{lineno} 行目: 日付が不正です: {day!r}") from None
            header, changes = (sha, parsed_day, author), []
            continue
        fields = line.split("\t")
        if header is None or len(fields) != 3 or not fields[2]:
            raise ValueError(f"{lineno} 行目: numstat の行として解釈できません: {line!r}")
        changes.append(FileChange(fields[2], _count(fields[0], lineno), _count(fields[1], lineno)))
    flush()
    return commits


def _in_window(commit: Commit, since: Optional[date]) -> bool:
    return since is None or commit.date >= since


def churn(commits: Iterable[Commit], since: Optional[date] = None) -> dict[str, Churn]:
    revisions: Counter = Counter()
    added: Counter = Counter()
    deleted: Counter = Counter()
    for commit in commits:
        if not _in_window(commit, since):
            continue
        for change in commit.changes:
            revisions[change.path] += 1
            added[change.path] += change.added or 0
            deleted[change.path] += change.deleted or 0
    return {path: Churn(revisions[path], added[path], deleted[path]) for path in revisions}


# ---------------------------------------------------------------------------
# 演習1-2: 複雑さとホットスポット
# ---------------------------------------------------------------------------

def complexity(source: str) -> int:
    decisions = 0
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.match_case)):
            decisions += 1
        elif isinstance(node, ast.BoolOp):
            decisions += len(node.values) - 1
        elif isinstance(node, ast.comprehension):
            decisions += 1 + len(node.ifs)
    return 1 + decisions


def hotspots(
    commits: Iterable[Commit],
    root: Path,
    since: Optional[date] = None,
    top: Optional[int] = None,
) -> list[Hotspot]:
    result = []
    for path, c in churn(commits, since).items():
        file = Path(root) / path
        if not path.endswith(".py") or not file.is_file():
            continue  # 削除済みのファイルや、Python 以外のファイルは対象外
        try:
            cx = complexity(file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        result.append(Hotspot(path, c.revisions, cx, c.revisions * cx))
    result.sort(key=lambda h: (-h.score, h.path))
    return result[:top] if top is not None else result


# ---------------------------------------------------------------------------
# 演習1-3: 変更の結合（一緒に変わるファイル）
# ---------------------------------------------------------------------------

def temporal_coupling(
    commits: Iterable[Commit],
    *,
    min_shared: int = 3,
    min_degree: float = 0.3,
    max_changeset_size: int = 30,
    since: Optional[date] = None,
) -> list[Coupling]:
    revisions: Counter = Counter()
    shared: Counter = Counter()
    for commit in commits:
        paths = sorted({c.path for c in commit.changes})
        # 一括の整形やライセンス表記の変更のような巨大なコミットは、偶然の同時変更なので除く
        if not _in_window(commit, since) or len(paths) > max_changeset_size:
            continue
        revisions.update(paths)
        shared.update(combinations(paths, 2))
    couplings = []
    for (a, b), n in shared.items():
        degree = n / ((revisions[a] + revisions[b]) / 2)
        if n >= min_shared and degree >= min_degree:
            couplings.append(Coupling(a, b, n, degree))
    couplings.sort(key=lambda c: (-c.degree, -c.shared, c.a, c.b))
    return couplings
