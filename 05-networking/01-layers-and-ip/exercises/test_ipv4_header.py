"""5.1 階層モデルとIP — テスト（ipv4_header）

実行: python3 tools/check.py 5.1   （またはこのディレクトリで python3 -m unittest -v）
"""
import dataclasses
import ipaddress
import random
import struct
import unittest

from ipv4_header import (
    PROTO_TCP,
    PROTO_UDP,
    FragmentationNeeded,
    IPv4Header,
    build_ipv4_header,
    fragment_ipv4,
    internet_checksum,
    parse_ipv4_header,
)

# よく知られた例: 192.168.0.1 → 192.168.0.199 の UDP、全長 115、DF あり、TTL 64
KNOWN_HEADER = bytes.fromhex("4500 0073 0000 4000 4011 b861 c0a8 0001 c0a8 00c7")


def reference_checksum(data: bytes) -> int:
    """答え合わせ用の素朴な実装（1 の補数和を 32 ビット整数で計算してから折り返す）。"""
    if len(data) % 2:
        data += b"\0"
    s = sum(struct.unpack(f"!{len(data) // 2}H", data))
    while s > 0xFFFF:
        s = (s & 0xFFFF) + (s >> 16)
    return 0xFFFF - s


class TestExercise5Checksum(unittest.TestCase):
    def test_rfc1071_example(self):
        # RFC 1071 の数値例: 0001 + f203 + f4f5 + f6f7 の 1 の補数和は ddf2、その補数が 220d
        self.assertEqual(internet_checksum(bytes.fromhex("0001f203f4f5f6f7")), 0x220D)

    def test_known_ipv4_header(self):
        zeroed = KNOWN_HEADER[:10] + b"\0\0" + KNOWN_HEADER[12:]
        self.assertEqual(internet_checksum(zeroed), 0xB861)
        self.assertEqual(internet_checksum(KNOWN_HEADER), 0, "正しいヘッダ全体のチェックサムは 0")

    def test_odd_length_and_empty(self):
        self.assertEqual(internet_checksum(b"\x01"), 0xFEFF, "奇数長は末尾に 0x00 を補う")
        self.assertEqual(internet_checksum(b""), 0xFFFF)
        self.assertEqual(internet_checksum(b"\xff\xff"), 0x0000)

    def test_carry_is_folded_back(self):
        self.assertEqual(internet_checksum(b"\xff\xff\x00\x01"), 0xFFFE, "FFFF + 0001 = 1_0000 → 0001")

    def test_matches_reference_and_verifies(self):
        rng = random.Random(61)
        for _ in range(300):
            data = bytes(rng.getrandbits(8) for _ in range(rng.randrange(0, 80)))
            c = internet_checksum(data)
            self.assertEqual(c, reference_checksum(data), data.hex())
            if len(data) % 2 == 0:
                self.assertEqual(internet_checksum(data + struct.pack("!H", c)), 0)


