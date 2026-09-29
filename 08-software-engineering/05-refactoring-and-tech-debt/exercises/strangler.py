"""8.5 リファクタリングと技術的負債 — 演習2: ストラングラー・フィグのルーター

古いシステム（legacy）を一度に作り直す（ビッグバン・リライト）のではなく、前段に置いた
ルーター（ファサード）で、機能（ルート）ごとに少しずつ新しい実装（modern）へ移していくのが
ストラングラー・フィグ（Strangler Fig）パターンです。この演習では、そのルーターと、
ルートごとの移行の状態機械を作ります。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 8.5

リクエストは dict で、"path" キーを必ず持つ（例: {"path": "/orders/42", "user_id": "u1"}）。
legacy と modern は、どちらも「リクエストを受け取って応答を返す関数」です。

ルートごとのモード（状態）と、handle の振る舞い:
    "legacy" : legacy だけを呼ぶ。
    "shadow" : legacy を呼んでその応答を返す。**さらに** 同じリクエストで modern も呼び、
               comparator(legacy の応答, modern の応答) が False なら不一致として記録する。
               modern が例外を送出したら、それも不一致として記録する（error に "型名: メッセージ"）。
               modern の結果や例外は、利用者への応答に一切影響させない。
               （読み取り専用のルートに使う。書き込みを二重に実行してしまうため）
    "canary" : キー（既定では user_id）から計算したバケット（0〜99）が percent 未満の利用者だけ
               modern を呼ぶ。それ以外は legacy。modern が例外を送出したら、エラーとして数え、
               legacy の応答を返す（フォールバック）。
               バケット = int(sha256(f"{ルートの接頭辞}:{キー}").hexdigest(), 16) % 100
    "modern" / "retired" : modern だけを呼ぶ。

ルートの対応: request["path"] が、登録された接頭辞と一致する（path == 接頭辞、または
path が 接頭辞 + "/" で始まる。接頭辞 "/" はすべてに一致する）ルートのうち、**最も長い** 接頭辞の
ルートを使う。どのルートにも一致しなければ legacy を呼ぶ。

移行の状態機械（promote で 1 段進め、rollback で legacy に戻す）:

    legacy ──promote()──▶ shadow ──promote(percent)──▶ canary(percent)
                                                        │  promote(より大きい percent)
                                                        ▼
                         retired ◀──promote()── modern ◀── promote()（percent 省略、または 100）

    - shadow → canary: 比較した回数が min_shadow_samples 以上、かつ不一致の割合が
      max_mismatch_rate 以下でなければ InvalidTransition。percent は 1〜99 の整数（省略時 1）。
    - canary → canary（割合を上げる）/ modern: canary で modern を呼んだ回数が
      min_canary_samples 以上、かつエラーの割合が max_error_rate 以下でなければ InvalidTransition。
      percent は今より大きい 1〜100 の整数（100 または省略で modern）。
    - modern → retired: 旧実装を撤去してよい状態。**ここからは rollback できない**。
    - rollback: shadow・canary・modern から legacy に戻し、そのルートの統計をリセットする。
      legacy・retired からは InvalidTransition。
    - 登録されていない接頭辞を指定したら KeyError。percent が範囲外なら ValueError。
"""
from __future__ import annotations

import hashlib  # noqa: F401  実装で使います
import operator
from dataclasses import dataclass
from typing import Any, Callable, Optional

Handler = Callable[[dict], Any]


class InvalidTransition(Exception):
    """状態機械で許されない遷移。"""


@dataclass(frozen=True)
class Mismatch:
    route: str  # ルートの接頭辞
    request: dict
    legacy: Any
    modern: Any  # modern が例外を送出したときは None
    error: Optional[str] = None  # modern の例外（"型名: メッセージ"）


@dataclass
class RouteStats:
    shadow_compared: int = 0  # shadow で比較した回数
    shadow_mismatches: int = 0  # そのうち不一致だった回数
    canary_requests: int = 0  # canary で modern を呼んだ回数
    canary_errors: int = 0  # そのうち modern が例外を送出した回数


class StranglerRouter:
    def __init__(
        self,
        legacy: Handler,
        modern: Handler,
        *,
        comparator: Callable[[Any, Any], bool] = operator.eq,
        key: Callable[[dict], str] = lambda request: str(request.get("user_id", "")),
        min_shadow_samples: int = 100,
        max_mismatch_rate: float = 0.01,
        min_canary_samples: int = 100,
        max_error_rate: float = 0.01,
        max_recorded_mismatches: int = 100,
    ) -> None:
        """mismatches（記録した不一致の一覧）は最初の max_recorded_mismatches 件まで保存する。
        統計（RouteStats）はすべてを数える。"""
        raise NotImplementedError("演習2: StranglerRouter を実装してください")

    @property
    def mismatches(self) -> list[Mismatch]:
        raise NotImplementedError("演習2: mismatches を実装してください")

    def add_route(self, prefix: str) -> None:
        """ルートを登録する（最初は "legacy"）。接頭辞は "/" で始まる。同じ接頭辞の二重登録は ValueError。"""
        raise NotImplementedError("演習2: add_route を実装してください")

    def mode(self, prefix: str) -> tuple[str, int]:
        """(モード, 割合) を返す。割合は canary のときだけ意味を持ち、それ以外は legacy・shadow で 0、modern・retired で 100。"""
        raise NotImplementedError("演習2: mode を実装してください")

    def stats(self, prefix: str) -> RouteStats:
        raise NotImplementedError("演習2: stats を実装してください")

    def handle(self, request: dict) -> Any:
        raise NotImplementedError("演習2: handle を実装してください")

    def promote(self, prefix: str, percent: Optional[int] = None) -> None:
        raise NotImplementedError("演習2: promote を実装してください")

    def rollback(self, prefix: str) -> None:
        raise NotImplementedError("演習2: rollback を実装してください")
