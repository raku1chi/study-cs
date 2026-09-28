"""4.2 仮想メモリ — 解答例: ページテーブル・TLB・ページ置換・コピーオンライト・ワーキングセット

演習の仕様は exercises/vmsim.py の docstring を参照してください。
"""
from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Hashable, NamedTuple, Sequence


class PageFault(Exception):
    """対応するページが存在しない（present でない）アドレスにアクセスした。"""

    def __init__(self, vaddr: int, reason: str = "ページが存在しません") -> None:
        super().__init__(f"{reason}: vaddr={vaddr:#x}")
        self.vaddr = vaddr


class ProtectionFault(Exception):
    """ページは存在するが、アクセスの種類が許可されていない。"""

    def __init__(self, vaddr: int, reason: str) -> None:
        super().__init__(f"{reason}: vaddr={vaddr:#x}")
        self.vaddr = vaddr


@dataclass
class PTE:
    frame: int
    present: bool = True
    writable: bool = True
    user: bool = True
    accessed: bool = False
    dirty: bool = False


# ---------------------------------------------------------------------------
# 演習1: 2 段のページテーブル
# ---------------------------------------------------------------------------

class TwoLevelPageTable:
    def __init__(self, page_size: int = 4096, l1_bits: int = 10, l2_bits: int = 10) -> None:
        if page_size < 1 or page_size & (page_size - 1):
            raise ValueError(f"page_size は 2 のべき乗: {page_size}")
        if l1_bits < 1 or l2_bits < 1:
            raise ValueError("l1_bits と l2_bits は 1 以上")
        self.page_size = page_size
        self.offset_bits = page_size.bit_length() - 1
        self.l1_bits = l1_bits
        self.l2_bits = l2_bits
        self.address_bits = self.offset_bits + l1_bits + l2_bits
        # 1 段目は最初から確保する。2 段目の表は、そこに対応付けが作られたときに初めて確保する
        self.root: list[list[PTE | None] | None] = [None] * (1 << l1_bits)

    def split(self, vaddr: int) -> tuple[int, int, int]:
        if not 0 <= vaddr < 1 << self.address_bits:
            raise ValueError(f"アドレス空間の範囲外です: {vaddr:#x}")
        offset = vaddr & (self.page_size - 1)
        l2 = (vaddr >> self.offset_bits) & ((1 << self.l2_bits) - 1)
        l1 = vaddr >> (self.offset_bits + self.l2_bits)
        return l1, l2, offset

    def _indices(self, vpn: int) -> tuple[int, int]:
        if not 0 <= vpn < 1 << (self.l1_bits + self.l2_bits):
            raise ValueError(f"仮想ページ番号が範囲外です: {vpn}")
        return vpn >> self.l2_bits, vpn & ((1 << self.l2_bits) - 1)

    def map(self, vpn: int, frame: int, *, writable: bool = True, user: bool = True) -> None:
        if frame < 0:
            raise ValueError(f"フレーム番号は 0 以上: {frame}")
        l1, l2 = self._indices(vpn)
        if self.root[l1] is None:
            self.root[l1] = [None] * (1 << self.l2_bits)
        self.root[l1][l2] = PTE(frame=frame, writable=writable, user=user)

    def unmap(self, vpn: int) -> None:
        l1, l2 = self._indices(vpn)
        table = self.root[l1]
        if table is not None:
            table[l2] = None  # 簡略化: 空になった 2 段目の表は解放しない

    def lookup(self, vpn: int) -> PTE | None:
        l1, l2 = self._indices(vpn)
        table = self.root[l1]
        return None if table is None else table[l2]

    def translate(self, vaddr: int, *, write: bool = False, user: bool = True) -> int:
        l1, l2, offset = self.split(vaddr)
        table = self.root[l1]  # メモリアクセス 1 回目（1 段目の表を読む）
        pte = None if table is None else table[l2]  # メモリアクセス 2 回目（2 段目の表を読む）
        if pte is None or not pte.present:
            raise PageFault(vaddr)
        if write and not pte.writable:
            raise ProtectionFault(vaddr, "読み取り専用のページへの書き込み")
        if user and not pte.user:
            raise ProtectionFault(vaddr, "ユーザーモードからカーネル専用のページへのアクセス")
        pte.accessed = True  # ページ置換（Clock など）が参照する「最近使われた」印
        if write:
            pte.dirty = True  # 追い出すときにディスクへ書き戻す必要がある印
        return pte.frame * self.page_size + offset

    def table_count(self) -> int:
        return 1 + sum(t is not None for t in self.root)

    def table_bytes(self, pte_size: int = 4) -> int:
        second_level = sum(t is not None for t in self.root)
        return ((1 << self.l1_bits) + second_level * (1 << self.l2_bits)) * pte_size


# ---------------------------------------------------------------------------
# 演習2: TLB と MMU
# ---------------------------------------------------------------------------

