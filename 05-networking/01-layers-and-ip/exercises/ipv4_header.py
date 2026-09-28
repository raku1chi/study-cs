"""5.1 階層モデルとIP — 演習（ipv4_header）: IPv4 ヘッダの組み立て・解析とフラグメンテーション

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 5.1
    python3 tools/check.py -v 5.1

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_ipv4_header

使ってよいもの:
    - struct モジュール（バイト列 ↔ 数値の変換）
    - アドレスの文字列 ↔ 4 バイトの変換には ipaddress を使ってかまいません
      （例: ipaddress.IPv4Address("10.0.0.1").packed == b"\\n\\x00\\x00\\x01"）。
      この演習の主題はヘッダのレイアウトとチェックサムです。

IPv4 ヘッダ（RFC 791）の構造。数値はすべてビッグエンディアン（ネットワークバイトオーダー）:

     0                   1                   2                   3
     0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
    +-------+-------+-----------+---+-------------------------------+
    |Version|  IHL  |   DSCP    |ECN|          Total Length         |
    +-------+-------+-----------+---+-----+-------------------------+
    |         Identification        |Flags|     Fragment Offset     |
    +---------------+---------------+-----+-------------------------+
    |  Time to Live |    Protocol   |        Header Checksum        |
    +---------------+---------------+-------------------------------+
    |                       Source Address                          |
    +---------------------------------------------------------------+
    |                    Destination Address                        |
    +---------------------------------------------------------------+
    |                    Options (0〜40 バイト)                      |
    +---------------------------------------------------------------+

    - Version は 4、IHL はヘッダ長を 32 ビット語（4 バイト）単位で表す（オプションなしなら 5）。
    - Flags は 3 ビット: 予約(0) / DF（Don't Fragment）/ MF（More Fragments）。
      2 バイトの値としては DF = 0x4000、MF = 0x2000。
    - Fragment Offset は 13 ビットで、「8 バイト単位」の値を格納する。
    - struct の書式 "!BBHHHBBH4s4s" で固定部分の 20 バイトを一度に pack/unpack できる。
"""
from __future__ import annotations

import ipaddress  # noqa: F401  アドレスの変換に使えます
import struct  # noqa: F401
from dataclasses import dataclass

HEADER_FORMAT = "!BBHHHBBH4s4s"
MIN_HEADER_LEN = 20

PROTO_ICMP = 1
PROTO_TCP = 6
PROTO_UDP = 17


class FragmentationNeeded(Exception):
    """DF ビットが立ったパケットを分割しなければならないときに送出する（実装済み）。

    ルータはこの状況でパケットを破棄し、送信元へ ICMP「Destination Unreachable /
    Fragmentation Needed」（タイプ 3・コード 4）を次ホップの MTU 付きで返します。
    これが経路 MTU 探索（Path MTU Discovery）の仕組みです。
    """

    def __init__(self, mtu: int) -> None:
        super().__init__(f"DF ビットが立っているため分割できません（次ホップの MTU: {mtu}）")
        self.mtu = mtu


@dataclass
class IPv4Header:
    """IPv4 ヘッダの各フィールド（実装済み）。

    fragment_offset はバイト単位（8 の倍数）で持ちます。ヘッダ上には 8 で割った値を書きます。
    checksum は parse_ipv4_header が読み取った値を入れるためのもので、
    build_ipv4_header はこの値を無視して計算し直します。
    """

    src: str
    dst: str
    protocol: int
    total_length: int = MIN_HEADER_LEN  # ヘッダ＋データのバイト数
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
# 演習5（★★★）: インターネットチェックサムとヘッダの組み立て・解析
# ---------------------------------------------------------------------------

def internet_checksum(data: bytes) -> int:
    """RFC 1071 のインターネットチェックサム（16 ビット）を計算する。

    1. data を 16 ビット（2 バイト、ビッグエンディアン）ずつの整数に区切る。
       奇数長なら末尾に 0x00 を 1 バイト補う。
    2. それらの「1 の補数和」をとる: 普通に足し、16 ビットからあふれた桁（上位）を
       下位 16 ビットに足し戻す。あふれがなくなるまで繰り返す。
    3. 結果のビットを反転した値（~sum & 0xFFFF）を返す。

    >>> hex(internet_checksum(bytes.fromhex("0001f203f4f5f6f7")))   # RFC 1071 の例
    '0x220d'
    >>> internet_checksum(b"")
    65535

    性質: チェックサム欄を含めた正しいヘッダ全体でもう一度計算すると 0 になる。
    受信側はこの性質で検証する。
    """
    raise NotImplementedError("演習5: internet_checksum を実装してください")


