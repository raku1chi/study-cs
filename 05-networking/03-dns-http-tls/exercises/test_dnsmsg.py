"""5.3 DNS・HTTP・TLS — テスト（dnsmsg）

実行: python3 tools/check.py 5.3   （またはこのディレクトリで python3 -m unittest -v）

応答のバイト列は data/*.hex にあります（「#」以降はコメント）。ファイルを開くと、各バイトの意味と
オフセットが注釈されているので、デバッグのときに読んでください。
"""
import re
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from dnsmsg import (
    CLASS_IN,
    TYPE_A,
    TYPE_AAAA,
    TYPE_ANY,
    TYPE_CAA,
    TYPE_CNAME,
    TYPE_MX,
    TYPE_NS,
    TYPE_OPT,
    TYPE_SOA,
    TYPE_SRV,
    TYPE_TXT,
    DNSFormatError,
    Question,
    ResourceRecord,
    build_query,
    decode_name,
    encode_name,
    parse_message,
)

DATA = Path(__file__).parent / "data"
HEADER_ONLY = bytes(12)  # 手作りのメッセージ用の、中身が 0 のヘッダ


def load(name: str) -> bytes:
    text = (DATA / name).read_text(encoding="utf-8")
    return bytes.fromhex("".join(re.sub(r"#.*", "", line) for line in text.splitlines()))


class TestEncodeAndBuildQuery(unittest.TestCase):
    def test_encode_name(self):
        self.assertEqual(encode_name("example.com"), b"\x07example\x03com\x00")
        self.assertEqual(encode_name("example.com."), b"\x07example\x03com\x00", "末尾のドットはあってもよい")
        self.assertEqual(encode_name("."), b"\x00")
        self.assertEqual(encode_name(""), b"\x00")
        self.assertEqual(encode_name("a" * 63 + ".jp")[:1], b"\x3f")

    def test_encode_name_errors(self):
        for bad in ("a" * 64 + ".com", "a..b", ".leading", ".".join(["a" * 63] * 4) + ".com", "例え.jp"):
            with self.assertRaises(ValueError, msg=bad[:30]):
                encode_name(bad)

    def test_build_query_bytes(self):
        expected = bytes.fromhex("1234 0100 0001 0000 0000 0000 07 6578616d706c65 03 636f6d 00 0001 0001")
        self.assertEqual(build_query("example.com", TYPE_A, txid=0x1234), expected)
        no_rd = build_query("example.com", TYPE_AAAA, txid=7, recursion_desired=False)
        self.assertEqual(no_rd[:4], bytes.fromhex("0007 0000"))
        self.assertEqual(no_rd[-4:], bytes.fromhex("001c 0001"))

    def test_build_query_round_trip(self):
        msg = parse_message(build_query("www.example.com", TYPE_MX, txid=0xABCD))
        self.assertEqual((msg.id, msg.qr, msg.rd, msg.rcode), (0xABCD, False, True, 0))
        self.assertEqual(msg.questions, [Question("www.example.com", TYPE_MX, CLASS_IN)])
        self.assertEqual((msg.answers, msg.authorities, msg.additionals), ([], [], []))

    def test_build_query_validates(self):
        with self.assertRaises(ValueError):
            build_query("example.com", TYPE_A, txid=0x10000)


class TestDecodeName(unittest.TestCase):
    def test_names_in_fixture(self):
        d = load("response_a_cname.hex")
        self.assertEqual(decode_name(d, 12), ("www.example.com", 29), "圧縮なし")
        self.assertEqual(decode_name(d, 16), ("example.com", 29), "名前の途中から読むこともできる")
        self.assertEqual(decode_name(d, 33), ("www.example.com", 35), "ポインタだけ: 次の位置はポインタの直後")
        self.assertEqual(decode_name(d, 45), ("web.example.com", 51), "ラベル＋ポインタ")
        self.assertEqual(decode_name(d, 51), ("web.example.com", 53), "ポインタの先にさらにポインタ")
        self.assertEqual(decode_name(d, 67), (".", 68), "ルートは「.」")

    def test_truncated_and_reserved_labels(self):
        cases = {
            "ラベルの途中で終わる": HEADER_ONLY + b"\x07exam",
            "終端の 0 がない": HEADER_ONLY + b"\x03com",
            "ポインタの 2 バイト目がない": HEADER_ONLY + b"\x03www\xc0",
            "予約済みのラベル形式 01": HEADER_ONLY + b"\x40abc\x00",
            "予約済みのラベル形式 10": HEADER_ONLY + b"\x80abc\x00",
        }
        for label, data in cases.items():
            with self.assertRaises(DNSFormatError, msg=label):
                decode_name(data, 12)

    def test_name_longer_than_255_bytes(self):
        data = HEADER_ONLY + (b"\x3f" + b"a" * 63) * 5 + b"\x00"  # 5 × 64 + 1 = 321 バイト
        with self.assertRaises(DNSFormatError):
            decode_name(data, 12)

    def test_malicious_pointers_terminate(self):
        # 素朴な実装はここで無限ループするので、別プロセスで制限時間とメモリの上限を付けて確かめる
        code = textwrap.dedent('''
            import sys
            try:
                import resource
                resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
            except Exception:
                pass
            from dnsmsg import decode_name, DNSFormatError
            header = bytes(12)
            cases = {
                "self": header + b"\\xc0\\x0c",                                  # 自分自身を指す
                "forward": header + b"\\xc0\\x0e\\x00",                          # 後ろを指す
                "cycle": header + b"\\x01a\\xc0\\x10\\x01b\\xc0\\x0c",           # a → b → a → ...
                "cycle-from-b": header + b"\\x01a\\xc0\\x10\\x01b\\xc0\\x0c",
            }
            starts = {"cycle-from-b": 16}
            for name, data in cases.items():
                try:
                    decode_name(data, starts.get(name, 12))
                    print(name, "no-error")
                except DNSFormatError:
                    print(name, "DNSFormatError")
                except Exception as exc:
                    print(name, type(exc).__name__)
        ''')
        try:
            proc = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).parent,
                                  capture_output=True, text=True, timeout=5)
        except subprocess.TimeoutExpired:
            self.fail("圧縮ポインタのループで decode_name が終わらない（ループ対策が必要）")
        results = dict(line.split() for line in proc.stdout.splitlines() if line.strip())
        self.assertEqual(results, {"self": "DNSFormatError", "forward": "DNSFormatError",
                                   "cycle": "DNSFormatError", "cycle-from-b": "DNSFormatError"},
                         proc.stderr[-500:])


