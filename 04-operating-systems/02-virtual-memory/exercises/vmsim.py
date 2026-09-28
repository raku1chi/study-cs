"""4.2 仮想メモリ — 演習: ページテーブル・TLB・ページ置換・コピーオンライト・ワーキングセット

MMU と OS のメモリ管理の中核を、小さなシミュレータとして実装します。
各関数・メソッドの docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 4.2          # 合格数を表示
    python3 tools/check.py -v 4.2       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v

演習の一覧:
    演習1（★★☆）: TwoLevelPageTable — 2 段のページテーブルによるアドレス変換と保護
    演習2（★★☆）: TLB と MMU — LRU で入れ替える TLB と、ヒット率の計測
    演習3（★★☆）: simulate_fifo / lru / opt / clock — ページ置換アルゴリズム
    演習4（★★★）: CowMemory — コピーオンライトの fork
    演習5（★★☆）: working_set_sizes — ワーキングセットの大きさ
"""
from __future__ import annotations

from collections import OrderedDict, deque  # noqa: F401  演習2・3 で使えます
from dataclasses import dataclass
from typing import Hashable, NamedTuple, Sequence


class PageFault(Exception):
    """対応するページが存在しない（present でない）アドレスにアクセスした。"""

    def __init__(self, vaddr: int, reason: str = "ページが存在しません") -> None:
        super().__init__(f"{reason}: vaddr={vaddr:#x}")
        self.vaddr = vaddr


class ProtectionFault(Exception):
    """ページは存在するが、アクセスの種類（書き込み・ユーザーモード）が許可されていない。"""

    def __init__(self, vaddr: int, reason: str) -> None:
        super().__init__(f"{reason}: vaddr={vaddr:#x}")
        self.vaddr = vaddr


@dataclass
class PTE:
    """ページテーブルエントリ（Page Table Entry）。実際の CPU では 1 つの整数のビットで表す。"""

    frame: int  # 物理フレーム番号
    present: bool = True  # P ビット: 物理メモリ上にあるか
    writable: bool = True  # R/W ビット: 書き込み可能か
    user: bool = True  # U/S ビット: ユーザーモードからアクセス可能か
    accessed: bool = False  # A ビット: 最近アクセスされたか（CPU が立てる）
    dirty: bool = False  # D ビット: 書き込まれたか（CPU が立てる）


# ---------------------------------------------------------------------------
# 演習1（★★☆）: 2 段のページテーブル
# ---------------------------------------------------------------------------

