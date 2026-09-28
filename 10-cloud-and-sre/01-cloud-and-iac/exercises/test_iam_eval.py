"""10.1 IAM ポリシー評価器 — テスト

実行: python3 tools/check.py 10.1   （またはこのディレクトリで python3 -m unittest -v）
"""
import random
import threading
import unittest

from iam_eval import Decision, Request, condition_matches, evaluate, wildcard_match


def policy(*statements):
    return {"Version": "2012-10-17", "Statement": list(statements)}


READ_REPORTS = {
    "Sid": "ReadReports",
    "Effect": "Allow",
    "Action": ["s3:GetObject", "s3:ListBucket"],
    "Resource": ["arn:aws:s3:::acme-reports", "arn:aws:s3:::acme-reports/*"],
}
FULL_ACCESS = {"Sid": "FullAWSAccess", "Effect": "Allow", "Action": "*", "Resource": "*"}


def reference_glob(pattern: str, value: str) -> bool:
    """テスト用の素直な動的計画法（答え合わせ用）。"""
    n, m = len(pattern), len(value)
    dp = [[False] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = True
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] and pattern[i - 1] == "*"
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            c = pattern[i - 1]
            if c == "*":
                dp[i][j] = dp[i - 1][j] or dp[i][j - 1]
            else:
                dp[i][j] = dp[i - 1][j - 1] and (c == "?" or c == value[j - 1])
    return dp[n][m]


class TestExercise1Wildcard(unittest.TestCase):
    def test_examples(self):
        self.assertTrue(wildcard_match("s3:Get*", "s3:GetObject"))
        self.assertTrue(wildcard_match("*", ""))
        self.assertTrue(wildcard_match("*", "anything"))
        self.assertTrue(wildcard_match("arn:aws:s3:::acme-reports/*", "arn:aws:s3:::acme-reports/2026/q1.csv"))
        self.assertTrue(wildcard_match("ec2:*Instances", "ec2:DescribeInstances"))
        self.assertTrue(wildcard_match("a?c", "abc"))
        self.assertFalse(wildcard_match("a?c", "ac"), "? はちょうど 1 文字")
        self.assertFalse(wildcard_match("s3:Get*", "s3:PutObject"))
        self.assertFalse(wildcard_match("arn:aws:s3:::acme-reports/*", "arn:aws:s3:::acme-reports"),
                         "バケット自体（末尾の / がない）はオブジェクトのパターンにマッチしない")
        self.assertTrue(wildcard_match("", ""))
        self.assertFalse(wildcard_match("", "a"))

    def test_star_is_always_a_wildcard(self):
        self.assertTrue(wildcard_match("*b", "*ab"), "パターン中の * はリテラルではなくワイルドカード")
        self.assertTrue(wildcard_match("a*b*c", "a*xb*yc"))

    def test_regex_metacharacters_are_literal(self):
        self.assertFalse(wildcard_match("a.b", "axb"))
        self.assertTrue(wildcard_match("a.b", "a.b"))
        self.assertFalse(wildcard_match("[ab]", "a"))
        self.assertTrue(wildcard_match("[ab]", "[ab]"))
        self.assertTrue(wildcard_match("x+y", "x+y"))

    def test_case_sensitivity(self):
        self.assertFalse(wildcard_match("s3:getobject", "s3:GetObject"))
        self.assertTrue(wildcard_match("s3:getobject", "s3:GetObject", ignore_case=True))
        self.assertTrue(wildcard_match("S3:GET*", "s3:GetObject", ignore_case=True))

    def test_agrees_with_reference(self):
        rng = random.Random(101)
        for _ in range(2000):
            pattern = "".join(rng.choice("ab*?") for _ in range(rng.randrange(0, 7)))
            value = "".join(rng.choice("ab") for _ in range(rng.randrange(0, 8)))
            self.assertEqual(wildcard_match(pattern, value), reference_glob(pattern, value), (pattern, value))

    def test_no_exponential_backtracking(self):
        # 素朴な再帰で * ごとに全分岐を試すと指数時間になる入力（10.5 の正規表現による障害を参照）
        pattern = "*a" * 25 + "b"
        value = "a" * 200
        result = []

        def run():
            try:
                result.append(wildcard_match(pattern, value))
            except BaseException as exc:  # noqa: BLE001  例外はメインスレッドで送出し直す
                result.append(exc)

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(timeout=10)
        self.assertFalse(worker.is_alive(), "10 秒以内に終わらない: 最悪でも O(len(pattern)×len(value)) にしてください")
        if isinstance(result[0], BaseException):
            raise result[0]
        self.assertEqual(result, [False])


