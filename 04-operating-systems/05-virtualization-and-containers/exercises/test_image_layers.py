"""4.5 仮想化とコンテナ — image_layers のテスト

実行: python3 tools/check.py 4.5   （またはこのディレクトリで python3 -m unittest -v test_image_layers）
"""
import hashlib
import unittest

from image_layers import (
    Layer,
    Step,
    Usage,
    build,
    cache_keys,
    content_digest,
    pull_bytes,
    select_files,
    storage_usage,
)

BASE = "python:3.12-slim@sha256:" + "1" * 64
CONTEXT = {
    "requirements.txt": b"flask==3.0.3\n",
    "app/main.py": b"print('v1')\n",
    "app/util.py": b"def f(): return 1\n",
    "README.md": b"# app\n",
}

# よくない順序: ソースをすべてコピーしてから依存関係をインストールする
NAIVE = [
    Step("WORKDIR /app"),
    Step("COPY . .", (".",)),
    Step("RUN pip install -r requirements.txt"),
    Step('CMD ["python", "app/main.py"]'),
]
# よい順序: 依存関係の定義だけを先にコピーしてインストールし、ソースは最後にコピーする
LAYERED = [
    Step("WORKDIR /app"),
    Step("COPY requirements.txt .", ("requirements.txt",)),
    Step("RUN pip install -r requirements.txt"),
    Step("COPY app/ app/", ("app/",)),
    Step('CMD ["python", "app/main.py"]'),
]


def changed(context, path, data):
    new = dict(context)
    new[path] = data
    return new


class TestExercise4BuildCache(unittest.TestCase):
    def test_select_files(self):
        self.assertEqual(select_files(CONTEXT, "."), sorted(CONTEXT))
        self.assertEqual(select_files(CONTEXT, "requirements.txt"), ["requirements.txt"])
        self.assertEqual(select_files(CONTEXT, "app/"), ["app/main.py", "app/util.py"])
        self.assertEqual(select_files(CONTEXT, "app"), ["app/main.py", "app/util.py"])
        with self.assertRaises(FileNotFoundError):
            select_files(CONTEXT, "missing.txt")

    def test_content_digest_depends_on_paths_and_contents(self):
        d = content_digest(CONTEXT, ["app/"])
        self.assertEqual(len(d), 64)
        self.assertEqual(d, content_digest(dict(reversed(list(CONTEXT.items()))), ["app"]), "辞書の順序に依存しない")
        self.assertNotEqual(d, content_digest(changed(CONTEXT, "app/util.py", b"def f(): return 2\n"), ["app/"]))
        renamed = {"app/main2.py" if k == "app/main.py" else k: v for k, v in CONTEXT.items()}
        self.assertNotEqual(d, content_digest(renamed, ["app/"]), "ファイル名の変更も内容の変更")
        self.assertEqual(content_digest(CONTEXT, ["app/"]), content_digest(CONTEXT, ["app/main.py", "app/util.py"]))

    def test_first_key_follows_the_documented_format(self):
        expected = hashlib.sha256(
            (hashlib.sha256(BASE.encode()).hexdigest() + "\nWORKDIR /app").encode()
        ).hexdigest()
        self.assertEqual(cache_keys(BASE, NAIVE, CONTEXT)[0], expected)

    def test_keys_chain_through_parents(self):
        keys = cache_keys(BASE, NAIVE, CONTEXT)
        self.assertEqual(len(keys), 4)
        self.assertEqual(len(set(keys)), 4)
        other_base = cache_keys("python:3.13-slim", NAIVE, CONTEXT)
        self.assertTrue(all(a != b for a, b in zip(keys, other_base)), "ベースイメージが変わると全段が変わる")

    def test_rebuild_with_naive_order(self):
        cache: set[str] = set()
        self.assertEqual(build(BASE, NAIVE, CONTEXT, cache), [True, True, True, True])
        self.assertEqual(build(BASE, NAIVE, CONTEXT, cache), [False, False, False, False], "2 回目はすべてキャッシュ")
        edited = changed(CONTEXT, "app/main.py", b"print('v2')\n")
        self.assertEqual(build(BASE, NAIVE, edited, cache), [False, True, True, True],
                         "ソースを 1 行変えただけで pip install からやり直しになる")

    def test_rebuild_with_dependency_layers_first(self):
        cache: set[str] = set()
        build(BASE, LAYERED, CONTEXT, cache)
        edited = changed(CONTEXT, "app/main.py", b"print('v2')\n")
        self.assertEqual(build(BASE, LAYERED, edited, cache), [False, False, False, True, True],
                         "ソースの変更では、依存関係のインストールはキャッシュのまま")
        readme = changed(CONTEXT, "README.md", b"# app (updated)\n")
        self.assertEqual(build(BASE, LAYERED, readme, cache), [False] * 5, "取り込まないファイルの変更は影響しない")
        deps = changed(CONTEXT, "requirements.txt", b"flask==3.1.0\n")
        self.assertEqual(build(BASE, LAYERED, deps, cache), [False, True, True, True, True])

    def test_run_is_cached_even_if_the_outside_world_changed(self):
        steps = [Step("RUN apt-get update"), Step("RUN apt-get install -y curl")]
        cache: set[str] = set()
        build(BASE, steps, {}, cache)
        # 何か月後でも、コマンドの文字列が同じならキャッシュが使われ、古いパッケージ一覧のままになる
        self.assertEqual(build(BASE, steps, {}, cache), [False, False])
        self.assertEqual(build(BASE, [Step("RUN apt-get update && apt-get install -y curl")], {}, cache), [True])

    def test_going_back_to_an_old_version_hits_the_cache(self):
        cache: set[str] = set()
        build(BASE, LAYERED, CONTEXT, cache)
        edited = changed(CONTEXT, "app/main.py", b"print('v2')\n")
        build(BASE, LAYERED, edited, cache)
        self.assertEqual(build(BASE, LAYERED, CONTEXT, cache), [False] * 5, "内容が同じならキーも同じ")

    def test_missing_source(self):
        with self.assertRaises(FileNotFoundError):
            cache_keys(BASE, [Step("COPY nope.txt .", ("nope.txt",))], CONTEXT)


