"""1.2 論理回路と CPU の仕組み — 演習5: 5 段パイプラインのデータハザード（★★☆）

教科書的な 5 段パイプライン（IF → ID → EX → MEM → WB）で、命令列を実行するとどこで何サイクル
待たされる（ストールする）かを計算します。フォワーディングの有無でストールがどう変わるか、
命令の並べ替え（命令スケジューリング）でストールを消せることを確かめます。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 1.2
このディレクトリで、この演習のテストだけを実行することもできます:
    python3 -m unittest -v test_pipesim

======================================================================
パイプラインのモデル（簡略化しています）
======================================================================

- 各段は 1 サイクル。ストールがなければ毎サイクル 1 命令ずつ、プログラムの順番どおりに進む。
  最初の命令は IF=1, ID=2, EX=3, MEM=4, WB=5 サイクル目。i 番目（0 始まり）の命令の EX は 3 + i。
- 追い越しはない（インオーダー）。後ろの命令の EX は、前の命令の EX より少なくとも 1 サイクル後。
- レジスタファイルは WB の前半で書き込み、ID の後半で読み出す（同じサイクルなら書いた値が読める）。
- 簡単のため、すべての命令はソースレジスタの値を「EX の開始時」に必要とする（store のデータも）。
- 命令は次の 4 種類。
    alu  : 結果は EX の終わりに分かり、WB でレジスタに書く
    load : 結果（メモリから読んだ値）は MEM の終わりに分かり、WB でレジスタに書く
    store: レジスタに書かない（dst は None）
    nop  : 何もしない（dst も srcs もない）
- 読み出すレジスタごとに「そのレジスタを最後に書いた、前にある命令」（書き手）を探し、
  次の条件を満たす最も早いサイクルを EX とする（書き手がいなければ制約なし）。
    フォワーディングなし: 読む側の ID >= 書き手の WB  つまり  EX >= 書き手の EX + 3
    フォワーディングあり: 書き手が alu  なら  EX >= 書き手の EX + 1（EX の結果を直後の EX へ転送）
                          書き手が load なら  EX >= 書き手の EX + 2（ロードユース: 1 サイクルは必ず待つ）
- 書き手のいないレジスタや、書き込みどうしの順序（WAW, WAR）は、インオーダーのこのモデルでは問題にならない。
"""
from __future__ import annotations

from typing import NamedTuple, Optional

KINDS = ("alu", "load", "store", "nop")


class Instr(NamedTuple):
    """命令 1 つ。レジスタ名は任意の文字列（"x1", "t0" など）。

    >>> Instr("load", "x1", ("x2",))          # x1 ← メモリ[x2 + …]
    Instr(kind='load', dst='x1', srcs=('x2',))
    >>> Instr("alu", "x3", ("x1", "x4"))       # x3 ← x1 + x4
    Instr(kind='alu', dst='x3', srcs=('x1', 'x4'))
    """

    kind: str                   # "alu" | "load" | "store" | "nop"
    dst: Optional[str] = None   # 結果を書き込むレジスタ（store と nop は None）
    srcs: tuple[str, ...] = ()  # 読み出すレジスタ


def schedule(program: list[Instr], forwarding: bool) -> list[int]:
    """各命令が EX ステージに入るサイクル番号（1 始まり）のリストを返す。

    - 空のプログラムなら []。
    - kind が KINDS 以外、alu / load なのに dst が None、store / nop なのに dst がある、
      nop なのに srcs がある、のいずれかなら ValueError。

    >>> schedule([Instr("alu", "x1", ("x2",)), Instr("alu", "x3", ("x1",))], forwarding=True)
    [3, 4]
    >>> schedule([Instr("alu", "x1", ("x2",)), Instr("alu", "x3", ("x1",))], forwarding=False)
    [3, 6]
    >>> schedule([Instr("load", "x1", ("x2",)), Instr("alu", "x3", ("x1",))], forwarding=True)
    [3, 5]

    ヒント: 前から順に、辞書「レジスタ名 → (書き手の EX サイクル, 書き手の種類)」を更新しながら進む。
    """
    raise NotImplementedError("演習5: schedule を実装してください")


def count_stalls(program: list[Instr], forwarding: bool) -> int:
    """ストール（待たされたサイクル）の合計。schedule を使う（用意済み）。

    ストールがなければ i 番目の EX は 3 + i。遅れは後ろの命令に引き継がれるので、
    最後の命令の遅れがストールの合計になる。
    """
    ex = schedule(program, forwarding)
    return ex[-1] - (len(ex) + 2) if ex else 0


def total_cycles(program: list[Instr], forwarding: bool) -> int:
    """最後の命令が WB を終えるまでのサイクル数（用意済み）。n 命令でストールがなければ n + 4。"""
    ex = schedule(program, forwarding)
    return ex[-1] + 2 if ex else 0


def _label(ins: Instr) -> str:
    if ins.kind == "nop":
        return "nop"
    left = ins.dst or ""
    right = ",".join(ins.srcs)
    return f"{ins.kind} {left}<-{right}" if left else f"{ins.kind} <-{right}"


def render(program: list[Instr], forwarding: bool) -> str:
    """パイプラインの図（テキスト）を返す（用意済み。schedule が完成すると使えます）。

    「--」は前の段で待たされている（ストールしている）サイクル。print(render(prog, True)) で表示できます。
    """
    ex = schedule(program, forwarding)
    if not ex:
        return ""
    width = ex[-1] + 2
    label_w = max(len(_label(ins)) for ins in program) + 1
    lines = [" " * label_w + "".join(f"{c:>4}" for c in range(1, width + 1))]
    id_start_prev = 2
    for i, (ins, e) in enumerate(zip(program, ex)):
        # i 番目は、前の命令が ID に入ったサイクルに IF に入り、前の命令が EX に進んだサイクルに ID に入る
        if_start = 1 if i == 0 else id_start_prev
        id_start = 2 if i == 0 else ex[i - 1]
        cells = ["    "] * width
        for c in range(if_start, id_start):
            cells[c - 1] = "  IF" if c == if_start else "  --"
        for c in range(id_start, e):
            cells[c - 1] = "  ID" if c == id_start else "  --"
        cells[e - 1], cells[e], cells[e + 1] = "  EX", " MEM", "  WB"
        lines.append(_label(ins).ljust(label_w) + "".join(cells).rstrip())
        id_start_prev = id_start
    return "\n".join(lines)
