"""12.5 演習2: モデルレジストリ — テスト

実行: python3 tools/check.py 12.5   （またはこのディレクトリで python3 -m unittest -v test_model_registry）
"""
import datetime as dt
import unittest

from model_registry import (
    ARCHIVED,
    NONE,
    PRODUCTION,
    STAGING,
    ChampionCheck,
    GateError,
    MetricGate,
    ModelRegistry,
    PromotionPolicy,
    RegistryError,
    TransitionError,
)


class FakeClock:
    def __init__(self):
        self.now = dt.datetime(2026, 4, 1, 9, 0, tzinfo=dt.timezone.utc)

    def __call__(self):
        self.now += dt.timedelta(minutes=1)
        return self.now


def make_policy():
    return PromotionPolicy(
        gates=(MetricGate("auc", ">=", 0.80), MetricGate("latency_p99_ms", "<=", 50)),
        required_approvals=1,
        champion_checks=(ChampionCheck("auc", higher_is_better=True, tolerance=0.005),),
    )


class RegistryTestCase(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.reg = ModelRegistry(clock=self.clock)
        self.reg.set_policy("fraud", make_policy())

    def register(self, auc=0.85, latency=30, by="alice"):
        return self.reg.register(
            "fraud", f"s3://models/fraud/{len(self.reg.versions('fraud')) + 1}",
            metrics={"auc": auc, "latency_p99_ms": latency},
            data_version="orders@2026-03-31", code_version="git:1a2b3c", created_by=by,
            params={"max_depth": 6},
        )

    def promote(self, mv, approver="bob"):
        self.reg.transition("fraud", mv.version, STAGING, actor="alice")
        self.reg.approve("fraud", mv.version, approver=approver)
        return self.reg.transition("fraud", mv.version, PRODUCTION, actor="alice")


class TestRegister(RegistryTestCase):
    def test_versions_increment_per_model(self):
        v1, v2 = self.register(), self.register()
        other = self.reg.register("churn", "s3://x", metrics={}, data_version="d", code_version="c", created_by="carol")
        self.assertEqual((v1.version, v2.version, other.version), (1, 2, 1))
        self.assertEqual(v1.stage, NONE)
        self.assertEqual(self.reg.get("fraud", 2), v2)
        self.assertEqual([m.version for m in self.reg.versions("fraud")], [1, 2])
        self.assertEqual(v1.params, {"max_depth": 6})
        self.assertEqual(v1.created_at, dt.datetime(2026, 4, 1, 9, 1, tzinfo=dt.timezone.utc), "注入した時計を使う")

    def test_lineage_is_required(self):
        with self.assertRaises(ValueError):
            self.reg.register("fraud", "s3://x", metrics={}, data_version="", code_version="c", created_by="a")
        with self.assertRaises(ValueError):
            self.reg.register("fraud", "s3://x", metrics={}, data_version="d", code_version="", created_by="a")

    def test_metrics_are_copied(self):
        metrics = {"auc": 0.9, "latency_p99_ms": 10}
        mv = self.reg.register("fraud", "s3://x", metrics=metrics, data_version="d", code_version="c", created_by="a")
        metrics["auc"] = 0.1
        self.assertEqual(mv.metrics["auc"], 0.9, "登録後に呼び出し元が辞書を変えても影響しない")

    def test_unknown_version(self):
        with self.assertRaises(RegistryError):
            self.reg.get("fraud", 1)


class TestTransitions(RegistryTestCase):
    def test_allowed_and_forbidden_transitions(self):
        mv = self.register()
        with self.assertRaises(TransitionError):
            self.reg.transition("fraud", mv.version, PRODUCTION, actor="alice")  # None → Production は不可
        self.reg.transition("fraud", mv.version, STAGING, actor="alice")
        with self.assertRaises(TransitionError):
            self.reg.transition("fraud", mv.version, NONE, actor="alice")
        self.reg.transition("fraud", mv.version, ARCHIVED, actor="alice")
        with self.assertRaises(TransitionError):
            self.reg.transition("fraud", mv.version, STAGING, actor="alice")  # Archived からは戻せない
        with self.assertRaises(TransitionError):
            self.reg.transition("fraud", mv.version, "Canary", actor="alice")

    def test_gates_block_promotion(self):
        bad = self.register(auc=0.78, latency=80)
        self.reg.transition("fraud", bad.version, STAGING, actor="alice")
        self.reg.approve("fraud", bad.version, approver="bob")
        with self.assertRaises(GateError) as cm:
            self.reg.transition("fraud", bad.version, PRODUCTION, actor="alice")
        reasons = " ".join(cm.exception.reasons)
        self.assertIn("auc", reasons)
        self.assertIn("latency_p99_ms", reasons)
        self.assertEqual(bad.stage, STAGING, "失敗したら状態は変わらない")

    def test_missing_metric_fails_gate(self):
        mv = self.reg.register("fraud", "s3://x", metrics={"auc": 0.9}, data_version="d", code_version="c", created_by="a")
        self.reg.transition("fraud", mv.version, STAGING, actor="a")
        self.reg.approve("fraud", mv.version, approver="b")
        with self.assertRaises(GateError) as cm:
            self.reg.transition("fraud", mv.version, PRODUCTION, actor="a")
        self.assertTrue(any("latency_p99_ms" in r for r in cm.exception.reasons))

    def test_approvals_and_separation_of_duties(self):
        mv = self.register(by="alice")
        self.reg.transition("fraud", mv.version, STAGING, actor="alice")
        with self.assertRaises(GateError):
            self.reg.transition("fraud", mv.version, PRODUCTION, actor="alice")  # 承認が 0 件
        with self.assertRaises(RegistryError):
            self.reg.approve("fraud", mv.version, approver="alice")  # 自分の版は承認できない
        self.reg.approve("fraud", mv.version, approver="bob")
        self.assertEqual(self.reg.transition("fraud", mv.version, PRODUCTION, actor="alice").stage, PRODUCTION)
        with self.assertRaises(RegistryError):
            self.reg.approve("fraud", mv.version, approver="carol")  # 本番の版にはもう承認できない

    def test_only_one_production_version(self):
        v1 = self.promote(self.register(auc=0.85))
        v2 = self.promote(self.register(auc=0.86))
        self.assertEqual(self.reg.production("fraud"), v2)
        self.assertEqual(v1.stage, ARCHIVED)
        self.assertEqual(sum(m.stage == PRODUCTION for m in self.reg.versions("fraud")), 1)

    def test_champion_check(self):
        self.promote(self.register(auc=0.86))
        worse = self.register(auc=0.85)  # 0.01 悪化（許容 0.005 を超える）
        with self.assertRaises(GateError) as cm:
            self.promote(worse)
        self.assertTrue(any("v1" in r for r in cm.exception.reasons), "比較した本番の版を理由に含める")
        within = self.register(auc=0.857)  # 0.003 の悪化は許容範囲
        self.assertEqual(self.promote(within).stage, PRODUCTION)

    def test_champion_check_for_lower_is_better_metric(self):
        self.reg.set_policy("fraud", PromotionPolicy(required_approvals=0, champion_checks=(
            ChampionCheck("latency_p99_ms", higher_is_better=False, tolerance=5),)))
        self.promote(self.register(latency=30))
        with self.assertRaises(GateError):
            self.promote(self.register(latency=40))
        self.assertEqual(self.promote(self.register(latency=34)).stage, PRODUCTION)

    def test_policy_validation(self):
        with self.assertRaises(ValueError):
            MetricGate("auc", ">", 0.8)
        with self.assertRaises(ValueError):
            self.reg.set_policy("fraud", PromotionPolicy(required_approvals=-1))


class TestRollbackAndAudit(RegistryTestCase):
    def test_rollback_restores_previous_versions_in_order(self):
        v1 = self.promote(self.register(auc=0.85))
        v2 = self.promote(self.register(auc=0.86))
        v3 = self.promote(self.register(auc=0.87))
        restored = self.reg.rollback("fraud", actor="oncall")
        self.assertEqual(restored, v2)
        self.assertEqual((v1.stage, v2.stage, v3.stage), (ARCHIVED, PRODUCTION, ARCHIVED))
        self.assertEqual(self.reg.rollback("fraud", actor="oncall"), v1)
        self.assertEqual(self.reg.production("fraud"), v1)
        with self.assertRaises(RegistryError):
            self.reg.rollback("fraud", actor="oncall")  # もう戻る先がない

    def test_rollback_skips_gates(self):
        v1 = self.promote(self.register(auc=0.85))
        self.promote(self.register(auc=0.9))
        self.reg.set_policy("fraud", PromotionPolicy(gates=(MetricGate("auc", ">=", 0.95),)))  # 方針が厳しくなった
        self.assertEqual(self.reg.rollback("fraud", actor="oncall"), v1, "障害対応のロールバックは条件を再確認しない")

    def test_rollback_without_history(self):
        self.promote(self.register())
        with self.assertRaises(RegistryError):
            self.reg.rollback("fraud", actor="oncall")

    def test_audit_log(self):
        mv = self.register(by="alice")
        self.promote(mv)
        actions = [(e.action, e.actor, e.version) for e in self.reg.audit_log]
        self.assertEqual(actions, [("register", "alice", 1), ("transition", "alice", 1),
                                   ("approve", "bob", 1), ("transition", "alice", 1)])
        times = [e.at for e in self.reg.audit_log]
        self.assertEqual(times, sorted(times))
        self.assertIn("Staging → Production", self.reg.audit_log[-1].detail)
        with self.assertRaises(GateError):
            self.promote(self.register(auc=0.5))
        self.assertEqual(self.reg.audit_log[-1].action, "promotion_rejected", "拒否も記録する")


if __name__ == "__main__":
    unittest.main()