class TLBEntry(NamedTuple):
    frame: int
    writable: bool
    user: bool


class TLB:
    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError(f"capacity は 1 以上: {capacity}")
        self.capacity = capacity
        self._entries: OrderedDict[int, object] = OrderedDict()  # 末尾ほど最近使われた
        self.hits = 0
        self.misses = 0

    def lookup(self, vpn: int) -> object | None:
        entry = self._entries.get(vpn)
        if entry is None:
            self.misses += 1
            return None
        self.hits += 1
        self._entries.move_to_end(vpn)
        return entry

    def insert(self, vpn: int, entry: object) -> int | None:
        if vpn in self._entries:
            self._entries[vpn] = entry
            self._entries.move_to_end(vpn)
            return None
        evicted = None
        if len(self._entries) >= self.capacity:
            evicted, _ = self._entries.popitem(last=False)  # 最も長く使われていないものを捨てる
        self._entries[vpn] = entry
        return evicted

    def invalidate(self, vpn: int | None = None) -> None:
        if vpn is None:
            self._entries.clear()  # 全消去（ASID/PCID のない CPU でのプロセス切り替えに相当）
        else:
            self._entries.pop(vpn, None)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, vpn: object) -> bool:
        return vpn in self._entries


class MMU:
    def __init__(self, page_table: TwoLevelPageTable, tlb: TLB) -> None:
        self.page_table = page_table
        self.tlb = tlb
        self.walks = 0

    def translate(self, vaddr: int, *, write: bool = False, user: bool = True) -> int:
        self.page_table.split(vaddr)  # 範囲の検査
        vpn, offset = divmod(vaddr, self.page_table.page_size)
        entry = self.tlb.lookup(vpn)
        if entry is None:
            # TLB ミス: ページテーブルをたどる（ページテーブルウォーク）。フォールトならキャッシュしない
            self.walks += 1
            paddr = self.page_table.translate(vaddr, write=write, user=user)
            pte = self.page_table.lookup(vpn)
            self.tlb.insert(vpn, TLBEntry(pte.frame, pte.writable, pte.user))  # その時点の写しを保持する
            return paddr
        # TLB ヒット: メモリ上のページテーブルを見ずに変換する。権限の検査は TLB の写しで行う
        if write and not entry.writable:
            raise ProtectionFault(vaddr, "読み取り専用のページへの書き込み")
        if user and not entry.user:
            raise ProtectionFault(vaddr, "ユーザーモードからカーネル専用のページへのアクセス")
        return entry.frame * self.page_table.page_size + offset


# ---------------------------------------------------------------------------
# 演習3: ページ置換アルゴリズム
# ---------------------------------------------------------------------------

def _check_frames(frames: int) -> None:
    if frames < 1:
        raise ValueError(f"frames は 1 以上: {frames}")


def simulate_fifo(refs: Sequence[Hashable], frames: int) -> int:
    _check_frames(frames)
    resident: set[Hashable] = set()
    order: deque[Hashable] = deque()  # 読み込んだ順
    faults = 0
    for page in refs:
        if page in resident:
            continue  # FIFO はヒットしても順番を変えない
        faults += 1
        if len(resident) == frames:
            resident.discard(order.popleft())  # 最も古く読み込んだページを追い出す
        resident.add(page)
        order.append(page)
    return faults


def simulate_lru(refs: Sequence[Hashable], frames: int) -> int:
    _check_frames(frames)
    recent: OrderedDict[Hashable, None] = OrderedDict()  # 末尾ほど最近使われた
    faults = 0
    for page in refs:
        if page in recent:
            recent.move_to_end(page)
            continue
        faults += 1
        if len(recent) == frames:
            recent.popitem(last=False)  # 最も長く使われていないページを追い出す
        recent[page] = None
    return faults


def simulate_opt(refs: Sequence[Hashable], frames: int) -> int:
    _check_frames(frames)
    n = len(refs)
    # next_use[i] = refs[i] と同じページが次に参照される位置（なければ無限大）。後ろから一度走査して求める
    next_use = [0] * n
    last_seen: dict[Hashable, int] = {}
    for i in range(n - 1, -1, -1):
        next_use[i] = last_seen.get(refs[i], n + i)  # 二度と使われないものは遠い未来（n 以上）とする
        last_seen[refs[i]] = i
    resident: dict[Hashable, int] = {}  # ページ -> 次に参照される位置
    faults = 0
    for i, page in enumerate(refs):
        if page not in resident:
            faults += 1
            if len(resident) == frames:
                victim = max(resident, key=resident.__getitem__)  # 最も遠い未来まで使われないもの
                del resident[victim]
        resident[page] = next_use[i]
    return faults


