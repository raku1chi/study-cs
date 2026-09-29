#!/usr/bin/env python3
"""演習の docstring の使用例を解答例で実行して確かめる（教材メンテナンス用 / 標準ライブラリのみ）

使い方:
  python3 tools/check_docstrings.py          # すべての章
  python3 tools/check_docstrings.py 1.1 6    # 章・部を指定（check.py と同じ指定方法）

各章の exercises/<module>.py（スタブ）の docstring にある `>>>` の例を、
solutions/<module>.py（解答例）の関数で実行し、書かれた結果と一致するかを確かめます。
スタブの説明と解答例の動作がずれていないかを検出するためのものです。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check  # noqa: E402  同じディレクトリの check.py の章の探索・準備を再利用する

# 1 章ぶんを別プロセスで実行するためのスクリプト（モジュールのキャッシュが章をまたいで混ざらないように）
WORKER = r"""
import doctest, importlib, importlib.util, json, sys
from pathlib import Path
run_dir, stub_dir = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(run_dir))
results = []


class LenientParser(doctest.DocTestParser):
    # doctest として解釈できない docstring（例: 衝突マーカー >>>>>>> を含む説明）は飛ばす

    skipped = []

    def get_doctest(self, string, globs, name, filename, lineno):
        try:
            return super().get_doctest(string, globs, name, filename, lineno)
        except ValueError as exc:
            LenientParser.skipped.append(f"{name}: {exc}")
            return super().get_doctest("", globs, name, filename, lineno)


for stub_path in sorted(stub_dir.glob("*.py")):
    name = stub_path.stem
    if name.startswith("test_") or not (run_dir / (name + ".py")).exists():
        continue
    try:
        solution = importlib.import_module(name)
        spec = importlib.util.spec_from_file_location("stub_" + name, stub_path)
        stub = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = stub  # dataclasses などはモジュールが登録済みであることを前提にする
        spec.loader.exec_module(stub)
    except Exception as exc:  # noqa: BLE001
        results.append({"module": name, "attempted": 0, "failed": 1, "detail": f"import に失敗: {exc!r}"})
        continue
    finder = doctest.DocTestFinder(parser=LenientParser())
    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE)
    details = []
    out = []
    for test in finder.find(stub, stub.__name__, globs=dict(vars(solution))):
        if not test.examples:
            continue
        runner.run(test, out=out.append)
    summary = runner.summarize(verbose=False)
    if summary.failed:
        details.append("".join(out)[-2000:])
    results.append({"module": name, "attempted": summary.attempted, "failed": summary.failed,
                    "detail": "\n".join(details), "skipped": list(LenientParser.skipped)})
    LenientParser.skipped.clear()
print(json.dumps(results, ensure_ascii=False))
"""


def main(argv: list[str]) -> int:
    chapters, had_error = check.select_chapters(argv)
    chapters = [c for c in chapters if (c / "solutions").is_dir()]
    total_attempted = total_failed = 0
    for chapter in chapters:
        with tempfile.TemporaryDirectory(prefix="study-cs-doc-") as tmp:
            run_dir = check.prepare_solution_dir(chapter, Path(tmp))
            proc = subprocess.run(
                [sys.executable, "-c", WORKER, str(run_dir), str(chapter / "exercises")],
                cwd=run_dir, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=check.TIMEOUT_SEC,
                env=dict(check.os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8"),
            )
        try:
            results = json.loads(proc.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            print(f"⚠️  {check.rel(chapter)}: 実行に失敗しました\n{proc.stderr[-2000:]}")
            total_failed += 1
            continue
        attempted = sum(r["attempted"] for r in results)
        failed = sum(r["failed"] for r in results)
        total_attempted += attempted
        total_failed += failed
        icon = "✅" if failed == 0 else "❌"
        print(f"{icon} {check.rel(chapter):55s} 例 {attempted:3d} 件 / 不一致 {failed}")
        for r in results:
            if r["failed"]:
                print(f"    {r['module']}: {r['detail']}")
            for skipped in r.get("skipped", []):
                print(f"    （doctest として解釈できないため飛ばしました）{skipped[:120]}")
    print(f"\n{len(chapters)} 章: docstring の例 {total_attempted} 件を実行、不一致 {total_failed} 件")
    return 1 if (total_failed or had_error) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
