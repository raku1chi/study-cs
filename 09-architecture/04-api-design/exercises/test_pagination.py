"""9.4 API設計 — カーソルページネーションのテスト

実行: python3 tools/check.py 9.4   （またはこのディレクトリで python3 -m unittest -v）
"""
import base64
import json
import random
import re
import unittest

from pagination import (
    MAX_LIMIT,
    InvalidCursorError,
    Item,
    ItemStore,
    decode_cursor,
    encode_cursor,
    paginate,
)

SECRET = b"test-secret-key-0123456789abcdef"


def make_store(n, start=1_700_000_000_000, step=1000):
    store = ItemStore()
    for i in range(n):
        store.insert(Item(f"item-{i:04d}", start + i * step, f"#{i}"))
    return store


def read_all(store, limit, secret=SECRET, scope="", between_pages=None):
    """全ページを読み、返った項目 ID をすべて返す。between_pages(ページ番号) を各ページの後に呼ぶ。"""
    seen, cursor, n = [], None, 0
    while True:
        page = paginate(store, limit, cursor, secret, scope=scope)
        seen.extend(i.item_id for i in page.items)
        n += 1
        if between_pages:
            between_pages(n)
        if page.next_cursor is None:
            return seen
        cursor = page.next_cursor
        assert n < 10_000, "終わらない"


