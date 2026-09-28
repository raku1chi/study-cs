"""12.4 LLMアプリケーション開発 — 演習2: 決定的なエージェントループ（解答例）

演習の仕様は exercises/agent_loop.py の docstring を参照してください。
"""
from __future__ import annotations

import copy
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence


# ---------------------------------------------------------------------------
# 実装済み: モデルの応答と、台本どおりに答える偽の LLM
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict
    call_id: str = ""


@dataclass(frozen=True)
class ModelTurn:
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


class ScriptedLLM:
    def __init__(self, turns: Sequence[ModelTurn]) -> None:
        self._turns = list(turns)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelTurn:
        self.calls.append({"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools)})
        if not self._turns:
            raise RuntimeError("台本の応答を使い切りました")
        return self._turns.pop(0)


# ---------------------------------------------------------------------------
# 演習2a: 引数の検証（JSON Schema の小さな部分集合）
# ---------------------------------------------------------------------------

_TYPE_CHECKS: dict[str, Callable[[Any], bool]] = {
    "string": lambda v: isinstance(v, str),
    # bool は int のサブクラスなので明示的に除く（True を整数として受け付けない）
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def _validate(schema: dict, value: Any, path: str, errors: list[str]) -> None:
    expected = schema.get("type")
    if expected is not None:
        check = _TYPE_CHECKS.get(expected)
        if check is None:
            raise ValueError(f"未対応の型です: {expected}")
        if not check(value):
            errors.append(f"{path}: {expected} であるべきところ {type(value).__name__} です")
            return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {schema['enum']} のどれかである必要があります")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {schema['minimum']} 以上である必要があります")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {schema['maximum']} 以下である必要があります")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: {schema['minLength']} 文字以上である必要があります")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: {schema['maxLength']} 文字以下である必要があります")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            _validate(schema["items"], item, f"{path}[{i}]", errors)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}.{name}: 必須の引数がありません")
        for name, item in value.items():
            if name in props:
                _validate(props[name], item, f"{path}.{name}", errors)
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{name}: 想定外の引数です")


def validate_arguments(schema: dict, arguments: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(arguments, dict):
        return ["$: 引数はオブジェクト（dict）である必要があります"]
    _validate(schema, arguments, "$", errors)
    return errors


# ---------------------------------------------------------------------------
# 演習2b: ツールと登録簿
# ---------------------------------------------------------------------------

@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    func: Callable[..., Any]
    dangerous: bool = False

    def schema(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"同じ名前のツールがすでにあります: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        return [self._tools[name].schema() for name in sorted(self._tools)]


# ---------------------------------------------------------------------------
# 演習2c: エージェントループ
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TraceEvent:
    step: int
    kind: str
    detail: dict[str, Any]


@dataclass
class AgentResult:
    answer: str | None
    stop_reason: str
    trace: list[TraceEvent] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _execute(
    registry: ToolRegistry,
    call: ToolCall,
    step: int,
    confirm: Callable[[ToolCall], bool] | None,
    trace: list[TraceEvent],
) -> str:
    tool = registry.get(call.name)
    if tool is None:
        # 例外で止めずに、誤りをモデルに伝えて自分で直させる
        trace.append(TraceEvent(step, "unknown_tool", {"name": call.name}))
        return _dump({"error": f"未知のツールです: {call.name}"})
    errors = validate_arguments(tool.parameters, call.arguments)
    if errors:
        trace.append(TraceEvent(step, "invalid_args", {"name": call.name, "errors": errors}))
        return _dump({"error": "引数が不正です", "details": errors})
    if tool.dangerous and not (confirm is not None and confirm(call)):
        # 危険なツールは、人の確認が取れない限り実行しない（既定で拒否）
        trace.append(TraceEvent(step, "denied", {"name": call.name, "arguments": call.arguments}))
        return _dump({"error": "ユーザーが実行を許可しませんでした"})
    trace.append(TraceEvent(step, "tool_call", {"name": call.name, "arguments": call.arguments}))
    try:
        result = tool.func(**call.arguments)
    except Exception as exc:  # noqa: BLE001  ツールの失敗もモデルに伝えて続行する
        trace.append(TraceEvent(step, "tool_error", {"name": call.name, "error": f"{type(exc).__name__}: {exc}"}))
        return _dump({"error": f"{type(exc).__name__}: {exc}"})
    trace.append(TraceEvent(step, "tool_result", {"name": call.name, "result": result}))
    return _dump({"result": result})


def run_agent(
    llm: Callable[[list[dict[str, Any]], list[dict[str, Any]]], ModelTurn],
    registry: ToolRegistry,
    user_message: str,
    *,
    system_prompt: str = "あなたは社内の業務を手伝うアシスタントです。",
    max_steps: int = 5,
    confirm: Callable[[ToolCall], bool] | None = None,
    max_identical_calls: int = 2,
) -> AgentResult:
    if max_steps < 1 or max_identical_calls < 1:
        raise ValueError("max_steps と max_identical_calls は 1 以上")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    trace: list[TraceEvent] = []
    seen: Counter = Counter()
    for step in range(1, max_steps + 1):
        turn = llm(messages, registry.schemas())
        trace.append(TraceEvent(step, "model", {
            "content": turn.content, "tool_calls": [c.name for c in turn.tool_calls],
        }))
        messages.append({
            "role": "assistant",
            "content": turn.content,
            "tool_calls": [{"id": c.call_id, "name": c.name, "arguments": c.arguments} for c in turn.tool_calls],
        })
        if not turn.tool_calls:
            trace.append(TraceEvent(step, "final", {"answer": turn.content}))
            return AgentResult(turn.content, "final", trace, messages)
        for call in turn.tool_calls:
            key = (call.name, json.dumps(call.arguments, sort_keys=True, ensure_ascii=False, default=str))
            seen[key] += 1
            if seen[key] > max_identical_calls:
                # 同じ呼び出しの繰り返しは、エージェントが堂々巡りしている兆候
                trace.append(TraceEvent(step, "stopped", {"reason": "repeated_call", "name": call.name}))
                return AgentResult(None, "repeated_call", trace, messages)
            content = _execute(registry, call, step, confirm, trace)
            messages.append({"role": "tool", "tool_call_id": call.call_id, "name": call.name, "content": content})
    trace.append(TraceEvent(max_steps, "stopped", {"reason": "max_steps"}))
    return AgentResult(None, "max_steps", trace, messages)
