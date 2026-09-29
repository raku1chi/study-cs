"""8.5 リファクタリングと技術的負債 — 演習3: 承認テスト（ゴールデンマスター）

テストのないレガシーコードを安全に変更するには、まず「今どう動いているか」を固定する必要があります。
仕様書がなく、正しい振る舞いが誰にも分からなくても、**現在の振る舞い** なら記録できます。
多数の入力に対する出力（と例外）をファイルに記録して人が確認・承認し（approved）、以後は
同じ入力で出力が変わっていないかを検証する——これが承認テスト（approval testing）、または
ゴールデンマスターと呼ばれる手法です（Michael Feathers のいう特性テストの一種）。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 8.5

使い方の流れ（テストで確かめます）:
    inputs = combinations(weight_g=[1, 2000, 2001], prefecture=["東京都", "沖縄県"], express=[False, True])
    result = verify(shipping_fee, inputs, Path("shipping_fee.approved.json"))
    # 1 回目: 承認済みのファイルがないので失敗し、shipping_fee.received.json が書き出される
    # → 人が中身を確認し、approve(Path("shipping_fee.approved.json")) で承認する
    # 2 回目以降: 出力が同じなら成功。変わったら失敗し、差分（unified diff）が result.diff に入る

直列化の形式（serialize）は、差分が読みやすいように「1 ケース 1 行」の JSON にします:
    [
    {"input": [1, "東京都", false], "output": 600},
    {"error": "ValueError: 沖縄県への速達は受け付けていません", "input": [1, "沖縄県", true]}
    ]
"""
from __future__ import annotations

import difflib  # noqa: F401  実装で使います
import json  # noqa: F401  実装で使います
import re  # noqa: F401  実装で使います
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence


def to_jsonable(value: Any) -> Any:
    """値を、JSON で表せる形に **決定的に** 変換する。

    - None・bool・int・str はそのまま。
    - float はそのまま。ただし NaN と ±inf は文字列 "nan"・"inf"・"-inf"（JSON では表せないため）。
    - list・tuple → list（要素も再帰的に変換）。
    - set・frozenset → 要素を変換し、各要素を json.dumps(..., sort_keys=True, ensure_ascii=False)
      した文字列の昇順に並べた list（集合の順序は実行ごとに変わりうるので、並べ替えて固定する）。
    - dict → キーを str() した dict（値も再帰的に変換）。
    - それ以外（Decimal・datetime・独自のクラスなど）→ repr(value) の文字列。
    """
    raise NotImplementedError("演習3: to_jsonable を実装してください")


def combinations(**params: Iterable[Any]) -> list[tuple]:
    """キーワード引数の値の全組み合わせ（直積）を、引数の順に並べたタプルのリストで返す。

    >>> combinations(weight=[1, 5], express=[False, True])
    [(1, False), (1, True), (5, False), (5, True)]

    多数の入力の組み合わせで振る舞いを記録するための補助関数です（ApprovalTests の
    CombinationApprovals に相当）。境界値（2000 と 2001 など）を必ず含めましょう。
    """
    raise NotImplementedError("演習3: combinations を実装してください")


def run_cases(func: Callable[..., Any], inputs: Iterable[Sequence[Any]]) -> list[dict]:
    """各入力（引数の並び）で func(*args) を呼び、結果を記録する。

    - 正常に返れば {"input": to_jsonable(list(args)), "output": to_jsonable(戻り値)}
    - 例外（Exception のサブクラス）なら {"input": ..., "error": "型名: メッセージ"}
      （例外も現在の振る舞いの一部なので、記録して固定する）
    """
    raise NotImplementedError("演習3: run_cases を実装してください")


def serialize(cases: list[dict], scrubbers: Sequence[tuple[str, str]] = ()) -> str:
    """ケースの一覧を、差分が読みやすい「1 ケース 1 行」の JSON の文字列にする。

    - 各ケースは json.dumps(case, ensure_ascii=False, sort_keys=True) で 1 行にする。
    - 全体は "[\\n" + ",\\n".join(各行) + "\\n]\\n"。ケースが 0 件なら "[]\\n"。
    - 最後に scrubbers の (正規表現, 置換文字列) を順に re.sub で適用する
      （時刻や乱数の ID のように、実行ごとに変わる部分を <TIMESTAMP> などに置き換えるため）。
    """
    raise NotImplementedError("演習3: serialize を実装してください")


@dataclass(frozen=True)
class Verification:
    ok: bool
    message: str  # 人が読む説明
    diff: str  # 承認済み → 今回 の unified diff（ok なら空文字列）
    received_path: Optional[Path]  # 書き出した received ファイル（ok なら None）


def received_path_for(approved_path: Path) -> Path:
    """"xxx.approved.json" に対応する "xxx.received.json" のパスを返す。

    approved_path の名前が ".approved.json" で終わらなければ ValueError。
    """
    raise NotImplementedError("演習3: received_path_for を実装してください")


def verify(
    func: Callable[..., Any],
    inputs: Iterable[Sequence[Any]],
    approved_path: Path,
    *,
    scrubbers: Sequence[tuple[str, str]] = (),
) -> Verification:
    """今回の結果 received = serialize(run_cases(func, inputs), scrubbers) を、承認済みのファイルと比べる。

    - 承認済みのファイルが存在し、内容（UTF-8）が received と完全に一致 → ok=True。
      古い received ファイルが残っていれば削除する。
    - 一致しない、または承認済みのファイルがない → received を received_path_for(approved_path)
      に書き出し、ok=False。diff は difflib.unified_diff で、承認済み（なければ空）から received への
      差分を作り、fromfile・tofile にそれぞれのファイル名を指定し、lineterm="" で作った行を "\\n" で
      つないだ文字列。message には、承認済みのファイルがないのか、内容が変わったのかを書く。
    """
    raise NotImplementedError("演習3: verify を実装してください")


def approve(approved_path: Path) -> None:
    """received ファイルを承認する（received を approved に置き換える）。received がなければ FileNotFoundError。"""
    raise NotImplementedError("演習3: approve を実装してください")
