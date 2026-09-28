"""11.4 パストラバーサル対策のファイル配信（safe_files）— テスト

実行: python3 tools/check.py 11.4   （またはこのディレクトリで python3 -m unittest -v）
"""
import os
import tempfile
import unittest
from pathlib import Path

from safe_files import UnsafePathError, safe_join, serve_file


class TestSafeFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / "public"
        (self.base / "css").mkdir(parents=True)
        (self.base / "index.html").write_bytes(b"<h1>hello</h1>")
        (self.base / "css" / "site.css").write_bytes(b"body{}")
        # ベースの外に置いた「秘密のファイル」
        self.secret = Path(self.tmp.name) / "secret.txt"
        self.secret.write_bytes(b"TOP SECRET")

    def tearDown(self):
        self.tmp.cleanup()

    def test_serves_files_inside_base(self):
        self.assertEqual(serve_file(self.base, "index.html"), b"<h1>hello</h1>")
        self.assertEqual(serve_file(self.base, "css/site.css"), b"body{}")
        self.assertEqual(serve_file(self.base, "./index.html"), b"<h1>hello</h1>")

    def test_safe_join_stays_inside(self):
        self.assertEqual(safe_join(self.base, "css/site.css"), (self.base / "css" / "site.css").resolve())
        # 中で ".." を使っても、base の中に戻ってくる分には許す
        self.assertEqual(safe_join(self.base, "css/../index.html"), (self.base / "index.html").resolve())

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            serve_file(self.base, "nope.html")
        with self.assertRaises(FileNotFoundError):
            serve_file(self.base, "css")  # ディレクトリは配信しない

    def test_dot_dot_traversal_is_blocked(self):
        for path in ["../secret.txt", "css/../../secret.txt", "../../etc/passwd",
                     "..", "css/../../"]:
            with self.assertRaises(UnsafePathError, msg=path):
                serve_file(self.base, path)

    def test_dot_dot_back_into_base_is_allowed(self):
        # 途中で ".." を使っても base の中に戻る分には安全（脱出していない）
        self.assertEqual(safe_join(self.base, "css/.."), self.base.resolve())

    def test_absolute_paths_are_blocked(self):
        with self.assertRaises(UnsafePathError):
            serve_file(self.base, "/etc/passwd")
        with self.assertRaises(UnsafePathError):
            serve_file(self.base, str(self.secret))

    def test_nul_byte_is_blocked(self):
        with self.assertRaises(UnsafePathError):
            serve_file(self.base, "index.html\x00.png")

    def test_non_string(self):
        with self.assertRaises(UnsafePathError):
            safe_join(self.base, 123)  # type: ignore[arg-type]

    @unittest.skipUnless(hasattr(os, "symlink"), "シンボリックリンク未対応の環境")
    def test_symlink_escape_is_blocked(self):
        link = self.base / "escape"
        try:
            link.symlink_to(self.tmp.name)  # base の外（親）を指すリンク
        except (OSError, NotImplementedError) as exc:  # 権限がない Windows など
            self.skipTest(f"シンボリックリンクを作成できません: {exc}")
        # リンクをたどって base の外の secret.txt を読もうとする
        with self.assertRaises(UnsafePathError):
            serve_file(self.base, "escape/secret.txt")

    @unittest.skipUnless(hasattr(os, "symlink"), "シンボリックリンク未対応の環境")
    def test_symlink_inside_base_is_allowed(self):
        target = self.base / "css" / "site.css"
        link = self.base / "alias.css"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"シンボリックリンクを作成できません: {exc}")
        self.assertEqual(serve_file(self.base, "alias.css"), b"body{}")


if __name__ == "__main__":
    unittest.main()
