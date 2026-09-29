"""8.5 リファクタリングと技術的負債 — 解答例: 承認テスト（ゴールデンマスター）

仕様は exercises/characterize.py の docstring を参照してください。
"""
from __future__ import annotations

import difflib
import itertools
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

APPROVED_SUFFIX = ".approved.json"
RECEIVED_SUFFIX = ".received.json"


def to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return value
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (set, frozenset)):
        # 集合の反復順は実行ごとに変わりうるので、直列化した文字列で並べて固定する
        items = [to_jsonable(v) for v in value]
        return sorted(items, key=lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False))
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    return repr(value)


def combinations(**params: Iterable[Any]) -> list[tuple]:
    return list(itertools.product(*(list(values) for values in params.values())))


def run_cases(func: Callable[..., Any], inputs: Iterable[Sequence[Any]]) -> list[dict]:
    cases = []
    for args in inputs:
        case: dict = {"input": to_jsonable(list(args))}
        try:
            case["output"] = to_jsonable(func(*args))
        except Exception as exc:  # 例外も現在の振る舞いの一部として記録する
            case["error"] = f"{type(exc).__name__}: {exc}"
        cases.append(case)
    return cases


def serialize(cases: list[dict], scrubbers: Sequence[tuple[str, str]] = ()) -> str:
    if cases:
        text = "[\n" + ",\n".join(json.dumps(c, ensure_ascii=False, sort_keys=True) for c in cases) + "\n]\n"
    else:
        text = "[]\n"
    for pattern, replacement in scrubbers:
        text = re.sub(pattern, replacement, text)
    return text


@dataclass(frozen=True)
class Verification:
    ok: bool
    message: str
    diff: str
    received_path: Optional[Path]


def received_path_for(approved_path: Path) -> Path:
    approved_path = Path(approved_path)
    if not approved_path.name.endswith(APPROVED_SUFFIX):
        raise ValueError(f"承認済みのファイル名は *{APPROVED_SUFFIX} にしてください: {approved_path.name}")
    return approved_path.with_name(approved_path.name[: -len(APPROVED_SUFFIX)] + RECEIVED_SUFFIX)


def verify(
    func: Callable[..., Any],
    inputs: Iterable[Sequence[Any]],
    approved_path: Path,
    *,
    scrubbers: Sequence[tuple[str, str]] = (),
) -> Verification:
    approved_path = Path(approved_path)
    received_path = received_path_for(approved_path)
    received = serialize(run_cases(func, inputs), scrubbers)
    approved = approved_path.read_text(encoding="utf-8") if approved_path.exists() else None

    if approved == received:
        if received_path.exists():
            received_path.unlink()  # 前回の失敗で残ったファイルを片付ける
        return Verification(True, "承認済みの振る舞いと一致しました", "", None)

    received_path.write_text(received, encoding="utf-8")
    diff = "\n".join(difflib.unified_diff(
        (approved or "").splitlines(), received.splitlines(),
        fromfile=approved_path.name, tofile=received_path.name, lineterm="",
    ))
    if approved is None:
        message = f"承認済みのファイルがありません。{received_path.name} の内容を確認し、正しければ承認してください"
    else:
        message = f"振る舞いが変わりました。差分を確認し、意図した変更なら {received_path.name} を承認してください"
    return Verification(False, message, diff, received_path)


def approve(approved_path: Path) -> None:
    received_path = received_path_for(approved_path)
    if not received_path.exists():
        raise FileNotFoundError(received_path)
    received_path.replace(approved_path)
