"""5.1 階層モデルとIP — 解答例（ipnet）

演習の仕様は exercises/ipnet.py の docstring を参照してください。
ここでは「なぜそう書くのか」が分かるように、コメントを多めに付けています。
ipaddress モジュールは使わず、32 ビット整数のビット演算だけで実装しています。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

MAX_ADDR = (1 << 32) - 1  # 255.255.255.255


# ---------------------------------------------------------------------------
# 演習1: IPv4 アドレスとネットマスク
# ---------------------------------------------------------------------------

def parse_ipv4(text: str) -> int:
    parts = text.split(".")
    if len(parts) != 4:
        raise ValueError(f"IPv4 アドレスはドットで区切った 4 つの数です: {text!r}")
    value = 0
    for part in parts:
        # isdigit() は全角数字や上付き数字も True にするので、ASCII であることも確認する
        if not (part.isascii() and part.isdigit()) or len(part) > 3:
            raise ValueError(f"不正なオクテットです: {part!r}（{text!r}）")
        # 先頭の 0 は 8 進数と解釈する実装（inet_aton など）があり、曖昧なので拒否する
        if len(part) > 1 and part[0] == "0":
            raise ValueError(f"先頭に 0 のあるオクテットは曖昧なので拒否します: {part!r}")
        octet = int(part)
        if octet > 255:
            raise ValueError(f"オクテットは 0〜255 です: {part!r}")
        value = (value << 8) | octet  # 上位のオクテットから順に 8 ビットずつ詰める
    return value


def format_ipv4(value: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_ADDR:
        raise ValueError(f"32 ビットの符号なし整数ではありません: {value!r}")
    return ".".join(str((value >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def prefix_to_netmask(prefix: int) -> int:
    if isinstance(prefix, bool) or not isinstance(prefix, int) or not 0 <= prefix <= 32:
        raise ValueError(f"プレフィックス長は 0〜32 です: {prefix!r}")
    # 上位 prefix ビットが 1、残りが 0。32 ビットに収まるようにマスクする
    return (MAX_ADDR << (32 - prefix)) & MAX_ADDR


def netmask_to_prefix(mask: int) -> int:
    if not 0 <= mask <= MAX_ADDR:
        raise ValueError(f"32 ビットの値ではありません: {mask!r}")
    host_bits = ~mask & MAX_ADDR  # 例: 255.255.255.0 → 0x000000FF
    # ホスト部が「下位に連続した 1」なら、1 を足すと繰り上がって共通のビットがなくなる
    if host_bits & (host_bits + 1):
        raise ValueError(f"1 が連続していないネットマスクです: {format_ipv4(mask)}")
    return 32 - host_bits.bit_length()


# ---------------------------------------------------------------------------
# 演習2: CIDR ブロック
# ---------------------------------------------------------------------------

@dataclass(frozen=True, order=True, repr=False)
class Network:
    address: int
    prefix: int

    def __post_init__(self) -> None:
        mask = prefix_to_netmask(self.prefix)  # prefix の範囲チェックも兼ねる
        if isinstance(self.address, bool) or not isinstance(self.address, int):
            raise ValueError(f"address は整数で指定してください: {self.address!r}")
        if not 0 <= self.address <= MAX_ADDR:
            raise ValueError(f"address が 32 ビットの範囲外です: {self.address!r}")
        if self.address & ~mask & MAX_ADDR:
            raise ValueError(f"ホスト部に 1 が立っています: {format_ipv4(self.address)}/{self.prefix}")

    @classmethod
    def parse(cls, text: str, *, strict: bool = True) -> Network:
        addr_text, slash, prefix_text = text.partition("/")
        if slash:
            if not (prefix_text.isascii() and prefix_text.isdigit()) or len(prefix_text) > 2:
                raise ValueError(f"不正なプレフィックス長です: {text!r}")
            prefix = int(prefix_text)
        else:
            prefix = 32  # "/" がなければ単一のアドレス（/32）
        address = parse_ipv4(addr_text)
        mask = prefix_to_netmask(prefix)
        if address & ~mask & MAX_ADDR:
            if strict:
                raise ValueError(f"ホスト部に 1 が立っています（strict=False なら切り捨てます）: {text!r}")
            address &= mask
        return cls(address, prefix)

    def __str__(self) -> str:
        return f"{format_ipv4(self.address)}/{self.prefix}"

    def __repr__(self) -> str:
        return f"Network('{self}')"

    @property
    def netmask(self) -> int:
        return prefix_to_netmask(self.prefix)

    @property
    def broadcast(self) -> int:
        # ホスト部をすべて 1 にしたもの = ブロックの最後のアドレス
        return self.address | (~self.netmask & MAX_ADDR)

    @property
    def num_addresses(self) -> int:
        return 1 << (32 - self.prefix)

    @property
    def host_count(self) -> int:
        if self.prefix == 32:
            return 1  # 単一ホストの経路
        if self.prefix == 31:
            return 2  # RFC 3021: 2 点間リンクではネットワーク／ブロードキャストを予約しない
        return self.num_addresses - 2  # ネットワークアドレスとブロードキャストアドレスを除く

    def contains(self, address: int) -> bool:
        # 「ネットマスクで上位ビットだけを残したら、ネットワークアドレスと一致する」
        return (address & self.netmask) == self.address

    def overlaps(self, other: Network) -> bool:
        # CIDR ブロックは「入れ子」か「まったく重ならない」かのどちらかしかない。
        # したがって、どちらかがもう一方の先頭アドレスを含むかを見れば十分
        return self.contains(other.address) or other.contains(self.address)

    def subnet_of(self, other: Network) -> bool:
        return other.prefix <= self.prefix and other.contains(self.address)

    def subnets(self, new_prefix: int) -> list[Network]:
        if isinstance(new_prefix, bool) or not isinstance(new_prefix, int):
            raise ValueError(f"new_prefix は整数で指定してください: {new_prefix!r}")
        if not self.prefix <= new_prefix <= 32:
            raise ValueError(f"new_prefix は {self.prefix}〜32 で指定してください: {new_prefix}")
        step = 1 << (32 - new_prefix)
        return [Network(a, new_prefix) for a in range(self.address, self.broadcast + 1, step)]

    def supernet(self) -> Network:
        if self.prefix == 0:
            raise ValueError("0.0.0.0/0 より大きなブロックはありません")
        parent = self.prefix - 1
        return Network(self.address & prefix_to_netmask(parent), parent)


def aggregate(networks: Iterable[Network]) -> list[Network]:
    # 1. アドレス順（同じアドレスなら大きいブロック＝短いプレフィックスが先）に並べる
    ordered = sorted(networks, key=lambda n: (n.address, n.prefix))
    # 2. 直前のブロックに含まれるもの（重複を含む）を捨てる。並べてあるので直前だけ見ればよい
    disjoint: list[Network] = []
    for net in ordered:
        if disjoint and net.address <= disjoint[-1].broadcast:
            continue
        disjoint.append(net)
    # 3. スタックを使って「兄弟」（同じ親を持つ隣り合った同じ大きさのブロック）を併合する。
    #    併合してできた親が、さらにスタックの 1 つ下と兄弟になることがあるので while で繰り返す
    stack: list[Network] = []
    for net in disjoint:
        stack.append(net)
        while len(stack) >= 2:
            left, right = stack[-2], stack[-1]
            if left.prefix != right.prefix or left.prefix == 0:
                break
            parent = left.supernet()
            if parent.address != left.address or right.address != left.broadcast + 1:
                break  # 大きさは同じでも、親の境界にそろっていない（兄弟ではない）
            stack[-2:] = [parent]
    return stack


# ---------------------------------------------------------------------------
# 演習3: 最長一致（longest prefix match）のルーティングテーブル
# ---------------------------------------------------------------------------

class RoutingTable:
    def __init__(self) -> None:
        # プレフィックス長ごとに「ネットワークアドレス → (経路, 次ホップ)」の辞書を持つ。
        # 検索は長いプレフィックスから順に最大 33 回の辞書引きで済む（経路数に依存しない）
        self._tables: dict[int, dict[int, tuple[Network, str]]] = {}

    def add(self, cidr: str, next_hop: str) -> None:
        net = Network.parse(cidr)
        self._tables.setdefault(net.prefix, {})[net.address] = (net, next_hop)

    def remove(self, cidr: str) -> None:
        net = Network.parse(cidr)
        table = self._tables.get(net.prefix, {})
        if net.address not in table:
            raise KeyError(cidr)
        del table[net.address]
        if not table:
            del self._tables[net.prefix]

    def lookup(self, address: str) -> tuple[Network, str] | None:
        addr = parse_ipv4(address)
        for prefix in sorted(self._tables, reverse=True):  # 長い（具体的な）プレフィックスから
            route = self._tables[prefix].get(addr & prefix_to_netmask(prefix))
            if route is not None:
                return route
        return None

    def routes(self) -> list[tuple[Network, str]]:
        return sorted(route for table in self._tables.values() for route in table.values())

    def __len__(self) -> int:
        return sum(len(table) for table in self._tables.values())


# ---------------------------------------------------------------------------
# 演習4: VPC の CIDR 設計
# ---------------------------------------------------------------------------

def subnet_prefix_for_hosts(hosts: int, *, reserved_per_subnet: int = 5, smallest_prefix: int = 28) -> int:
    if hosts < 1:
        raise ValueError(f"必要なホスト数は 1 以上です: {hosts}")
    if reserved_per_subnet < 0:
        raise ValueError(f"予約アドレス数は 0 以上です: {reserved_per_subnet}")
    needed = hosts + reserved_per_subnet
    size = 1 << (needed - 1).bit_length()  # needed 以上の最小の 2 のべき乗
    prefix = 32 - (size.bit_length() - 1)
    if prefix < 0:
        raise ValueError(f"IPv4 の空間に収まりません: {hosts}")
    return min(prefix, smallest_prefix)  # クラウドの最小サブネット（AWS なら /28）より小さくしない


def plan_vpc(
    vpc_cidr: str,
    azs: Sequence[str],
    tiers: Sequence[tuple[str, int]],
    *,
    reserved_per_subnet: int = 5,
    smallest_prefix: int = 28,
) -> dict[str, dict[str, Network]]:
    vpc = Network.parse(vpc_cidr)
    if not azs or len(set(azs)) != len(azs):
        raise ValueError(f"AZ は 1 つ以上、重複なしで指定してください: {list(azs)}")
    names = [name for name, _ in tiers]
    if not tiers or len(set(names)) != len(names):
        raise ValueError(f"階層（tier）は 1 つ以上、重複なしで指定してください: {names}")

    requests: list[tuple[int, str, str]] = []  # (プレフィックス長, 階層名, AZ)
    for name, hosts in tiers:
        prefix = subnet_prefix_for_hosts(
            hosts, reserved_per_subnet=reserved_per_subnet, smallest_prefix=smallest_prefix
        )
        if prefix < vpc.prefix:
            raise ValueError(f"階層 {name!r} のサブネット（/{prefix}）が VPC（{vpc}）より大きくなります")
        requests.extend((prefix, name, az) for az in azs)

    # 大きいブロックから順に先頭から詰める（安定ソートなので同じ大きさは入力順のまま）。
    # 2 のべき乗の大きさを降順に並べると、次のブロックの先頭は必ずその大きさの倍数になり、
    # 境界合わせによる隙間が生じない。合計が VPC に収まるなら必ず割り当てられる
    requests.sort(key=lambda r: r[0])
    plan: dict[str, dict[str, Network]] = {name: {} for name in names}
    cursor = vpc.address
    for prefix, name, az in requests:
        size = 1 << (32 - prefix)
        if cursor + size - 1 > vpc.broadcast:
            raise ValueError(f"VPC {vpc} のアドレスが足りません（{name!r} / {az!r} を割り当てられません）")
        plan[name][az] = Network(cursor, prefix)
        cursor += size
    return plan
