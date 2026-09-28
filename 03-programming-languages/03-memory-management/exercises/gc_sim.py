"""3.3 メモリ管理とランタイム — 演習1・3・4: ガベージコレクタのシミュレーション

実際のメモリの代わりに Python のデータ構造で「オブジェクトの参照関係」を表し、
ガベージコレクション（GC）の代表的なアルゴリズムを実装します。

    演習1（★★☆）: mark / sweep / collect      — マーク＆スイープ
    演習3（★★★）: RefCountHeap                  — 参照カウントと、循環参照の回収（試行削除）
    演習4（★★★）: SemiSpaceHeap.alloc / collect — コピー GC（Cheney のアルゴリズム）

（演習2 のメモリアロケータは allocator.py にあります）

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 3.3

このディレクトリで演習ごとに実行することもできます:
    python3 -m unittest -v test_gc_sim.TestExercise1MarkSweep
    python3 -m unittest -v test_gc_sim.TestExercise3RefCount
    python3 -m unittest -v test_gc_sim.TestExercise4Cheney

注意: テストには 10 万個のオブジェクトがつながったリストが含まれます。
グラフをたどる処理は再帰ではなく、明示的なスタック（リスト）を使って書いてください。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 演習1（★★☆）: マーク＆スイープ
# ---------------------------------------------------------------------------


@dataclass
class ObjectGraph:
    """シミュレーション用のヒープ（与えられたもの）。

    - objects: オブジェクト ID → そのオブジェクトが持つ参照（参照先 ID のリスト。重複あり）
    - roots:   ルート集合。グローバル変数やスタック上の局所変数など、プログラムが
               直接たどれる参照を表す。ルートから到達できるオブジェクトが「生きている」。

    >>> g = ObjectGraph()
    >>> a = g.new(root=True)      # ルートから参照されるオブジェクト
    >>> b = g.new()
    >>> g.link(a, b)              # a が b を参照する
    >>> g.objects
    {1: [2], 2: []}
    """

    objects: dict[int, list[int]] = field(default_factory=dict)
    roots: set[int] = field(default_factory=set)
    _next_id: int = 1

    def new(self, *refs: int, root: bool = False) -> int:
        """refs を参照する新しいオブジェクトを作り、その ID を返す。root=True ならルートに加える。"""
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
        """src から dst への参照を 1 つ追加する。"""
        if dst not in self.objects:
            raise KeyError(f"存在しないオブジェクトは参照できません: {dst}")
        self.objects[src].append(dst)

    def unlink(self, src: int, dst: int) -> None:
        """src から dst への参照を 1 つ取り除く。"""
        self.objects[src].remove(dst)


def mark(graph: ObjectGraph) -> set[int]:
    """ルートから参照をたどって到達できるオブジェクトの ID の集合を返す（マークフェーズ）。

    - 循環参照があっても停止すること（一度印を付けたオブジェクトは再び辿らない）。
    - ルートや参照が存在しないオブジェクトを指していたら ValueError（ヒープが壊れている）。
    - graph は変更しない。

    ヒント: 「これから調べるオブジェクト」を入れたスタック（作業リスト）を使う。
    3 色抽象で言えば、印の付いた集合が黒、スタックの中が灰色、それ以外が白。
    """
    raise NotImplementedError("演習1: mark を実装してください")


def sweep(graph: ObjectGraph, marked: set[int]) -> set[int]:
    """marked に含まれないオブジェクトを graph.objects から取り除き、その ID の集合を返す（スイープフェーズ）。"""
    raise NotImplementedError("演習1: sweep を実装してください")


def collect(graph: ObjectGraph) -> set[int]:
    """マーク＆スイープを 1 回行い、解放したオブジェクトの ID の集合を返す。

    >>> g = ObjectGraph()
    >>> a = g.new(root=True)
    >>> b = g.new(); c = g.new(b); g.link(b, c)   # b と c は互いに参照し合う（循環）が、ルートから届かない
    >>> sorted(collect(g))
    [2, 3]
    """
    raise NotImplementedError("演習1: collect を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★★）: 参照カウントと、循環参照の回収
# ---------------------------------------------------------------------------


class HeapError(Exception):
    """解放済み・存在しないオブジェクトの操作など、ヒープの使い方の誤り（与えられたもの）。"""


class RefCountHeap:
    """参照カウント方式のヒープのシミュレーション。

    各オブジェクトは参照カウント（自分を指している参照の数）を持つ。参照には 2 種類ある。
    - 外部参照: プログラムの変数などヒープの外からの参照。new() で 1 つ持った状態で作られ、
      incref() / decref() で増減する。
    - 内部参照: ヒープ内のオブジェクトのフィールドからの参照。add_ref() / remove_ref() で増減する。
      refs[src] に参照先の ID が（重複も含めて）並ぶ。

    参照カウントが 0 になったオブジェクトは **その場で** 解放され、そのオブジェクトが持っていた
    内部参照も手放される（参照先のカウントが減り、0 になればそれも連鎖的に解放される）。

    属性（与えられたもの）:
        refcount: dict[int, int]        生きているオブジェクト → 参照カウント
        refs: dict[int, list[int]]      生きているオブジェクト → 持っている内部参照
        freed_log: list[int]            解放されたオブジェクトの ID（解放された順）

    >>> h = RefCountHeap()
    >>> a = h.new(); b = h.new()
    >>> h.add_ref(a, b); h.decref(b)     # b は a からだけ参照される
    []
    >>> sorted(h.decref(a))              # a が解放されると、b も連鎖的に解放される
    [1, 2]
    """

    def __init__(self) -> None:
        self.refcount: dict[int, int] = {}
        self.refs: dict[int, list[int]] = {}
        self.freed_log: list[int] = []
        self._next_id = 1

    def is_alive(self, oid: int) -> bool:
        """oid がまだ解放されていなければ True（与えられたもの）。"""
        return oid in self.refcount

    def new(self) -> int:
        """参照カウント 1（作った側の外部参照）の新しいオブジェクトを作り、ID を返す。ID は 1, 2, 3, ... の順。"""
        raise NotImplementedError("演習3: RefCountHeap.new を実装してください")

    def incref(self, oid: int) -> None:
        """外部参照を 1 つ増やす。oid が生きていなければ HeapError。"""
        raise NotImplementedError("演習3: RefCountHeap.incref を実装してください")

    def decref(self, oid: int) -> list[int]:
        """外部参照を 1 つ減らす。解放されたオブジェクトの ID のリスト（順序は問わない）を返す。

        - oid が生きていなければ HeapError（解放済みのオブジェクトへの操作 = use-after-free を検出する）。
        - 参照カウントが 0 になったら解放し、連鎖的な解放も行う。解放したら freed_log にも追記する。
        - 長い連結リストが一度に解放されることがあるので、再帰ではなく作業リストで処理すること。
        """
        raise NotImplementedError("演習3: RefCountHeap.decref を実装してください")

    def add_ref(self, src: int, dst: int) -> None:
        """src のフィールドに dst への参照を 1 つ追加する（dst の参照カウントが増える）。

        src か dst が生きていなければ HeapError。
        """
        raise NotImplementedError("演習3: RefCountHeap.add_ref を実装してください")

    def remove_ref(self, src: int, dst: int) -> list[int]:
        """src から dst への参照を 1 つ取り除き、解放されたオブジェクトの ID のリストを返す。

        src か dst が生きていない、または src が dst を参照していなければ HeapError。
        """
        raise NotImplementedError("演習3: RefCountHeap.remove_ref を実装してください")

    def collect_cycles(self) -> set[int]:
        """循環参照によって回収されずに残ったゴミを見つけて解放し、その ID の集合を返す。

        参照カウントだけでは、互いに参照し合うオブジェクト（循環）は、外から誰も参照して
        いなくてもカウントが 0 にならず、永遠に解放されない（メモリリーク）。
        CPython の循環ガベージコレクタと同じ考え方（試行削除, trial deletion）で回収する:

        1. 生きている各オブジェクトについて、参照カウントを作業用の値 gc_refs にコピーする。
        2. 各オブジェクトが持つ内部参照について、参照先の gc_refs を 1 ずつ減らす。
           → 残った gc_refs は「ヒープの外からの参照（外部参照）の数」になる。
        3. gc_refs > 0 のオブジェクトを起点に、内部参照をたどって到達できるものを「生きている」とする。
        4. 生きていないものがゴミ（循環と、循環からしか参照されていないもの）。
        5. ゴミが「ゴミでないオブジェクト」に向けていた参照の分だけ、その参照カウントを減らし、
           ゴミを refcount と refs から取り除き、freed_log に追記する（ID の昇順で）。

        >>> h = RefCountHeap()
        >>> a = h.new(); b = h.new()
        >>> h.add_ref(a, b); h.add_ref(b, a)       # a と b が互いに参照し合う
        >>> h.decref(a), h.decref(b)               # 外部参照を手放しても解放されない（リーク）
        ([], [])
        >>> sorted(h.collect_cycles())
        [1, 2]
        """
        raise NotImplementedError("演習3: RefCountHeap.collect_cycles を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★★）: コピー GC（Cheney のアルゴリズム）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ref:
    """ヒープ内のオブジェクトへの参照（ポインタ）。addr はオブジェクトの先頭ワードの位置（与えられたもの）。"""

    addr: int


@dataclass(frozen=True)
class Forward:
    """転送ポインタ（forwarding pointer）。コピー済みのオブジェクトの元の場所に書き、
    to 空間での新しいアドレスを記録する（与えられたもの）。"""

    addr: int


class SemiSpaceHeap:
    """半空間（semi-space）コピー GC のシミュレーション。

    ヒープは同じ大きさの 2 つの空間（from 空間と to 空間）からなり、ワード（list の要素）単位で扱う。
    オブジェクトは from 空間に連続して置かれ、次の形をしている:

        [ヘッダ: フィールド数 n][フィールド0][フィールド1]...[フィールド n-1]

    フィールドの値は int（ただの数値）、Ref（他のオブジェクトへの参照）、None のいずれか。
    Ref 型なので「ポインタかどうか」が正確に分かる（正確な GC, precise GC）。

    属性（与えられたもの）:
        size:        各空間のワード数
        from_space:  現在オブジェクトが置かれている空間（list）
        to_space:    GC のときのコピー先（list）
        free:        from 空間の空き領域の先頭（ここから先は未使用）
        roots:       ルート（Ref か None のリスト）。GC はこのリストの要素を **その場で** 書き換える
        collections: これまでに GC を行った回数

    read / write / fields は与えられています。alloc と collect を実装してください。

    注意: GC はオブジェクトを移動させます。GC の後は、roots に入れていなかった Ref は
    古いアドレスを指したままになり、使えません（実際のランタイムが、すべてのポインタの
    場所を GC に正確に教えなければならない理由です）。
    """

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
        """ref が指すオブジェクトの i 番目のフィールドを読む。"""
        n = self._n_fields(ref)
        if not 0 <= i < n:
            raise IndexError(f"フィールド番号が範囲外です: {i}（フィールド数 {n}）")
        return self.from_space[ref.addr + 1 + i]

    def write(self, ref: Ref, i: int, value: object) -> None:
        """ref が指すオブジェクトの i 番目のフィールドに書き込む。"""
        n = self._n_fields(ref)
        if not 0 <= i < n:
            raise IndexError(f"フィールド番号が範囲外です: {i}（フィールド数 {n}）")
        if not (value is None or isinstance(value, Ref) or type(value) is int):
            raise TypeError(f"フィールドには int・Ref・None だけを書き込めます: {value!r}")
        self.from_space[ref.addr + 1 + i] = value

    def fields(self, ref: Ref) -> list[object]:
        """ref が指すオブジェクトのフィールドのリスト（コピー）を返す。"""
        n = self._n_fields(ref)
        return self.from_space[ref.addr + 1 : ref.addr + 1 + n]

    # ---- 演習 ----
    def alloc(self, fields: list[object]) -> Ref:
        """fields を持つ新しいオブジェクトを from 空間に確保し、その Ref を返す。

        - 必要なワード数は 1 + len(fields)。空き領域の先頭（free）から切り出し、free を進める
          （バンプポインタ割り当て, bump-pointer allocation）。
        - fields の要素が int・Ref・None 以外なら TypeError。
        - 空きが足りなければ collect() を 1 回実行してから確保する。それでも足りなければ MemoryError。
        - 重要: GC はオブジェクトを移動させるので、fields に含まれる Ref も GC の間だけ一時的に
          ルートとして扱い、移動後のアドレスに更新してから書き込むこと（GC 後に roots は元に戻す）。

        >>> h = SemiSpaceHeap(8)
        >>> h.alloc([1, 2])
        Ref(addr=0)
        >>> h.alloc([None])
        Ref(addr=3)
        >>> h.free
        5
        """
        raise NotImplementedError("演習4: SemiSpaceHeap.alloc を実装してください")

    def collect(self) -> int:
        """Cheney のアルゴリズムで、ルートから到達できるオブジェクトを to 空間にコピーする。

        手順:
        1. roots を先頭から順に見て、Ref ならそのオブジェクトを to 空間にコピー（退避, evacuate）し、
           roots の要素を新しいアドレスの Ref に置き換える。
        2. to 空間を先頭から走査する（scan ポインタ）。各オブジェクトのフィールドを先頭から見て、
           Ref ならその参照先をコピーし、フィールドを新しいアドレスに書き換える。
           scan が free（コピー先の末尾）に追いついたら終わり。
           → scan から free までが「未処理のオブジェクトのキュー」となり、幅優先でコピーされる。
        3. from 空間と to 空間を入れ替え、free をコピーした総ワード数にする。collections を 1 増やす。

        オブジェクトをコピーしたら、元の場所のヘッダを Forward(新しいアドレス) に書き換えること。
        同じオブジェクトに再び出会ったら、コピーせずに転送先を使う（これで共有と循環が正しく保たれる）。

        戻り値: コピーした（生きている）ワード数。

        ヒント: 「Ref を受け取り、未コピーならコピーして転送ポインタを残し、新しい Ref を返す」
        関数 evacuate を内側に作ると、手順 1 と 2 の両方で使える。
        """
        raise NotImplementedError("演習4: SemiSpaceHeap.collect を実装してください")
