"""12.4 演習2: エージェントループ — テスト

実行: python3 tools/check.py 12.4   （またはこのディレクトリで python3 -m unittest -v test_agent_loop）
LLM の代わりに、決められた応答を順に返す ScriptedLLM を使うので、結果は常に同じです。
"""
import json
import unittest

from agent_loop import (
    AgentResult,
    ModelTurn,
    ScriptedLLM,
    Tool,
    ToolCall,
    ToolRegistry,
    run_agent,
    validate_arguments,
)

SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 50},
        "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
    },
    "required": ["query"],
    "additionalProperties": False,
}
EMAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "to": {"type": "string"},
        "subject": {"type": "string"},
        "priority": {"type": "string", "enum": ["low", "normal", "high"]},
        "cc": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["to", "subject"],
}


def make_registry(log):
    registry = ToolRegistry()

    def search_handbook(query, top_k=3):
        log.append(("search_handbook", query, top_k))
        return [f"{query} に関する規程 {i + 1}" for i in range(top_k)]

    def send_email(to, subject, priority="normal", cc=None):
        log.append(("send_email", to, subject))
        return {"status": "sent", "to": to}

    def flaky():
        raise ConnectionError("タイムアウトしました")

    registry.register(Tool("search_handbook", "社内規程を検索する", SEARCH_SCHEMA, search_handbook))
    registry.register(Tool("send_email", "メールを送信する", EMAIL_SCHEMA, send_email, dangerous=True))
    registry.register(Tool("flaky", "よく失敗するツール", {"type": "object", "properties": {}}, flaky))
    return registry


def kinds(result):
    return [e.kind for e in result.trace]


class TestValidation(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_arguments(SEARCH_SCHEMA, {"query": "経費", "top_k": 3}), [])
        self.assertEqual(validate_arguments(SEARCH_SCHEMA, {"query": "経費"}), [])
        self.assertEqual(validate_arguments(EMAIL_SCHEMA, {"to": "a@example.com", "subject": "件名",
                                                           "cc": ["b@example.com"], "extra": 1}), [],
                         "additionalProperties の指定がなければ余分な引数は許す")

    def test_errors_are_reported(self):
        cases = [
            ({}, "query"),  # 必須
            ({"query": 123}, "query"),  # 型
            ({"query": ""}, "query"),  # minLength
            ({"query": "あ" * 51}, "query"),  # maxLength
            ({"query": "x", "top_k": 0}, "top_k"),  # minimum
            ({"query": "x", "top_k": 11}, "top_k"),  # maximum
            ({"query": "x", "top_k": 2.5}, "top_k"),  # integer に小数
            ({"query": "x", "top_k": True}, "top_k"),  # bool は integer ではない
            ({"query": "x", "debug": True}, "debug"),  # additionalProperties: False
        ]
        for args, field in cases:
            errors = validate_arguments(SEARCH_SCHEMA, args)
            self.assertTrue(errors, f"{args} はエラーになるべき")
            self.assertTrue(any(field in e for e in errors), f"エラーに引数名 {field} を含める: {errors}")

    def test_nested_and_enum(self):
        errors = validate_arguments(EMAIL_SCHEMA, {"to": "a", "subject": "s", "priority": "urgent", "cc": ["x", 1]})
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("priority" in e for e in errors))
        self.assertTrue(any("cc[1]" in e for e in errors), errors)

    def test_arguments_must_be_object(self):
        self.assertTrue(validate_arguments(SEARCH_SCHEMA, ["経費"]))


class TestRegistry(unittest.TestCase):
    def test_register_and_schemas(self):
        registry = make_registry([])
        self.assertIsNone(registry.get("unknown"))
        self.assertEqual([s["name"] for s in registry.schemas()], ["flaky", "search_handbook", "send_email"])
        self.assertEqual(registry.schemas()[1]["parameters"], SEARCH_SCHEMA)
        with self.assertRaises(ValueError):
            registry.register(Tool("flaky", "重複", {}, lambda: None))