class TestExercise2Conditions(unittest.TestCase):
    def test_empty_condition_matches(self):
        self.assertTrue(condition_matches(None, {}))
        self.assertTrue(condition_matches({}, {"aws:SourceIp": "192.0.2.1"}))

    def test_string_operators(self):
        cond = {"StringEquals": {"aws:RequestedRegion": ["ap-northeast-1", "ap-northeast-3"]}}
        self.assertTrue(condition_matches(cond, {"aws:RequestedRegion": "ap-northeast-3"}), "複数の値は OR")
        self.assertFalse(condition_matches(cond, {"aws:RequestedRegion": "us-east-1"}))
        self.assertFalse(condition_matches(cond, {}), "キーがなければ false")
        self.assertFalse(condition_matches(cond, {"aws:RequestedRegion": "AP-NORTHEAST-1"}), "StringEquals は大文字小文字を区別")
        like = {"StringLike": {"s3:prefix": "home/alice/*"}}
        self.assertTrue(condition_matches(like, {"s3:prefix": "home/alice/photos/"}))
        self.assertFalse(condition_matches(like, {"s3:prefix": "home/bob/"}))

    def test_negated_operators(self):
        cond = {"StringNotEquals": {"aws:RequestedRegion": ["ap-northeast-1", "ap-northeast-3"]}}
        self.assertTrue(condition_matches(cond, {"aws:RequestedRegion": "us-east-1"}))
        self.assertFalse(condition_matches(cond, {"aws:RequestedRegion": "ap-northeast-1"}),
                         "否定形は「どの値にも一致しない」とき true")
        self.assertTrue(condition_matches(cond, {}), "否定形はキーがなければ true")

    def test_keys_are_case_insensitive(self):
        cond = {"StringEquals": {"aws:PrincipalTag/team": "payments"}}
        self.assertTrue(condition_matches(cond, {"AWS:principaltag/TEAM": "payments"}))

    def test_multiple_operators_and_keys_are_and(self):
        cond = {
            "StringEquals": {"aws:RequestedRegion": "ap-northeast-1", "aws:PrincipalTag/team": "sre"},
            "Bool": {"aws:SecureTransport": "true"},
        }
        ctx = {"aws:RequestedRegion": "ap-northeast-1", "aws:PrincipalTag/team": "sre", "aws:SecureTransport": True}
        self.assertTrue(condition_matches(cond, ctx))
        self.assertFalse(condition_matches(cond, dict(ctx, **{"aws:SecureTransport": False})))
        self.assertFalse(condition_matches(cond, dict(ctx, **{"aws:PrincipalTag/team": "web"})))

    def test_bool_and_if_exists(self):
        cond = {"BoolIfExists": {"aws:MultiFactorAuthPresent": "false"}}
        self.assertTrue(condition_matches(cond, {}), "IfExists はキーがなければ true")
        self.assertTrue(condition_matches(cond, {"aws:MultiFactorAuthPresent": False}))
        self.assertTrue(condition_matches(cond, {"aws:MultiFactorAuthPresent": "false"}))
        self.assertFalse(condition_matches(cond, {"aws:MultiFactorAuthPresent": True}))
        plain = {"Bool": {"aws:MultiFactorAuthPresent": "false"}}
        self.assertFalse(condition_matches(plain, {}), "IfExists なしならキーがないと false")

    def test_numeric_operators(self):
        cond = {"NumericLessThanEquals": {"aws:MultiFactorAuthAge": "3600"}}
        self.assertTrue(condition_matches(cond, {"aws:MultiFactorAuthAge": 3600}))
        self.assertTrue(condition_matches(cond, {"aws:MultiFactorAuthAge": "120"}))
        self.assertFalse(condition_matches(cond, {"aws:MultiFactorAuthAge": 3601}))
        self.assertFalse(condition_matches(cond, {}))
        self.assertTrue(condition_matches({"NumericGreaterThan": {"n": 1}}, {"n": 1.5}))
        self.assertFalse(condition_matches({"NumericLessThan": {"n": 1}}, {"n": 1}))
        self.assertTrue(condition_matches({"NumericGreaterThanEquals": {"n": 1}}, {"n": 1}))
        self.assertTrue(condition_matches({"NumericEquals": {"n": "2"}}, {"n": 2.0}))

    def test_ip_address(self):
        cond = {"IpAddress": {"aws:SourceIp": ["203.0.113.0/24", "2001:db8::/32"]}}
        self.assertTrue(condition_matches(cond, {"aws:SourceIp": "203.0.113.77"}))
        self.assertTrue(condition_matches(cond, {"aws:SourceIp": "2001:db8::1"}))
        self.assertFalse(condition_matches(cond, {"aws:SourceIp": "198.51.100.1"}))
        not_cond = {"NotIpAddress": {"aws:SourceIp": "203.0.113.0/24"}}
        self.assertTrue(condition_matches(not_cond, {"aws:SourceIp": "198.51.100.1"}))
        self.assertFalse(condition_matches(not_cond, {"aws:SourceIp": "203.0.113.5"}))

    def test_invalid_input(self):
        with self.assertRaises(ValueError):
            condition_matches({"StringEqualz": {"k": "v"}}, {"k": "v"})
        with self.assertRaises(ValueError):
            condition_matches({"NumericLessThan": {"n": "10"}}, {"n": "ten"})
        with self.assertRaises(ValueError):
            condition_matches({"Bool": {"b": "true"}}, {"b": "yes"})
        with self.assertRaises(ValueError):
            condition_matches({"IpAddress": {"aws:SourceIp": "10.0.0.0/8"}}, {"aws:SourceIp": "not-an-ip"})


