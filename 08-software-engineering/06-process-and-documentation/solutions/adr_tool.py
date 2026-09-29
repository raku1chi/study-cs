"""8.6 開発プロセスとドキュメンテーション — 解答例: ADR（アーキテクチャ決定記録）の管理ツール

仕様は exercises/adr_tool.py の docstring を参照してください。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

STATUSES = ("提案中", "承認済み", "却下", "非推奨", "置き換え済み")
FILENAME_RE = re.compile(r"(\d{4})-.*\.md")
STATUS_HEADING = "## ステータス"

TEMPLATE = """# {number}. {title}

- 日付: {day}

## ステータス

{status}

## コンテキスト

（この決定が必要になった背景、制約、検討した選択肢を書く）

## 決定

（何をするか。「〜する」と能動態で書く）

## 結果

（この決定によって、何が容易になり、何が困難になるか。良い面も悪い面も書く）
"""


@dataclass(frozen=True)
class AdrInfo:
    number: int
    title: str
    status: str
    path: Path


def slugify(title: str) -> str:
    words = re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKC", title).lower())
    return "-".join(words) or "decision"


def _adr_files(directory: Path) -> dict[int, Path]:
    directory = Path(directory)
    if not directory.is_dir():
        return {}
    files = {}
    for path in directory.iterdir():
        m = FILENAME_RE.fullmatch(path.name)
        if m and path.is_file():
            files[int(m.group(1))] = path
    return files


def _check_status(status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"ステータスは {STATUSES} のいずれかにしてください: {status!r}")


def new_adr(
    directory: Path, title: str, *, on: date, status: str = "提案中", slug: Optional[str] = None
) -> Path:
    title = title.strip()
    if not title:
        raise ValueError("タイトルが空です")
    _check_status(status)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    number = max(_adr_files(directory), default=0) + 1  # 欠番は埋めない（番号は一度使ったら再利用しない）
    path = directory / f"{number:04d}-{slug or slugify(title)}.md"
    path.write_text(TEMPLATE.format(number=number, title=title, day=on.isoformat(), status=status), encoding="utf-8")
    return path


def _parse(number: int, path: Path) -> AdrInfo:
    lines = path.read_text(encoding="utf-8").splitlines()
    prefix = f"# {number}. "
    title = lines[0][len(prefix):] if lines and lines[0].startswith(prefix) else ""
    return AdrInfo(number, title, _status_line(lines)[1], path)


def _status_line(lines: list[str]) -> tuple[int, str]:
    """(ステータスの行の番号, ステータス) を返す。"""
    start = lines.index(STATUS_HEADING)
    for i in range(start + 1, len(lines)):
        if lines[i].strip():
            return i, lines[i].strip()
    raise ValueError("ステータスがありません")


def list_adrs(directory: Path) -> list[AdrInfo]:
    return [_parse(n, p) for n, p in sorted(_adr_files(directory).items())]


def _rewrite_status(path: Path, status: str, link: Optional[str] = None) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    i, _ = _status_line(lines)
    replacement = [status] if link is None else [status, "", link]
    lines[i:i + 1] = replacement
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_status(directory: Path, number: int, status: str) -> None:
    _check_status(status)
    files = _adr_files(directory)
    if number not in files:
        raise KeyError(number)
    _rewrite_status(files[number], status)


def supersede(directory: Path, old_number: int, new_title: str, *, on: date, slug: Optional[str] = None) -> Path:
    files = _adr_files(directory)
    if old_number not in files:
        raise KeyError(old_number)
    old = _parse(old_number, files[old_number])
    if old.status == "置き換え済み":
        raise ValueError(f"ADR-{old_number:04d} はすでに置き換えられています")
    new_path = new_adr(directory, new_title, on=on, status="承認済み", slug=slug)
    new = _parse(int(new_path.name[:4]), new_path)
    # 双方向にリンクを張る: 新しい ADR から古い ADR へ、古い ADR から新しい ADR へ
    _rewrite_status(new_path, "承認済み", f"置き換え元: [ADR-{old.number:04d} {old.title}]({old.path.name})")
    _rewrite_status(old.path, "置き換え済み", f"置き換え先: [ADR-{new.number:04d} {new.title}]({new_path.name})")
    return new_path
