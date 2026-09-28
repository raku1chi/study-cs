"""7.4 合意と協調 — Saga オーケストレーターのテスト

実行: python3 tools/check.py 7.4   （またはこのディレクトリで python3 -m unittest -v test_saga）

EC サイトの注文処理（在庫の引き当て → 決済 → 配送の手配 → 確認メール）を題材にします。
"""
import unittest

from saga import (
    COMPENSATED,
    COMPENSATING,
    COMPLETED,
    FAILED,
    RUNNING,
    InMemorySagaStore,
    RetryableError,
    SagaOrchestrator,
    SimulatedCrash,
    Step,
)


class OutOfStock(Exception):
    pass


class FakeServices:
    """各サービスの呼び出しを記録し、指定どおりに失敗する偽物。"""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail: dict[str, list] = {}  # 名前 → 送出する例外のリスト（先頭から順に使う）

    def op(self, name: str, result_key: str | None = None):
        def run(ctx: dict) -> None:
            self.calls.append(name)
            queue = self.fail.get(name)
            if queue:
                raise queue.pop(0)
            if result_key:
                ctx[result_key] = f"{name}-ok"

        return run


def order_steps(svc: FakeServices, payment_attempts: int = 3) -> list[Step]:
    return [
        Step("reserve", svc.op("reserve", "reservation_id"), svc.op("release")),
        Step("pay", svc.op("pay", "payment_id"), svc.op("refund"), max_attempts=payment_attempts),
        Step("ship", svc.op("ship", "shipment_id"), svc.op("cancel_shipment")),
        Step("email", svc.op("email")),  # 補償なし（最後のステップ）
    ]