class TestExercise5Header(unittest.TestCase):
    def test_build_known_header(self):
        h = IPv4Header(src="192.168.0.1", dst="192.168.0.199", protocol=PROTO_UDP,
                       total_length=115, ttl=64, identification=0, dont_fragment=True)
        self.assertEqual(build_ipv4_header(h), KNOWN_HEADER)

    def test_parse_known_header(self):
        h = parse_ipv4_header(KNOWN_HEADER)
        self.assertEqual((h.src, h.dst, h.protocol), ("192.168.0.1", "192.168.0.199", PROTO_UDP))
        self.assertEqual((h.total_length, h.ttl, h.identification), (115, 64, 0))
        self.assertEqual((h.dont_fragment, h.more_fragments, h.fragment_offset), (True, False, 0))
        self.assertEqual((h.dscp, h.ecn, h.options, h.checksum), (0, 0, b"", 0xB861))
        self.assertEqual(h.header_length, 20)

    def test_field_layout(self):
        h = IPv4Header(src="10.0.0.1", dst="10.0.0.2", protocol=PROTO_TCP, total_length=1500, ttl=3,
                       identification=0xBEEF, more_fragments=True, fragment_offset=1480, dscp=46, ecn=1)
        raw = build_ipv4_header(h)
        self.assertEqual(len(raw), 20)
        fields = struct.unpack("!BBHHHBBH4s4s", raw)
        self.assertEqual(fields[0], 0x45, "バージョン 4・IHL 5")
        self.assertEqual(fields[1], (46 << 2) | 1, "DSCP 46（EF）と ECN 1")
        self.assertEqual(fields[2:4], (1500, 0xBEEF))
        self.assertEqual(fields[4], 0x2000 | 185, "MF ビットと 8 バイト単位のオフセット 1480/8 = 185")
        self.assertEqual(fields[5:7], (3, 6))
        self.assertEqual(fields[8], ipaddress.IPv4Address("10.0.0.1").packed)
        self.assertEqual(internet_checksum(raw), 0)

    def test_options_change_ihl(self):
        options = bytes([1, 1, 1, 0])  # NOP, NOP, NOP, End of Option List
        h = IPv4Header(src="10.0.0.1", dst="10.0.0.2", protocol=PROTO_UDP, total_length=24, options=options)
        raw = build_ipv4_header(h)
        self.assertEqual(len(raw), 24)
        self.assertEqual(raw[0], 0x46, "IHL は 32 ビット語の数（24 バイト → 6）")
        parsed = parse_ipv4_header(raw + b"payload")
        self.assertEqual(parsed.options, options)
        self.assertEqual(parsed.header_length, 24)

    def test_round_trip_random_headers(self):
        rng = random.Random(62)
        for _ in range(300):
            opts = bytes(rng.getrandbits(8) for _ in range(4 * rng.randrange(0, 11)))
            h = IPv4Header(
                src=str(ipaddress.IPv4Address(rng.getrandbits(32))),
                dst=str(ipaddress.IPv4Address(rng.getrandbits(32))),
                protocol=rng.randrange(256), total_length=rng.randrange(20 + len(opts), 65536),
                ttl=rng.randrange(256), identification=rng.randrange(65536),
                dont_fragment=rng.random() < 0.5, more_fragments=rng.random() < 0.5,
                fragment_offset=8 * rng.randrange(8192), dscp=rng.randrange(64), ecn=rng.randrange(4),
                options=opts,
            )
            raw = build_ipv4_header(h)
            parsed = parse_ipv4_header(raw)
            self.assertEqual(dataclasses.replace(parsed, checksum=0), h)
            self.assertEqual(parsed.checksum, struct.unpack("!H", raw[10:12])[0])

    def test_build_validates_fields(self):
        base = IPv4Header(src="10.0.0.1", dst="10.0.0.2", protocol=PROTO_UDP, total_length=100)
        bad = [
            {"ttl": 256}, {"ttl": -1}, {"protocol": 300}, {"identification": 65536},
            {"dscp": 64}, {"ecn": 4}, {"fragment_offset": 3}, {"fragment_offset": 65536},
            {"total_length": 19}, {"total_length": 65536}, {"options": b"\x01\x01\x01"},
            {"options": bytes(44)}, {"src": "10.0.0.256"},
        ]
        for change in bad:
            with self.assertRaises(ValueError, msg=str(change)):
                build_ipv4_header(dataclasses.replace(base, **change))

    def test_parse_rejects_malformed(self):
        cases = {
            "短すぎる": KNOWN_HEADER[:19],
            "バージョンが 6": bytes([0x65]) + KNOWN_HEADER[1:],
            "IHL が 4": bytes([0x44]) + KNOWN_HEADER[1:],
            "オプションが途中で切れている": bytes([0x46]) + KNOWN_HEADER[1:],
            "全長がヘッダ長より小さい": KNOWN_HEADER[:2] + b"\x00\x10" + KNOWN_HEADER[4:],
        }
        for label, data in cases.items():
            with self.assertRaises(ValueError, msg=label):
                parse_ipv4_header(data, verify_checksum=False)

    def test_checksum_is_verified(self):
        corrupted = bytearray(KNOWN_HEADER)
        corrupted[8] = 63  # TTL を書き換えたのにチェックサムを直していない
        with self.assertRaises(ValueError):
            parse_ipv4_header(bytes(corrupted))
        self.assertEqual(parse_ipv4_header(bytes(corrupted), verify_checksum=False).ttl, 63)