class TestExercise2Evaluate(unittest.TestCase):
    def test_default_deny(self):
        d = evaluate(Request("s3:GetObject", "arn:aws:s3:::acme-reports/a.csv"), [])
        self.assertEqual(d, Decision(False, "implicit_deny"))

    def test_allow(self):
        d = evaluate(Request("s3:GetObject", "arn:aws:s3:::acme-reports/a.csv"), [policy(READ_REPORTS)])
        self.assertEqual(d, Decision(True, "allowed", ("ReadReports",)))

    def test_statement_may_be_a_single_object(self):
        single = {"Version": "2012-10-17", "Statement": READ_REPORTS}
        self.assertTrue(evaluate(Request("s3:ListBucket", "arn:aws:s3:::acme-reports"), [single]).allowed)

    def test_action_is_case_insensitive_resource_is_not(self):
        pols = [policy(READ_REPORTS)]
        self.assertTrue(evaluate(Request("S3:getobject", "arn:aws:s3:::acme-reports/a.csv"), pols).allowed)
        self.assertFalse(evaluate(Request("s3:GetObject", "arn:aws:s3:::ACME-reports/a.csv"), pols).allowed)

    def test_explicit_deny_wins_across_policies(self):
        deny_secret = {
            "Sid": "DenySecret",
            "Effect": "Deny",
            "Action": "s3:*",
            "Resource": "arn:aws:s3:::acme-reports/secret/*",
        }
        pols = [policy(READ_REPORTS), policy(FULL_ACCESS, deny_secret)]
        d = evaluate(Request("s3:GetObject", "arn:aws:s3:::acme-reports/secret/salary.csv"), pols)
        self.assertEqual(d, Decision(False, "explicit_deny", ("DenySecret",)))
        d = evaluate(Request("s3:GetObject", "arn:aws:s3:::acme-reports/public.csv"), pols)
        self.assertEqual(d, Decision(True, "allowed", ("ReadReports", "FullAWSAccess")))

    def test_not_action_grants_everything_else(self):
        # 「IAM 以外は全部許可」— NotAction + Allow は想像以上に広い権限になる典型例
        power_user = {"Sid": "PowerUser", "Effect": "Allow", "NotAction": ["iam:*", "organizations:*"], "Resource": "*"}
        pols = [policy(power_user)]
        self.assertTrue(evaluate(Request("ec2:TerminateInstances", "*"), pols).allowed)
        self.assertTrue(evaluate(Request("kms:ScheduleKeyDeletion", "*"), pols).allowed)
        self.assertEqual(evaluate(Request("iam:CreateUser", "*"), pols).reason, "implicit_deny")

    def test_not_resource_in_deny(self):
        deny_other_buckets = {
            "Sid": "OnlyReports",
            "Effect": "Deny",
            "Action": "s3:*",
            "NotResource": ["arn:aws:s3:::acme-reports", "arn:aws:s3:::acme-reports/*"],
        }
        pols = [policy(FULL_ACCESS, deny_other_buckets)]
        self.assertTrue(evaluate(Request("s3:PutObject", "arn:aws:s3:::acme-reports/x"), pols).allowed)
        d = evaluate(Request("s3:PutObject", "arn:aws:s3:::acme-backups/x"), pols)
        self.assertEqual(d.reason, "explicit_deny")

    def test_mfa_required_pattern(self):
        deny_without_mfa = {
            "Sid": "DenyAllExceptListedIfNoMFA",
            "Effect": "Deny",
            "NotAction": ["iam:ListMFADevices", "iam:EnableMFADevice", "sts:GetSessionToken"],
            "Resource": "*",
            "Condition": {"BoolIfExists": {"aws:MultiFactorAuthPresent": "false"}},
        }
        pols = [policy(FULL_ACCESS, deny_without_mfa)]
        ec2 = "ec2:StartInstances"
        self.assertTrue(evaluate(Request(ec2, "*", {"aws:MultiFactorAuthPresent": True}), pols).allowed)
        self.assertEqual(evaluate(Request(ec2, "*", {"aws:MultiFactorAuthPresent": False}), pols).reason,
                         "explicit_deny")
        self.assertEqual(evaluate(Request(ec2, "*", {}), pols).reason, "explicit_deny",
                         "長期のアクセスキーにはキー自体がない → IfExists なので拒否")
        self.assertTrue(evaluate(Request("iam:EnableMFADevice", "*", {}), pols).allowed,
                        "MFA を設定するための操作は MFA なしでも許可")

    def test_ip_restriction(self):
        deny_outside = {
            "Sid": "DenyOutsideOffice",
            "Effect": "Deny",
            "Action": "*",
            "Resource": "*",
            "Condition": {"NotIpAddress": {"aws:SourceIp": "203.0.113.0/24"}},
        }
        pols = [policy(FULL_ACCESS, deny_outside)]
        self.assertTrue(evaluate(Request("s3:GetObject", "x", {"aws:SourceIp": "203.0.113.10"}), pols).allowed)
        self.assertFalse(evaluate(Request("s3:GetObject", "x", {"aws:SourceIp": "198.51.100.10"}), pols).allowed)

    def test_permissions_boundary_is_an_intersection(self):
        identity = policy({"Sid": "Admin", "Effect": "Allow", "Action": ["s3:*", "iam:*"], "Resource": "*"})
        boundary = policy({"Sid": "S3Only", "Effect": "Allow", "Action": ["s3:*", "ec2:*"], "Resource": "*"})
        self.assertTrue(evaluate(Request("s3:GetObject", "x"), [identity], boundary=boundary).allowed)
        self.assertEqual(evaluate(Request("iam:CreateRole", "x"), [identity], boundary=boundary),
                         Decision(False, "boundary"), "境界で許可されていない")
        self.assertEqual(evaluate(Request("ec2:RunInstances", "x"), [identity], boundary=boundary),
                         Decision(False, "implicit_deny"), "境界は権限を与えない（上限を決めるだけ）")

    def test_scp_levels(self):
        region_guard = {
            "Sid": "DenyOutsideJapan",
            "Effect": "Deny",
            "NotAction": ["iam:*", "sts:*", "organizations:*", "support:*"],
            "Resource": "*",
            "Condition": {"StringNotEquals": {"aws:RequestedRegion": ["ap-northeast-1", "ap-northeast-3"]}},
        }
        s3_only = {"Sid": "S3Only", "Effect": "Allow", "Action": "s3:*", "Resource": "*"}
        identity = [policy(FULL_ACCESS)]
        tokyo = {"aws:RequestedRegion": "ap-northeast-1"}
        scps = [[policy(FULL_ACCESS)], [policy(region_guard), policy(FULL_ACCESS)]]
        self.assertTrue(evaluate(Request("ec2:RunInstances", "*", tokyo), identity, scps=scps).allowed)
        d = evaluate(Request("ec2:RunInstances", "*", {"aws:RequestedRegion": "us-east-1"}), identity, scps=scps)
        self.assertEqual(d, Decision(False, "explicit_deny", ("DenyOutsideJapan",)))
        self.assertTrue(evaluate(Request("iam:ListRoles", "*", {"aws:RequestedRegion": "us-east-1"}),
                                 identity, scps=scps).allowed, "グローバルサービスは除外している")
        # 各階層で許可が必要: 下位の OU が s3 だけを許可していれば、それが上限になる
        narrow = [[policy(FULL_ACCESS)], [policy(s3_only)]]
        self.assertEqual(evaluate(Request("ec2:RunInstances", "*", tokyo), identity, scps=narrow),
                         Decision(False, "scp"))
        self.assertTrue(evaluate(Request("s3:GetObject", "*", tokyo), identity, scps=narrow).allowed)
        # 上位の階層に Allow がなければ、下位で許可しても使えない
        missing_root = [[], [policy(FULL_ACCESS)]]
        self.assertEqual(evaluate(Request("s3:GetObject", "*"), identity, scps=missing_root).reason, "scp")

    def test_scp_does_not_grant(self):
        scps = [[policy(FULL_ACCESS)]]
        self.assertEqual(evaluate(Request("s3:GetObject", "*"), [], scps=scps), Decision(False, "implicit_deny"))

    def test_invalid_policies(self):
        bad = [
            policy({"Effect": "Permit", "Action": "*", "Resource": "*"}),
            policy({"Action": "*", "Resource": "*"}),
            policy({"Effect": "Allow", "Action": "*", "NotAction": "iam:*", "Resource": "*"}),
            policy({"Effect": "Allow", "Resource": "*"}),
            policy({"Effect": "Allow", "Action": "*"}),
            {"Version": "2012-10-17"},
        ]
        for p in bad:
            with self.assertRaises(ValueError, msg=str(p)):
                evaluate(Request("s3:GetObject", "x"), [p])
        # 評価の結果に関係なく、不正なポリシーは検出する（Deny が先に見つかっても）
        with self.assertRaises(ValueError):
            evaluate(Request("s3:GetObject", "x"), [policy({"Effect": "Deny", "Action": "*", "Resource": "*"}),
                                                    policy({"Effect": "Allow", "Action": "*"})])


if __name__ == "__main__":
    unittest.main()
