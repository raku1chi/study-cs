"""9.4 API設計 — 後方互換性の検査のテスト

実行: python3 tools/check.py 9.4   （またはこのディレクトリで python3 -m unittest -v）
"""
import copy
import unittest

from api_compat import Change, diff_schemas, format_report, is_backward_compatible

V1 = {
    "endpoints": {
        "POST /orders": {
            "request": {
                "items": {"type": "array", "required": True, "items": {"type": "object", "fields": {
                    "sku": {"type": "string", "required": True},
                    "quantity": {"type": "integer", "required": True},
                }}},
                "coupon": {"type": "string"},
                "payment_method": {"type": "string", "required": True, "enum": ["card", "bank_transfer"]},
                "note": {"type": "string"},
            },
            "response": {
                "id": {"type": "string", "required": True},
                "status": {"type": "string", "required": True, "enum": ["pending", "paid"]},
                "total": {"type": "integer", "required": True},
                "channel": {"type": "string"},
                "shipping": {"type": "object", "fields": {
                    "method": {"type": "string", "required": True},
                    "eta_days": {"type": "integer"},
                }},
            },
        },
        "GET /orders/{id}": {
            "response": {"id": {"type": "string", "required": True}},
        },
        "DELETE /orders/{id}": {},
    }
}


def v2(mutate):
    schema = copy.deepcopy(V1)
    mutate(schema)
    return schema


def req(schema):
    return schema["endpoints"]["POST /orders"]["request"]


def res(schema):
    return schema["endpoints"]["POST /orders"]["response"]


def summary(changes):
    return [(c.endpoint, c.location, c.path, c.kind, c.breaking) for c in changes]


class TestExercise4Basics(unittest.TestCase):
    def test_identical_schemas(self):
        self.assertEqual(diff_schemas(V1, copy.deepcopy(V1)), [])
        self.assertTrue(is_backward_compatible(V1, V1))

    def test_additive_changes_are_compatible(self):
        def mutate(s):
            req(s)["gift_message"] = {"type": "string"}                          # 任意の入力
            res(s)["points_earned"] = {"type": "integer", "required": True}      # 出力の追加
            s["endpoints"]["GET /orders"] = {"response": {"count": {"type": "integer"}}}
        changes = diff_schemas(V1, v2(mutate))
        self.assertEqual(summary(changes), [
            ("GET /orders", "endpoint", "", "endpoint-added", False),
            ("POST /orders", "request", "gift_message", "field-added", False),
            ("POST /orders", "response", "points_earned", "field-added", False),
        ])
        self.assertTrue(is_backward_compatible(V1, v2(mutate)))

    def test_required_request_field_is_breaking(self):
        new = v2(lambda s: req(s).__setitem__("store_id", {"type": "string", "required": True}))
        self.assertEqual(summary(diff_schemas(V1, new)),
                         [("POST /orders", "request", "store_id", "field-added", True)])
        self.assertFalse(is_backward_compatible(V1, new))

    def test_removals_are_breaking(self):
        def mutate(s):
            del s["endpoints"]["DELETE /orders/{id}"]
            del req(s)["note"]
            del res(s)["channel"]  # 任意のフィールドでも、読んでいるクライアントがいれば壊れる
        self.assertEqual(summary(diff_schemas(V1, v2(mutate))), [
            ("DELETE /orders/{id}", "endpoint", "", "endpoint-removed", True),
            ("POST /orders", "request", "note", "field-removed", True),
            ("POST /orders", "response", "channel", "field-removed", True),
        ])

    def test_missing_body_counts_as_no_fields(self):
        new = v2(lambda s: s["endpoints"]["GET /orders/{id}"].pop("response"))
        self.assertEqual(summary(diff_schemas(V1, new)),
                         [("GET /orders/{id}", "response", "id", "field-removed", True)])
        added = v2(lambda s: s["endpoints"]["DELETE /orders/{id}"].update(
            request={"reason": {"type": "string"}}))
        self.assertEqual(summary(diff_schemas(V1, added)),
                         [("DELETE /orders/{id}", "request", "reason", "field-added", False)])


