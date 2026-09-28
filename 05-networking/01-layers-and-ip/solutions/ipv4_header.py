"""5.1 階層モデルとIP — 解答例（ipv4_header）

演習の仕様は exercises/ipv4_header.py の docstring を参照してください。
"""
from __future__ import annotations

import dataclasses
import ipaddress
import struct
from dataclasses import dataclass

# 固定部分 20 バイト: バージョン+IHL, TOS(DSCP+ECN), 全長, ID, フラグ+断片オフセット,
# TTL, プロトコル, チェックサム, 送信元, 宛先。"!" はネットワークバイトオーダー（ビッグエンディアン）
HEADER_FORMAT = "!BBHHHBBH4s4s"
MIN_HEADER_LEN = struct.calcsize(HEADER_FORMAT)  # 20
MAX_OPTIONS_LEN = 40  # IHL は 4 ビットなので最大 15 × 4 = 60 バイト、うち固定部分が 20

PROTO_ICMP = 1
PROTO_TCP = 6
PROTO_UDP = 17

FLAG_DF = 0x4000  # Don't Fragment
FLAG_MF = 0x2000  # More Fragments
OFFSET_MASK = 0x1FFF  # 断片オフセット（8 バイト単位）


class FragmentationNeeded(Exception):
    def __init__(self, mtu: int) -> None:
        super().__init__(f"DF ビットが立っているため分割できません（次ホップの MTU: {mtu}）")
        self.mtu = mtu


@dataclass
class IPv4Header:
    src: str
    dst: str
    protocol: int
    total_length: int = MIN_HEADER_LEN
    ttl: int = 64
    identification: int = 0
    dont_fragment: bool = False
    more_fragments: bool = False
    fragment_offset: int = 0
    dscp: int = 0
    ecn: int = 0
    options: bytes = b""
    checksum: int = 0

    @property
    def header_length(self) -> int:
        return MIN_HEADER_LEN + len(self.options)


# ---------------------------------------------------------------------------
# 演習5: インターネットチェックサムとヘッダの組み立て・解析
# ---------------------------------------------------------------------------

def internet_checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"  # 奇数長なら末尾に 0 を 1 バイト補って 16 ビット単位にする
    total = 0
    for (word,) in struct.iter_unpack("!H", data):
        total += word
    # 1 の補数和: 16 ビットからあふれた桁を下位に足し戻す（あふれがなくなるまで）
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


