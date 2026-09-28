"""1.2 論理回路と CPU の仕組み — 演習5 解答例: 5 段パイプラインのデータハザード

仕様（パイプラインのモデル）は exercises/pipesim.py の docstring を参照してください。
"""
from __future__ import annotations

from typing import NamedTuple, Optional

KINDS = ("alu", "load", "store", "nop")


class Instr(NamedTuple):
    kind: str                   # "alu" | "load" | "store" | "nop"
    dst: Optional[str] = None   # 結果を書き込むレジスタ（store と nop は None）
    srcs: tuple[str, ...] = ()  # 読み出すレジスタ


def _validate(program: list[Instr]) -> None:
    for i, ins in enumerate(program):
        if ins.kind not in KINDS:
            raise ValueError(f"{i} 番目: 未知の種類です: {ins.kind!r}")
        if ins.kind in ("alu", "load") and ins.dst is None:
            raise ValueError(f"{i} 番目: {ins.kind} には dst が必要です")
        if ins.kind in ("store", "nop") and ins.dst is not None:
            raise ValueError(f"{i} 番目: {ins.kind} は dst を持ちません")
        if ins.kind == "nop" and ins.srcs:
            raise ValueError(f"{i} 番目: nop は srcs を持ちません")


def schedule(program: list[Instr], forwarding: bool) -> list[int]:
    _validate(program)
    ex_cycles: list[int] = []
    # レジスタ名 → (そのレジスタを最後に書いた命令の EX サイクル, その命令の種類)
    last_writer: dict[str, tuple[int, str]] = {}
    for k, ins in enumerate(program):
        # 1 サイクルに 1 命令ずつ、順番どおりに進む（最初の命令は IF=1, ID=2, EX=3）
        earliest = 3 if k == 0 else ex_cycles[-1] + 1
        for reg in ins.srcs:
            if reg not in last_writer:
                continue  # プログラムより前から入っている値（ハザードなし）
            ex_p, kind_p = last_writer[reg]
            if not forwarding:
                # 書き込みは WB（EX の 2 サイクル後）の前半、読み出しは ID の後半。
                # 読む側の ID >= 書く側の WB  ⇔  読む側の EX >= 書く側の EX + 3
                need = ex_p + 3
            elif kind_p == "load":
                # ロードの値は MEM の終わりに分かる → 次の次のサイクルの EX へ転送（ロードユース）
                need = ex_p + 2
            else:
                # ALU の結果は EX の終わりに分かる → 直後の命令の EX へ転送できる
                need = ex_p + 1
            earliest = max(earliest, need)
        ex_cycles.append(earliest)
        if ins.dst is not None:
            last_writer[ins.dst] = (earliest, ins.kind)
    return ex_cycles


def count_stalls(program: list[Instr], forwarding: bool) -> int:
    ex = schedule(program, forwarding)
    # ストールがなければ i 番目の EX は 3 + i。順番どおりに進むので、遅れは後ろの命令に引き継がれる。
    # よって最後の命令の遅れが、ストールの合計になる
    return ex[-1] - (len(ex) + 2) if ex else 0


def total_cycles(program: list[Instr], forwarding: bool) -> int:
    ex = schedule(program, forwarding)
    # 最後の命令の WB が終わるサイクル = 最後の EX + 2（MEM, WB）
    return ex[-1] + 2 if ex else 0


def _label(ins: Instr) -> str:
    if ins.kind == "nop":
        return "nop"
    left = ins.dst or ""
    right = ",".join(ins.srcs)
    return f"{ins.kind} {left}<-{right}" if left else f"{ins.kind} <-{right}"


def render(program: list[Instr], forwarding: bool) -> str:
    """パイプラインの図（テキスト）を返す。「--」は前の段で待たされている（ストール）サイクル。"""
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