class TestExercise2Cursor(unittest.TestCase):
    def test_round_trip(self):
        for pos in [(0, ""), (1_700_000_000_123, "item-0001"), (5, "日本語のID/with.dots")]:
            c = encode_cursor(pos, SECRET)
            self.assertEqual(decode_cursor(c, SECRET), pos)

    def test_cursor_is_url_safe(self):
        c = encode_cursor((1_700_000_000_123, "a/b+c=d 日本"), SECRET, scope="owner=u1")
        self.assertRegex(c, r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")

    def test_tampering_is_detected(self):
        c = encode_cursor((100, "item-1"), SECRET)
        payload, sig = c.split(".")
        forged = base64.urlsafe_b64encode(
            json.dumps({"id": "item-9", "s": "", "t": 999, "v": 1}, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
        flipped = sig[:5] + ("A" if sig[5] != "A" else "B") + sig[6:]  # 署名の途中の 1 文字を変える
        for bad in (forged + "." + sig, payload + "." + flipped):
            with self.assertRaises(InvalidCursorError):
                decode_cursor(bad, SECRET)

    def test_wrong_secret_or_scope(self):
        c = encode_cursor((100, "item-1"), SECRET, scope="owner=u1")
        with self.assertRaises(InvalidCursorError):
            decode_cursor(c, b"another-secret", scope="owner=u1")
        with self.assertRaises(InvalidCursorError, msg="別の検索条件のカーソルは使えない"):
            decode_cursor(c, SECRET, scope="owner=u2")
        self.assertEqual(decode_cursor(c, SECRET, scope="owner=u1"), (100, "item-1"))

    def test_garbage(self):
        for bad in ("", ".", "abc", "a.b.c", "!!!.???", "YWJj.", "日本.語"):
            with self.assertRaises(InvalidCursorError, msg=repr(bad)):
                decode_cursor(bad, SECRET)

    def test_signed_but_malformed_payload_is_rejected(self):
        import hashlib
        import hmac as hmac_mod

        def signed(obj):
            raw = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
            b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()  # noqa: E731
            return b64(raw) + "." + b64(hmac_mod.new(SECRET, raw, hashlib.sha256).digest())

        for obj in (b"not json", [1, 2], {"v": 2, "t": 1, "id": "x", "s": ""},
                    {"v": 1, "t": "1", "id": "x", "s": ""}, {"v": 1, "t": True, "id": "x", "s": ""},
                    {"v": 1, "t": 1, "id": 5, "s": ""}, {"v": 1, "id": "x", "s": ""}):
            with self.assertRaises(InvalidCursorError, msg=repr(obj)):
                decode_cursor(signed(obj), SECRET)
        self.assertEqual(decode_cursor(signed({"v": 1, "t": 1, "id": "x", "s": ""}), SECRET), (1, "x"))


class TestExercise2Paginate(unittest.TestCase):
    def test_pages_are_newest_first(self):
        store = make_store(25)
        p1 = paginate(store, 10, None, SECRET)
        self.assertEqual([i.item_id for i in p1.items], [f"item-{i:04d}" for i in range(24, 14, -1)])
        p2 = paginate(store, 10, p1.next_cursor, SECRET)
        p3 = paginate(store, 10, p2.next_cursor, SECRET)
        self.assertEqual(len(p2.items), 10)
        self.assertEqual([i.item_id for i in p3.items], [f"item-{i:04d}" for i in range(4, -1, -1)])
        self.assertIsNone(p3.next_cursor)

    def test_no_cursor_that_leads_to_an_empty_page(self):
        store = make_store(20)
        p1 = paginate(store, 10, None, SECRET)
        p2 = paginate(store, 10, p1.next_cursor, SECRET)
        self.assertEqual(len(p2.items), 10)
        self.assertIsNone(p2.next_cursor, "ちょうど割り切れたら、最後のページで終わる")
        self.assertEqual(paginate(ItemStore(), 10, None, SECRET), paginate(ItemStore(), 10, None, SECRET))
        self.assertEqual(paginate(ItemStore(), 10, None, SECRET).items, [])
        self.assertIsNone(paginate(ItemStore(), 10, None, SECRET).next_cursor)

    def test_ties_on_created_at_use_item_id(self):
        store = ItemStore()
        for i in range(30):
            store.insert(Item(f"id-{i:02d}", 1000 + (i // 10)))  # 10 件ずつ同じ時刻
        seen = read_all(store, 7)
        self.assertEqual(len(seen), 30)
        self.assertEqual(len(set(seen)), 30)
        expected = [k[1] for k in sorted((store.get(x).key for x in seen), reverse=True)]
        self.assertEqual(seen, expected)

    def test_inserting_newer_items_does_not_cause_duplicates(self):
        store = make_store(30)
        original = {f"item-{i:04d}" for i in range(30)}
        counter = [0]

        def insert_new(_page_no):
            for _ in range(3):  # 読んでいる間に新しい投稿が 3 件ずつ増える
                counter[0] += 1
                store.insert(Item(f"new-{counter[0]:03d}", 2_000_000_000_000 + counter[0]))

        seen = read_all(store, 10, between_pages=insert_new)
        self.assertEqual(len(seen), len(set(seen)), "同じ項目が 2 回返ってはいけない")
        self.assertEqual(set(seen), original, "最初からあった項目はすべて 1 回ずつ返る")

    def test_deleting_the_cursor_item_is_safe(self):
        store = make_store(20)
        p1 = paginate(store, 5, None, SECRET)
        store.delete(p1.items[-1].item_id)  # カーソルが指している項目そのものを削除
        store.delete("item-0013")           # 次のページに入るはずだった項目も削除
        p2 = paginate(store, 5, p1.next_cursor, SECRET)
        self.assertEqual([i.item_id for i in p2.items],
                         ["item-0014", "item-0012", "item-0011", "item-0010", "item-0009"])

    def test_random_interleaving_keeps_invariants(self):
        rng = random.Random(94)
        for trial in range(20):
            store = make_store(rng.randrange(0, 60), step=rng.choice([0, 1, 7]))
            original = {store.get(k[1]).item_id for k in store.sorted_keys()}
            deleted = set()
            counter = [0]

            def mutate(_page_no):
                for _ in range(rng.randrange(0, 4)):
                    action = rng.random()
                    if action < 0.5:
                        counter[0] += 1
                        created = rng.randrange(1_600_000_000_000, 1_800_000_000_000)
                        store.insert(Item(f"x{trial}-{counter[0]}", created))
                    elif len(store):
                        victim = rng.choice(store.sorted_keys())[1]
                        store.delete(victim)
                        deleted.add(victim)

            seen = read_all(store, rng.randrange(1, 12), between_pages=mutate)
            self.assertEqual(len(seen), len(set(seen)), f"trial {trial}: 重複")
            self.assertLessEqual(original - deleted, set(seen), f"trial {trial}: 欠落")

    def test_limit_validation(self):
        store = make_store(3)
        for bad in (0, -1, MAX_LIMIT + 1, 1.5, True, "10"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                paginate(store, bad, None, SECRET)
        self.assertEqual(len(paginate(store, MAX_LIMIT, None, SECRET).items), 3)

    def test_cursor_scope_is_enforced(self):
        store = make_store(10)
        page = paginate(store, 3, None, SECRET, scope="owner=u1")
        with self.assertRaises(InvalidCursorError):
            paginate(store, 3, page.next_cursor, SECRET, scope="owner=u2")
        self.assertEqual(len(paginate(store, 3, page.next_cursor, SECRET, scope="owner=u1").items), 3)

    def test_invalid_cursor_is_an_error_not_the_first_page(self):
        with self.assertRaises(InvalidCursorError):
            paginate(make_store(5), 2, "not-a-cursor", SECRET)
        self.assertTrue(issubclass(InvalidCursorError, ValueError))


if __name__ == "__main__":
    unittest.main()
