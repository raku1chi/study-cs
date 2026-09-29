#!/usr/bin/env python3
"""study-cs 演習テストランナー（Python 3.10+ / 標準ライブラリのみ）

使い方:
  python3 tools/check.py                    # すべての演習をテスト
  python3 tools/check.py 1                  # 第1部の演習をテスト
  python3 tools/check.py 1.1                # 1.1章の演習をテスト
  python3 tools/check.py 01-computer-systems/01-data-representation   # パス指定も可
  python3 tools/check.py -v 1.1             # unittest の詳細出力を表示
  python3 tools/check.py 3.4 -k TestStage1  # 名前に TestStage1 を含むテストだけを実行
  python3 tools/check.py --list             # 演習のある章の一覧
  python3 tools/check.py --solutions        # 解答例（solutions/）でテスト（教材の検証用）

各章の exercises/ にある test_*.py を unittest で実行し、合格したテスト数を表示します。
--solutions を付けると、exercises/ を一時ディレクトリへコピーし、solutions/ の
ファイルで上書きしてからテストします（学習者のファイルは変更しません）。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_PYTHON = (3, 10)
TIMEOUT_SEC = 300

RAN_RE = re.compile(r"^Ran (\d+) tests? in", re.M)
SUMMARY_RE = re.compile(r"^(OK|FAILED)(?: \((.*)\))?\s*$", re.M)
FAILED_ID_RE = re.compile(r"^(?:FAIL|ERROR): (\S+ \([^)]*\))", re.M)
LOAD_ERROR_MARKERS = (
    "unittest.loader._FailedTest",
    "Failed to import test module",
    "SyntaxError",
    "IndentationError",
)


@dataclass
class Result:
    chapter: Path
    ran: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    load_error: bool = False
    timed_out: bool = False
    output: str = ""
    failed_tests: int | None = None  # 失敗したテストメソッドの数（subTest による重複を除く）

    @property
    def passed(self) -> int:
        failed = self.failed_tests if self.failed_tests is not None else self.failures + self.errors
        return max(self.ran - failed - self.skipped, 0)

    @property
    def counted(self) -> int:
        return max(self.ran - self.skipped, 0)

    @property
    def ok(self) -> bool:
        return (
            not self.load_error
            and not self.timed_out
            and self.ran > 0
            and self.failures == 0
            and self.errors == 0
        )


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def all_chapters() -> list[Path]:
    """exercises/test_*.py を持つ章ディレクトリを列挙する。"""
    chapters = set()
    for ex_dir in ROOT.rglob("exercises"):
        if not ex_dir.is_dir():
            continue
        parts = ex_dir.relative_to(ROOT).parts
        if any(p.startswith(".") or p in ("solutions", "__pycache__") for p in parts):
            continue
        if any(ex_dir.glob("test_*.py")):
            chapters.add(ex_dir.parent)
    return sorted(chapters)


def resolve_target(target: str) -> Path | None:
    """'1' / '1.1' / パス のいずれかをディレクトリに解決する。"""
    m = re.fullmatch(r"(\d+)(?:\.(\d+))?", target.strip())
    if m:
        part_no = int(m.group(1))
        parts = sorted(ROOT.glob(f"{part_no:02d}-*"))
        if not parts:
            return None
        if m.group(2) is None:
            return parts[0]
        chapters = sorted(parts[0].glob(f"{int(m.group(2)):02d}-*"))
        return chapters[0] if chapters else None
    for base in (Path.cwd(), ROOT):
        candidate = (base / target).resolve()
        if candidate.exists():
            return candidate
    return None


def select_chapters(targets: list[str]) -> tuple[list[Path], bool]:
    """(テスト対象の章, 対象の指定に誤りがあったか) を返す。"""
    chapters = all_chapters()
    if not targets:
        return chapters, False
    selected: list[Path] = []
    had_error = False
    for t in targets:
        path = resolve_target(t)
        if path is None:
            print(f"⚠️  対象が見つかりません: {t}", file=sys.stderr)
            had_error = True
            continue
        if path.name in ("exercises", "solutions"):
            path = path.parent
        matched = [c for c in chapters if c == path or path in c.parents]
        if not matched:
            if (path / "README.md").exists():
                print(f"ℹ️  {rel(path)} には自動採点の演習（exercises/）はありません。取り組み方は章の本文を参照してください")
            else:
                print(f"⚠️  演習（exercises/test_*.py）がありません: {rel(path)}", file=sys.stderr)
                had_error = True
        selected.extend(m for m in matched if m not in selected)
    return selected, had_error


def prepare_solution_dir(chapter: Path, tmp_root: Path) -> Path:
    """exercises/ をコピーし、solutions/ のファイルで上書きしたディレクトリを返す。"""
    run_dir = tmp_root / "exercises"
    shutil.copytree(
        chapter / "exercises",
        run_dir,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    sol_dir = chapter / "solutions"
    if sol_dir.is_dir():
        for src in sol_dir.rglob("*"):
            if "__pycache__" in src.parts or not src.is_file():
                continue
            dst = run_dir / src.relative_to(sol_dir)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    return run_dir


def parse_output(result: Result, output: str) -> None:
    result.output = output
    ran = RAN_RE.findall(output)
    result.ran = int(ran[-1]) if ran else 0
    summary = SUMMARY_RE.findall(output)
    if summary:
        _, detail = summary[-1]
        for item in detail.split(","):
            if "=" not in item:
                continue
            key, value = item.strip().split("=", 1)
            if key == "failures":
                result.failures = int(value)
            elif key == "errors":
                result.errors = int(value)
            elif key == "skipped":
                result.skipped = int(value)
    result.load_error = any(marker in output for marker in LOAD_ERROR_MARKERS)
    # subTest の失敗は 1 つのテストメソッドにつき複数回数えられるので、テスト ID の重複を除いて数える
    failed_ids = set(FAILED_ID_RE.findall(output))
    if failed_ids:
        result.failed_tests = len(failed_ids)


def run_chapter(chapter: Path, use_solutions: bool, verbose: bool, patterns: list[str] | None = None) -> Result:
    result = Result(chapter)
    with tempfile.TemporaryDirectory(prefix="study-cs-") as tmp:
        run_dir = (
            prepare_solution_dir(chapter, Path(tmp)) if use_solutions else chapter / "exercises"
        )
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", ".", "-t", ".", "-p", "test_*.py"]
        if verbose:
            cmd.append("-v")
        for pattern in patterns or []:
            cmd += ["-k", pattern]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        try:
            proc = subprocess.run(
                cmd,
                cwd=run_dir,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=TIMEOUT_SEC,
            )
            parse_output(result, proc.stdout + proc.stderr)
        except subprocess.TimeoutExpired as exc:
            result.timed_out = True
            out = exc.stdout or ""
            err = exc.stderr or ""
            if isinstance(out, bytes):
                out = out.decode("utf-8", "replace")
            if isinstance(err, bytes):
                err = err.decode("utf-8", "replace")
            result.output = out + err
    return result


def summarize_failures(output: str, limit: int = 40) -> list[str]:
    """unittest の出力から「失敗したテスト名 — 例外メッセージ1行目」の一覧を作る。"""
    blocks = re.split(r"^={50,}$", output, flags=re.M)[1:]
    items: list[str] = []
    for block in blocks:
        lines = block.strip("\n").splitlines()
        if not lines:
            continue
        head = re.match(r"^(ERROR|FAIL): (\S+) \(([^)]*)\)", lines[0])
        if not head:
            continue
        name = head.group(3).split(".", 1)[-1] if "." in head.group(3) else head.group(2)
        message = ""
        for line in lines[2:]:
            if not line.strip() or line.startswith((" ", "\t", "Traceback")):
                continue
            if re.match(r"^-{50,}$", line):
                break
            message = line.strip()
            break
        if len(message) > 140:
            message = message[:137] + "..."
        items.append(f"✗ {name} — {message}" if message else f"✗ {name}")
    if len(items) > limit:
        items = items[:limit] + [f"…ほか {len(items) - limit} 件（-v で全件表示）"]
    return items


def bar(passed: int, total: int, width: int = 20) -> str:
    if total <= 0:
        return "·" * width
    filled = round(width * passed / total)
    return "█" * filled + "·" * (width - filled)


def status_icon(r: Result) -> str:
    if r.timed_out:
        return "⏱ "
    if r.load_error:
        return "⚠️ "
    if r.ok:
        return "✅"
    if r.passed == 0:
        return "⬜"
    return "🟡"


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < MIN_PYTHON:
        print(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 以上が必要です（現在: {sys.version.split()[0]}）")
        return 2

    parser = argparse.ArgumentParser(description="study-cs の演習テストを実行します。")
    parser.add_argument("targets", nargs="*", help="部・章の番号（例: 1, 1.1）またはパス")
    parser.add_argument("-v", "--verbose", action="store_true", help="unittest の詳細出力を表示する")
    parser.add_argument("--solutions", action="store_true", help="解答例でテストする（教材の検証用）")
    parser.add_argument("--list", action="store_true", help="演習のある章を一覧表示する")
    parser.add_argument(
        "-k", dest="patterns", action="append", metavar="PATTERN",
        help="名前にパターンを含むテストだけを実行する（unittest の -k と同じ。例: -k TestStage1）",
    )
    args = parser.parse_args(argv)

    chapters, had_error = select_chapters(args.targets)
    if args.list:
        for c in chapters:
            tests = sorted(p.name for p in (c / "exercises").glob("test_*.py"))
            print(f"{rel(c):55s} {', '.join(tests)}")
        return 0
    if not chapters:
        if had_error:
            print("テスト対象の章がありません。")
            return 1
        return 0

    mode = "解答例（solutions/）" if args.solutions else "あなたのコード（exercises/）"
    print(f"対象: {mode} / {len(chapters)}章\n")

    results: list[Result] = []
    for chapter in chapters:
        r = run_chapter(chapter, args.solutions, args.verbose, args.patterns)
        results.append(r)
        note = ""
        if r.timed_out:
            note = f"  タイムアウト（{TIMEOUT_SEC}秒）"
        elif r.load_error:
            note = "  テストの読み込みに失敗（構文エラー・import エラーを確認）"
        elif r.skipped:
            note = f"  （この環境ではスキップ: {r.skipped}）"
        print(f"{status_icon(r)} {rel(chapter):52s} {bar(r.passed, r.counted)} {r.passed:3d}/{r.counted:<3d}{note}")
        if args.verbose and r.output.strip():
            print("\n".join("    " + line for line in r.output.rstrip().splitlines()))
            print()
        elif not r.ok and (args.solutions or len(chapters) == 1):
            summary = summarize_failures(r.output)
            if summary and not r.load_error and not r.timed_out:
                print("\n".join("    " + line for line in summary))
            else:
                lines = r.output.rstrip().splitlines()
                if len(lines) > 60:
                    lines = ["...（先頭を省略）..."] + lines[-60:]
                print("\n".join("    " + line for line in lines))
            print()

    done = sum(r.ok for r in results)
    passed = sum(r.passed for r in results)
    total = sum(r.counted for r in results)
    print(f"\n完了した章: {done}/{len(results)}　合格したテスト: {passed}/{total}")
    if not args.verbose and done < len(results) and len(results) > 1:
        print("ヒント: 章を指定して実行すると失敗内容が表示されます（例: python3 tools/check.py 1.1）")
    return 0 if done == len(results) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:  # 出力を head などにパイプしたとき
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(1)