class TestExercise4Direction(unittest.TestCase):
    def test_required_changes_depend_on_direction(self):
        def mutate(s):
            req(s)["coupon"]["required"] = True           # 入力: 任意 → 必須（破壊的）
            req(s)["payment_method"]["required"] = False  # 入力: 必須 → 任意（互換）
            res(s)["total"]["required"] = False           # 出力: 必須 → 任意（破壊的）
            res(s)["channel"]["required"] = True          # 出力: 任意 → 必須（互換）
        self.assertEqual(summary(diff_schemas(V1, v2(mutate))), [
            ("POST /orders", "request", "coupon", "made-required", True),
            ("POST /orders", "request", "payment_method", "made-optional", False),
            ("POST /orders", "response", "channel", "made-required", False),
            ("POST /orders", "response", "total", "made-optional", True),
        ])

    def test_enum_asymmetry(self):
        add_values = v2(lambda s: (req(s)["payment_method"]["enum"].append("convenience_store"),
                                   res(s)["status"]["enum"].append("refunded")))
        self.assertEqual(summary(diff_schemas(V1, add_values)), [
            ("POST /orders", "request", "payment_method", "enum-values-added", False),
            ("POST /orders", "response", "status", "enum-values-added", True),
        ])
        remove_values = v2(lambda s: (req(s)["payment_method"]["enum"].remove("bank_transfer"),
                                      res(s)["status"]["enum"].remove("pending")))
        self.assertEqual(summary(diff_schemas(V1, remove_values)), [
            ("POST /orders", "request", "payment_method", "enum-values-removed", True),
            ("POST /orders", "response", "status", "enum-values-removed", False),
        ])

    def test_enum_values_added_and_removed_at_once(self):
        new = v2(lambda s: res(s)["status"].__setitem__("enum", ["pending", "captured"]))
        self.assertEqual(summary(diff_schemas(V1, new)), [
            ("POST /orders", "response", "status", "enum-values-added", True),
            ("POST /orders", "response", "status", "enum-values-removed", False),
        ])

    def test_enum_constraint_added_or_removed(self):
        def mutate(s):
            req(s)["coupon"]["enum"] = ["WELCOME", "SUMMER"]   # 入力の制限を追加（破壊的）
            del req(s)["payment_method"]["enum"]               # 入力の制限を撤廃（互換）
            res(s)["channel"]["enum"] = ["web", "app"]         # 出力の制限を追加（互換）
            del res(s)["status"]["enum"]                       # 出力の制限を撤廃（破壊的）
        self.assertEqual(summary(diff_schemas(V1, v2(mutate))), [
            ("POST /orders", "request", "coupon", "enum-added", True),
            ("POST /orders", "request", "payment_method", "enum-removed", False),
            ("POST /orders", "response", "channel", "enum-added", False),
            ("POST /orders", "response", "status", "enum-removed", True),
        ])

    def test_type_changes(self):
        def mutate(s):
            req(s)["note"] = {"type": "integer"}                                   # string → integer
            res(s)["total"] = {"type": "number", "required": True}                 # 出力を広げる（破壊的）
            req(s)["items"]["items"]["fields"]["quantity"] = {"type": "number", "required": True}  # 入力を広げる
            res(s)["id"] = {"type": "integer", "required": False}                  # 型が変わったら他は見ない
        self.assertEqual(summary(diff_schemas(V1, v2(mutate))), [
            ("POST /orders", "request", "items[].quantity", "type-changed", False),
            ("POST /orders", "request", "note", "type-changed", True),
            ("POST /orders", "response", "id", "type-changed", True),
            ("POST /orders", "response", "total", "type-changed", True),
        ])
        # 逆向き（number → integer に狭める）は、入力なら破壊的・出力なら互換
        back = {c.path: c.breaking for c in diff_schemas(v2(mutate), V1) if c.kind == "type-changed"}
        self.assertEqual(back["items[].quantity"], True)
        self.assertEqual(back["total"], False)


class TestExercise4Nested(unittest.TestCase):
    def test_nested_paths(self):
        def mutate(s):
            fields = req(s)["items"]["items"]["fields"]
            fields["gift_wrap"] = {"type": "boolean", "required": True}
            del res(s)["shipping"]["fields"]["eta_days"]
            res(s)["shipping"]["fields"]["carrier"] = {"type": "string"}
        self.assertEqual(summary(diff_schemas(V1, v2(mutate))), [
            ("POST /orders", "request", "items[].gift_wrap", "field-added", True),
            ("POST /orders", "response", "shipping.carrier", "field-added", False),
            ("POST /orders", "response", "shipping.eta_days", "field-removed", True),
        ])

    def test_array_item_type_change(self):
        schema = {"endpoints": {"GET /tags": {"response": {
            "tags": {"type": "array", "items": {"type": "string", "enum": ["a", "b"]}}}}}}
        new = copy.deepcopy(schema)
        new["endpoints"]["GET /tags"]["response"]["tags"]["items"]["enum"].append("c")
        self.assertEqual(summary(diff_schemas(schema, new)),
                         [("GET /tags", "response", "tags[]", "enum-values-added", True)])
        new2 = copy.deepcopy(schema)
        new2["endpoints"]["GET /tags"]["response"]["tags"]["items"] = {"type": "integer"}
        self.assertEqual(summary(diff_schemas(schema, new2)),
                         [("GET /tags", "response", "tags[]", "type-changed", True)])


class TestExercise4Validation(unittest.TestCase):
    def test_invalid_schemas_raise(self):
        bad_schemas = [
            {},
            {"endpoints": {"orders": {}}},
            {"endpoints": {"FETCH /orders": {}}},
            {"endpoints": {"GET /x": {"body": {}}}},
            {"endpoints": {"GET /x": {"response": {"a": {"type": "str"}}}}},
            {"endpoints": {"GET /x": {"response": {"a": {"type": "string", "requird": True}}}}},
            {"endpoints": {"GET /x": {"response": {"a": {"type": "object"}}}}},
            {"endpoints": {"GET /x": {"response": {"a": {"type": "string", "fields": {}}}}}},
            {"endpoints": {"GET /x": {"response": {"a": {"type": "boolean", "enum": [True]}}}}},
            {"endpoints": {"GET /x": {"response": {"a": {"type": "string", "required": "yes"}}}}},
            {"endpoints": {"GET /x": {"response": {"a": {"type": "array", "items": {
                "type": "string", "required": True}}}}}},
        ]
        for bad in bad_schemas:
            with self.assertRaises(ValueError, msg=repr(bad)):
                diff_schemas(V1, bad)
            with self.assertRaises(ValueError, msg=repr(bad)):
                diff_schemas(bad, V1)


class TestExercise4Report(unittest.TestCase):
    def test_changes_are_sorted_and_reported(self):
        def mutate(s):
            del s["endpoints"]["DELETE /orders/{id}"]
            res(s)["status"]["enum"].append("refunded")
            req(s)["gift_message"] = {"type": "string"}
        changes = diff_schemas(V1, v2(mutate))
        self.assertEqual(changes, sorted(changes))
        self.assertIsInstance(changes[0], Change)
        text = format_report(changes)
        self.assertIn("[破壊的] POST /orders response status:", text)
        self.assertEqual(text.splitlines()[-1], "破壊的な変更 2 件 / 互換な変更 1 件")


if __name__ == "__main__":
    unittest.main()
