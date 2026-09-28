"""11.2 ブロック暗号の利用モード（block_modes）— テスト

【教育目的・本番では使わない】
実行: python3 tools/check.py 11.2   （またはこのディレクトリで python3 -m unittest -v）
"""
import random
import unittest

from block_modes import (
    BLOCK_SIZE,
    ToyFeistelCipher,
    count_repeated_blocks,
    ctr_bitflip,
    ctr_encrypt,
    ctr_keystream,
    ecb_decrypt,
    ecb_encrypt,
    looks_like_ecb,
    pkcs7_pad,
    pkcs7_unpad,
    recover_plaintext_from_nonce_reuse,
    xor_bytes,
)

KEY = bytes(range(16))


def image_rows() -> list[bytes]:
    """16 文字 = 1 ブロックの「画像」。同じ模様の行が何度も現れる（ECB ペンギンの縮小版）。"""
    return [
        b"................",
        b"......####......",
        b"....########....",
        b"...##########...",
        b"....########....",
        b"......####......",
        b"................",
        b"................",
    ]


class TestExercise1Feistel(unittest.TestCase):
    def test_known_answer(self):
        c = ToyFeistelCipher(KEY)
        self.assertEqual(c.encrypt_block(b"YELLOW SUBMARINE").hex(), "899ad565b4c6c62e8a0d845c311b2604")

    def test_round_trip(self):
        rng = random.Random(1)
        for rounds in (1, 2, 3, 4, 8):
            c = ToyFeistelCipher(rng.randbytes(16), rounds=rounds)
            for _ in range(50):
                block = rng.randbytes(16)
                self.assertEqual(c.decrypt_block(c.encrypt_block(block)), block, rounds)

    def test_permutation_no_collisions(self):
        c = ToyFeistelCipher(KEY)
        blocks = {i.to_bytes(16, "big") for i in range(2000)}
        self.assertEqual(len({c.encrypt_block(b) for b in blocks}), len(blocks), "置換なので衝突しない")

    def test_one_round_is_insecure(self):
        # 1 ラウンドでは平文の右半分がそのまま暗号文の左半分に出てしまう
        c = ToyFeistelCipher(KEY, rounds=1)
        self.assertEqual(c.encrypt_block(b"YELLOW SUBMARINE")[:8], b"UBMARINE")

    def test_avalanche(self):
        # 平文を 1 ビット変えると、暗号文の約半分（64 ビット前後）のビットが変わる
        c = ToyFeistelCipher(KEY)
        rng = random.Random(2)
        total = 0
        for _ in range(200):
            p = rng.randbytes(16)
            bit = rng.randrange(128)
            q = bytearray(p)
            q[bit // 8] ^= 1 << (bit % 8)
            diff = int.from_bytes(c.encrypt_block(p), "big") ^ int.from_bytes(c.encrypt_block(bytes(q)), "big")
            total += bin(diff).count("1")
        self.assertTrue(54 <= total / 200 <= 74, total / 200)

    def test_block_length_is_checked(self):
        c = ToyFeistelCipher(KEY)
        for bad in (b"", b"short", b"x" * 17):
            with self.assertRaises(ValueError):
                c.encrypt_block(bad)
            with self.assertRaises(ValueError):
                c.decrypt_block(bad)
        with self.assertRaises(ValueError):
            ToyFeistelCipher(b"too short")


class TestExercise2EcbAndPadding(unittest.TestCase):
    def test_pkcs7_pad(self):
        self.assertEqual(pkcs7_pad(b""), b"\x10" * 16)
        self.assertEqual(pkcs7_pad(b"A" * 15), b"A" * 15 + b"\x01")
        self.assertEqual(pkcs7_pad(b"A" * 16), b"A" * 16 + b"\x10" * 16, "割り切れても 1 ブロック追加する")
        self.assertEqual(pkcs7_pad(b"YELLOW SUBMARINE", 20), b"YELLOW SUBMARINE\x04\x04\x04\x04")

    def test_pkcs7_unpad(self):
        for n in range(0, 40):
            data = bytes(range(n))
            self.assertEqual(pkcs7_unpad(pkcs7_pad(data)), data)

    def test_pkcs7_unpad_rejects_invalid(self):
        bad = {
            "空": b"",
            "ブロック長の倍数でない": b"A" * 15,
            "末尾が 0": b"A" * 15 + b"\x00",
            "末尾がブロック長より大きい": b"A" * 15 + b"\x11",
            "パディングの中身が不揃い": b"A" * 12 + b"\x01\x04\x04\x04",
        }
        for label, data in bad.items():
            with self.assertRaises(ValueError, msg=label):
                pkcs7_unpad(data)

    def test_ecb_round_trip(self):
        c = ToyFeistelCipher(KEY)
        for n in (0, 1, 15, 16, 17, 100):
            data = bytes(range(n))
            ct = ecb_encrypt(c, data)
            self.assertEqual(len(ct) % BLOCK_SIZE, 0)
            self.assertEqual(ecb_decrypt(c, ct), data)
        with self.assertRaises(ValueError):
            ecb_decrypt(c, b"x" * 15)

    def test_ecb_leaks_patterns(self):
        c = ToyFeistelCipher(KEY)
        ct = ecb_encrypt(c, b"".join(image_rows()))
        blocks = [ct[i:i + 16] for i in range(0, len(ct), 16)]
        # 同じ平文ブロック → 同じ暗号文ブロック。模様の「形」が暗号文に残る
        self.assertEqual(blocks[0], blocks[6])
        self.assertEqual(blocks[1], blocks[5])
        self.assertEqual(blocks[2], blocks[4])
        self.assertNotEqual(blocks[0], blocks[1])


class TestExercise3Ctr(unittest.TestCase):
    def test_keystream_definition(self):
        c = ToyFeistelCipher(KEY)
        nonce = b"\x01" * 8
        ks = ctr_keystream(c, nonce, 40)
        self.assertEqual(len(ks), 40)
        self.assertEqual(ks[:16], c.encrypt_block(nonce + (0).to_bytes(8, "big")))
        self.assertEqual(ks[16:32], c.encrypt_block(nonce + (1).to_bytes(8, "big")))
        self.assertEqual(ks[32:], c.encrypt_block(nonce + (2).to_bytes(8, "big"))[:8])
        self.assertEqual(ctr_keystream(c, nonce, 0), b"")

    def test_round_trip_without_padding(self):
        c = ToyFeistelCipher(KEY)
        nonce = b"\x00" * 8
        for n in range(0, 50):
            data = bytes(range(n))
            ct = ctr_encrypt(c, nonce, data)
            self.assertEqual(len(ct), n, "CTR はパディング不要で、長さが変わらない")
            self.assertEqual(ctr_encrypt(c, nonce, ct), data)

    def test_nonce_validation(self):
        c = ToyFeistelCipher(KEY)
        for bad in (b"", b"\x00" * 7, b"\x00" * 16):
            with self.assertRaises(ValueError):
                ctr_encrypt(c, bad, b"data")

    def test_ctr_hides_patterns(self):
        c = ToyFeistelCipher(KEY)
        ct = ctr_encrypt(c, b"\x07" * 8, b"".join(image_rows()))
        self.assertEqual(count_repeated_blocks(ct), 0)
        self.assertFalse(looks_like_ecb(ct))

    def test_different_nonces_give_different_ciphertexts(self):
        c = ToyFeistelCipher(KEY)
        msg = b"attack at dawn!!"
        self.assertNotEqual(ctr_encrypt(c, b"\x00" * 8, msg), ctr_encrypt(c, b"\x01" * 8, msg))


class TestExercise4Attacks(unittest.TestCase):
    def test_count_repeated_blocks(self):
        self.assertEqual(count_repeated_blocks(b""), 0)
        self.assertEqual(count_repeated_blocks(b"A" * 16 * 4 + b"B" * 16 * 2), 4)
        self.assertEqual(count_repeated_blocks(b"A" * 16 + b"B" * 16), 0)
        self.assertEqual(count_repeated_blocks(b"A" * 20), 0, "端数のブロックは数えない")
        self.assertEqual(count_repeated_blocks(b"AB" * 4, block_size=2), 3)

    def test_detect_ecb(self):
        c = ToyFeistelCipher(KEY)
        ct = ecb_encrypt(c, b"".join(image_rows()))
        self.assertTrue(looks_like_ecb(ct))
        self.assertEqual(count_repeated_blocks(ct), 4)

    def test_nonce_reuse_leaks_xor_of_plaintexts(self):
        c = ToyFeistelCipher(b"secret key 12345")
        nonce = b"\x00" * 8  # 誤って固定の nonce を使い回している
        p1 = b"From: alice, amount: 1000 yen"
        p2 = b"PIN code of bob is 4921 !!!!!"
        c1, c2 = ctr_encrypt(c, nonce, p1), ctr_encrypt(c, nonce, p2)
        self.assertEqual(xor_bytes(c1, c2), xor_bytes(p1, p2), "鍵ストリームが消え、平文どうしの XOR が漏れる")
        # 一方の平文を知っている（推測できる）だけで、もう一方が丸ごと読める
        self.assertEqual(recover_plaintext_from_nonce_reuse(c1, c2, p1), p2)
        self.assertEqual(recover_plaintext_from_nonce_reuse(c1, c2, p1[:10]), p2[:10])

    def test_bitflip_without_key(self):
        c = ToyFeistelCipher(b"secret key 12345")
        nonce = b"\x05" * 8
        original = b"transfer amount=100 to=bob"
        ct = ctr_encrypt(c, nonce, original)
        # 攻撃者は鍵を知らないが、平文の形式を知っている
        forged = ctr_bitflip(ct, original, b"transfer amount=900 to=bob")
        self.assertEqual(ctr_encrypt(c, nonce, forged), b"transfer amount=900 to=bob",
                         "暗号化だけでは改ざんを防げない → AEAD（GCM など）が必要")
        with self.assertRaises(ValueError):
            ctr_bitflip(ct, original, b"short")

    def test_xor_bytes_helper(self):
        self.assertEqual(xor_bytes(b"\x0f\xf0", b"\xff\xff"), b"\xf0\x0f")
        with self.assertRaises(ValueError):
            xor_bytes(b"a", b"ab")


if __name__ == "__main__":
    unittest.main()
