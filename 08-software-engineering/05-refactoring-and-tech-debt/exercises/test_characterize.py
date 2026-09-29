"""8.5 演習3 — 承認テスト（ゴールデンマスター）のテスト

実行: python3 tools/check.py 8.5   （またはこのディレクトリで python3 -m unittest -v test_characterize）

exercises/data/characterize/shipping_fee.approved.json は、legacy_shipping.shipping_fee の
現在の振る舞い（72 ケース）を記録して「承認」したファイルです。
"""
import itertools
import json
import math
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from characterize import (
    Verification,
    approve,
    combinations,
    received_path_for,
    run_cases,
    serialize,
    to_jsonable,
    verify,
)
from legacy_shipping import shipping_fee

APPROVED = Path(__file__).parent / "data" / "characterize" / "shipping_fee.approved.json"
# combinations(weight_g=..., prefecture=..., express=..., member=...) と同じ入力
# （スタブのままでもテストを読み込めるよう、ここでは itertools で作る）
INPUTS = list(itertools.product(
    [1, 2000, 2001, 3000, 3001, 5500],
    ["東京都", "北海道", "沖縄県"],
    [False, True],
    [False, True],
))


def refactored_shipping_fee(weight_g, prefecture, express=False, member=False):
    """「読みやすく書き直した」つもりの版。重量の追加料金の計算が、旧実装と微妙に違う。"""
    if weight_g <= 0:
        raise ValueError("weight_g must be positive")
    base = {"沖縄県": 1200, "北海道": 900}.get(prefecture, 600)
    if weight_g > 2000:
        base += math.ceil((weight_g - 2000) / 1000) * 200
    if express:
        if prefecture == "沖縄県":
            raise ValueError("沖縄県への速達は受け付けていません")
        base = base * 3 // 2
    if member and not express:
        base -= 100
    return base


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)


class TestBuildingBlocks(unittest.TestCase):
    def test_to_jsonable(self):
        self.assertEqual(to_jsonable({"a": (1, 2), 3: None}), {"a": [1, 2], "3": None})
        self.assertEqual(to_jsonable([1.5, float("nan"), float("inf"), -float("inf")]), [1.5, "nan", "inf", "-inf"])
        self.assertEqual(to_jsonable({"b", "a", "c"}), ["a", "b", "c"])
        self.assertEqual(to_jsonable(frozenset({3, 1, 2})), [1, 2, 3])
        self.assertEqual(to_jsonable(Decimal("1.10")), "Decimal('1.10')")
        self.assertEqual(to_jsonable(True), True)
        nested = to_jsonable({"k": [{1, 2}, ("x", {"y": Decimal("0")})]})
        self.assertEqual(nested, {"k": [[1, 2], ["x", {"y": "Decimal('0')"}]]})
        json.dumps(nested)  # JSON にできること

    def test_set_order_does_not_depend_on_iteration_order(self):
        values = {f"item-{i}" for i in range(50)}
        self.assertEqual(to_jsonable(values), sorted(values))

    def test_combinations(self):
        self.assertEqual(combinations(weight=[1, 5], express=[False, True]),
                         [(1, False), (1, True), (5, False), (5, True)])
        self.assertEqual(
            combinations(weight_g=[1, 2000, 2001, 3000, 3001, 5500], prefecture=["東京都", "北海道", "沖縄県"],
                         express=[False, True], member=[False, True]),
            INPUTS,
        )
        self.assertEqual(combinations(), [()])

    def test_run_cases_records_outputs_and_errors(self):
        cases = run_cases(shipping_fee, [(1, "東京都", False, False), (1, "沖縄県", True, False), (0, "東京都")])
        self.assertEqual(cases[0], {"input": [1, "東京都", False, False], "output": 600})
        self.assertEqual(cases[1], {"input": [1, "沖縄県", True, False], "error": "ValueError: 沖縄県への速達は受け付けていません"})
        self.assertEqual(cases[2]["error"], "ValueError: weight_g must be positive")

    def test_serialize_format(self):
        cases = [{"output": 600, "input": [1, "東京都"]}, {"input": [2], "error": "ValueError: x"}]
        self.assertEqual(
            serialize(cases),
            '[\n{"input": [1, "東京都"], "output": 600},\n{"error": "ValueError: x", "input": [2]}\n]\n',
        )
        self.assertEqual(serialize([]), "[]\n")

    def test_scrubbers(self):
        cases = [{"input": [1], "output": {"created_at": "2026-09-28T12:34:56+00:00", "id": "ord_8f3a"}}]
        text = serialize(cases, scrubbers=[(r"\d{4}-\d{2}-\d{2}T[0-9:+.]+", "<TIMESTAMP>"), (r"ord_[0-9a-f]+", "<ID>")])
        self.assertEqual(text, '[\n{"input": [1], "output": {"created_at": "<TIMESTAMP>", "id": "<ID>"}}\n]\n')

    def test_received_path(self):
        self.assertEqual(received_path_for(Path("d/fee.approved.json")), Path("d/fee.received.json"))
        with self.assertRaises(ValueError):
            received_path_for(Path("d/fee.json"))