class TestExercise5Storage(unittest.TestCase):
    OS = Layer("sha256:os", 80)
    PY = Layer("sha256:py", 50)
    NODE = Layer("sha256:node", 60)

    def images(self):
        return {
            "api": [self.OS, self.PY, Layer("sha256:api", 10)],
            "worker": [self.OS, self.PY, Layer("sha256:worker", 15)],
            "web": [self.OS, self.NODE, Layer("sha256:web", 5)],
        }

    def test_storage_usage(self):
        usage = storage_usage(self.images())
        self.assertEqual(usage, Usage(
            logical=140 + 145 + 145,  # 共有を考えない場合の合計 430
            physical=80 + 50 + 60 + 10 + 15 + 5,  # 実際に必要な容量 220
            shared=80 + 50,  # 複数のイメージが使うレイヤ
            unique={"api": 10, "worker": 15, "web": 60 + 5},
        ))

    def test_duplicate_layer_in_one_image_is_counted_once(self):
        usage = storage_usage({"a": [self.OS, self.OS]})
        self.assertEqual((usage.logical, usage.physical, usage.shared), (80, 80, 0))

    def test_same_digest_with_different_sizes_is_an_error(self):
        with self.assertRaises(ValueError):
            storage_usage({"a": [Layer("sha256:x", 1)], "b": [Layer("sha256:x", 2)]})

    def test_pull_bytes(self):
        present = {self.OS.digest, self.PY.digest}  # api のイメージを既に持っているノード
        worker = self.images()["worker"]
        self.assertEqual(pull_bytes(worker, present), 15, "共有レイヤは再ダウンロードしない")
        self.assertEqual(pull_bytes(self.images()["web"], present), 65)
        self.assertEqual(pull_bytes(worker, set()), 145)
        self.assertEqual(pull_bytes([], present), 0)


if __name__ == "__main__":
    unittest.main()
