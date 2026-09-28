"""3.3 メモリ管理とランタイム — ガベージコレクタのシミュレーション（解答例）

演習の仕様は exercises/gc_sim.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 演習1: マーク＆スイープ
# ---------------------------------------------------------------------------


@dataclass
class ObjectGraph:
    objects: dict[int, list[int]] = field(default_factory=dict)
    roots: set[int] = field(default_factory=set)
    _next_id: int = 1

    def new(self, *refs: int, root: bool = False) -> int:
        for r in refs:
            if r not in self.objects:
                raise KeyError(f"存在しないオブジェクトは参照できません: {r}")
        oid = self._next_id
        self._next_id += 1
        self.objects[oid] = list(refs)
        if root:
            self.roots.add(oid)
        return oid

    def link(self, src: int, dst: int) -> None:
        if dst not in self.objects:
            raise KeyError(f"存在しないオブジェクトは参照できません: {dst}")
        self.objects[src].append(dst)

    def unlink(self, src: int, dst: int) -> None:
        self.objects[src].remove(dst)


def mark(graph: ObjectGraph) -> set[int]:
    marked: set[int] = set()
    # 再帰ではなく明示的なスタック（作業リスト）を使う。長い連結リストでも安全
    stack = list(graph.roots)
    while stack:
        oid = stack.pop()
        if oid in marked:
            continue  # 循環していても、印の付いたオブジェクトは二度と辿らない
        if oid not in graph.objects:
            raise ValueError(f"存在しないオブジェクト {oid} への参照があります（ヒープが壊れています）")
        marked.add(oid)
        stack.extend(graph.objects[oid])
    return marked


def sweep(graph: ObjectGraph, marked: set[int]) -> set[int]:
    garbage = {oid for oid in graph.objects if oid not in marked}
    for oid in garbage:
        del graph.objects[oid]
    return garbage


def collect(graph: ObjectGraph) -> set[int]:
    return sweep(graph, mark(graph))


# ---------------------------------------------------------------------------
# 演習3: 参照カウントと循環参照の回収
# ---------------------------------------------------------------------------


class HeapError(Exception):
    """解放済み・存在しないオブジェクトの操作など、ヒープの使い方の誤り。"""


class RefCountHeap:
    def __init__(self) -> None:
        self.refcount: dict[int, int] = {}
        self.refs: dict[int, list[int]] = {}
        self.freed_log: list[int] = []
        self._next_id = 1

    def _check_alive(self, oid: int) -> None:
        if oid not in self.refcount:
            raise HeapError(f"解放済み、または存在しないオブジェクトです: {oid}（use-after-free）")

    def is_alive(self, oid: int) -> bool:
        return oid in self.refcount

    def new(self) -> int:
        oid = self._next_id
        self._next_id += 1
        self.refcount[oid] = 1  # 作った側が 1 つ参照を持っている
        self.refs[oid] = []
        return oid

    def incref(self, oid: int) -> None:
        self._check_alive(oid)
        self.refcount[oid] += 1

    def _release(self, oid: int) -> list[int]:
        """oid の参照カウントを 1 減らし、0 になったら連鎖的に解放する。"""
        freed: list[int] = []
        worklist = [oid]
        # 解放の連鎖も再帰ではなく作業リストで処理する（長い連結リストの一括解放で
        # スタックが溢れないように。CPython も深い連鎖に対して同様の工夫をしている）
        while worklist:
            cur = worklist.pop()
            self.refcount[cur] -= 1
            if self.refcount[cur] == 0:
                children = self.refs.pop(cur)
                del self.refcount[cur]
                freed.append(cur)
                self.freed_log.append(cur)
                worklist.extend(children)  # 解放したオブジェクトが持っていた参照を手放す
        return freed

    def decref(self, oid: int) -> list[int]:
        self._check_alive(oid)
        return self._release(oid)

    def add_ref(self, src: int, dst: int) -> None:
        self._check_alive(src)
        self._check_alive(dst)
        self.refs[src].append(dst)
        self.refcount[dst] += 1

    def remove_ref(self, src: int, dst: int) -> list[int]:
        self._check_alive(src)
        self._check_alive(dst)
        try:
            self.refs[src].remove(dst)
        except ValueError:
            raise HeapError(f"{src} は {dst} を参照していません") from None
        return self._release(dst)

    def collect_cycles(self) -> set[int]:
        # (1) 参照カウントを作業用にコピーする
        gc_refs = dict(self.refcount)
        # (2) ヒープ内のオブジェクトからの参照を差し引く。残った値は「ヒープの外から」の参照の数
        for oid, children in self.refs.items():
            for child in children:
                gc_refs[child] -= 1
        # (3) 外から参照されているオブジェクトを起点に、到達できるものはすべて生きている
        alive: set[int] = set()
        stack = [oid for oid, n in gc_refs.items() if n > 0]
        while stack:
            oid = stack.pop()
            if oid in alive:
                continue
            alive.add(oid)
            stack.extend(self.refs[oid])
        # (4) 残りは、互いの参照だけで生き延びていたゴミ（循環とそこからぶら下がるもの）
        garbage = set(self.refcount) - alive
        # (5) ゴミが生きているオブジェクトに向けていた参照を取り除き、ゴミを解放する
        for oid in garbage:
            for child in self.refs[oid]:
                if child not in garbage:
                    self.refcount[child] -= 1
        for oid in sorted(garbage):
            del self.refcount[oid]
            del self.refs[oid]
            self.freed_log.append(oid)
        return garbage


# ---------------------------------------------------------------------------
# 演習4: コピー GC（Cheney のアルゴリズム）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ref:
    addr: int


@dataclass(frozen=True)
class Forward:
    addr: int


class SemiSpaceHeap:
    def __init__(self, size: int) -> None:
        if size < 1:
            raise ValueError(f"size は 1 以上: {size}")
        self.size = size
        self.from_space: list[object] = [None] * size
        self.to_space: list[object] = [None] * size
        self.free = 0
        self.roots: list[Ref | None] = []
        self.collections = 0

    # ---- 与えられたもの ----
    def _n_fields(self, ref: Ref) -> int:
        if not isinstance(ref, Ref) or not 0 <= ref.addr < self.free:
            raise ValueError(f"無効な参照です: {ref!r}")
        header = self.from_space[ref.addr]
        if type(header) is not int:
            raise ValueError(f"オブジェクトの先頭を指していない参照です: {ref!r}")
        return header

    def read(self, ref: Ref, i: int) -> object:
        n = self._n_fields(ref)
        if not 0 <= i < n:
            raise IndexError(f"フィールド番号が範囲外です: {i}（フィールド数 {n}）")
        return self.from_space[ref.addr + 1 + i]

    def write(self, ref: Ref, i: int, value: object) -> None:
        n = self._n_fields(ref)
        if not 0 <= i < n:
            raise IndexError(f"フィールド番号が範囲外です: {i}（フィールド数 {n}）")
        if not (value is None or isinstance(value, Ref) or type(value) is int):
            raise TypeError(f"フィールドには int・Ref・None だけを書き込めます: {value!r}")
        self.from_space[ref.addr + 1 + i] = value

    def fields(self, ref: Ref) -> list[object]:
        n = self._n_fields(ref)
        return self.from_space[ref.addr + 1 : ref.addr + 1 + n]

    # ---- 演習 ----
    def alloc(self, fields: list[object]) -> Ref:
        for v in fields:
            if not (v is None or isinstance(v, Ref) or type(v) is int):
                raise TypeError(f"フィールドには int・Ref・None だけを書き込めます: {v!r}")
        need = 1 + len(fields)
        if self.free + need > self.size:
            # GC はオブジェクトを移動させる。fields の中の参照も一時的にルートに加えて
            # 一緒に更新しないと、移動前の古いアドレスを書き込んでしまう
            base = len(self.roots)
            self.roots.extend(v if isinstance(v, Ref) else None for v in fields)
            self.collect()
            moved = self.roots[base:]
            del self.roots[base:]
            fields = [m if isinstance(v, Ref) else v for v, m in zip(fields, moved)]
            if self.free + need > self.size:
                raise MemoryError(
                    f"GC 後も空きが足りません（必要 {need} ワード、空き {self.size - self.free} ワード）"
                )
        addr = self.free  # バンプポインタ: 空き領域の先頭から切り出すだけ
        self.from_space[addr] = len(fields)
        self.from_space[addr + 1 : addr + 1 + len(fields)] = fields
        self.free += need
        return Ref(addr)

    def collect(self) -> int:
        to = self.to_space
        free = 0

        def evacuate(ref: Ref) -> Ref:
            nonlocal free
            header = self.from_space[ref.addr]
            if isinstance(header, Forward):
                return Ref(header.addr)  # コピー済み: 転送先を返す（共有と循環が保たれる）
            n = header
            new_addr = free
            to[new_addr : new_addr + 1 + n] = self.from_space[ref.addr : ref.addr + 1 + n]
            free += 1 + n
            self.from_space[ref.addr] = Forward(new_addr)  # 元の場所に転送先を書いておく
            return Ref(new_addr)

        # (1) ルートが指すオブジェクトをコピーする
        for i, r in enumerate(self.roots):
            if isinstance(r, Ref):
                self.roots[i] = evacuate(r)
        # (2) to 空間を先頭から走査する。scan から free までが「未処理のキュー」になる（幅優先）
        scan = 0
        while scan < free:
            n = to[scan]
            for i in range(scan + 1, scan + 1 + n):
                if isinstance(to[i], Ref):
                    to[i] = evacuate(to[i])
            scan += 1 + n
        # (3) 空間を入れ替える。古い from 空間は丸ごと空き領域になる
        for i in range(self.size):
            self.from_space[i] = None
        self.from_space, self.to_space = to, self.from_space
        self.free = free
        self.collections += 1
        return free
