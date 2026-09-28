"""11.3 ワンタイムパスワード（totp）— テスト

実行: python3 tools/check.py 11.3   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest

from totp import TotpVerifier, b32decode_secret, hotp, time_step, totp

SECRET_SHA1 = b"12345678901234567890"  # 20 バイト
SECRET_SHA256 = b"12345678901234567890123456789012"  # 32 バイト
SECRET_SHA512 = b"1234567890" * 6 + b"1234"  # 64 バイト

# RFC 4226 Appendix D（HOTP, HMAC-SHA-1, 6 桁, カウンタ 0〜9）
RFC4226_HOTP = ["755224", "287082", "359152", "969429", "338314",
                "254676", "287922", "162583", "399871", "520489"]

# RFC 6238 Appendix B（TOTP, 30 秒, 8 桁）: 時刻 → (SHA-1, SHA-256, SHA-512)
# （執筆時に、RFC の表の値と hmac モジュールによる計算が一致することを確認済み）
RFC6238_TOTP = {
    59: ("94287082", "46119246", "90693936"),
    1111111109: ("07081804", "68084774", "25091201"),
    1111111111: ("14050471", "67062674", "99943326"),
    1234567890: ("89005924", "91819424", "93441116"),
    2000000000: ("69279037", "90698825", "38618901"),
    20000000000: ("65353130", "77737706", "47863826"),
}


class TestExercise1Hotp(unittest.TestCase):
    def test_rfc4226_vectors(self):
        for counter, expected in enumerate(RFC4226_HOTP):
            self.assertEqual(hotp(SECRET_SHA1, counter), expected, f"counter={counter}")

    def test_leading_zeros_are_kept(self):
        codes = [hotp(SECRET_SHA1, c) for c in range(2000)]
        self.assertTrue(all(len(c) == 6 and c.isdigit() for c in codes))
        self.assertTrue(any(c.startswith("0") for c in codes), "先頭が 0 のコードも 6 桁で返す")

    def test_digits_and_algorithm_validation(self):
        self.assertEqual(len(hotp(SECRET_SHA1, 0, digits=8)), 8)
        for bad in (5, 9, 0):
            with self.assertRaises(ValueError):
                hotp(SECRET_SHA1, 0, digits=bad)
        with self.assertRaises(ValueError):
            hotp(SECRET_SHA1, 0, algorithm="md5")
        with self.assertRaises(ValueError):
            hotp(SECRET_SHA1, -1)


class TestExercise2Totp(unittest.TestCase):
    def test_time_step(self):
        self.assertEqual(time_step(59), 1)
        self.assertEqual(time_step(1111111109), 0x23523EC)
        self.assertEqual(time_step(20000000000), 0x27BC86AA)
        self.assertEqual(time_step(29.999), 0)
        self.assertEqual(time_step(30), 1)
        self.assertEqual(time_step(100, step=60, t0=40), 1)
        with self.assertRaises(ValueError):
            time_step(100, step=0)

    def test_rfc6238_vectors(self):
        for t, (e1, e256, e512) in RFC6238_TOTP.items():
            self.assertEqual(totp(SECRET_SHA1, t, digits=8), e1, f"SHA-1 T={t}")
            self.assertEqual(totp(SECRET_SHA256, t, digits=8, algorithm="sha256"), e256, f"SHA-256 T={t}")
            self.assertEqual(totp(SECRET_SHA512, t, digits=8, algorithm="sha512"), e512, f"SHA-512 T={t}")

    def test_same_code_within_a_step(self):
        self.assertEqual(totp(SECRET_SHA1, 1_700_000_010), totp(SECRET_SHA1, 1_700_000_039))
        self.assertEqual(totp(SECRET_SHA1, 1_700_000_010), hotp(SECRET_SHA1, 1_700_000_010 // 30))

    def test_b32decode_secret(self):
        self.assertEqual(b32decode_secret("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"), SECRET_SHA1)
        self.assertEqual(b32decode_secret("gezd gnbv gy3t qojq gezd gnbv gy3t qojq"), SECRET_SHA1,
                         "小文字と空白（認証アプリの表示形式）も受け付ける")
        self.assertEqual(b32decode_secret("GE"), b"1", "パディング（=）の省略を受け付ける")
        for bad in ("!!!!", "GEZDGNB1"):
            with self.assertRaises(ValueError, msg=bad):
                b32decode_secret(bad)


class Clock:
    """テスト用の時計。t を書き換えて時間を進める。"""

    def __init__(self, t: float) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


class TestExercise3Verifier(unittest.TestCase):
    T = 1_700_000_000  # 2023-11-14 のある時刻。time_step = 56666666

    def code_at(self, t: float) -> str:
        return totp(SECRET_SHA1, t)

    def test_accepts_current_code(self):
        v = TotpVerifier(SECRET_SHA1, clock=Clock(self.T))
        self.assertTrue(v.verify(self.code_at(self.T)))
        self.assertEqual(v.last_used_step, self.T // 30)

    def test_replay_is_rejected(self):
        v = TotpVerifier(SECRET_SHA1, clock=Clock(self.T))
        code = self.code_at(self.T)
        self.assertTrue(v.verify(code))
        self.assertFalse(v.verify(code), "盗み見られた同じコードの再利用（リプレイ）を拒否する")

    def test_clock_skew_window(self):
        v = TotpVerifier(SECRET_SHA1, clock=Clock(self.T), window=1)
        self.assertTrue(v.verify(self.code_at(self.T - 30)), "1 ステップ前のコードは許容範囲")
        v2 = TotpVerifier(SECRET_SHA1, clock=Clock(self.T), window=1)
        self.assertFalse(v2.verify(self.code_at(self.T - 60)), "2 ステップ前は拒否")
        v3 = TotpVerifier(SECRET_SHA1, clock=Clock(self.T), window=1)
        self.assertTrue(v3.verify(self.code_at(self.T + 30)), "端末の時計が進んでいる場合")
        v4 = TotpVerifier(SECRET_SHA1, clock=Clock(self.T), window=0)
        self.assertFalse(v4.verify(self.code_at(self.T - 30)), "window=0 なら現在のステップのみ")

    def test_older_code_after_newer_is_rejected(self):
        clock = Clock(self.T)
        v = TotpVerifier(SECRET_SHA1, clock=clock)
        self.assertTrue(v.verify(self.code_at(self.T)))
        # 許容範囲内でも、すでに受理したステップ以前のコードは拒否する
        self.assertFalse(v.verify(self.code_at(self.T - 30)))
        clock.t = self.T + 30
        self.assertTrue(v.verify(self.code_at(self.T + 30)), "次のステップの新しいコードは受理")

    def test_explicit_now_overrides_clock(self):
        v = TotpVerifier(SECRET_SHA1, clock=Clock(0))
        self.assertTrue(v.verify(self.code_at(self.T), now=self.T))

    def test_malformed_codes(self):
        v = TotpVerifier(SECRET_SHA1, clock=Clock(self.T))
        good = self.code_at(self.T)
        for bad in ("", good[:-1], good + "0", "12345a", " " + good[1:], "１２３４５６", None, 123456):
            self.assertFalse(v.verify(bad), repr(bad))  # type: ignore[arg-type]
        self.assertIsNone(v.last_used_step, "失敗した検証で状態を変えない")

    def test_eight_digits_sha256(self):
        v = TotpVerifier(SECRET_SHA256, digits=8, algorithm="sha256", clock=Clock(59))
        self.assertTrue(v.verify("46119246"))

    def test_constructor_validation(self):
        with self.assertRaises(ValueError):
            TotpVerifier(SECRET_SHA1, digits=4)
        with self.assertRaises(ValueError):
            TotpVerifier(SECRET_SHA1, algorithm="md5")
        with self.assertRaises(ValueError):
            TotpVerifier(SECRET_SHA1, window=-1)


if __name__ == "__main__":
    unittest.main()
