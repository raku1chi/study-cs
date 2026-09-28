"""8.3 演習1 — Git のオブジェクトモデル（minigit）のテスト

実行: python3 tools/check.py 8.3   （またはこのディレクトリで python3 -m unittest -v test_minigit）

期待値のハッシュは、hashlib で計算するか、本物の Git（2.43）で同じオブジェクトを作って確かめた値です。
このテストの実行に Git は必要ありません。
"""
import hashlib
import unittest

from minigit import (
    Commit,
    ObjectStore,
    commit_tree,
    encode_object,
    hash_object,
    is_ancestor,
    log,
    merge_bases,
    parse_commit,
    write_tree,
)

ALICE = "Alice <alice@example.com>"
T0 = 1700000000

# 本物の Git で確かめた値（git write-tree / git commit-tree の結果）
DEMO_FILES = {
    "hello.txt": b"hello\n",
    "src/app.py": b'print("hi")\n',
    "run.sh": b"#!/bin/sh\necho run\n",
    "a.txt": b"x\n",
    "a/b.txt": b"y\n",
}
DEMO_TREE = "15bbfb89a66be054ceb4e2b1023d98ab8d2fc6c4"
ORDER_TREE = "83e50cefa1b5e66b7158ab38437149e36417d80c"  # {"a-b", "a/c", "a0", "A", "b/x/y/z.txt"}
UTF8_TREE = "7ff4177ec189989400e99d05afae335592c03a16"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
COMMIT_A = "5a28fd34431ce942ce6db390448395d634c9e8d1"  # DEMO_TREE, メッセージ「最初のコミット」
COMMIT_B = "41ff7000cf3535fd4b774686e251dbc92e3ff5ec"  # 親 A、100 秒後、メッセージ「B」
COMMIT_M = "c9182e347382737c4f4ce90c31b80dcabf77ad78"  # 親 C と E のマージ


def parse_tree(content: bytes) -> list[tuple[bytes, bytes, str]]:
    """テスト用: tree オブジェクトの内容を (モード, 名前, sha) の列に分解する。"""
    entries, i = [], 0
    while i < len(content):
        space = content.index(b" ", i)
        nul = content.index(b"\0", space)
        entries.append((content[i:space], content[space + 1:nul], content[nul + 1:nul + 21].hex()))
        i = nul + 21
    return entries


def sha1_object(obj_type: str, content: bytes) -> str:
    return hashlib.sha1(f"{obj_type} {len(content)}".encode() + b"\0" + content).hexdigest()