class TestGoldenMaster(TempDirTestCase):
    def copy_approved(self):
        path = self.dir / "shipping_fee.approved.json"
        shutil.copy(APPROVED, path)
        return path

    def test_legacy_code_matches_the_committed_golden_master(self):
        approved = self.copy_approved()
        result = verify(shipping_fee, INPUTS, approved)
        self.assertIsInstance(result, Verification)
        self.assertTrue(result.ok, result.message + "\n" + result.diff)
        self.assertEqual((result.diff, result.received_path), ("", None))
        self.assertFalse((self.dir / "shipping_fee.received.json").exists())

    def test_committed_file_is_exactly_the_serialized_output(self):
        self.assertEqual(serialize(run_cases(shipping_fee, INPUTS)), APPROVED.read_text(encoding="utf-8"))

    def test_behavior_change_produces_a_readable_diff(self):
        approved = self.copy_approved()
        result = verify(refactored_shipping_fee, INPUTS, approved)
        self.assertFalse(result.ok)
        self.assertEqual(result.received_path, self.dir / "shipping_fee.received.json")
        self.assertTrue(result.received_path.exists())
        self.assertIn("--- shipping_fee.approved.json", result.diff)
        self.assertIn("+++ shipping_fee.received.json", result.diff)
        self.assertIn('-{"input": [3000, "東京都", false, false], "output": 1000},', result.diff)
        self.assertIn('+{"input": [3000, "東京都", false, false], "output": 800},', result.diff)
        changed = [line for line in result.diff.splitlines() if line.startswith("-{") or line.startswith("+{")]
        self.assertEqual(len(changed), 20, "変わったのは 3000g の 10 ケースだけ（削除 10 行 + 追加 10 行）")
        self.assertTrue(all('[3000,' in line for line in changed))
        self.assertEqual(APPROVED.read_text(encoding="utf-8"), approved.read_text(encoding="utf-8"),
                         "承認済みのファイルは書き換えない")


class TestApprovalWorkflow(TempDirTestCase):
    def test_first_run_then_approve_then_pass(self):
        approved = self.dir / "fee.approved.json"
        first = verify(shipping_fee, INPUTS[:6], approved)
        self.assertFalse(first.ok)
        self.assertFalse(approved.exists())
        self.assertTrue(first.received_path.exists())
        self.assertTrue(first.diff.startswith("--- fee.approved.json"))
        self.assertEqual(sum(1 for line in first.diff.splitlines() if line.startswith("+{")), 6)
        approve(approved)
        self.assertTrue(approved.exists())
        self.assertFalse(first.received_path.exists(), "承認したら received は approved になる")
        self.assertTrue(verify(shipping_fee, INPUTS[:6], approved).ok)

    def test_stale_received_file_is_removed_on_success(self):
        approved = self.dir / "fee.approved.json"
        approved.write_text(serialize(run_cases(shipping_fee, INPUTS[:4])), encoding="utf-8")
        received = self.dir / "fee.received.json"
        received.write_text("古い失敗の記録", encoding="utf-8")
        self.assertTrue(verify(shipping_fee, INPUTS[:4], approved).ok)
        self.assertFalse(received.exists())

    def test_approve_without_received_file(self):
        with self.assertRaises(FileNotFoundError):
            approve(self.dir / "nothing.approved.json")

    def test_scrubbers_make_nondeterministic_output_verifiable(self):
        counter = {"n": 0}

        def create_order(amount):
            counter["n"] += 1
            created = datetime(2026, 9, 28, tzinfo=timezone.utc) + timedelta(seconds=counter["n"])
            return {"amount": amount, "created_at": created.isoformat(), "id": f"ord_{counter['n']:04x}"}

        scrubbers = [(r"\d{4}-\d{2}-\d{2}T[0-9:+.]+", "<TIMESTAMP>"), (r"ord_[0-9a-f]+", "<ID>")]
        approved = self.dir / "orders.approved.json"
        self.assertFalse(verify(create_order, [(100,), (200,)], approved, scrubbers=scrubbers).ok)
        approve(approved)
        # 2 回目の実行では時刻も ID も変わるが、スクラブしているので一致する
        self.assertTrue(verify(create_order, [(100,), (200,)], approved, scrubbers=scrubbers).ok)
        self.assertFalse(verify(create_order, [(100,), (200,)], approved).ok, "スクラブしなければ毎回変わる")


if __name__ == "__main__":
    unittest.main()
