"""11.1 脅威モデリング（threatmodel）— テスト

実行: python3 tools/check.py 11.1   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest

from threatmodel import (
    CATEGORY_NAMES,
    MITIGATIONS,
    Element,
    Flow,
    Threat,
    ThreatModel,
    crosses_trust_boundary,
    exposure,
    generate_threats,
    prioritize,
    render_checklist,
    stride_for_element,
    validate_model,
)


def sample_model() -> ThreatModel:
    """経費精算サービスを単純化した DFD（README の図と同じもの）。"""
    zones = {"internet": 0, "partner": 1, "app": 2, "data": 3}
    elements = [
        Element("user", "利用者のブラウザ", "external_entity", "internet", 3, frozenset({"authn"})),
        Element("web", "経費精算API", "process", "app", 4, frozenset({"input_validation", "authz"})),
        Element("db", "経費データベース", "data_store", "data", 5, frozenset({"encryption"})),
        Element("audit", "監査ログ", "data_store", "data", 3, is_log=True),
        Element("bank", "銀行API", "external_entity", "partner", 4, frozenset({"authn"})),
    ]
    flows = [
        Flow("f1", "user", "web", "経費の申請", 4, frozenset({"tls"})),
        Flow("f2", "web", "user", "申請結果の表示", 3, frozenset({"tls"})),
        Flow("f3", "web", "db", "経費データの読み書き", 5),
        Flow("f4", "web", "audit", "操作ログの記録", 3),
        Flow("f5", "web", "bank", "振込依頼", 5, frozenset({"tls", "signing"})),
    ]
    return ThreatModel(zones, elements, flows)


def by_id(threats):
    return {t.id: t for t in threats}


class TestExercise1Model(unittest.TestCase):
    def test_stride_per_element_table(self):
        self.assertEqual(stride_for_element(Element("u", "利用者", "external_entity", "z")), "SR")
        self.assertEqual(stride_for_element(Element("p", "API", "process", "z")), "STRIDE")
        self.assertEqual(stride_for_element(Element("d", "DB", "data_store", "z")), "TID")
        self.assertEqual(
            stride_for_element(Element("l", "監査ログ", "data_store", "z", is_log=True)),
            "TRID",
            "監査ログのストアには否認（R）の脅威も加わる",
        )

    def test_crosses_trust_boundary(self):
        m = sample_model()
        flows = {f.id: f for f in m.flows}
        self.assertTrue(crosses_trust_boundary(m, flows["f1"]))
        self.assertTrue(crosses_trust_boundary(m, flows["f3"]))
        same_zone = ThreatModel(
            {"app": 2},
            [Element("a", "A", "process", "app"), Element("b", "B", "process", "app")],
            [Flow("x", "a", "b", "内部呼び出し")],
        )
        self.assertFalse(crosses_trust_boundary(same_zone, same_zone.flows[0]))

    def test_valid_model_passes(self):
        validate_model(sample_model())  # 例外が出なければよい

    def test_invalid_models_are_rejected(self):
        def model_with(elements=None, flows=None, zones=None):
            base = sample_model()
            return ThreatModel(
                zones if zones is not None else base.zones,
                elements if elements is not None else base.elements,
                flows if flows is not None else base.flows,
            )

        base = sample_model()
        cases = {
            "IDの重複": model_with(elements=base.elements + [Element("web", "重複", "process", "app")]),
            "要素とフローのIDの重複": model_with(flows=base.flows + [Flow("db", "web", "db", "x")]),
            "未知の種類": model_with(elements=base.elements + [Element("q", "Q", "queue", "app")]),
            "未定義のゾーン": model_with(elements=base.elements + [Element("q", "Q", "process", "moon")]),
            "未知の対策": model_with(
                elements=base.elements + [Element("q", "Q", "process", "app", 3, frozenset({"magic"}))]
            ),
            "sensitivity=0": model_with(elements=base.elements + [Element("q", "Q", "process", "app", 0)]),
            "sensitivity=6": model_with(elements=base.elements + [Element("q", "Q", "process", "app", 6)]),
            "sensitivity=True": model_with(
                elements=base.elements + [Element("q", "Q", "process", "app", True)]
            ),
            "is_logはデータストアのみ": model_with(
                elements=base.elements + [Element("q", "Q", "process", "app", is_log=True)]
            ),
            "未定義の要素を参照": model_with(flows=base.flows + [Flow("f9", "web", "nowhere", "x")]),
            "自己ループ": model_with(flows=base.flows + [Flow("f9", "web", "web", "x")]),
            "プロセスを経ないフロー": model_with(flows=base.flows + [Flow("f9", "user", "db", "直接書き込み")]),
            "フローのsensitivity": model_with(flows=base.flows + [Flow("f9", "web", "db", "x", 9)]),
            "負のtrust": model_with(zones={**base.zones, "app": -1}),
        }
        for label, model in cases.items():
            with self.assertRaises(ValueError, msg=label):
                validate_model(model)


class TestExercise2Threats(unittest.TestCase):
    def test_exposure_levels(self):
        m = sample_model()
        expected = {
            "user": 2,  # 要素自身がインターネット（trust 0）にある
            "web": 2,  # インターネットと直接やり取りする
            "db": 1,  # 別ゾーン（app）とやり取りする
            "audit": 1,
            "bank": 1,
            "f1": 2,  # インターネットとの境界をまたぐフロー
            "f2": 2,
            "f3": 1,
            "f5": 1,
        }
        for target, level in expected.items():
            self.assertEqual(exposure(m, target), level, target)

    def test_exposure_zero_inside_single_zone(self):
        m = ThreatModel(
            {"app": 2},
            [Element("a", "A", "process", "app"), Element("s", "S", "data_store", "app")],
            [Flow("x", "a", "s", "書き込み")],
        )
        self.assertEqual(exposure(m, "a"), 0)
        self.assertEqual(exposure(m, "x"), 0)
        threats = generate_threats(m)
        self.assertEqual(len(threats), 6 + 3, "境界をまたがないフローからは脅威を生成しない")
        self.assertTrue(all(t.likelihood == 3 for t in threats), "露出なし・対策なしなら発生可能性は 3")

    def test_threat_count_and_ids(self):
        threats = generate_threats(sample_model())
        # 要素: 2 + 6 + 3 + 4 + 2 = 17、境界をまたぐフロー 5 本 × 3 = 15
        self.assertEqual(len(threats), 32)
        self.assertEqual([t.id for t in threats], [f"T{i:03d}" for i in range(1, 33)])
        self.assertTrue(all(isinstance(t, Threat) for t in threats))

    def test_generation_order_and_categories(self):
        threats = generate_threats(sample_model())
        got = [(t.target_id, t.category) for t in threats]
        expected = (
            [("user", c) for c in "SR"]
            + [("web", c) for c in "STRIDE"]
            + [("db", c) for c in "TID"]
            + [("audit", c) for c in "TRID"]
            + [("bank", c) for c in "SR"]
            + [(f, c) for f in ("f1", "f2", "f3", "f4", "f5") for c in "TID"]
        )
        self.assertEqual(got, expected)

    def test_likelihood_impact_and_controls(self):
        t = by_id(generate_threats(sample_model()))
        # (発生可能性, 影響度, 既存の対策)
        expected = {
            "T001": (4, 3, ("authn",)),  # 利用者のなりすまし: 3 + 2 - 1（authn）
            "T002": (5, 3, ()),  # 利用者の否認: 対策なし
            "T003": (5, 4, ()),
            "T004": (4, 4, ("input_validation",)),
            "T006": (4, 4, ("authz",)),
            "T008": (3, 4, ("authz", "input_validation")),  # 権限昇格: 2 つの対策が効く
            "T009": (4, 5, ()),
            "T010": (3, 5, ("encryption",)),
            "T016": (3, 4, ("authn",)),
            "T018": (4, 4, ("tls",)),
            "T030": (2, 5, ("signing", "tls")),  # 振込依頼の改ざん: tls と signing
            "T031": (3, 5, ("tls",)),
            "T032": (4, 5, ()),
        }
        for tid, (likelihood, impact, controls) in expected.items():
            self.assertEqual((t[tid].likelihood, t[tid].impact, t[tid].existing_controls),
                             (likelihood, impact, controls), tid)
        self.assertEqual(t["T008"].score, 12)
        self.assertEqual(t["T008"].priority, "中")
        self.assertEqual(t["T009"].priority, "高")
        self.assertEqual(t["T030"].score, 10)

    def test_likelihood_never_below_one(self):
        m = ThreatModel(
            {"app": 2},
            [
                Element("p", "P", "process", "app", 2, frozenset({"authz", "input_validation", "least_privilege", "sandbox"})),
            ],
            [],
        )
        e = [t for t in generate_threats(m) if t.category == "E"][0]
        self.assertEqual(e.likelihood, 1, "3 - 4 = -1 でも下限は 1")
        self.assertEqual(e.priority, "低")

    def test_generate_validates_first(self):
        bad = ThreatModel({"z": 0}, [Element("a", "A", "robot", "z")], [])
        with self.assertRaises(ValueError):
            generate_threats(bad)

    def test_threat_labels(self):
        t = by_id(generate_threats(sample_model()))
        self.assertEqual(t["T003"].category_name, CATEGORY_NAMES["S"])
        self.assertEqual(t["T003"].mitigation, MITIGATIONS["S"])
        self.assertEqual(t["T003"].target_name, "経費精算API")


class TestExercise3Prioritize(unittest.TestCase):
    def test_order(self):
        ordered = prioritize(generate_threats(sample_model()))
        self.assertEqual(
            [t.id for t in ordered[:10]],
            # 20 点のうち影響度 5 → 影響度 4 の順、同点は ID 順
            ["T009", "T011", "T024", "T025", "T026", "T032", "T003", "T005", "T007", "T020"],
        )
        self.assertEqual(ordered[-1].id, "T030")
        scores = [t.score for t in ordered]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_top(self):
        threats = generate_threats(sample_model())
        self.assertEqual([t.id for t in prioritize(threats, top=3)], ["T009", "T011", "T024"])
        self.assertEqual(len(prioritize(threats, top=100)), 32)
        self.assertEqual(prioritize([], top=3), [])

    def test_prioritize_does_not_mutate_input(self):
        threats = generate_threats(sample_model())
        before = [t.id for t in threats]
        prioritize(threats)
        self.assertEqual([t.id for t in threats], before)

    def test_checklist_format(self):
        text = render_checklist(generate_threats(sample_model()))
        lines = text.splitlines()
        self.assertTrue(text.endswith("\n"))
        self.assertEqual(lines[0], "# 対策チェックリスト（32 件）")
        self.assertEqual(len(lines), 33)
        self.assertEqual(
            lines[1],
            "- [ ] [高/20] T009 改ざん（Tampering） — 経費データベース: " + MITIGATIONS["T"],
        )
        self.assertEqual(
            lines[-1],
            "- [ ] [中/10] T030 改ざん（Tampering） — 振込依頼: " + MITIGATIONS["T"]
            + "（既存の対策: signing, tls）",
        )

    def test_checklist_empty(self):
        self.assertEqual(render_checklist([]), "# 対策チェックリスト（0 件）\n")


if __name__ == "__main__":
    unittest.main()