class TestObjects(unittest.TestCase):
    def test_encode_object(self):
        self.assertEqual(encode_object("blob", b"hello\n"), b"blob 6\x00hello\n")
        self.assertEqual(encode_object("tree", b""), b"tree 0\x00")
        self.assertEqual(encode_object("blob", "あ".encode()), b"blob 3\x00" + "あ".encode(), "長さは文字数ではなくバイト数")

    def test_hash_object_matches_git(self):
        self.assertEqual(hash_object(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a")
        self.assertEqual(hash_object(b""), "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")
        self.assertEqual(hash_object(b"", "tree"), EMPTY_TREE)

    def test_hash_object_is_sha1_of_header_and_content(self):
        for content in (b"a", b"x" * 1000, bytes(range(256))):
            self.assertEqual(hash_object(content), sha1_object("blob", content))
            self.assertEqual(hash_object(content, "commit"), sha1_object("commit", content))

    def test_unknown_type(self):
        with self.assertRaises(ValueError):
            hash_object(b"x", "file")

    def test_store_deduplicates(self):
        store = ObjectStore()
        s1 = store.put("blob", b"same\n")
        s2 = store.put("blob", b"same\n")
        self.assertEqual(s1, s2)
        self.assertEqual(len(store), 1)
        self.assertEqual(store.get(s1), ("blob", b"same\n"))


class TestWriteTree(unittest.TestCase):
    def setUp(self):
        self.store = ObjectStore()

    def test_single_file(self):
        sha = write_tree(self.store, {"hello.txt": b"hello\n"})
        expected = b"100644 hello.txt\x00" + bytes.fromhex("ce013625030ba8dba906f756967f9e9ca394464a")
        self.assertEqual(self.store.get(sha), ("tree", expected))
        self.assertEqual(sha, sha1_object("tree", expected))

    def test_matches_git_for_nested_directories_and_executables(self):
        self.assertEqual(write_tree(self.store, DEMO_FILES, executables={"run.sh"}), DEMO_TREE)

    def test_directory_mode_and_order(self):
        sha = write_tree(self.store, DEMO_FILES, executables={"run.sh"})
        entries = parse_tree(self.store.get(sha)[1])
        self.assertEqual(
            [(mode, name) for mode, name, _ in entries],
            [(b"100644", b"a.txt"), (b"40000", b"a"), (b"100644", b"hello.txt"),
             (b"100755", b"run.sh"), (b"40000", b"src")],
            "ディレクトリのモードは 40000、ディレクトリ名は末尾に / があるものとして並べる",
        )
        a_tree = entries[1][2]
        self.assertEqual(self.store.get(a_tree)[0], "tree")
        self.assertEqual(parse_tree(self.store.get(a_tree)[1])[0][:2], (b"100644", b"b.txt"))

    def test_ordering_edge_cases_match_git(self):
        files = {"a-b": b"1\n", "a/c": b"2\n", "a0": b"3\n", "A": b"4\n", "b/x/y/z.txt": b"deep\n"}
        sha = write_tree(self.store, files)
        names = [name for _, name, _ in parse_tree(self.store.get(sha)[1])]
        self.assertEqual(names, [b"A", b"a-b", b"a", b"a0", b"b"], "'-' < '/' < '0' の順")
        self.assertEqual(sha, ORDER_TREE)

    def test_utf8_names_match_git(self):
        files = {"ドキュメント/読んでね.md": "こんにちは\n".encode(), "README.md": b"# t\n"}
        self.assertEqual(write_tree(self.store, files), UTF8_TREE)

    def test_executable_changes_the_hash(self):
        normal = write_tree(self.store, {"hello.txt": b"hello\n"})
        executable = write_tree(self.store, {"hello.txt": b"hello\n"}, executables=["hello.txt"])
        self.assertNotEqual(normal, executable)
        self.assertEqual(parse_tree(self.store.get(executable)[1])[0][0], b"100755")

    def test_all_objects_are_stored(self):
        write_tree(self.store, {"a/b/c.txt": b"1", "a/d.txt": b"2", "e.txt": b"1"})
        # blob 2 つ（"1" は重複排除）+ tree 3 つ（根・a・a/b）
        kinds = sorted(self.store.get(sha)[0] for sha in list(self.store._objects))
        self.assertEqual(kinds, ["blob", "blob", "tree", "tree", "tree"])

    def test_empty_tree(self):
        self.assertEqual(write_tree(self.store, {}), EMPTY_TREE)

    def test_invalid_paths(self):
        for bad in ["", "/abs.txt", "dir/", "a//b", "./a", "a/../b", "a/./b"]:
            with self.assertRaises(ValueError, msg=repr(bad)):
                write_tree(self.store, {bad: b"x"})
        with self.assertRaises(ValueError, msg="a がファイルとディレクトリの両方"):
            write_tree(self.store, {"a": b"x", "a/b": b"y"})
        with self.assertRaises(ValueError, msg="順序が逆でも検出する"):
            write_tree(self.store, {"a/b": b"y", "a": b"x"})
        with self.assertRaises(ValueError, msg="executables に存在しないパス"):
            write_tree(self.store, {"a": b"x"}, executables=["b"])


class DagTestCase(unittest.TestCase):
    """本物の Git で確かめた DAG:

        A ── B ── C ─────── M ── F        （main）
              \\           /
               D ─── E ──┴──── G        （feature）
        X1 = merge(C, E)、X2 = merge(E, C)   （互いにマージし合った criss-cross）
    """

    def setUp(self):
        self.store = ObjectStore()
        self.tree = write_tree(self.store, DEMO_FILES, executables={"run.sh"})
        self.c = {}
        spec = [("A", [], 0, "最初のコミット"), ("B", ["A"], 100, "B"), ("C", ["B"], 200, "C"),
                ("D", ["B"], 300, "D"), ("E", ["D"], 400, "E"), ("M", ["C", "E"], 500, "Merge feature"),
                ("F", ["M"], 600, "F"), ("G", ["E"], 700, "G"), ("X1", ["C", "E"], 800, "X1"),
                ("X2", ["E", "C"], 900, "X2")]
        for name, parents, dt, message in spec:
            self.c[name] = commit_tree(self.store, self.tree, [self.c[p] for p in parents], message, ALICE, T0 + dt)
        self.name_of = {sha: name for name, sha in self.c.items()}

    def names(self, shas):
        return [self.name_of[s] for s in shas]


class TestCommits(DagTestCase):
    def test_commit_hashes_match_git(self):
        self.assertEqual(self.c["A"], COMMIT_A)
        self.assertEqual(self.c["B"], COMMIT_B)
        self.assertEqual(self.c["M"], COMMIT_M)

    def test_commit_content_format(self):
        obj_type, content = self.store.get(self.c["B"])
        self.assertEqual(obj_type, "commit")
        self.assertEqual(
            content.decode(),
            f"tree {self.tree}\nparent {COMMIT_A}\n"
            f"author {ALICE} {T0 + 100} +0900\ncommitter {ALICE} {T0 + 100} +0900\n\nB\n",
        )

    def test_message_newline_is_not_doubled_and_committer_can_differ(self):
        sha = commit_tree(self.store, self.tree, [], "msg\n", ALICE, T0, "-0500",
                          committer="Bob <bob@example.com>", committer_timestamp=T0 + 5)
        content = self.store.get(sha)[1].decode()
        self.assertTrue(content.endswith("\n\nmsg\n"))
        self.assertIn(f"author {ALICE} {T0} -0500\n", content)
        self.assertIn(f"committer Bob <bob@example.com> {T0 + 5} -0500\n", content)

    def test_parse_commit(self):
        commit = parse_commit(self.store.get(self.c["M"])[1])
        self.assertIsInstance(commit, Commit)
        self.assertEqual(commit.tree, self.tree)
        self.assertEqual(commit.parents, (self.c["C"], self.c["E"]))
        self.assertEqual(commit.author, f"{ALICE} {T0 + 500} +0900")
        self.assertEqual(commit.message, "Merge feature\n")
        self.assertEqual(commit.committer_time, T0 + 500)
        self.assertEqual(parse_commit(self.store.get(self.c["A"])[1]).parents, ())

    def test_parse_commit_skips_multiline_headers(self):
        content = (
            f"tree {EMPTY_TREE}\nauthor {ALICE} {T0} +0900\ncommitter {ALICE} {T0} +0900\n"
            "gpgsig -----BEGIN PGP SIGNATURE-----\n \n abcdef\n -----END PGP SIGNATURE-----\n\n署名付き\n"
        ).encode()
        commit = parse_commit(content)
        self.assertEqual((commit.tree, commit.message), (EMPTY_TREE, "署名付き\n"))
        with self.assertRaises(ValueError):
            parse_commit(b"author x\n\nno tree\n")

    def test_invalid_arguments(self):
        blob = self.store.put("blob", b"not a tree")
        with self.assertRaises(ValueError, msg="tree が存在しない"):
            commit_tree(self.store, "0" * 40, [], "m", ALICE, T0)
        with self.assertRaises(ValueError, msg="tree の位置に blob"):
            commit_tree(self.store, blob, [], "m", ALICE, T0)
        with self.assertRaises(ValueError, msg="親が commit ではない"):
            commit_tree(self.store, self.tree, [self.tree], "m", ALICE, T0)
        with self.assertRaises(ValueError, msg="タイムゾーンの形式"):
            commit_tree(self.store, self.tree, [], "m", ALICE, T0, tz="JST")


class TestHistory(DagTestCase):
    def test_log_orders_by_committer_time(self):
        self.assertEqual(self.names(log(self.store, self.c["F"])), ["F", "M", "E", "D", "C", "B", "A"])

    def test_log_first_parent(self):
        self.assertEqual(self.names(log(self.store, self.c["F"], first_parent=True)), ["F", "M", "C", "B", "A"])
        self.assertEqual(self.names(log(self.store, self.c["A"], first_parent=True)), ["A"])

    def test_log_ties_are_broken_by_sha(self):
        p = commit_tree(self.store, self.tree, [], "p", ALICE, T0)
        x = commit_tree(self.store, self.tree, [p], "x", ALICE, T0 + 10)
        y = commit_tree(self.store, self.tree, [p], "y", ALICE, T0 + 10)
        m = commit_tree(self.store, self.tree, [x, y], "m", ALICE, T0 + 20)
        self.assertEqual(log(self.store, m), [m] + sorted([x, y]) + [p])

    def test_is_ancestor(self):
        self.assertTrue(is_ancestor(self.store, self.c["B"], self.c["F"]))
        self.assertTrue(is_ancestor(self.store, self.c["E"], self.c["F"]), "マージで取り込まれた側の祖先")
        self.assertTrue(is_ancestor(self.store, self.c["F"], self.c["F"]), "自分自身も含む")
        self.assertFalse(is_ancestor(self.store, self.c["G"], self.c["F"]))
        self.assertFalse(is_ancestor(self.store, self.c["F"], self.c["B"]))

    def test_merge_base_of_diverged_branches(self):
        self.assertEqual(self.names(merge_bases(self.store, self.c["C"], self.c["E"])), ["B"])

    def test_merge_base_after_merge(self):
        self.assertEqual(self.names(merge_bases(self.store, self.c["F"], self.c["G"])), ["E"])

    def test_merge_base_when_one_is_ancestor(self):
        self.assertEqual(self.names(merge_bases(self.store, self.c["A"], self.c["F"])), ["A"])
        self.assertEqual(self.names(merge_bases(self.store, self.c["F"], self.c["F"])), ["F"])

    def test_criss_cross_merge_has_two_bases(self):
        bases = merge_bases(self.store, self.c["X1"], self.c["X2"])
        self.assertEqual(sorted(self.names(bases)), ["C", "E"])
        self.assertEqual(bases, sorted(bases), "sha の昇順で返す")

    def test_unrelated_histories(self):
        other_tree = write_tree(self.store, {"other.txt": b"z\n"})
        root = commit_tree(self.store, other_tree, [], "別の履歴", ALICE, T0)
        self.assertEqual(merge_bases(self.store, root, self.c["F"]), [])


if __name__ == "__main__":
    unittest.main()