class TestAgentLoop(unittest.TestCase):
    def setUp(self):
        self.log = []
        self.registry = make_registry(self.log)

    def test_answer_without_tools(self):
        llm = ScriptedLLM([ModelTurn(content="こんにちは")])
        result = run_agent(llm, self.registry, "挨拶して")
        self.assertIsInstance(result, AgentResult)
        self.assertEqual((result.answer, result.stop_reason), ("こんにちは", "final"))
        self.assertEqual(kinds(result), ["model", "final"])
        self.assertEqual(llm.calls[0]["messages"][0]["role"], "system")
        self.assertEqual(llm.calls[0]["messages"][1], {"role": "user", "content": "挨拶して"})
        self.assertEqual([t["name"] for t in llm.calls[0]["tools"]], ["flaky", "search_handbook", "send_email"])

    def test_tool_result_is_fed_back_to_the_model(self):
        llm = ScriptedLLM([
            ModelTurn(tool_calls=(ToolCall("search_handbook", {"query": "経費", "top_k": 2}, "c1"),)),
            ModelTurn(content="経費は翌月10日までに精算します [1]"),
        ])
        result = run_agent(llm, self.registry, "経費精算の締め切りは？")
        self.assertEqual(result.stop_reason, "final")
        self.assertEqual(self.log, [("search_handbook", "経費", 2)])
        tool_msg = llm.calls[1]["messages"][-1]
        self.assertEqual((tool_msg["role"], tool_msg["tool_call_id"], tool_msg["name"]), ("tool", "c1", "search_handbook"))
        self.assertEqual(json.loads(tool_msg["content"]), {"result": ["経費 に関する規程 1", "経費 に関する規程 2"]})
        assistant_msg = llm.calls[1]["messages"][-2]
        self.assertEqual(assistant_msg["role"], "assistant")
        self.assertEqual(assistant_msg["tool_calls"], [{"id": "c1", "name": "search_handbook",
                                                        "arguments": {"query": "経費", "top_k": 2}}])
        self.assertEqual(kinds(result), ["model", "tool_call", "tool_result", "model", "final"])

    def test_unknown_tool_and_invalid_args_are_reported_not_executed(self):
        llm = ScriptedLLM([
            ModelTurn(tool_calls=(ToolCall("delete_database", {}, "c1"),
                                  ToolCall("search_handbook", {"query": 42}, "c2"))),
            ModelTurn(tool_calls=(ToolCall("search_handbook", {"query": "休暇"}, "c3"),)),
            ModelTurn(content="有給休暇は…"),
        ])
        result = run_agent(llm, self.registry, "休暇について")
        self.assertEqual(result.stop_reason, "final")
        self.assertEqual(self.log, [("search_handbook", "休暇", 3)], "不正な呼び出しは実行しない")
        msgs = llm.calls[1]["messages"]
        self.assertIn("error", json.loads(msgs[-2]["content"]))
        err = json.loads(msgs[-1]["content"])
        self.assertIn("error", err)
        self.assertTrue(any("query" in d for d in err["details"]))
        self.assertEqual(kinds(result)[:3], ["model", "unknown_tool", "invalid_args"])

    def test_dangerous_tool_requires_confirmation(self):
        def script():
            return ScriptedLLM([
                ModelTurn(tool_calls=(ToolCall("send_email", {"to": "boss@example.com", "subject": "報告"}, "c1"),)),
                ModelTurn(content="完了しました"),
            ])

        denied = run_agent(script(), self.registry, "報告して")  # confirm なし → 拒否
        self.assertEqual(self.log, [])
        self.assertIn("denied", kinds(denied))

        asked = []
        refused = run_agent(script(), self.registry, "報告して", confirm=lambda call: asked.append(call) or False)
        self.assertEqual(self.log, [])
        self.assertEqual(asked[0].name, "send_email")
        self.assertEqual(asked[0].arguments["to"], "boss@example.com")
        self.assertIn("denied", kinds(refused))

        approved = run_agent(script(), self.registry, "報告して", confirm=lambda call: True)
        self.assertEqual(self.log, [("send_email", "boss@example.com", "報告")])
        self.assertEqual(approved.answer, "完了しました")

    def test_confirmation_is_not_asked_for_invalid_calls(self):
        asked = []
        llm = ScriptedLLM([
            ModelTurn(tool_calls=(ToolCall("send_email", {"to": "x@example.com"}, "c1"),)),  # subject がない
            ModelTurn(content="失敗しました"),
        ])
        result = run_agent(llm, self.registry, "送って", confirm=lambda c: asked.append(c) or True)
        self.assertEqual(asked, [], "不正な引数の呼び出しで人に確認を求めない")
        self.assertIn("invalid_args", kinds(result))

    def test_tool_exception_becomes_error_message(self):
        llm = ScriptedLLM([ModelTurn(tool_calls=(ToolCall("flaky", {}, "c1"),)), ModelTurn(content="あとで再試行します")])
        result = run_agent(llm, self.registry, "やって")
        self.assertEqual(result.stop_reason, "final")
        content = json.loads(llm.calls[1]["messages"][-1]["content"])
        self.assertIn("ConnectionError", content["error"])
        self.assertIn("tool_error", kinds(result))

    def test_max_steps_guard(self):
        turns = [ModelTurn(tool_calls=(ToolCall("search_handbook", {"query": f"q{i}"}, f"c{i}"),)) for i in range(10)]
        llm = ScriptedLLM(turns)
        result = run_agent(llm, self.registry, "調べ続けて", max_steps=3)
        self.assertEqual((result.answer, result.stop_reason), (None, "max_steps"))
        self.assertEqual(len(llm.calls), 3, "モデルの呼び出しは max_steps 回まで")
        self.assertEqual(len(self.log), 3)
        self.assertEqual(result.trace[-1].kind, "stopped")

    def test_repeated_identical_calls_are_stopped(self):
        same = ToolCall("search_handbook", {"query": "経費", "top_k": 1}, "c")
        llm = ScriptedLLM([ModelTurn(tool_calls=(same,))] * 5)
        result = run_agent(llm, self.registry, "経費", max_steps=5, max_identical_calls=2)
        self.assertEqual(result.stop_reason, "repeated_call")
        self.assertEqual(len(self.log), 2, "同じ呼び出しは 2 回までしか実行しない")

    def test_invalid_limits(self):
        with self.assertRaises(ValueError):
            run_agent(ScriptedLLM([]), self.registry, "x", max_steps=0)


if __name__ == "__main__":
    unittest.main()