class TestParseMessage(unittest.TestCase):
    def test_a_with_cname(self):
        m = parse_message(load("response_a_cname.hex"))
        self.assertEqual((m.id, m.qr, m.opcode, m.aa, m.tc, m.rd, m.ra, m.rcode),
                         (0xBEEF, True, 0, False, False, True, True, 0))
        self.assertEqual(m.questions, [Question("www.example.com", TYPE_A, CLASS_IN)])
        self.assertEqual(m.answers, [
            ResourceRecord("www.example.com", TYPE_CNAME, CLASS_IN, 3600, "web.example.com"),
            ResourceRecord("web.example.com", TYPE_A, CLASS_IN, 60, "192.0.2.10"),
        ])
        opt = m.additionals[0]
        self.assertEqual((opt.name, opt.rtype, opt.rclass, opt.data), (".", TYPE_OPT, 1232, b""),
                         "OPT の「クラス」欄は UDP で受け取れる大きさ")

    def test_mx_with_additional_records(self):
        m = parse_message(load("response_mx.hex"))
        self.assertTrue(m.aa, "権威サーバーからの応答")
        self.assertEqual([r.data for r in m.answers], [(10, "mx1.example.com"), (20, "mx2.example.com")])
        self.assertEqual([(r.name, r.rtype, r.data) for r in m.additionals],
                         [("mx1.example.com", TYPE_A, "192.0.2.25"), ("mx1.example.com", TYPE_AAAA, "2001:db8::25")])

    def test_nxdomain_with_soa(self):
        m = parse_message(load("response_nxdomain.hex"))
        self.assertEqual(m.rcode, 3, "NXDOMAIN")
        self.assertEqual(m.answers, [])
        soa = m.authorities[0]
        self.assertEqual((soa.name, soa.rtype, soa.ttl), ("example.com", TYPE_SOA, 300))
        self.assertEqual(soa.data, ("ns1.example.com", "hostmaster.example.com", 2026092801, 7200, 3600, 1209600, 300))
        negative_ttl = min(soa.ttl, soa.data[-1])  # RFC 2308: 否定応答をキャッシュしてよい時間
        self.assertEqual(negative_ttl, 300)

    def test_various_types(self):
        m = parse_message(load("response_any.hex"))
        self.assertEqual(m.questions[0].qtype, TYPE_ANY)
        self.assertEqual([(r.rtype, r.data) for r in m.answers], [
            (TYPE_NS, "ns1.example.com"),
            (TYPE_TXT, (b"v=spf1 -all",)),
            (TYPE_TXT, (b"hello", b"world")),
            (TYPE_CAA, (0, "issue", b"letsencrypt.org")),
        ])
        self.assertEqual(m.answers[0].ttl, 86400)

    def test_srv(self):
        m = parse_message(load("response_srv.hex"))
        self.assertEqual(m.answers[0].name, "_imaps._tcp.example.com")
        self.assertEqual((m.answers[0].rtype, m.answers[0].data), (TYPE_SRV, (0, 1, 993, "mail.example.com")))

    def test_truncated_messages_are_rejected(self):
        for name in ("response_a_cname.hex", "response_mx.hex", "response_nxdomain.hex",
                     "response_any.hex", "response_srv.hex"):
            data = load(name)
            for cut in range(len(data)):
                with self.assertRaises(DNSFormatError, msg=f"{name} を {cut} バイトで切った"):
                    parse_message(data[:cut])

    def test_trailing_garbage_is_rejected(self):
        with self.assertRaises(DNSFormatError):
            parse_message(load("response_srv.hex") + b"\x00")

    def test_rdlength_mismatch(self):
        data = bytearray(load("response_a_cname.hex"))
        data[62] = 5  # 回答 2（A レコード）の RDATA の長さを 4 → 5 に
        with self.assertRaises(DNSFormatError):
            parse_message(bytes(data) + b"\x00")

    def test_truncated_flag(self):
        data = bytearray(load("response_a_cname.hex"))
        data[2] |= 0x02  # TC ビット（応答が切り詰められた → TCP で問い合わせ直す合図）
        self.assertTrue(parse_message(bytes(data)).tc)


if __name__ == "__main__":
    unittest.main()
