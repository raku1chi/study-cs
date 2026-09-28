"""5.1 階層モデルとIP — 演習（ipnet）: IPv4 アドレス・CIDR・経路表・VPC 設計

各関数・メソッドの docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 5.1          # 合格数を表示
    python3 tools/check.py -v 5.1       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_ipnet

制約（学びのための縛り）:
    - 標準ライブラリの ipaddress モジュールは使わないでください。アドレスは 32 ビットの
      整数として持ち、シフト（<<, >>）・AND（&）・OR（|）・NOT（~）で計算します。
    - テストの中では答え合わせのために ipaddress を使っています。

この演習での約束:
    - IPv4 アドレスは 0〜2**32-1 の int で表します（例: 192.168.1.10 → 0xC0A8010A）。
    - Python の int には桁数の上限がないので、~x のように上位ビットが 1 になる演算の後は
      `& MAX_ADDR` で 32 ビットに切りそろえてください（~0xFF は -256 という負の数になります）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

MAX_ADDR = (1 << 32) - 1  # 255.255.255.255


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: IPv4 アドレスとネットマスク
# ---------------------------------------------------------------------------

def parse_ipv4(text: str) -> int:
    """ドット区切り 10 進表記の IPv4 アドレスを 32 ビット整数に変換する。

    - ちょうど 4 つの部分（オクテット）からなり、各部分は ASCII の数字 1〜3 桁で 0〜255。
    - 次の場合は ValueError: 部分の数が 4 でない、空の部分、数字以外（符号・空白・16 進など）、
      全角数字、256 以上、先頭に 0 がある（"01" など。"0" そのものは可）。
      先頭の 0 を拒否するのは、古い実装（C の inet_aton など）が 8 進数と解釈するため
      曖昧になるからです。

    >>> parse_ipv4("192.168.1.10") == 0xC0A8010A
    True
    >>> parse_ipv4("0.0.0.0")
    0

    ヒント: 上位のオクテットから順に「これまでの値 << 8 | オクテット」を繰り返す。
    str.isdigit() は "１"（全角）や "²" も True にするので、str.isascii() と組み合わせる。
    """
    raise NotImplementedError("演習1: parse_ipv4 を実装してください")


def format_ipv4(value: int) -> str:
    """32 ビット整数をドット区切り 10 進表記にする（parse_ipv4 の逆）。

    - value が 0〜2**32-1 の int でなければ ValueError。

    >>> format_ipv4(0xC0A8010A)
    '192.168.1.10'
    """
    raise NotImplementedError("演習1: format_ipv4 を実装してください")


def prefix_to_netmask(prefix: int) -> int:
    """プレフィックス長（0〜32）をネットマスク（32 ビット整数）に変換する。

    - 上位 prefix ビットが 1、残りが 0 の値を返す。
    - prefix が 0〜32 の int でなければ ValueError。

    >>> hex(prefix_to_netmask(24))
    '0xffffff00'
    >>> prefix_to_netmask(0)
    0
    """
    raise NotImplementedError("演習1: prefix_to_netmask を実装してください")


def netmask_to_prefix(mask: int) -> int:
    """ネットマスク（32 ビット整数）をプレフィックス長に変換する。

    - 上位から 1 が連続し、その後はすべて 0 でなければならない。
      255.0.255.0 のような「1 が連続していない」マスクは ValueError。
    - 32 ビットの範囲外も ValueError。

    >>> netmask_to_prefix(0xFFFFF000)
    20

    ヒント: ホスト部（~mask & MAX_ADDR）が 0b000…0111…1 の形かどうかは、
    「x & (x + 1) == 0」で判定できる。
    """
    raise NotImplementedError("演習1: netmask_to_prefix を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: CIDR ブロック
# ---------------------------------------------------------------------------

@dataclass(frozen=True, order=True)
class Network:
    """IPv4 の CIDR ブロック（例: 10.0.0.0/8）。

    address はネットワークアドレス（ホスト部がすべて 0）の 32 ビット整数、prefix はプレフィックス長。
    frozen=True なので辞書のキーや集合の要素に使え、order=True なので (address, prefix) の順で
    並べ替えられます。__post_init__ は実装済みです（prefix_to_netmask を使うので、演習1が先）。
    """

    address: int
    prefix: int

    def __post_init__(self) -> None:
        mask = prefix_to_netmask(self.prefix)  # prefix の範囲チェックも兼ねる
        if isinstance(self.address, bool) or not isinstance(self.address, int):
            raise ValueError(f"address は整数で指定してください: {self.address!r}")
        if not 0 <= self.address <= MAX_ADDR:
            raise ValueError(f"address が 32 ビットの範囲外です: {self.address!r}")
        if self.address & ~mask & MAX_ADDR:
            raise ValueError(f"ホスト部に 1 が立っています: address={self.address:#010x}, prefix={self.prefix}")

    @classmethod
    def parse(cls, text: str, *, strict: bool = True) -> Network:
        """"10.0.0.0/8" 形式の文字列から Network を作る。

        - "/" がなければ /32（単一アドレス）とみなす。
        - プレフィックス長は ASCII の数字 1〜2 桁で 0〜32。それ以外は ValueError。
        - ホスト部に 1 が立っている（"10.0.0.5/24" など）場合、strict=True なら ValueError、
          strict=False ならホスト部を 0 にしたブロック（10.0.0.0/24）を返す。

        >>> str(Network.parse("192.168.10.5/24", strict=False))
        '192.168.10.0/24'
        """
        raise NotImplementedError("演習2: Network.parse を実装してください")

    def __str__(self) -> str:
        """"10.0.0.0/8" の形式にする。"""
        raise NotImplementedError("演習2: Network.__str__ を実装してください")

    @property
    def netmask(self) -> int:
        """ネットマスク（例: /24 → 0xFFFFFF00）。"""
        raise NotImplementedError("演習2: Network.netmask を実装してください")

    @property
    def broadcast(self) -> int:
        """ブロックの最後のアドレス（ホスト部がすべて 1）。例: 10.0.0.0/24 → 10.0.0.255。"""
        raise NotImplementedError("演習2: Network.broadcast を実装してください")

    @property
    def num_addresses(self) -> int:
        """ブロックに含まれるアドレスの総数（2 ** (32 - prefix)）。"""
        raise NotImplementedError("演習2: Network.num_addresses を実装してください")

    @property
    def host_count(self) -> int:
        """ホストに割り当てられるアドレスの数。

        - 通常はネットワークアドレスとブロードキャストアドレスを除いた num_addresses - 2。
        - /31 は 2（RFC 3021: 2 点間リンクでは両端に割り当てる）、/32 は 1。
        """
        raise NotImplementedError("演習2: Network.host_count を実装してください")

    def contains(self, address: int) -> bool:
        """アドレス（32 ビット整数）がこのブロックに含まれるか。

        ヒント: 「アドレス & ネットマスク」がネットワークアドレスと一致するか。
        """
        raise NotImplementedError("演習2: Network.contains を実装してください")

    def overlaps(self, other: Network) -> bool:
        """2 つのブロックが 1 つでもアドレスを共有するか。

        ヒント: CIDR ブロックどうしは「一方が他方を含む」か「まったく重ならない」かの
        どちらかで、部分的に重なることはない。
        """
        raise NotImplementedError("演習2: Network.overlaps を実装してください")

    def subnet_of(self, other: Network) -> bool:
        """このブロックが other の内側（同じブロックを含む）にあるか。"""
        raise NotImplementedError("演習2: Network.subnet_of を実装してください")

    def subnets(self, new_prefix: int) -> list[Network]:
        """このブロックを /new_prefix のブロックに等分割し、アドレス順のリストで返す。

        - new_prefix が prefix〜32 の範囲外なら ValueError。new_prefix == prefix なら [self]。

        >>> [str(s) for s in Network.parse("10.0.0.0/24").subnets(25)]
        ['10.0.0.0/25', '10.0.0.128/25']
        """
        raise NotImplementedError("演習2: Network.subnets を実装してください")

    def supernet(self) -> Network:
        """1 ビット短いプレフィックスの親ブロック。例: 10.0.1.0/24 → 10.0.0.0/23。/0 なら ValueError。"""
        raise NotImplementedError("演習2: Network.supernet を実装してください")


def aggregate(networks: Iterable[Network]) -> list[Network]:
    """ブロックの集まりを、同じアドレス集合を表す最小個数のブロックにまとめる（経路集約）。

    - 重複や、他のブロックに含まれるブロックは取り除く。
    - 「兄弟」（同じ親を持つ同じ大きさの 2 つ）は親にまとめる。まとめた結果がさらにまとめられる
      なら繰り返す。
    - 結果はアドレス順に並べる。空の入力なら空のリスト。

    >>> [str(n) for n in aggregate([Network.parse("10.0.0.0/25"), Network.parse("10.0.0.128/25")])]
    ['10.0.0.0/24']
    >>> [str(n) for n in aggregate([Network.parse("10.0.1.0/24"), Network.parse("10.0.2.0/24")])]
    ['10.0.1.0/24', '10.0.2.0/24']

    2 つ目の例は隣り合っていますが、10.0.1.0/24 と 10.0.2.0/24 をまとめた 10.0.1.0/23 は
    ホスト部に 1 が立つので CIDR ブロックになりません。

    ヒント: ① (address, prefix) で並べ替え、② 直前のブロックに含まれるものを捨て、
    ③ スタックに積みながら「上の 2 つが兄弟なら親に置き換える」を繰り返す。
    """
    raise NotImplementedError("演習2: aggregate を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: 最長一致（longest prefix match）のルーティングテーブル
# ---------------------------------------------------------------------------

class RoutingTable:
    """宛先アドレスから次ホップを決める経路表。

    ルータや OS のカーネルと同じく、宛先に一致する経路のうち「プレフィックスが最も長い
    （最も具体的な）もの」を選びます。0.0.0.0/0 はすべてに一致するデフォルトルートです。

    >>> table = RoutingTable()
    >>> table.add("0.0.0.0/0", "isp")
    >>> table.add("10.0.0.0/8", "corp")
    >>> table.lookup("10.1.2.3")[1]
    'corp'
    >>> table.lookup("8.8.8.8")[1]
    'isp'

    ヒント: 全経路を毎回なめる（O(経路数)）実装でもテストは通ります。発展として、
    プレフィックス長ごとの辞書 {prefix: {ネットワークアドレス: 経路}} を作り、長い順に
    最大 33 回の辞書引きで探す方法や、2 分木（トライ）を試してみましょう。
    """

    def __init__(self) -> None:
        raise NotImplementedError("演習3: RoutingTable.__init__ を実装してください")

    def add(self, cidr: str, next_hop: str) -> None:
        """経路を追加する。同じ宛先ブロックがすでにあれば次ホップを上書きする。

        cidr は Network.parse(cidr)（strict=True）で解釈し、不正なら ValueError。
        """
        raise NotImplementedError("演習3: RoutingTable.add を実装してください")

    def remove(self, cidr: str) -> None:
        """経路を削除する。存在しなければ KeyError。"""
        raise NotImplementedError("演習3: RoutingTable.remove を実装してください")

    def lookup(self, address: str) -> tuple[Network, str] | None:
        """宛先アドレス（文字列）に対して最長一致した (経路のブロック, 次ホップ) を返す。

        一致する経路がなければ None。
        """
        raise NotImplementedError("演習3: RoutingTable.lookup を実装してください")

    def routes(self) -> list[tuple[Network, str]]:
        """すべての経路を (Network, 次ホップ) のリストで、Network の順に並べて返す。"""
        raise NotImplementedError("演習3: RoutingTable.routes を実装してください")

    def __len__(self) -> int:
        """経路の数。"""
        raise NotImplementedError("演習3: RoutingTable.__len__ を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: VPC の CIDR 設計
# ---------------------------------------------------------------------------

def subnet_prefix_for_hosts(hosts: int, *, reserved_per_subnet: int = 5, smallest_prefix: int = 28) -> int:
    """hosts 台を収容できる最小のサブネットのプレフィックス長を返す。

    - クラウドはサブネットごとにいくつかのアドレスを予約する（AWS は先頭 4 つと最後の 1 つの
      計 5 つ）。hosts + reserved_per_subnet 個以上のアドレスを持つ最小のブロックを選ぶ。
    - ただし smallest_prefix より小さいブロック（長いプレフィックス）にはしない
      （AWS のサブネットは /28 が最小）。
    - hosts < 1 や reserved_per_subnet < 0 は ValueError。

    >>> subnet_prefix_for_hosts(251)   # 251 + 5 = 256 → /24
    24
    >>> subnet_prefix_for_hosts(252)   # 257 個必要 → 512 個の /23
    23
    >>> subnet_prefix_for_hosts(1)     # 6 個なら /29 で足りるが、最小の /28 に切り上げ
    28
    """
    raise NotImplementedError("演習4: subnet_prefix_for_hosts を実装してください")


def plan_vpc(
    vpc_cidr: str,
    azs: Sequence[str],
    tiers: Sequence[tuple[str, int]],
    *,
    reserved_per_subnet: int = 5,
    smallest_prefix: int = 28,
) -> dict[str, dict[str, Network]]:
    """VPC のアドレス空間を「階層（tier）× AZ」ごとの重ならないサブネットに割り当てる。

    引数:
        vpc_cidr: VPC 全体のブロック（例: "10.0.0.0/16"）。strict に解釈する。
        azs: アベイラビリティゾーンの名前のリスト（1 つ以上、重複なし）。
        tiers: (階層の名前, 1 サブネットあたりに必要なホスト数) のリスト（1 つ以上、名前の重複なし）。

    戻り値:
        {階層の名前: {AZ の名前: Network}}。外側は tiers の順、内側は azs の順に並べる。

    割り当て方（テストはこの規則どおりの結果を期待します）:
        1. 各階層のサブネットの大きさを subnet_prefix_for_hosts で決める（全 AZ で同じ大きさ）。
        2. (階層, AZ) の組を「大きいブロック（短いプレフィックス）から順」に並べる。
           大きさが同じなら tiers の順、その中では azs の順（安定ソート）。
        3. VPC の先頭から順に、隙間なく割り当てる。

    2 のべき乗の大きさのブロックを大きい順に並べると、次のブロックの先頭は必ずその大きさの
    倍数になるので、境界合わせによる無駄な隙間が生じません。

    エラー（ValueError）:
        - 引数が不正（azs や tiers が空・重複、vpc_cidr が不正）
        - ある階層のサブネットが VPC より大きい、または全体が VPC に収まらない

    >>> plan = plan_vpc("10.0.0.0/16", ["a", "c"], [("public", 200), ("app", 1000)])
    >>> {t: {az: str(n) for az, n in m.items()} for t, m in plan.items()}
    {'public': {'a': '10.0.8.0/24', 'c': '10.0.9.0/24'}, 'app': {'a': '10.0.0.0/22', 'c': '10.0.4.0/22'}}
    """
    raise NotImplementedError("演習4: plan_vpc を実装してください")