def _check_range(name: str, value: int, lo: int, hi: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise ValueError(f"{name} は {lo}〜{hi} の整数です: {value!r}")


def build_ipv4_header(header: IPv4Header) -> bytes:
    if len(header.options) % 4 or len(header.options) > MAX_OPTIONS_LEN:
        raise ValueError(f"options は 4 の倍数かつ {MAX_OPTIONS_LEN} バイト以下です: {len(header.options)}")
    hlen = header.header_length
    _check_range("total_length", header.total_length, hlen, 0xFFFF)
    _check_range("ttl", header.ttl, 0, 255)
    _check_range("protocol", header.protocol, 0, 255)
    _check_range("identification", header.identification, 0, 0xFFFF)
    _check_range("dscp", header.dscp, 0, 63)
    _check_range("ecn", header.ecn, 0, 3)
    _check_range("fragment_offset", header.fragment_offset, 0, OFFSET_MASK * 8)
    if header.fragment_offset % 8:
        raise ValueError(f"fragment_offset は 8 の倍数です: {header.fragment_offset}")

    flags_offset = header.fragment_offset // 8  # ヘッダ上は 8 バイト単位で格納する
    if header.dont_fragment:
        flags_offset |= FLAG_DF
    if header.more_fragments:
        flags_offset |= FLAG_MF
    raw = struct.pack(
        HEADER_FORMAT,
        (4 << 4) | (hlen // 4),  # バージョン 4 と IHL（32 ビット語の数）
        (header.dscp << 2) | header.ecn,
        header.total_length,
        header.identification,
        flags_offset,
        header.ttl,
        header.protocol,
        0,  # チェックサムは 0 として計算し、あとで埋める
        ipaddress.IPv4Address(header.src).packed,
        ipaddress.IPv4Address(header.dst).packed,
    ) + header.options
    checksum = internet_checksum(raw)
    return raw[:10] + struct.pack("!H", checksum) + raw[12:]


def parse_ipv4_header(data: bytes, *, verify_checksum: bool = True) -> IPv4Header:
    if len(data) < MIN_HEADER_LEN:
        raise ValueError(f"IPv4 ヘッダには最低 {MIN_HEADER_LEN} バイト必要です: {len(data)}")
    version, ihl = data[0] >> 4, data[0] & 0x0F
    if version != 4:
        raise ValueError(f"IPv4 ではありません（version={version}）")
    if ihl < 5:
        raise ValueError(f"IHL が小さすぎます: {ihl}")
    hlen = ihl * 4
    if len(data) < hlen:
        raise ValueError(f"オプションを含むヘッダ（{hlen} バイト）が途中で切れています")
    (_, tos, total_length, ident, flags_offset, ttl, proto, checksum, src, dst) = struct.unpack(
        HEADER_FORMAT, data[:MIN_HEADER_LEN]
    )
    if total_length < hlen:
        raise ValueError(f"全長 {total_length} がヘッダ長 {hlen} より小さい")
    # 正しいヘッダは、チェックサム欄を含めて 1 の補数和をとると 0xFFFF（その補数は 0）になる
    if verify_checksum and internet_checksum(data[:hlen]) != 0:
        raise ValueError(f"ヘッダチェックサムが一致しません（ヘッダ内の値: {checksum:#06x}）")
    return IPv4Header(
        src=str(ipaddress.IPv4Address(src)),
        dst=str(ipaddress.IPv4Address(dst)),
        protocol=proto,
        total_length=total_length,
        ttl=ttl,
        identification=ident,
        dont_fragment=bool(flags_offset & FLAG_DF),
        more_fragments=bool(flags_offset & FLAG_MF),
        fragment_offset=(flags_offset & OFFSET_MASK) * 8,
        dscp=tos >> 2,
        ecn=tos & 0x03,
        options=bytes(data[MIN_HEADER_LEN:hlen]),
        checksum=checksum,
    )


# ---------------------------------------------------------------------------
# 演習6: フラグメンテーション
# ---------------------------------------------------------------------------

def fragment_ipv4(packet: bytes, mtu: int) -> list[bytes]:
    header = parse_ipv4_header(packet)
    if header.total_length > len(packet):
        raise ValueError(f"全長 {header.total_length} に対してデータが足りません: {len(packet)}")
    packet = packet[: header.total_length]  # 末尾の余分なバイト（イーサネットの詰め物など）は無視
    if header.total_length <= mtu:
        return [packet]
    if header.dont_fragment:
        # ルータなら破棄して ICMP「Fragmentation Needed」（タイプ 3・コード 4）を送り返す場面
        raise FragmentationNeeded(mtu)

    hlen = header.header_length
    chunk = (mtu - hlen) // 8 * 8  # 最後以外の断片のデータ長は 8 の倍数でなければならない
    if chunk < 8:
        raise ValueError(f"MTU {mtu} ではヘッダ {hlen} バイトの断片を作れません")
    payload = packet[hlen:]
    fragments: list[bytes] = []
    for start in range(0, len(payload), chunk):
        data = payload[start : start + chunk]
        is_last = start + chunk >= len(payload)
        frag = dataclasses.replace(
            header,
            total_length=hlen + len(data),
            fragment_offset=header.fragment_offset + start,  # すでに断片なら元のオフセットに足す
            # 最後の断片は元の MF を引き継ぐ（元が途中の断片なら、まだ後ろに続きがある）
            more_fragments=header.more_fragments if is_last else True,
        )
        fragments.append(build_ipv4_header(frag) + data)
    return fragments