def make_packet(payload_len: int, *, df=False, mf=False, offset=0, options=b"", ident=4242) -> bytes:
    payload = bytes((i * 7 + 3) % 256 for i in range(payload_len))
    h = IPv4Header(src="192.0.2.1", dst="198.51.100.7", protocol=PROTO_UDP,
                   total_length=20 + len(options) + payload_len, identification=ident,
                   dont_fragment=df, more_fragments=mf, fragment_offset=offset, options=options)
    return build_ipv4_header(h) + payload


class TestExercise6Fragmentation(unittest.TestCase):
    def test_textbook_example(self):
        # 4000 バイトのデータグラム（ヘッダ 20 + データ 3980）を MTU 1500 のリンクへ
        packet = make_packet(3980)
        frags = fragment_ipv4(packet, 1500)
        headers = [parse_ipv4_header(f) for f in frags]
        self.assertEqual([h.total_length for h in headers], [1500, 1500, 1040])
        self.assertEqual([h.fragment_offset for h in headers], [0, 1480, 2960])
        self.assertEqual([h.more_fragments for h in headers], [True, True, False])
        self.assertEqual({h.identification for h in headers}, {4242}, "識別子は全断片で同じ")
        self.assertEqual(b"".join(f[20:] for f in frags), packet[20:])
        self.assertEqual([len(f) for f in frags], [1500, 1500, 1040])

    def test_small_packet_is_unchanged(self):
        packet = make_packet(1480)
        self.assertEqual(fragment_ipv4(packet, 1500), [packet])
        self.assertEqual(fragment_ipv4(packet + b"\0" * 6, 1500), [packet], "全長より後ろの余分なバイトは捨てる")

    def test_dont_fragment_raises(self):
        with self.assertRaises(FragmentationNeeded) as ctx:
            fragment_ipv4(make_packet(1600, df=True), 1500)
        self.assertEqual(ctx.exception.mtu, 1500)
        self.assertEqual(len(fragment_ipv4(make_packet(1400, df=True), 1500)), 1, "収まるなら DF でも問題ない")

    def test_offsets_are_multiples_of_eight(self):
        packet = make_packet(1000)
        frags = fragment_ipv4(packet, 100)  # データは (100 - 20) // 8 * 8 = 80 バイトずつ
        for f in frags[:-1]:
            h = parse_ipv4_header(f)
            self.assertEqual(h.total_length - 20, 80)
            self.assertEqual(h.fragment_offset % 8, 0)
            self.assertLessEqual(len(f), 100)
        self.assertEqual(len(frags), 13)

    def test_refragmenting_a_fragment(self):
        # すでに断片（オフセット 1480、MF=1）のパケットを、さらに小さい MTU で分割する
        packet = make_packet(1480, mf=True, offset=1480)
        headers = [parse_ipv4_header(f) for f in fragment_ipv4(packet, 576)]
        self.assertEqual([h.fragment_offset for h in headers], [1480, 1480 + 552, 1480 + 1104])
        self.assertEqual([h.more_fragments for h in headers], [True, True, True], "元の MF=1 を最後の断片も引き継ぐ")

    def test_options_are_copied(self):
        options = bytes([1, 1, 1, 0])
        packet = make_packet(300, options=options)
        frags = fragment_ipv4(packet, 124)  # (124 - 24) // 8 * 8 = 96 バイトずつ
        self.assertEqual(len(frags), 4)
        for f in frags:
            self.assertEqual(parse_ipv4_header(f).options, options)
        self.assertEqual(b"".join(f[24:] for f in frags), packet[24:])

    def test_reassembly_from_random_mtus(self):
        rng = random.Random(63)
        for _ in range(100):
            packet = make_packet(rng.randrange(1, 5000), ident=rng.randrange(65536))
            mtu = rng.randrange(68, 1600)
            frags = fragment_ipv4(packet, mtu)
            rng.shuffle(frags)  # 断片は順不同で届きうる
            pieces = {}
            for f in frags:
                h = parse_ipv4_header(f)  # チェックサムも検証される
                self.assertLessEqual(len(f), mtu)
                pieces[h.fragment_offset] = f[h.header_length:h.total_length]
            data = b"".join(pieces[k] for k in sorted(pieces))
            self.assertEqual(data, packet[20:])

    def test_mtu_too_small(self):
        with self.assertRaises(ValueError):
            fragment_ipv4(make_packet(100), 27)


if __name__ == "__main__":
    unittest.main()