class TwoLevelPageTable:
    """2 段のページテーブル。既定値は 32 ビットの x86 と同じ（10 + 10 + 12 ビット）。

    仮想アドレスのビットの分け方（上位から）:

        | 1 段目の添字 (l1_bits) | 2 段目の添字 (l2_bits) | ページ内オフセット (log2(page_size)) |

    仮想ページ番号（VPN）= 仮想アドレス // page_size = (1 段目の添字 << l2_bits) | 2 段目の添字

    - 1 段目の表（要素数 2**l1_bits）は最初から確保する。
    - 2 段目の表（要素数 2**l2_bits）は、その範囲に初めて map() されたときに確保する。
      こうすると、使っていないアドレス範囲の表を持たずに済む（多段にする理由）。
    - 簡略化: unmap() で空になった 2 段目の表は解放しない。
    """

    def __init__(self, page_size: int = 4096, l1_bits: int = 10, l2_bits: int = 10) -> None:
        if page_size < 1 or page_size & (page_size - 1):
            raise ValueError(f"page_size は 2 のべき乗: {page_size}")
        if l1_bits < 1 or l2_bits < 1:
            raise ValueError("l1_bits と l2_bits は 1 以上")
        self.page_size = page_size
        self.offset_bits = page_size.bit_length() - 1  # 4096 なら 12
        self.l1_bits = l1_bits
        self.l2_bits = l2_bits
        self.address_bits = self.offset_bits + l1_bits + l2_bits  # 既定値なら 32
        # 1 段目の表。各要素は None（2 段目の表がない）か、長さ 2**l2_bits のリスト（要素は PTE か None）
        self.root: list[list[PTE | None] | None] = [None] * (1 << l1_bits)

    def split(self, vaddr: int) -> tuple[int, int, int]:
        """仮想アドレスを (1 段目の添字, 2 段目の添字, オフセット) に分ける。

        0 <= vaddr < 2**address_bits でなければ ValueError。

        >>> TwoLevelPageTable().split(0x12345678)
        (72, 837, 1656)

        ヒント: シフト（>>）とマスク（& ((1 << n) - 1)）で取り出す（1.1 の演習と同じ技法）。
        """
        raise NotImplementedError("演習1: split を実装してください")

    def map(self, vpn: int, frame: int, *, writable: bool = True, user: bool = True) -> None:
        """仮想ページ vpn を物理フレーム frame に対応付ける（present=True の PTE を作る）。

        既に対応付けがあれば上書きする。vpn が範囲外（0 <= vpn < 2**(l1_bits + l2_bits) でない）
        または frame < 0 なら ValueError。
        """
        raise NotImplementedError("演習1: map を実装してください")

    def unmap(self, vpn: int) -> None:
        """vpn の対応付けを消す（対応付けがなければ何もしない）。vpn が範囲外なら ValueError。"""
        raise NotImplementedError("演習1: unmap を実装してください")

    def lookup(self, vpn: int) -> PTE | None:
        """vpn の PTE を返す（なければ None）。検査やフラグの操作はしない。範囲外は ValueError。"""
        raise NotImplementedError("演習1: lookup を実装してください")

    def translate(self, vaddr: int, *, write: bool = False, user: bool = True) -> int:
        """仮想アドレスを物理アドレス（frame * page_size + オフセット）に変換する。

        - PTE がない、または present でなければ PageFault(vaddr)
        - write=True なのに writable でなければ ProtectionFault(vaddr, 理由)
        - user=True（ユーザーモードのアクセス）なのに PTE の user が False なら ProtectionFault
        - 成功したら PTE の accessed を True に、write=True なら dirty も True にする
        - vaddr が範囲外なら ValueError

        >>> pt = TwoLevelPageTable()
        >>> pt.map(0x12345, 0x777)
        >>> hex(pt.translate(0x12345678))
        '0x777678'
        """
        raise NotImplementedError("演習1: translate を実装してください")

    def table_count(self) -> int:
        """確保されている表の数（1 段目の表 1 つ ＋ 確保済みの 2 段目の表の数）。"""
        raise NotImplementedError("演習1: table_count を実装してください")

    def table_bytes(self, pte_size: int = 4) -> int:
        """表が占めるメモリのバイト数。1 エントリ pte_size バイトとして、全エントリ数 × pte_size。

        例: 既定の形で 2 段目の表が 2 つなら (1024 + 2 * 1024) * 4 = 12288 バイト。
        """
        raise NotImplementedError("演習1: table_bytes を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: TLB と MMU
# ---------------------------------------------------------------------------

class TLBEntry(NamedTuple):
    """TLB が覚えておく、変換結果の写し。"""

    frame: int
    writable: bool
    user: bool


class TLB:
    """容量 capacity の TLB。満杯のときは、最も長く使われていない（LRU）エントリを追い出す。

    キーは仮想ページ番号（vpn）、値は任意のオブジェクト（MMU は TLBEntry を入れる）。
    hits / misses は lookup() の結果だけを数える（insert や invalidate では変わらない）。
    """

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError(f"capacity は 1 以上: {capacity}")
        self.capacity = capacity
        self._entries: OrderedDict[int, object] = OrderedDict()  # 末尾ほど最近使われた、として使うとよい
        self.hits = 0
        self.misses = 0

    def lookup(self, vpn: int) -> object | None:
        """vpn のエントリを返す。あれば hits を 1 増やし「最近使われた」扱いにする。
        なければ misses を 1 増やして None を返す。"""
        raise NotImplementedError("演習2: TLB.lookup を実装してください")

    def insert(self, vpn: int, entry: object) -> int | None:
        """エントリを追加し、追い出した vpn を返す（追い出さなければ None）。

        vpn が既にあれば値を更新して「最近使われた」扱いにする（このときは追い出さない）。
        """
        raise NotImplementedError("演習2: TLB.insert を実装してください")

    def invalidate(self, vpn: int | None = None) -> None:
        """vpn のエントリを消す（なければ何もしない）。vpn が None なら全エントリを消す（フラッシュ）。"""
        raise NotImplementedError("演習2: TLB.invalidate を実装してください")

    @property
    def hit_rate(self) -> float:
        """hits / (hits + misses)。まだ一度も lookup していなければ 0.0。"""
        raise NotImplementedError("演習2: TLB.hit_rate を実装してください")

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, vpn: object) -> bool:
        return vpn in self._entries  # 統計や LRU の順序は変えない


