"""1.4 プログラムが動く仕組み — 演習5 解答例: 小さなリンカ

仕様は exercises/minilinker.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass, field

Instr = tuple


@dataclass
class ObjectModule:
    name: str
    code: list[Instr]
    symbols: dict[str, int] = field(default_factory=dict)
    local_symbols: dict[str, int] = field(default_factory=dict)
    relocations: list[tuple[int, str]] = field(default_factory=list)


class LinkError(Exception):
    """リンクの失敗（未定義のシンボル、重複定義、不正な再配置など）。"""


START_CODE_SIZE = 2  # 先頭に置くスタートアップコード: CALL entry, 0 / HALT


def link(modules: list[ObjectModule], entry: str = "main") -> tuple[list[Instr], dict[str, int]]:
    # 1. 配置: スタートアップコードの後ろに、モジュールを渡された順に並べ、各モジュールの先頭番地を決める
    bases: list[int] = []
    addr = START_CODE_SIZE
    for module in modules:
        bases.append(addr)
        addr += len(module.code)

    # 2. シンボル解決: グローバルシンボルの最終的な番地の表を作る
    table: dict[str, int] = {}
    defined_in: dict[str, str] = {}
    for module, base in zip(modules, bases):
        for kind, symbols in (("グローバル", module.symbols), ("ローカル", module.local_symbols)):
            for name, offset in symbols.items():
                if not 0 <= offset < len(module.code):
                    raise LinkError(f"{module.name}: {kind}シンボル {name} の位置 {offset} がコードの範囲外です")
        for name, offset in module.symbols.items():
            if name in table:
                raise LinkError(
                    f"シンボル {name} が複数定義されています: {defined_in[name]} と {module.name}"
                )
            table[name] = base + offset
            defined_in[name] = module.name
    if entry not in table:
        raise LinkError(f"エントリポイント {entry} が定義されていません")

    # 3. 再配置: 各モジュールのコードをコピーし、番地が入るべき引数を書き換える
    code: list[Instr] = [("CALL", table[entry], 0), ("HALT",)]
    for module, base in zip(modules, bases):
        patched = list(module.code)  # 入力のモジュールは書き換えない
        for index, name in module.relocations:
            if not 0 <= index < len(patched):
                raise LinkError(f"{module.name}: 再配置の位置 {index} がコードの範囲外です")
            if name in module.local_symbols:      # 同じモジュールのローカルシンボルが優先
                target = base + module.local_symbols[name]
            elif name in table:
                target = table[name]
            else:
                raise LinkError(f"{module.name}: 未定義のシンボル {name} を参照しています")
            instr = patched[index]
            if len(instr) < 2:
                raise LinkError(f"{module.name}: 位置 {index} の命令 {instr!r} には書き換える引数がありません")
            patched[index] = (instr[0], target, *instr[2:])
        code.extend(patched)
    return code, table