def simulate_clock(refs: Sequence[Hashable], frames: int) -> int:
    _check_frames(frames)
    slots: list[Hashable | None] = [None] * frames
    ref_bit = [False] * frames
    where: dict[Hashable, int] = {}  # ページ -> スロット番号
    hand = 0
    faults = 0
    for page in refs:
        slot = where.get(page)
        if slot is not None:
            ref_bit[slot] = True  # 使われた印（ハードウェアが PTE の accessed ビットを立てるのに相当）
            continue
        faults += 1
        if len(where) < frames:
            slot = slots.index(None)  # 空きフレームがあれば番号の小さい方から使う
        else:
            while ref_bit[hand]:  # 印の付いたページには「もう一度だけ機会」を与え、印を消して進む
                ref_bit[hand] = False
                hand = (hand + 1) % frames
            slot = hand
            del where[slots[slot]]
            hand = (hand + 1) % frames
        slots[slot] = page
        ref_bit[slot] = True
        where[page] = slot
    return faults


# ---------------------------------------------------------------------------
# 演習4: コピーオンライトの fork
# ---------------------------------------------------------------------------

@dataclass
class CowPTE:
    frame: int
    writable: bool
    cow: bool = False  # 書き込まれたらコピーすべき共有ページか


class CowMemory:
    def __init__(self) -> None:
        self.frames: dict[int, object] = {}  # フレーム番号 -> 内容
        self.refcount: dict[int, int] = {}  # フレーム番号 -> 参照しているページの数
        self.page_tables: dict[int, dict[int, CowPTE]] = {}  # pid -> {vpn: PTE}
        self.copies = 0
        self.cow_faults = 0
        self._next_frame = 0
        self._next_pid = 1

    def _table(self, pid: int) -> dict[int, CowPTE]:
        try:
            return self.page_tables[pid]
        except KeyError:
            raise ValueError(f"存在しないプロセスです: {pid}") from None

    def _new_frame(self, value: object) -> int:
        frame = self._next_frame
        self._next_frame += 1
        self.frames[frame] = value
        self.refcount[frame] = 1
        return frame

    def _release(self, frame: int) -> None:
        self.refcount[frame] -= 1
        if self.refcount[frame] == 0:
            del self.refcount[frame]
            del self.frames[frame]

    def spawn(self) -> int:
        pid = self._next_pid
        self._next_pid += 1
        self.page_tables[pid] = {}
        return pid

    def alloc(self, pid: int, vpn: int, value: object, *, writable: bool = True) -> None:
        table = self._table(pid)
        if vpn in table:
            raise ValueError(f"vpn {vpn} はすでに割り当て済みです")
        table[vpn] = CowPTE(self._new_frame(value), writable)

    def fork(self, pid: int) -> int:
        parent = self._table(pid)
        child_pid = self.spawn()
        child = self.page_tables[child_pid]
        for vpn, pte in parent.items():
            # データはコピーしない。同じフレームを指し、参照数を増やすだけ
            self.refcount[pte.frame] += 1
            if pte.writable or pte.cow:
                # 書き込み可能だったページは、親子の両方で読み取り専用＋CoW にする
                pte.writable, pte.cow = False, True
            child[vpn] = CowPTE(pte.frame, pte.writable, pte.cow)
        return child_pid

    def read(self, pid: int, vpn: int) -> object:
        pte = self._table(pid).get(vpn)
        if pte is None:
            raise PageFault(vpn)
        return self.frames[pte.frame]

    def write(self, pid: int, vpn: int, value: object) -> None:
        pte = self._table(pid).get(vpn)
        if pte is None:
            raise PageFault(vpn)
        if not pte.writable:
            if not pte.cow:
                raise ProtectionFault(vpn, "読み取り専用のページへの書き込み")
            # ここが CoW のページフォールト処理
            self.cow_faults += 1
            if self.refcount[pte.frame] > 1:
                old = pte.frame
                pte.frame = self._new_frame(self.frames[old])  # 内容をコピーした新しいフレーム
                self._release(old)
                self.copies += 1
            # 参照が自分だけなら、コピーせずにそのまま書き込み可能に戻せる
            pte.writable, pte.cow = True, False
        self.frames[pte.frame] = value

    def exit(self, pid: int) -> None:
        table = self._table(pid)
        for pte in table.values():
            self._release(pte.frame)
        del self.page_tables[pid]

    def frames_in_use(self) -> int:
        return len(self.frames)


# ---------------------------------------------------------------------------
# 演習5: ワーキングセット
# ---------------------------------------------------------------------------

def working_set_sizes(refs: Sequence[Hashable], window: int) -> list[int]:
    if window < 1:
        raise ValueError(f"window は 1 以上: {window}")
    counts: dict[Hashable, int] = {}  # 窓の中での出現回数
    sizes: list[int] = []
    for t, page in enumerate(refs):
        counts[page] = counts.get(page, 0) + 1
        if t >= window:  # 窓から外れた参照を 1 つ取り除く
            old = refs[t - window]
            counts[old] -= 1
            if counts[old] == 0:
                del counts[old]
        sizes.append(len(counts))
    return sizes