class MMU:
    """TLB とページテーブルを組み合わせてアドレスを変換する。

    walks: ページテーブルを引いた（ページテーブルウォークをした）回数
    """

    def __init__(self, page_table: TwoLevelPageTable, tlb: TLB) -> None:
        self.page_table = page_table
        self.tlb = tlb
        self.walks = 0

    def translate(self, vaddr: int, *, write: bool = False, user: bool = True) -> int:
        """仮想アドレスを物理アドレスに変換する。

        1. vaddr が範囲外なら ValueError（page_table.split で検査できる）。
        2. TLB を vpn で引く（tlb.lookup）。
        3. ミスなら walks を 1 増やし、page_table.translate で変換する（フォールトはそのまま送出し、
           TLB には入れない）。成功したら、その時点の PTE の写し TLBEntry(frame, writable, user) を
           TLB に入れる。
        4. ヒットなら、ページテーブルは見ずに、TLB の写しで権限を検査して変換する
           （違反なら ProtectionFault）。簡略化のため、ヒット時は PTE の accessed/dirty を更新しない。

        TLB は写しを持つので、OS がページテーブルを書き換えたら、該当するエントリを
        tlb.invalidate() で消さない限り、古い変換が使われ続ける（テストで確かめます）。
        """
        raise NotImplementedError("演習2: MMU.translate を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: ページ置換アルゴリズム
# ---------------------------------------------------------------------------
# どの関数も、ページ参照列 refs を先頭から処理したときのページフォールトの回数を返す。
# - 物理フレームは frames 個。最初はすべて空で、空きがあるうちは追い出さずに読み込む。
# - ページは任意のハッシュ可能な値（整数、文字列など）。
# - frames < 1 なら ValueError。refs が空なら 0。

def simulate_fifo(refs: Sequence[Hashable], frames: int) -> int:
    """FIFO: 最も古く読み込んだページを追い出す（ヒットしても順番は変わらない）。

    >>> simulate_fifo([1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5], 3)
    9
    """
    raise NotImplementedError("演習3: simulate_fifo を実装してください")


def simulate_lru(refs: Sequence[Hashable], frames: int) -> int:
    """LRU: 最も長く使われていないページを追い出す。"""
    raise NotImplementedError("演習3: simulate_lru を実装してください")


def simulate_opt(refs: Sequence[Hashable], frames: int) -> int:
    """OPT（Belady の MIN）: 次に使われるのが最も遠い未来（二度と使われないものを最優先）のページを追い出す。

    未来の参照を知っている必要があるので実際の OS では使えないが、他の方式を評価する基準になる。
    ヒント: 各位置について「同じページが次に参照される位置」を、refs を後ろから 1 回走査して
    前計算しておくと効率よく実装できる。
    """
    raise NotImplementedError("演習3: simulate_opt を実装してください")


def simulate_clock(refs: Sequence[Hashable], frames: int) -> int:
    """Clock（セカンドチャンス）: 参照ビットで LRU を近似する。

    フレームを 0〜frames-1 の円環として並べ、針（hand）を 1 つ持つ。針の初期位置は 0。
    - ヒット: そのページの参照ビットを 1 にする。
    - ミスで空きフレームがある: 番号の最も小さい空きフレームに読み込み、参照ビットを 1 にする
      （針は動かさない）。
    - ミスで空きがない: 針の指すフレームの参照ビットが 1 なら 0 にして針を 1 つ進める、を繰り返す。
      参照ビットが 0 のフレームに当たったら、そのページを追い出して新しいページを読み込み、
      参照ビットを 1 にして、針を 1 つ進める。

    >>> simulate_clock([1, 2, 3, 1, 4, 5], 3)
    5
    """
    raise NotImplementedError("演習3: simulate_clock を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★★）: コピーオンライトの fork
# ---------------------------------------------------------------------------

@dataclass
class CowPTE:
    frame: int
    writable: bool
    cow: bool = False  # 書き込まれたらコピーすべき共有ページか


class CowMemory:
    """物理フレームとプロセスごとのページテーブルを持ち、fork をコピーオンライトで実装する。

    属性:
        frames: フレーム番号 -> ページの内容（任意のオブジェクト）
        refcount: フレーム番号 -> そのフレームを指しているページの数
        page_tables: pid -> {vpn: CowPTE}
        copies: CoW によってページをコピーした回数
        cow_faults: CoW のページへの書き込み（コピーが必要かを判断する処理）が起きた回数

    存在しない pid を指定されたら ValueError。spawn と frames_in_use は実装済みです。
    """

    def __init__(self) -> None:
        self.frames: dict[int, object] = {}
        self.refcount: dict[int, int] = {}
        self.page_tables: dict[int, dict[int, CowPTE]] = {}
        self.copies = 0
        self.cow_faults = 0
        self._next_frame = 0  # 新しいフレームに振る番号（使い回さなくてよい）
        self._next_pid = 1

    def spawn(self) -> int:
        """ページを 1 つも持たない新しいプロセスを作り、その pid を返す。"""
        pid = self._next_pid
        self._next_pid += 1
        self.page_tables[pid] = {}
        return pid

    def frames_in_use(self) -> int:
        """使用中の物理フレームの数。"""
        return len(self.frames)

    def alloc(self, pid: int, vpn: int, value: object, *, writable: bool = True) -> None:
        """新しいフレームに value を入れ、プロセス pid の vpn に対応付ける（参照数 1）。

        writable=False なら読み取り専用のページ（プログラムのコードなど）になる。
        その vpn が既に割り当て済みなら ValueError。
        """
        raise NotImplementedError("演習4: alloc を実装してください")

    def fork(self, pid: int) -> int:
        """プロセス pid の子を作り、子の pid を返す。

        - データはコピーしない。子のページテーブルは、親と同じフレームを指す PTE の写しにする。
        - 各フレームの参照数を 1 ずつ増やす。
        - 書き込み可能だったページ（または既に CoW のページ）は、親子の **両方** で
          writable=False, cow=True にする。読み取り専用のページは読み取り専用のまま共有する。
        """
        raise NotImplementedError("演習4: fork を実装してください")

    def read(self, pid: int, vpn: int) -> object:
        """ページの内容を返す。対応付けがなければ PageFault(vpn)。"""
        raise NotImplementedError("演習4: read を実装してください")

    def write(self, pid: int, vpn: int, value: object) -> None:
        """ページに value を書き込む。

        - 対応付けがなければ PageFault(vpn)。
        - writable なら、そのまま書き込む。
        - cow のページなら cow_faults を 1 増やしたうえで:
            * フレームの参照数が 2 以上: 内容をコピーした新しいフレームを作り（copies を 1 増やす）、
              元のフレームの参照数を 1 減らし、この PTE を新しいフレームに向ける。
            * 参照数が 1（他に共有者がいない）: コピーせずにそのまま使う。
          どちらの場合も PTE を writable=True, cow=False にしてから書き込む。
        - 読み取り専用で cow でもないページなら ProtectionFault(vpn, 理由)。
        """
        raise NotImplementedError("演習4: write を実装してください")

    def exit(self, pid: int) -> None:
        """プロセスを終了させる。各ページのフレームの参照数を 1 減らし、0 になったフレームは解放する。"""
        raise NotImplementedError("演習4: exit を実装してください")


# ---------------------------------------------------------------------------
# 演習5（★★☆）: ワーキングセット
# ---------------------------------------------------------------------------

def working_set_sizes(refs: Sequence[Hashable], window: int) -> list[int]:
    """各時刻 t（0 始まり）のワーキングセット W(t, window) の大きさのリストを返す。

    W(t, window) = refs[max(0, t - window + 1)] 〜 refs[t] に現れる、異なるページの集合
    （直近 window 回の参照で使われたページ）。window < 1 なら ValueError。

    >>> working_set_sizes([1, 2, 1, 3, 4, 4, 4, 1], 3)
    [1, 2, 2, 3, 3, 2, 1, 2]

    ヒント: 毎回スライスして set() を作ると O(len(refs) × window) かかる。窓の中での各ページの
    出現回数を辞書で持ち、窓に入る参照と窓から出る参照だけを更新すれば O(len(refs)) になる。
    """
    raise NotImplementedError("演習5: working_set_sizes を実装してください")
