#!/usr/bin/env python3
"""教材の体裁チェック（執筆・メンテナンス用 / 標準ライブラリのみ）

使い方:
  python3 tools/lint_content.py              # リポジトリ全体をチェック
  python3 tools/lint_content.py 01-computer-systems   # 指定ディレクトリ配下のみ

チェック内容:
  - 章 README の必須見出し・タイトル形式・メタ情報（学習時間）の書式
  - 相対リンク切れ・リンク先の見出し（#アンカー）の有無（コードブロック内は除外）
  - コードフェンス・<details> の対応
  - Mermaid ブロックの典型的な構文ミス（未クォートのラベル内の括弧など）
  - GitHub の数式記法と衝突しやすい「$」の使い方
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent

CHAPTER_HEADINGS = [
    "## この章のゴール",
    "## なぜ学ぶのか",
    "## よくある落とし穴",
    "## 演習",
    "## 理解度チェック",
    "## さらに学ぶために",
    "## まとめ",
]
CTO_HEADING = "## CTOの視点"
# 「CTOの視点」を必須とする部（第14部は全体がCTOの仕事なので不要）
PARTS_REQUIRING_CTO_VIEW = {f"{n:02d}" for n in range(1, 14)}
# 章テンプレートの必須見出しを適用しない部（タイトルと学習時間はチェックする）
PARTS_WITHOUT_TEMPLATE = {"00", "15"}

TIME_RE = re.compile(r"本文\s*\d+(?:\.\d+)?\s*h\s*[+＋]\s*演習\s*\d+(?:\.\d+)?\s*h")
LINK_RE = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
INLINE_CODE_RE = re.compile(r"(`+)(.+?)\1")
FENCE_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
HEADING_RE = re.compile(r"^ {0,3}#{1,6}\s+(.+?)(?:\s+#+)?\s*$")
MERMAID_TYPES = (
    "flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram",
    "stateDiagram-v2", "erDiagram", "gantt", "pie", "journey", "mindmap",
    "timeline", "quadrantChart", "gitGraph", "xychart-beta", "block-beta",
    "sankey-beta", "requirementDiagram", "C4Context", "C4Container", "C4Component",
    "C4Dynamic", "C4Deployment", "architecture-beta", "packet-beta", "kanban",
)
# ノード形状 [..] {..} や、エッジラベル |..| の中に、クォートなしで括弧がある
MERMAID_UNQUOTED_PAREN_RE = re.compile(r"(\[|\{|\|)(?!\")([^\"\[\]{}|]*[()][^\"\[\]{}|]*)(\]|\}|\|)")
CURRENCY_RE = re.compile(r"(?<![\\\w])\$\d[\d,]*(?:\.\d+)?\s*(?:ドル|USD|[KMB]\b|万|億|千|/)")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, path: Path, line: int | None, msg: str) -> None:
        self.errors.append(f"{rel(path)}{':' + str(line) if line else ''}: {msg}")

    def warn(self, path: Path, line: int | None, msg: str) -> None:
        self.warnings.append(f"{rel(path)}{':' + str(line) if line else ''}: {msg}")


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def iter_markdown(targets: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for t in targets:
        if t.is_file() and t.suffix == ".md":
            files.add(t)
        elif t.is_dir():
            for p in t.rglob("*.md"):
                if any(part.startswith(".") or part == "node_modules" for part in p.relative_to(ROOT).parts):
                    continue
                files.add(p)
    return sorted(files)


def split_blocks(lines: list[str]):
    """(行番号, 行, フェンス内か, フェンスの言語) を順に返し、未閉鎖フェンスを検出する。"""
    in_fence = False
    fence_char = ""
    fence_len = 0
    lang = ""
    open_line = 0
    out = []
    for i, line in enumerate(lines, 1):
        m = FENCE_RE.match(line)
        if m:
            marker = m.group(2)
            if not in_fence:
                in_fence, fence_char, fence_len = True, marker[0], len(marker)
                lang = m.group(3).strip().split(" ")[0] if m.group(3).strip() else ""
                open_line = i
                out.append((i, line, False, ""))
                continue
            if marker[0] == fence_char and len(marker) >= fence_len and not m.group(3).strip():
                in_fence = False
                out.append((i, line, False, ""))
                continue
        out.append((i, line, in_fence, lang if in_fence else ""))
    unclosed = open_line if in_fence else 0
    return out, unclosed


def slugify(heading: str) -> str:
    """GitHub が見出しに付けるアンカー名（小文字化し、文字・数字・-・_ 以外を除き、空白を - にする）"""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    text = re.sub(r"<[^>]+>", "", text).replace("`", "").replace("*", "")
    out = []
    for ch in text.lower():
        if ch == " ":
            out.append("-")
        elif ch in "-_" or unicodedata.category(ch)[0] in "LMN":
            out.append(ch)
    return "".join(out)


_ANCHOR_CACHE: dict[Path, set[str]] = {}


def heading_anchors(path: Path) -> set[str]:
    if path not in _ANCHOR_CACHE:
        lines = path.read_text(encoding="utf-8").splitlines()
        seen: dict[str, int] = {}
        anchors: set[str] = set()
        for _, line, in_fence, _ in split_blocks(lines)[0]:
            m = HEADING_RE.match(line)
            if in_fence or not m:
                continue
            slug = slugify(m.group(1))
            count = seen.get(slug, 0)
            seen[slug] = count + 1
            anchors.add(slug if count == 0 else f"{slug}-{count}")  # 同名の見出しには -1, -2 … が付く
        anchors.update(re.findall(r"<a\s+(?:id|name)=\"([^\"]+)\"", "\n".join(lines)))
        _ANCHOR_CACHE[path] = anchors
    return _ANCHOR_CACHE[path]


def check_links(path: Path, blocks, report: Report) -> None:
    for i, line, in_fence, _ in blocks:
        if in_fence:
            continue
        text = INLINE_CODE_RE.sub("", line)
        for m in LINK_RE.finditer(text):
            target = m.group(1)
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                continue
            target_path, _, fragment = target.split("?", 1)[0].partition("#")
            resolved = (path.parent / target_path).resolve() if target_path else path
            if not resolved.exists():
                report.error(path, i, f"リンク切れ: {target}")
                continue
            if resolved.is_dir():
                resolved = resolved / "README.md"
            if fragment and resolved.suffix == ".md" and resolved.exists():
                if unquote(fragment) not in heading_anchors(resolved):
                    report.error(path, i, f"リンク先に見出し（アンカー）がありません: {target}")


def check_details(path: Path, blocks, report: Report) -> None:
    opens = closes = 0
    for idx, (i, line, in_fence, _) in enumerate(blocks):
        if in_fence:
            continue
        text = INLINE_CODE_RE.sub("", line)
        opens += len(re.findall(r"<details\b", text))
        closes += len(re.findall(r"</details>", text))
        stripped = line.strip()
        # GitHub では、<summary> の直後と </details> の直前に空行がないと中の Markdown が描画されない
        if stripped.endswith("</summary>") and idx + 1 < len(blocks):
            nxt = blocks[idx + 1][1].strip()
            if nxt and nxt != "</details>":
                report.error(path, i, "</summary> の次の行は空行にしてください（中の Markdown が描画されません）")
        if stripped == "</details>" and idx > 0:
            prev = blocks[idx - 1][1].strip()
            if prev and not prev.endswith("</summary>"):
                report.error(path, i, "</details> の前の行は空行にしてください（中の Markdown が描画されません）")
    if opens != closes:
        report.error(path, None, f"<details> の開始({opens})と終了({closes})の数が一致しません")


def check_mermaid(path: Path, blocks, report: Report) -> None:
    current_start = None
    first_line_checked = False
    for i, line, in_fence, lang in blocks:
        if in_fence and lang == "mermaid":
            if current_start is None:
                current_start = i
                first_line_checked = False
            stripped = line.strip()
            if not first_line_checked and stripped and not stripped.startswith("%%"):
                first_line_checked = True
                head = stripped.split()[0]
                if head not in MERMAID_TYPES:
                    report.error(path, i, f"Mermaid: 未知の図の種類 '{head}'")
            if MERMAID_UNQUOTED_PAREN_RE.search(line):
                report.error(path, i, "Mermaid: ラベル内の括弧はダブルクォートで囲んでください（例: A[\"説明 (補足)\"]）")
        else:
            current_start = None


def check_dollar(path: Path, blocks, report: Report) -> None:
    for i, line, in_fence, _ in blocks:
        if in_fence:
            continue
        text = INLINE_CODE_RE.sub("", line)
        if CURRENCY_RE.search(text):
            report.warn(path, i, "「$」+数字は GitHub で数式と解釈されることがあります。金額は「100ドル」「USD 100」と書いてください")


def chapter_info(path: Path):
    """章 README なら (部番号, 章番号) を返す。"""
    try:
        parts = path.relative_to(ROOT).parts
    except ValueError:
        return None
    if len(parts) == 3 and parts[2] == "README.md":
        pm = re.match(r"^(\d\d)-", parts[0])
        cm = re.match(r"^(\d\d)-", parts[1])
        if pm and cm:
            return pm.group(1), cm.group(1)
    return None


def check_chapter(path: Path, lines: list[str], blocks, part: str, chap: str, report: Report) -> None:
    title = lines[0] if lines else ""
    expected_prefix = f"# {int(part)}.{int(chap)} "
    if not title.startswith(expected_prefix):
        report.error(path, 1, f"タイトルは「{expected_prefix}…」で始めてください（現在: {title[:40]!r}）")
    if not any("学習時間の目安" in line and TIME_RE.search(line) for line in lines[:40]):
        report.error(path, None, "メタ情報表に「学習時間の目安 | 本文 Xh ＋ 演習 Yh」がありません")
    if part not in PARTS_WITHOUT_TEMPLATE:
        headings = {line.strip() for _, line, in_fence, _ in blocks if not in_fence and line.startswith("## ")}
        required = list(CHAPTER_HEADINGS)
        if part in PARTS_REQUIRING_CTO_VIEW:
            required.insert(3, CTO_HEADING)
        for h in required:
            if h not in headings:
                report.error(path, None, f"必須見出しがありません: {h}")
    ex_dir = path.parent / "exercises"
    if ex_dir.is_dir():
        if not any(ex_dir.glob("test_*.py")):
            report.warn(path, None, "exercises/ に test_*.py がありません")
        if not (path.parent / "solutions").is_dir():
            report.error(path, None, "exercises/ があるのに solutions/ がありません")


def main(argv: list[str]) -> int:
    targets = [ROOT / a if not Path(a).is_absolute() else Path(a) for a in argv] or [ROOT]
    for t in targets:
        if not t.exists():
            print(f"見つかりません: {t}")
            return 2
    report = Report()
    files = iter_markdown(targets)
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        blocks, unclosed = split_blocks(lines)
        if unclosed:
            report.error(path, unclosed, "コードフェンスが閉じられていません")
        check_links(path, blocks, report)
        check_details(path, blocks, report)
        check_mermaid(path, blocks, report)
        check_dollar(path, blocks, report)
        info = chapter_info(path)
        if info:
            check_chapter(path, lines, blocks, info[0], info[1], report)

    for w in report.warnings:
        print(f"WARN  {w}")
    for e in report.errors:
        print(f"ERROR {e}")
    print(f"\n{len(files)} ファイルをチェック: エラー {len(report.errors)} 件 / 警告 {len(report.warnings)} 件")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
