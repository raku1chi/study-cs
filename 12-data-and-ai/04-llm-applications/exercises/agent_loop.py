"""12.4 LLMアプリケーション開発 — 演習2: 決定的なエージェントループ（★★☆）

LLM に「ツール（関数）」を使わせるエージェントの中核、つまり

    モデルを呼ぶ → ツール呼び出しの要求を受け取る → 引数を検証する → （危険なら人に確認する）
    → 実行する → 結果をモデルに返す → … → 最終回答

のループを実装します。本物の LLM の代わりに、台本どおりの応答を返す ScriptedLLM を使うので、
テストは決定的で、API キーも不要です。本物の API に差し替えても、ループの構造は同じです。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 12.4
このディレクトリで直接実行する場合:
    python3 -m unittest -v test_agent_loop

メッセージの形式（この演習での約束。実際の API の形式は提供元ごとに少しずつ違います）:
    {"role": "system", "content": "..."}
    {"role": "user", "content": "..."}
    {"role": "assistant", "content": "..." または None,
     "tool_calls": [{"id": 呼び出しID, "name": ツール名, "arguments": {...}}, ...]}
    {"role": "tool", "tool_call_id": 呼び出しID, "name": ツール名, "content": JSON 文字列}
"""
from __future__ import annotations

import copy
import json  # noqa: F401
from collections import Counter  # noqa: F401
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence


# ---------------------------------------------------------------------------
# 実装済み: モデルの応答と、台本どおりに答える偽の LLM
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolCall:
    """モデルが要求したツール呼び出し。"""

    name: str
    arguments: dict
    call_id: str = ""


@dataclass(frozen=True)
class ModelTurn:
    """モデルの 1 回の応答。tool_calls が空なら content が最終回答。"""

    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


class ScriptedLLM:
    """決められた応答（ModelTurn）を順に返す偽の LLM。

    呼ばれるたびに、受け取った messages と tools のコピーを self.calls に記録する
    （テストで「モデルに何が渡されたか」を確かめるため）。台本を使い切ると RuntimeError。
    """

    def __init__(self, turns: Sequence[ModelTurn]) -> None:
        self._turns = list(turns)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ModelTurn:
        self.calls.append({"messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools)})
        if not self._turns:
            raise RuntimeError("台本の応答を使い切りました")
        return self._turns.pop(0)


# ---------------------------------------------------------------------------
# 演習2a（★★☆）: 引数の検証（JSON Schema の小さな部分集合）
# ---------------------------------------------------------------------------

def validate_arguments(schema: dict, arguments: Any) -> list[str]:
    """ツールの引数を、JSON Schema の小さな部分集合で検証し、エラーメッセージのリストを返す（空なら正常）。

    arguments が dict でなければ、それだけでエラー 1 件。対応するキーワード（再帰的に適用する）:
        type:     "string" / "integer" / "number" / "boolean" / "array" / "object"
                  （bool は integer・number として受け付けない。integer に小数は不可）
                  型が合わなければ、その値についての他のチェックは行わない
        enum:     許される値のリスト
        minimum / maximum:     数値の範囲（両端を含む）
        minLength / maxLength: 文字列の長さ
        items:    配列の各要素に適用するスキーマ
        properties / required / additionalProperties（False のときだけ余分なキーを禁止）

    エラーメッセージには、問題の場所を "$.query" や "$.cc[1]" のような形で含めること
    （テストはメッセージに引数名が含まれることを確かめる）。
    モデルは引数を間違えることがあるので、ツールを実行する前に必ず検証する。
    """
    raise NotImplementedError("演習2a: validate_arguments を実装してください")


# ---------------------------------------------------------------------------
# 演習2b（★☆☆）: ツールと登録簿
# ---------------------------------------------------------------------------

@dataclass
class Tool:
    """モデルに使わせるツール。dangerous=True のツールは、実行前に人の確認が必要。"""

    name: str
    description: str
    parameters: dict  # 引数の JSON Schema
    func: Callable[..., Any]  # 実行する関数（引数はキーワード引数で渡す）
    dangerous: bool = False

    def schema(self) -> dict[str, Any]:
        """モデルに見せる情報 {"name", "description", "parameters"}（実装済み）。"""
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


class ToolRegistry:
    """ツールの登録簿。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """登録する。同じ名前がすでにあれば ValueError。"""
        raise NotImplementedError("演習2b: ToolRegistry.register を実装してください")

    def get(self, name: str) -> Tool | None:
        """名前でツールを探す（なければ None）。"""
        raise NotImplementedError("演習2b: ToolRegistry.get を実装してください")

    def schemas(self) -> list[dict[str, Any]]:
        """全ツールの schema() を名前の昇順で返す（モデルに渡すツール一覧。順番を決定的にする）。"""
        raise NotImplementedError("演習2b: ToolRegistry.schemas を実装してください")


# ---------------------------------------------------------------------------
# 演習2c（★★☆）: エージェントループ
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TraceEvent:
    """ループの中で起きたことの記録（実装済み）。

    kind の種類: "model"（モデルの応答）、"tool_call"（ツールを実行した）、"tool_result"（成功）、
    "tool_error"（ツールが例外を投げた）、"unknown_tool"、"invalid_args"、"denied"（確認で拒否）、
    "final"（最終回答）、"stopped"（ガードで停止）
    """

    step: int
    kind: str
    detail: dict[str, Any]


@dataclass
class AgentResult:
    """ループの結果（実装済み）。stop_reason は "final" / "max_steps" / "repeated_call"。"""

    answer: str | None
    stop_reason: str
    trace: list[TraceEvent] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)


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
    """エージェントのループを実行する。

    1. messages = [system, user] で始める。max_steps < 1 または max_identical_calls < 1 なら ValueError。
    2. step = 1, 2, …, max_steps について:
       a. turn = llm(messages, registry.schemas())。TraceEvent(step, "model", {...}) を記録し、
          assistant のメッセージ（content と tool_calls）を messages に追加する。
       b. turn.tool_calls が空なら、TraceEvent "final" を記録し、AgentResult(turn.content, "final") を返す。
       c. 各ツール呼び出しについて順に:
          - (名前, 引数を json.dumps(sort_keys=True) した文字列) が、このループで max_identical_calls 回を
            超えて呼ばれたら、TraceEvent "stopped" を記録して AgentResult(None, "repeated_call") を返す
            （同じ呼び出しの繰り返しは、エージェントが堂々巡りしている兆候）。
          - 未知のツール → "unknown_tool" を記録し、結果を {"error": ...} とする。
          - validate_arguments でエラー → "invalid_args" を記録し、結果を
            {"error": ..., "details": エラーのリスト} とする（実行しない。確認も求めない）。
          - dangerous なツールは、confirm が None か confirm(call) が False なら "denied" を記録し、
            結果を {"error": ...} とする（既定で拒否 = fail closed）。
          - それ以外は "tool_call" を記録して func(**arguments) を実行する。成功なら "tool_result" を記録し
            結果を {"result": 戻り値}、例外なら "tool_error" を記録し {"error": "例外の型名: メッセージ"} とする。
          - 結果を json.dumps(ensure_ascii=False, default=str) した文字列を content として、
            {"role": "tool", "tool_call_id", "name", "content"} を messages に追加する。
            エラーも例外で止めずにモデルに返す（モデルが自分で直せるように）。
    3. max_steps 回で終わらなければ、TraceEvent "stopped" を記録し AgentResult(None, "max_steps") を返す。
    戻り値の trace と messages には、記録したものをすべて入れる。
    """
    raise NotImplementedError("演習2c: run_agent を実装してください")
