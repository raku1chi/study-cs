"""14.5 ガバナンス・リスク・コンプライアンスと法務 — テスト（license_policy.py）

実行: python3 tools/check.py 14.5   （またはこのディレクトリで python3 -m unittest -v test_license_policy）
"""
import random
import unittest

from license_policy import (
    DEFAULT_POLICY,
    And,
    Evaluation,
    License,
    Or,
    Policy,
    audit,
    evaluate,
    license_category,
    overall_decision,
    parse,
    to_spdx,
    tokenize,
)

MIT = License("MIT")
APACHE = License("Apache-2.0")
BSD3 = License("BSD-3-Clause")


class TestTokenize(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(
            tokenize("(MIT OR Apache-2.0) AND GPL-2.0+"),
            ["(", "MIT", "OR", "Apache-2.0", ")", "AND", "GPL-2.0+"],
        )
        self.assertEqual(tokenize("(MIT)"), ["(", "MIT", ")"])
        self.assertEqual(tokenize("  MIT  "), ["MIT"])
        self.assertEqual(
            tokenize("DocumentRef-spdx-tool-1.2:LicenseRef-MIT-Style-2"),
            ["DocumentRef-spdx-tool-1.2:LicenseRef-MIT-Style-2"],
        )
        self.assertEqual(tokenize(""), [])

    def test_invalid_characters(self):
        for bad in ["MIT/Apache-2.0", "MIT, BSD-3-Clause", "GPL-2.0 +", "GPL-2.0++", "ＭＩＴ", "MIT & BSD-3-Clause"]:
            with self.assertRaises(ValueError, msg=bad):
                tokenize(bad)


class TestParse(unittest.TestCase):
    def test_single_and_canonical_case(self):
        self.assertEqual(parse("MIT"), MIT)
        self.assertEqual(parse("mit"), MIT)
        self.assertEqual(parse("apache-2.0"), APACHE)
        self.assertEqual(parse("LicenseRef-Proprietary"), License("LicenseRef-Proprietary"))

    def test_precedence_and_before_or(self):
        self.assertEqual(parse("MIT OR Apache-2.0 AND BSD-3-Clause"), Or((MIT, And((APACHE, BSD3)))))
        self.assertEqual(parse("MIT AND Apache-2.0 OR BSD-3-Clause"), Or((And((MIT, APACHE)), BSD3)))

    def test_parentheses_override_precedence(self):
        self.assertEqual(parse("(MIT OR Apache-2.0) AND BSD-3-Clause"), And((Or((MIT, APACHE)), BSD3)))
        self.assertEqual(parse("((MIT))"), MIT)

    def test_flattening(self):
        self.assertEqual(parse("MIT AND Apache-2.0 AND BSD-3-Clause"), And((MIT, APACHE, BSD3)))
        self.assertEqual(parse("(MIT AND Apache-2.0) AND BSD-3-Clause"), And((MIT, APACHE, BSD3)))
        self.assertEqual(parse("MIT OR (Apache-2.0 OR BSD-3-Clause)"), Or((MIT, APACHE, BSD3)))

    def test_with_and_plus(self):
        self.assertEqual(
            parse("GPL-2.0-only WITH classpath-exception-2.0"),
            License("GPL-2.0-only", exception="Classpath-exception-2.0"),
        )
        self.assertEqual(parse("GPL-2.0+"), License("GPL-2.0", or_later=True))
        self.assertEqual(
            parse("MIT OR GPL-2.0+ WITH GCC-exception-3.1"),
            Or((MIT, License("GPL-2.0", or_later=True, exception="GCC-exception-3.1"))),
        )
        # WITH は AND より強く結合する
        self.assertEqual(
            parse("Apache-2.0 WITH LLVM-exception AND MIT"),
            And((License("Apache-2.0", exception="LLVM-exception"), MIT)),
        )

    def test_syntax_errors(self):
        bad = [
            "", "   ", "MIT AND", "AND MIT", "MIT OR OR Apache-2.0", "(MIT", "MIT)", "()",
            "MIT Apache-2.0", "mit and apache-2.0", "MIT WITH", "WITH Classpath-exception-2.0",
            "(MIT OR Apache-2.0) WITH Classpath-exception-2.0", "GPL-2.0 WITH AND",
            "GPL-2.0 WITH Classpath-exception-2.0+", "MIT/Apache-2.0", "MIT AND (Apache-2.0",
        ]
        for expr in bad:
            with self.assertRaises(ValueError, msg=repr(expr)):
                parse(expr)


class TestToSpdx(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(to_spdx(Or((MIT, And((APACHE, BSD3))))), "MIT OR Apache-2.0 AND BSD-3-Clause")
        self.assertEqual(
            to_spdx(And((MIT, Or((APACHE, License("GPL-2.0", or_later=True)))))),
            "MIT AND (Apache-2.0 OR GPL-2.0+)",
        )
        self.assertEqual(
            to_spdx(License("GPL-2.0-only", exception="Classpath-exception-2.0")),
            "GPL-2.0-only WITH Classpath-exception-2.0",
        )

    def test_round_trip_on_random_trees(self):
        rng = random.Random(14)
        ids = ["MIT", "Apache-2.0", "BSD-3-Clause", "GPL-2.0-only", "LGPL-2.1-or-later", "LicenseRef-X"]

        def random_tree(depth):
            if depth == 0 or rng.random() < 0.3:
                exc = "Classpath-exception-2.0" if rng.random() < 0.2 else None
                return License(rng.choice(ids), rng.random() < 0.2, exc)
            cls = rng.choice([And, Or])
            children = []
            for _ in range(rng.randint(2, 3)):
                child = random_tree(depth - 1)
                # 平坦化の規則に合わせて、同じ種類の子は持たせない
                children.extend(child.items if isinstance(child, cls) else [child])
            return cls(tuple(children))

        for _ in range(300):
            tree = random_tree(4)
            self.assertEqual(parse(to_spdx(tree)), tree, to_spdx(tree))


class TestCategory(unittest.TestCase):
    def test_basic_categories(self):
        self.assertEqual(license_category(MIT), ("permissive", []))
        self.assertEqual(license_category(License("AGPL-3.0-only")), ("network-copyleft", []))
        self.assertEqual(license_category(License("BUSL-1.1")), ("source-available", []))
        self.assertEqual(license_category(License("gpl-3.0-only")), ("strong-copyleft", []))
        self.assertEqual(license_category(License("LicenseRef-Foo")), ("unknown", []))
        # "+" はカテゴリに影響しない
        self.assertEqual(license_category(License("GPL-2.0", or_later=True)), ("strong-copyleft", []))

    def test_exceptions(self):
        self.assertEqual(
            license_category(License("GPL-2.0-only", exception="Classpath-exception-2.0")),
            ("weak-copyleft", []),
        )
        # 例外は条件を緩めるだけで、厳しくはしない
        self.assertEqual(license_category(License("Apache-2.0", exception="LLVM-exception")), ("permissive", []))
        self.assertEqual(
            license_category(License("MIT", exception="Classpath-exception-2.0")), ("permissive", [])
        )
        # ソース公開型や未知のライセンスは例外で変えない
        self.assertEqual(
            license_category(License("SSPL-1.0", exception="LLVM-exception")), ("source-available", [])
        )
        category, notes = license_category(License("GPL-3.0-only", exception="Foo-exception"))
        self.assertEqual(category, "strong-copyleft")
        self.assertEqual(notes, ["未知の例外 Foo-exception は考慮しない"])


class TestEvaluate(unittest.TestCase):
    def test_single_licenses_per_model(self):
        expected = {
            "MIT": ("allowed", "allowed", "allowed"),
            "LGPL-2.1-only": ("allowed", "allowed", "review"),
            "GPL-3.0-only": ("allowed", "review", "prohibited"),
            "AGPL-3.0-only": ("review", "prohibited", "prohibited"),
            "BUSL-1.1": ("review", "review", "review"),
            "LicenseRef-Foo": ("review", "review", "review"),
        }
        for expr, decisions in expected.items():
            for model, decision in zip(("internal", "saas", "distributed"), decisions):
                self.assertEqual(evaluate(expr, model).decision, decision, (expr, model))

    def test_reason_format(self):
        ev = evaluate("GPL-3.0-only", "saas")
        self.assertEqual(ev, Evaluation("review", ("GPL-3.0-only",),
                                        ("GPL-3.0-only: 強いコピーレフト → 要レビュー（SaaS）",)))

    def test_or_chooses_the_most_favorable(self):
        ev = evaluate("AGPL-3.0-only OR MIT", "saas")
        self.assertEqual((ev.decision, ev.licenses), ("allowed", ("MIT",)))
        self.assertEqual(ev.reasons[-1], "OR の選択肢から MIT を選択")
        # 同じ判定なら先に書かれた方
        self.assertEqual(evaluate("Apache-2.0 OR MIT", "distributed").licenses, ("Apache-2.0",))

    def test_and_takes_the_worst_and_all_licenses(self):
        ev = evaluate("MIT AND GPL-2.0-only AND MIT", "distributed")
        self.assertEqual(ev.decision, "prohibited")
        self.assertEqual(ev.licenses, ("MIT", "GPL-2.0-only"))
        self.assertEqual(len(ev.reasons), 3)

    def test_nested_expression(self):
        ev = evaluate("(MIT AND BSD-3-Clause) OR GPL-2.0-or-later", "distributed")
        self.assertEqual(ev.decision, "allowed")
        self.assertEqual(ev.licenses, ("MIT", "BSD-3-Clause"))
        self.assertEqual(
            ev.reasons,
            (
                "MIT: パーミッシブ → 許可（配布）",
                "BSD-3-Clause: パーミッシブ → 許可（配布）",
                "OR の選択肢から MIT AND BSD-3-Clause を選択",
            ),
        )

    def test_exception_changes_decision(self):
        self.assertEqual(evaluate("GPL-2.0-only", "distributed").decision, "prohibited")
        self.assertEqual(
            evaluate("GPL-2.0-only WITH Classpath-exception-2.0", "distributed").decision, "review"
        )
        ev = evaluate("GPL-2.0-only WITH Unknown-exception", "distributed")
        self.assertEqual(ev.decision, "prohibited")
        self.assertIn("未知の例外 Unknown-exception は考慮しない", ev.reasons)

    def test_accepts_tree_and_custom_policy(self):
        self.assertEqual(evaluate(Or((License("AGPL-3.0-only"), MIT)), "saas").decision, "allowed")
        strict = Policy(
            categories={"MIT": "permissive"},
            exceptions={},
            rules={"permissive": {"internal": "allowed", "saas": "allowed", "distributed": "review"}},
            unknown_decision="prohibited",
        )
        self.assertEqual(evaluate("MIT", "distributed", strict).decision, "review")
        self.assertEqual(evaluate("Apache-2.0", "internal", strict).decision, "prohibited")

    def test_errors(self):
        with self.assertRaises(ValueError):
            evaluate("MIT", "on-premise")
        with self.assertRaises(ValueError):
            evaluate("MIT AND", "saas")


class TestAudit(unittest.TestCase):
    DEPS = {
        "web-framework": "MIT",
        "crypto-lib": "Apache-2.0 OR MIT",
        "image-codec": "(MIT AND BSD-3-Clause) OR GPL-2.0-or-later",
        "jdbc-driver": "GPL-2.0-only WITH Classpath-exception-2.0",
        "pdf-engine": "AGPL-3.0-only",
        "search-server": "SSPL-1.0 OR Elastic-2.0 OR AGPL-3.0-only",
        "legacy-widget": "LicenseRef-Proprietary-Vendor",
        "bad-metadata": "MIT/Apache-2.0",
    }

    def test_order_and_decisions_for_distribution(self):
        findings = audit(self.DEPS, "distributed")
        self.assertEqual(
            [(f.package, f.evaluation.decision) for f in findings],
            [
                ("pdf-engine", "prohibited"),
                ("bad-metadata", "review"),
                ("jdbc-driver", "review"),
                ("legacy-widget", "review"),
                ("search-server", "review"),
                ("crypto-lib", "allowed"),
                ("image-codec", "allowed"),
                ("web-framework", "allowed"),
            ],
        )
        self.assertEqual(overall_decision(findings), "prohibited")

    def test_saas_and_internal(self):
        saas = {f.package: f.evaluation.decision for f in audit(self.DEPS, "saas")}
        self.assertEqual(saas["jdbc-driver"], "allowed")
        self.assertEqual(saas["pdf-engine"], "prohibited")
        self.assertEqual(saas["search-server"], "review")
        internal = audit(self.DEPS, "internal")
        self.assertEqual(overall_decision(internal), "review")

    def test_broken_expression_becomes_review(self):
        (finding,) = audit({"bad-metadata": "MIT/Apache-2.0"}, "saas")
        self.assertEqual(finding.evaluation.decision, "review")
        self.assertEqual(finding.evaluation.licenses, ())
        self.assertTrue(finding.evaluation.reasons[0].startswith("ライセンス式を解釈できない: "))

    def test_empty_and_invalid_model(self):
        self.assertEqual(audit({}, "saas"), [])
        self.assertEqual(overall_decision([]), "allowed")
        with self.assertRaises(ValueError):
            audit({"x": "MIT"}, "cloud")

    def test_default_policy_matrix(self):
        # すべてのカテゴリに 3 つの提供形態の判定があり、evaluate がその表どおりに判定すること
        representatives = {
            "permissive": "MIT",
            "weak-copyleft": "MPL-2.0",
            "strong-copyleft": "GPL-2.0-only",
            "network-copyleft": "AGPL-3.0-or-later",
            "source-available": "Elastic-2.0",
        }
        for category, rules in DEFAULT_POLICY.rules.items():
            self.assertEqual(set(rules), {"internal", "saas", "distributed"}, category)
            for model, decision in rules.items():
                self.assertEqual(
                    evaluate(representatives[category], model).decision, decision, (category, model)
                )


if __name__ == "__main__":
    unittest.main()