def build_ipv4_header(header: IPv4Header) -> bytes:
    """IPv4Header をヘッダのバイト列（20〜60 バイト）にする。チェックサムは計算して埋める。

    - IHL は header_length // 4、Version は 4。
    - DSCP と ECN は 1 バイトにまとめる: (dscp << 2) | ecn。
    - フラグと断片オフセットは 2 バイトにまとめる: DF=0x4000、MF=0x2000、
      下位 13 ビットに fragment_offset // 8。
    - チェックサムは「チェックサム欄を 0 にしたヘッダ（オプション含む）」の internet_checksum。

    次の場合は ValueError:
        - options の長さが 4 の倍数でない、または 40 バイトを超える
        - total_length が header_length 未満、または 65535 を超える
        - ttl・protocol が 0〜255、identification が 0〜65535、dscp が 0〜63、ecn が 0〜3 の範囲外
        - fragment_offset が 8 の倍数でない、または 0〜65528（8191 × 8）の範囲外
        - src・dst が IPv4 アドレスとして不正

    >>> h = IPv4Header(src="192.168.0.1", dst="192.168.0.199", protocol=PROTO_UDP,
    ...                total_length=115, dont_fragment=True)
    >>> build_ipv4_header(h).hex(" ")
    '45 00 00 73 00 00 40 00 40 11 b8 61 c0 a8 00 01 c0 a8 00 c7'
    """
    raise NotImplementedError("演習5: build_ipv4_header を実装してください")


def parse_ipv4_header(data: bytes, *, verify_checksum: bool = True) -> IPv4Header:
    """バイト列（ヘッダで始まるパケット）から IPv4Header を読み取る。

    - data はヘッダの後ろにデータが続いていてもよい。ヘッダ長は IHL から求めること
      （「IPv4 ヘッダは 20 バイト」と決め打ちすると、オプション付きのパケットで壊れる）。
    - options にはオプション部分のバイト列、checksum にはヘッダ内の値を入れる。

    次の場合は ValueError:
        - 20 バイト未満、Version が 4 でない、IHL が 5 未満、IHL が示す長さより data が短い
        - total_length がヘッダ長より小さい
        - verify_checksum=True で、ヘッダ全体の internet_checksum が 0 でない

    >>> h = parse_ipv4_header(bytes.fromhex("45000073000040004011b861c0a80001c0a800c7"))
    >>> (h.src, h.dst, h.protocol, h.total_length, h.dont_fragment)
    ('192.168.0.1', '192.168.0.199', 17, 115, True)
    """
    raise NotImplementedError("演習5: parse_ipv4_header を実装してください")


# ---------------------------------------------------------------------------
# 演習6（★★★）: フラグメンテーション
# ---------------------------------------------------------------------------

def fragment_ipv4(packet: bytes, mtu: int) -> list[bytes]:
    """IPv4 パケット（ヘッダ＋データ）を、MTU 以下の断片（それぞれ完全な IPv4 パケット）に分ける。

    - packet は total_length までを 1 つのパケットとみなす（それより後ろのバイトは捨てる）。
      total_length より短ければ ValueError。
    - total_length <= mtu ならそのまま [packet] を返す。
    - 分割が必要で DF が立っていれば FragmentationNeeded(mtu) を送出する。
    - 各断片のデータ長は、最後の断片を除き「(mtu - ヘッダ長) を 8 の倍数に切り下げた値」。
      これが 8 未満になる（MTU が小さすぎる）なら ValueError。
    - 各断片のヘッダは元のヘッダをコピーし、total_length・fragment_offset・more_fragments・
      チェックサムを更新する（identification は同じ値のまま。受信側はこれで断片を束ねる）。
    - fragment_offset は「元のパケットの fragment_offset ＋ 元のデータ内での位置」。
      すでに断片であるパケットをさらに分割する場合も正しく扱うため。
    - more_fragments は最後以外の断片で True。最後の断片は元のパケットの MF を引き継ぐ。
    - オプションは簡略化のため、すべての断片にそのままコピーする（実際の RFC 791 では、
      「copied」フラグが立ったオプションだけを 2 つ目以降の断片にコピーする）。

    例: ヘッダ 20 バイト＋データ 3980 バイト（全長 4000）を MTU 1500 で分割すると、
    データは 1480・1480・1020 バイトの 3 つ、オフセットは 0・1480・2960、MF は 1・1・0。

    ヒント: dataclasses.replace(header, total_length=..., ...) で一部のフィールドだけを
    変えたコピーが作れる。
    """
    raise NotImplementedError("演習6: fragment_ipv4 を実装してください")
