#!/usr/bin/env python3
"""章一覧と進捗チェックリストを生成する（教材メンテナンス用 / 標準ライブラリのみ）

使い方:
  python3 tools/build_index.py          # README.md の章一覧と PROGRESS.md を更新
  python3 tools/build_index.py --check  # 生成結果が最新かどうかだけを確認（差分があれば終了コード 1）

各部の README.md の 1 行目（# 第N部 タイトル）と、各章の README.md の
1 行目（# N.M タイトル）とメタ情報表（学習時間の目安 | 本文 Xh ＋ 演習 Yh）を読み取ります。
PROGRESS.md のチェック済みの項目（- [x]）は、再生成しても保持されます。
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
PROGRESS = ROOT / "PROGRESS.md"
BEGIN = "<!-- BEGIN:CURRICULUM（この範囲は tools/build_index.py が自動生成します） -->"
END = "<!-- END:CURRICULUM -->"

PART_TITLE_RE = re.compile(r"^#\s*第(\d+)部\s+(.+?)\s*$")
CHAPTER_TITLE_RE = re.compile(r"^#\s*(\d+)\.(\d+)\s+(.+?)\s*$")
TIME_RE = re.compile(r"本文\s*(\d+(?:\.\d+)?)\s*h\s*[+＋]\s*演習\s*(\d+(?:\.\d+)?)\s*h")
STAGES = [
    ("Stage I 基礎", range(1, 6)),
    ("Stage II 応用", range(6, 13)),
    ("Stage III リーダーシップ", range(13, 16)),
]


@dataclass
class Chapter:
    number: str
    title: str
    path: Path
    read_h: float
    exercise_h: float
    has_code: bool

    @property
    def hours(self) -> float:
        return self.read_h + self.exercise_h


@dataclass
class Part:
    number: int
    title: str
    path: Path
    chapters: list[Chapter] = field(default_factory=list)

    @property
    def hours(self) -> float:
        return sum(c.hours for c in self.chapters)


def fmt_hours(h: float) -> str:
    return f"{h:g}h"


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_parts() -> list[Part]:
    parts: list[Part] = []
    for part_dir in sorted(ROOT.glob("[0-9][0-9]-*")):
        number = int(part_dir.name[:2])
        if number == 0 or not part_dir.is_dir():
            continue
        readme = part_dir / "README.md"
        title = part_dir.name
        if readme.exists():
            m = PART_TITLE_RE.match(readme.read_text(encoding="utf-8").splitlines()[0])
            if m:
                title = m.group(2)
        part = Part(number, title, readme)
        for chap_dir in sorted(part_dir.glob("[0-9][0-9]-*")):
            chap_readme = chap_dir / "README.md"
            if not chap_readme.exists():
                continue
            lines = chap_readme.read_text(encoding="utf-8").splitlines()
            m = CHAPTER_TITLE_RE.match(lines[0]) if lines else None
            if not m:
                print(f"警告: タイトル行を読めません: {rel(chap_readme)}", file=sys.stderr)
                continue
            read_h = exercise_h = 0.0
            for line in lines[:40]:
                t = TIME_RE.search(line)
                if "学習時間の目安" in line and t:
                    read_h, exercise_h = float(t.group(1)), float(t.group(2))
                    break
            else:
                print(f"警告: 学習時間を読めません: {rel(chap_readme)}", file=sys.stderr)
            has_code = any((chap_dir / "exercises").glob("test_*.py"))
            part.chapters.append(
                Chapter(f"{m.group(1)}.{m.group(2)}", m.group(3), chap_readme, read_h, exercise_h, has_code)
            )
        parts.append(part)
    return parts


def render_curriculum(parts: list[Part]) -> str:
    total = sum(p.hours for p in parts)
    n_chapters = sum(len(p.chapters) for p in parts)
    n_code = sum(c.has_code for p in parts for c in p.chapters)
    out = [
        BEGIN,
        "",
        f"全 {len(parts)} 部・{n_chapters} 章（コード演習付き {n_code} 章）、学習時間の目安は合計 **約 {total:,.0f} 時間** です"
        "（本文と演習のみ。推薦図書による深掘りは含みません）。",
        "",
    ]
    for stage_name, numbers in STAGES:
        stage_parts = [p for p in parts if p.number in numbers]
        if not stage_parts:
            continue
        stage_hours = sum(p.hours for p in stage_parts)
        out += [f"### {stage_name}（約 {stage_hours:,.0f} 時間）", ""]
        for p in stage_parts:
            link = f"[第{p.number}部 {p.title}]({rel(p.path)})" if p.path.exists() else f"第{p.number}部 {p.title}"
            out += [f"**{link}** — 約 {p.hours:,.0f} 時間", "", "| 章 | タイトル | 学習時間 | 演習 |", "|---|---|---|---|"]
            for c in p.chapters:
                kind = "コード" if c.has_code else "記述"
                out.append(
                    f"| {c.number} | [{c.title}]({rel(c.path)}) | "
                    f"{fmt_hours(c.read_h)} ＋ {fmt_hours(c.exercise_h)} | {kind} |"
                )
            out.append("")
    out.append(END)
    return "\n".join(out)


def render_progress(parts: list[Part]) -> str:
    out = [
        "# 学習の進捗",
        "",
        "自分のリポジトリ（fork）でこのファイルを編集し、終わった項目を `- [ ]` から `- [x]` に変えて進捗を記録しましょう。",
        "演習の合格状況は `python3 tools/check.py` でいつでも確認できます。",
        "",
        "各章の完了の目安:",
        "",
        "1. 本文を読み、本文中のコード例を実際に動かした",
        "2. 演習のテストがすべて合格した（記述演習は解答例と見比べて振り返った）",
        "3. 理解度チェックの問題に、解答を見ずに答えられた",
        "",
        "> このファイルは `tools/build_index.py` で再生成できます（チェック済みの項目は保持されます）。",
        "",
    ]
    for stage_name, numbers in STAGES:
        stage_parts = [p for p in parts if p.number in numbers]
        if not stage_parts:
            continue
        out += [f"## {stage_name}", ""]
        for p in stage_parts:
            out += [f"### 第{p.number}部 {p.title}", ""]
            for c in p.chapters:
                out.append(f"- [ ] **{c.number} {c.title}**（{fmt_hours(c.hours)}）")
                out.append(f"  - [ ] {c.number} 本文とコード例")
                if c.has_code:
                    out.append(f"  - [ ] {c.number} 演習（`python3 tools/check.py {c.number}`）")
                else:
                    out.append(f"  - [ ] {c.number} 記述演習")
                out.append(f"  - [ ] {c.number} 理解度チェック")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def carry_over_checks(new_text: str, old_text: str) -> str:
    """古い PROGRESS.md でチェック済みだった項目を、新しい内容にも反映する。"""
    checked = {
        line.strip()[len("- [x] "):]
        for line in old_text.splitlines()
        if line.strip().lower().startswith("- [x] ")
    }
    lines = []
    for line in new_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ] ") and stripped[len("- [ ] "):] in checked:
            line = line.replace("- [ ] ", "- [x] ", 1)
        lines.append(line)
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    check_only = "--check" in argv
    parts = load_parts()

    readme_text = README.read_text(encoding="utf-8")
    start, end = readme_text.find(BEGIN), readme_text.find(END)
    if start < 0 or end < 0:
        print("README.md に生成範囲のマーカーがありません", file=sys.stderr)
        return 2
    new_readme = readme_text[:start] + render_curriculum(parts) + readme_text[end + len(END):]

    new_progress = render_progress(parts)
    if PROGRESS.exists():
        new_progress = carry_over_checks(new_progress, PROGRESS.read_text(encoding="utf-8"))

    changed = []
    if new_readme != readme_text:
        changed.append("README.md")
    if not PROGRESS.exists() or PROGRESS.read_text(encoding="utf-8") != new_progress:
        changed.append("PROGRESS.md")

    if check_only:
        if changed:
            print("更新が必要です: " + ", ".join(changed))
            return 1
        print("最新です")
        return 0

    README.write_text(new_readme, encoding="utf-8")
    PROGRESS.write_text(new_progress, encoding="utf-8")
    n = sum(len(p.chapters) for p in parts)
    print(f"{len(parts)} 部・{n} 章から生成しました: " + (", ".join(changed) if changed else "変更なし"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