class TestExercise7Saga(unittest.TestCase):
    def setUp(self):
        self.svc = FakeServices()
        self.store = InMemorySagaStore()
        self.saga = SagaOrchestrator(order_steps(self.svc), self.store)

    def test_all_steps_succeed(self):
        result = self.saga.start("order-1", {"order_id": 1})
        self.assertEqual(result.status, COMPLETED)
        self.assertEqual(result.completed, ["reserve", "pay", "ship", "email"])
        self.assertEqual(result.compensated, [])
        self.assertIsNone(result.error)
        self.assertEqual(self.svc.calls, ["reserve", "pay", "ship", "email"])
        self.assertEqual(result.ctx["payment_id"], "pay-ok", "ステップは ctx に結果を書ける")
        self.assertEqual(self.store.load("order-1")["status"], COMPLETED)

    def test_failure_compensates_completed_steps_in_reverse_order(self):
        self.svc.fail["ship"] = [OutOfStock("配送枠なし")]
        result = self.saga.start("order-2", {})
        self.assertEqual(result.status, COMPENSATED)
        self.assertEqual(result.completed, ["reserve", "pay"])
        self.assertEqual(result.compensated, ["pay", "reserve"])
        self.assertEqual(self.svc.calls, ["reserve", "pay", "ship", "refund", "release"])
        self.assertIn("ship", result.error)
        self.assertNotIn("cancel_shipment", self.svc.calls, "失敗したステップは完了していないので補償しない")

    def test_first_step_failure_needs_no_compensation(self):
        self.svc.fail["reserve"] = [OutOfStock("在庫切れ")]
        result = self.saga.start("order-3", {})
        self.assertEqual((result.status, result.compensated), (COMPENSATED, []))
        self.assertEqual(self.svc.calls, ["reserve"])

    def test_retryable_failure_is_retried(self):
        self.svc.fail["pay"] = [RetryableError("timeout"), RetryableError("timeout")]
        result = self.saga.start("order-4", {})
        self.assertEqual(result.status, COMPLETED)
        self.assertEqual(self.svc.calls.count("pay"), 3)

    def test_retries_are_bounded(self):
        self.svc.fail["pay"] = [RetryableError("timeout")] * 5
        result = self.saga.start("order-5", {})
        self.assertEqual(result.status, COMPENSATED)
        self.assertEqual(self.svc.calls.count("pay"), 3, "max_attempts=3 まで")
        self.assertEqual(result.compensated, ["reserve"])

    def test_non_retryable_error_is_not_retried(self):
        self.svc.fail["pay"] = [ValueError("カードが拒否されました")]
        result = self.saga.start("order-6", {})
        self.assertEqual(self.svc.calls.count("pay"), 1)
        self.assertEqual(result.status, COMPENSATED)

    def test_step_without_retries_fails_on_first_retryable_error(self):
        svc = FakeServices()
        saga = SagaOrchestrator(order_steps(svc, payment_attempts=1), InMemorySagaStore())
        svc.fail["pay"] = [RetryableError("timeout")]
        self.assertEqual(saga.start("o", {}).status, COMPENSATED)
        self.assertEqual(svc.calls.count("pay"), 1)

    def test_crash_mid_saga_resumes_from_persisted_state(self):
        self.svc.fail["pay"] = [SimulatedCrash()]
        with self.assertRaises(SimulatedCrash):
            self.saga.start("order-7", {"order_id": 7})
        persisted = self.store.load("order-7")
        self.assertEqual(persisted["status"], RUNNING)
        self.assertEqual(persisted["completed"], ["reserve"])
        self.assertEqual(persisted["current"], "pay", "実行中だったステップが記録されている")
        self.assertEqual(persisted["ctx"]["reservation_id"], "reserve-ok")
        # プロセスを再起動した想定: 新しいオーケストレーターが同じストアから再開する
        restarted = SagaOrchestrator(order_steps(self.svc), self.store)
        result = restarted.resume("order-7")
        self.assertEqual(result.status, COMPLETED)
        self.assertEqual(self.svc.calls.count("reserve"), 1, "完了済みのステップは再実行しない")
        self.assertEqual(self.svc.calls.count("pay"), 2, "実行中だったステップはやり直す（だから冪等性が必要）")
        self.assertEqual(result.ctx["order_id"], 7)

    def test_crash_during_compensation_resumes_compensation(self):
        self.svc.fail["ship"] = [OutOfStock("x")]
        self.svc.fail["release"] = [SimulatedCrash()]
        with self.assertRaises(SimulatedCrash):
            self.saga.start("order-8", {})
        persisted = self.store.load("order-8")
        self.assertEqual(persisted["status"], COMPENSATING)
        self.assertEqual(persisted["compensated"], ["pay"])
        result = SagaOrchestrator(order_steps(self.svc), self.store).resume("order-8")
        self.assertEqual(result.status, COMPENSATED)
        self.assertEqual(result.compensated, ["pay", "reserve"])
        self.assertEqual(self.svc.calls.count("refund"), 1, "補償済みのステップは再度補償しない")
        self.assertEqual(self.svc.calls.count("release"), 2)

    def test_compensation_failure_needs_manual_intervention(self):
        self.svc.fail["ship"] = [OutOfStock("x")]
        self.svc.fail["refund"] = [ConnectionError("決済代行が停止中")] * 3
        result = self.saga.start("order-9", {})
        self.assertEqual(result.status, FAILED)
        self.assertIn("pay", result.error, "どのステップの補償に失敗したかをエラーに含める")
        self.assertEqual(self.svc.calls.count("refund"), 3, "補償は compensation_attempts 回まで試す")
        self.assertEqual(result.compensated, [])
        # 運用者が原因を取り除いた（決済代行が復旧した）後に再開する
        result = self.saga.resume("order-9")
        self.assertEqual(result.status, COMPENSATED)
        self.assertEqual(result.compensated, ["pay", "reserve"])

    def test_resume_of_finished_saga_does_nothing(self):
        self.saga.start("order-10", {})
        calls = list(self.svc.calls)
        self.assertEqual(self.saga.resume("order-10").status, COMPLETED)
        self.assertEqual(self.svc.calls, calls)

    def test_state_is_persisted_at_every_transition(self):
        self.saga.start("order-11", {})
        # 開始 + 各ステップの開始と完了（4 × 2）+ 完了 = 10 回
        self.assertGreaterEqual(self.store.saves, 10)

    def test_errors(self):
        self.saga.start("dup", {})
        with self.assertRaises(ValueError):
            self.saga.start("dup", {})
        with self.assertRaises(KeyError):
            self.saga.resume("unknown")
        with self.assertRaises(ValueError):
            SagaOrchestrator([Step("a", print), Step("a", print)], InMemorySagaStore())
        with self.assertRaises(ValueError):
            SagaOrchestrator([Step("a", print, max_attempts=0)], InMemorySagaStore())
        with self.assertRaises(TypeError, msg="ctx は永続化（JSON）できる値だけ"):
            self.saga.start("bad-ctx", {"when": object()})


if __name__ == "__main__":
    unittest.main()
