"""8.4 演習1 — フィーチャーフラグの評価エンジンのテスト

実行: python3 tools/check.py 8.4   （またはこのディレクトリで python3 -m unittest -v test_flags）
"""
import hashlib
import unittest

from flags import BUCKETS, Evaluation, bucket, evaluate


def expected_bucket(flag_key, key):
    digest = hashlib.sha256(f"{flag_key}:{key}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % 10_000


def on_off_flag(**overrides):
    flag = {
        "enabled": True,
        "variants": {"on": True, "off": False},
        "off_variant": "off",
        "default": {"variant": "off"},
    }
    flag.update(overrides)
    return flag


USERS = [{"user_id": f"user-{i}"} for i in range(10_000)]


class TestBucket(unittest.TestCase):
    def test_matches_specification(self):
        for key in ("user-1", "user-42", "山田", ""):
            self.assertEqual(bucket("new-checkout", key), expected_bucket("new-checkout", key), key)
        self.assertEqual(BUCKETS, 10_000)

    def test_is_stable_and_in_range(self):
        values = [bucket("f", f"u{i}") for i in range(2000)]
        self.assertEqual(values, [bucket("f", f"u{i}") for i in range(2000)])
        self.assertTrue(all(0 <= v < 10_000 for v in values))

    def test_is_roughly_uniform(self):
        counts = [0] * 10
        for u in USERS:
            counts[bucket("uniformity", u["user_id"]) // 1000] += 1
        for c in counts:
            self.assertTrue(880 <= c <= 1120, f"各 10% の区間に約 1,000 人ずつ入るはず: {counts}")

    def test_different_flags_are_independent(self):
        both = sum(
            1 for u in USERS
            if bucket("flag-a", u["user_id"]) < 2000 and bucket("flag-b", u["user_id"]) < 2000
        )
        # 独立なら約 20% × 20% = 4%（400 人）。フラグのキーを混ぜないと 20%（2,000 人）になる
        self.assertTrue(300 <= both <= 500, both)


class TestBasicEvaluation(unittest.TestCase):
    def test_default_variant(self):
        result = evaluate({"f": on_off_flag()}, "f", {"user_id": "u1"})
        self.assertIsInstance(result, Evaluation)
        self.assertEqual((result.value, result.variant, result.reason), (False, "off", "DEFAULT"))

    def test_kill_switch(self):
        flag = on_off_flag(enabled=False, default={"variant": "on"},
                           rules=[{"clauses": [], "serve": {"variant": "on"}}])
        result = evaluate({"f": flag}, "f", {"user_id": "u1"})
        self.assertEqual((result.value, result.variant, result.reason), (False, "off", "OFF"))

    def test_rule_order_and_index(self):
        flag = on_off_flag(rules=[
            {"clauses": [{"attribute": "plan", "op": "in", "values": ["free"]}], "serve": {"variant": "off"}},
            {"clauses": [{"attribute": "country", "op": "in", "values": ["JP"]}], "serve": {"variant": "on"}},
        ])
        flags = {"f": flag}
        jp = evaluate(flags, "f", {"country": "JP", "plan": "pro"})
        self.assertEqual((jp.variant, jp.reason, jp.rule_index), ("on", "RULE_MATCH", 1))
        free_jp = evaluate(flags, "f", {"country": "JP", "plan": "free"})
        self.assertEqual((free_jp.variant, free_jp.rule_index), ("off", 0), "上のルールが優先")
        us = evaluate(flags, "f", {"country": "US", "plan": "pro"})
        self.assertEqual((us.variant, us.reason, us.rule_index), ("off", "DEFAULT", None))

    def test_all_clauses_must_match(self):
        flag = on_off_flag(rules=[{"clauses": [
            {"attribute": "country", "op": "in", "values": ["JP"]},
            {"attribute": "age", "op": "gte", "values": [18]},
        ], "serve": {"variant": "on"}}])
        self.assertTrue(evaluate({"f": flag}, "f", {"country": "JP", "age": 20}).value)
        self.assertFalse(evaluate({"f": flag}, "f", {"country": "JP", "age": 17}).value)

    def test_variants_can_hold_any_values(self):
        flag = {
            "enabled": True,
            "variants": {"blue": {"color": "#1a73e8", "label": "購入"}, "green": {"color": "#188038", "label": "今すぐ買う"}},
            "off_variant": "blue",
            "default": {"variant": "green"},
        }
        self.assertEqual(evaluate({"button": flag}, "button", {}).value, {"color": "#188038", "label": "今すぐ買う"})


class TestClauses(unittest.TestCase):
    def matches(self, clause, context):
        flag = on_off_flag(rules=[{"clauses": [clause], "serve": {"variant": "on"}}])
        result = evaluate({"f": flag}, "f", context)
        self.assertNotEqual(result.reason, "ERROR", result.error)
        return result.value

    def test_membership(self):
        self.assertTrue(self.matches({"attribute": "plan", "op": "in", "values": ["pro", "enterprise"]}, {"plan": "pro"}))
        self.assertFalse(self.matches({"attribute": "plan", "op": "in", "values": ["pro"]}, {"plan": "free"}))
        self.assertTrue(self.matches({"attribute": "plan", "op": "not_in", "values": ["free"]}, {"plan": "pro"}))
        self.assertFalse(self.matches({"attribute": "plan", "op": "not_in", "values": ["free"]}, {"plan": "free"}))

    def test_string_operators(self):
        email = {"email": "alice@example.com"}
        self.assertTrue(self.matches({"attribute": "email", "op": "ends_with", "values": ["@example.org", "@example.com"]}, email))
        self.assertTrue(self.matches({"attribute": "email", "op": "starts_with", "values": ["alice"]}, email))
        self.assertTrue(self.matches({"attribute": "email", "op": "contains", "values": ["@exa"]}, email))
        self.assertFalse(self.matches({"attribute": "email", "op": "contains", "values": ["bob"]}, email))
        self.assertFalse(self.matches({"attribute": "email", "op": "contains", "values": ["1"]}, {"email": 123}), "型が違えば不成立")

    def test_numeric_operators(self):
        cases = [("lt", 10, True), ("lt", 11, False), ("lte", 11, True), ("gt", 11, False),
                 ("gt", 12, True), ("gte", 11, True), ("gte", 10.5, False)]
        for op, value, expected in cases:
            self.assertEqual(self.matches({"attribute": "n", "op": op, "values": [11]}, {"n": value}), expected, (op, value))
        self.assertFalse(self.matches({"attribute": "n", "op": "gt", "values": [0]}, {"n": True}), "bool は数値として扱わない")
        self.assertFalse(self.matches({"attribute": "n", "op": "gt", "values": [0]}, {"n": "5"}), "文字列は数値ではない")

    def test_missing_attribute_never_matches(self):
        self.assertFalse(self.matches({"attribute": "plan", "op": "not_in", "values": ["free"]}, {}),
                         "属性がない利用者を、否定の条件で誤って対象にしない")
        self.assertFalse(self.matches({"attribute": "plan", "op": "in", "values": ["free"]}, {"user_id": "u"}))


class TestRollout(unittest.TestCase):
    def rollout_flag(self, on_percent, **serve_extra):
        serve = {"rollout": [["on", on_percent], ["off", 100 - on_percent]], **serve_extra}
        return on_off_flag(default=serve)

    def on_users(self, flag, users=USERS, key="rollout-test"):
        return {u["user_id"] for u in users if evaluate({key: flag}, key, u).value}

    def test_percentage_is_respected(self):
        on = self.on_users(self.rollout_flag(20))
        self.assertTrue(1800 <= len(on) <= 2200, len(on))

    def test_bucket_boundaries(self):
        flag = self.rollout_flag(20)
        for u in USERS[:3000]:
            expected = expected_bucket("rollout-test", u["user_id"]) < 2000
            self.assertEqual(evaluate({"rollout-test": flag}, "rollout-test", u).value, expected, u)

    def test_ramping_up_keeps_existing_users(self):
        on10 = self.on_users(self.rollout_flag(10))
        on25 = self.on_users(self.rollout_flag(25))
        on50 = self.on_users(self.rollout_flag(50))
        self.assertTrue(on10 <= on25 <= on50, "割合を上げても、すでに有効だった利用者は有効のまま")
        self.assertEqual(self.on_users(self.rollout_flag(0)), set())
        self.assertEqual(len(self.on_users(self.rollout_flag(100))), len(USERS))

    def test_bucket_by_another_attribute(self):
        flag = self.rollout_flag(50, bucket_by="org_id")
        members = [{"user_id": f"u{i}", "org_id": f"org-{i % 20}"} for i in range(400)]
        by_org = {}
        for m in members:
            by_org.setdefault(m["org_id"], set()).add(evaluate({"f": flag}, "f", m).value)
        self.assertTrue(all(len(v) == 1 for v in by_org.values()), "同じ組織の利用者は同じ体験になる")
        self.assertEqual({v for s in by_org.values() for v in s}, {True, False})

    def test_rollout_in_a_rule(self):
        flag = on_off_flag(rules=[{
            "clauses": [{"attribute": "country", "op": "in", "values": ["JP"]}],
            "serve": {"rollout": [["on", 30], ["off", 70]]},
        }])
        jp_users = [{"user_id": f"u{i}", "country": "JP"} for i in range(5000)]
        results = [evaluate({"f": flag}, "f", u) for u in jp_users]
        self.assertTrue(all(r.reason == "RULE_MATCH" for r in results))
        self.assertTrue(1300 <= sum(r.value for r in results) <= 1700)


class TestPrerequisites(unittest.TestCase):
    def flags(self, cart_enabled=True, cart_default="on"):
        return {
            "new-cart": on_off_flag(enabled=cart_enabled, default={"variant": cart_default}),
            "new-checkout": on_off_flag(default={"variant": "on"},
                                        prerequisites=[{"flag": "new-cart", "variant": "on"}]),
        }

    def test_satisfied_prerequisite(self):
        result = evaluate(self.flags(), "new-checkout", {"user_id": "u"})
        self.assertEqual((result.variant, result.reason), ("on", "DEFAULT"))

    def test_unsatisfied_prerequisite_serves_off(self):
        for flags in (self.flags(cart_default="off"), self.flags(cart_enabled=False)):
            result = evaluate(flags, "new-checkout", {"user_id": "u"})
            self.assertEqual((result.value, result.variant, result.reason), (False, "off", "PREREQUISITE_FAILED"))

    def test_missing_prerequisite_flag(self):
        flags = {"new-checkout": on_off_flag(default={"variant": "on"},
                                             prerequisites=[{"flag": "ghost", "variant": "on"}])}
        self.assertEqual(evaluate(flags, "new-checkout", {}).reason, "PREREQUISITE_FAILED")

    def test_prerequisite_cycle_is_an_error(self):
        flags = {
            "a": on_off_flag(default={"variant": "on"}, prerequisites=[{"flag": "b", "variant": "on"}]),
            "b": on_off_flag(default={"variant": "on"}, prerequisites=[{"flag": "a", "variant": "on"}]),
        }
        result = evaluate(flags, "a", {}, default="fallback")
        self.assertEqual((result.value, result.variant, result.reason), ("fallback", None, "ERROR"))


class TestErrorsNeverRaise(unittest.TestCase):
    def assert_error(self, flags, key="f", context=None):
        result = evaluate(flags, key, context if context is not None else {"user_id": "u"}, default="safe-default")
        self.assertEqual((result.value, result.variant, result.reason), ("safe-default", None, "ERROR"), result)
        self.assertTrue(result.error)

    def test_unknown_flag(self):
        self.assert_error({}, "nope")

    def test_unknown_variant(self):
        self.assert_error({"f": on_off_flag(default={"variant": "maybe"})})

    def test_weights_must_sum_to_100(self):
        self.assert_error({"f": on_off_flag(default={"rollout": [["on", 30], ["off", 60]]})})
        self.assert_error({"f": on_off_flag(default={"rollout": [["on", -10], ["off", 110]]})})

    def test_unknown_operator(self):
        self.assert_error({"f": on_off_flag(rules=[{"clauses": [{"attribute": "x", "op": "regex", "values": [".*"]}],
                                                  "serve": {"variant": "on"}}])}, context={"x": "1"})

    def test_missing_bucketing_attribute(self):
        self.assert_error({"f": on_off_flag(default={"rollout": [["on", 50], ["off", 50]]})}, context={})

    def test_garbage_configuration(self):
        for garbage in (None, "on", {"enabled": True}, {"variants": {}, "enabled": True, "off_variant": "x"}):
            self.assert_error({"f": garbage})


if __name__ == "__main__":
    unittest.main()
