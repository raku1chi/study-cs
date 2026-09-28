"""8.3 バージョン管理とコードレビュー — 解答例: Git のオブジェクトモデル（minigit）

仕様は exercises/minigit.py の docstring を参照してください。
本物の Git（2.43）で作ったオブジェクトとハッシュが一致することを確かめてあります。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable, Optional, Union

OBJECT_TYPES = ("blob", "tree", "commit", "tag")
TZ_PATTERN = re.compile(r"[+-]\d{4}")

FILE_MODE = b"100644"
EXECUTABLE_MODE = b"100755"
TREE_MODE = b"40000"  # オブジェクトの中では先頭の 0 がない


# ---------------------------------------------------------------------------
# 演習1-1: オブジェクトの符号化とハッシュ
# ---------------------------------------------------------------------------

def encode_object(obj_type: str, content: bytes) -> bytes:
    if obj_type not in OBJECT_TYPES:
        raise ValueError(f"不明なオブジェクトの型です: {obj_type!r}")
    return f"{obj_type} {len(content)}".encode("ascii") + b"\0" + content


def hash_object(content: bytes, obj_type: str = "blob") -> str:
    return hashlib.sha1(encode_object(obj_type, content)).hexdigest()


class ObjectStore:
    def __init__(self) -> None:
        self._objects: dict[str, tuple[str, bytes]] = {}

    def put(self, obj_type: str, content: bytes) -> str:
        sha = hash_object(content, obj_type)
        self._objects[sha] = (obj_type, content)
        return sha

    def get(self, sha: str) -> tuple[str, bytes]:
        return self._objects[sha]

    def __contains__(self, sha: object) -> bool:
        return sha in self._objects

    def __len__(self) -> int:
        return len(self._objects)


# ---------------------------------------------------------------------------
# 演習1-2: tree オブジェクト
# ---------------------------------------------------------------------------

# 入れ子の辞書: 名前 → ファイル（(内容, 実行可能か)）またはサブディレクトリ（辞書）
Node = dict[str, Union["Node", tuple[bytes, bool]]]


def _split_path(path: str) -> list[str]:
    parts = path.split("/")
    if not path or any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"不正なパスです: {path!r}")
    return parts


def _build_hierarchy(files: dict[str, bytes], executables: set[str]) -> Node:
    root: Node = {}
    for path, content in files.items():
        *dirs, name = _split_path(path)
        node = root
        for d in dirs:
            child = node.setdefault(d, {})
            if not isinstance(child, dict):
                raise ValueError(f"{path!r}: {d!r} はファイルとディレクトリの両方として使われています")
            node = child
        if name in node:
            raise ValueError(f"{path!r} はファイルとディレクトリの両方として使われています")
        node[name] = (content, path in executables)
    return root


def _write_node(store: ObjectStore, node: Node) -> str:
    entries = []
    for name, child in node.items():
        name_bytes = name.encode("utf-8")
        if isinstance(child, dict):
            mode, sha = TREE_MODE, _write_node(store, child)
            sort_key = name_bytes + b"/"  # ディレクトリは末尾に "/" があるものとして比較する
        else:
            content, executable = child
            mode = EXECUTABLE_MODE if executable else FILE_MODE
            sha = store.put("blob", content)
            sort_key = name_bytes
        entries.append((sort_key, mode + b" " + name_bytes + b"\0" + bytes.fromhex(sha)))
    entries.sort(key=lambda e: e[0])
    return store.put("tree", b"".join(entry for _, entry in entries))


def write_tree(store: ObjectStore, files: dict[str, bytes], executables: Iterable[str] = ()) -> str:
    executable_set = set(executables)
    unknown = executable_set - set(files)
    if unknown:
        raise ValueError(f"files にない実行可能ファイルが指定されています: {sorted(unknown)}")
    return _write_node(store, _build_hierarchy(files, executable_set))


# ---------------------------------------------------------------------------
# 演習1-3: commit オブジェクト
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Commit:
    tree: str
    parents: tuple[str, ...]
    author: str
    committer: str
    message: str

    @property
    def committer_time(self) -> int:
        return int(self.committer.rsplit(" ", 2)[1])


def _require_type(store: ObjectStore, sha: str, expected: str) -> None:
    if sha not in store or store.get(sha)[0] != expected:
        raise ValueError(f"{sha} は {expected} オブジェクトとして存在しません")


def commit_tree(
    store: ObjectStore,
    tree: str,
    parents: Iterable[str],
    message: str,
    author: str,
    timestamp: int,
    tz: str = "+0900",
    committer: Optional[str] = None,
    committer_timestamp: Optional[int] = None,
) -> str:
    parents = list(parents)
    _require_type(store, tree, "tree")
    for parent in parents:
        _require_type(store, parent, "commit")
    if not TZ_PATTERN.fullmatch(tz):
        raise ValueError(f"タイムゾーンは +0900 のような形式で指定してください: {tz!r}")
    committer = committer if committer is not None else author
    committer_timestamp = committer_timestamp if committer_timestamp is not None else timestamp
    if not message.endswith("\n"):
        message += "\n"
    lines = [f"tree {tree}"]
    lines += [f"parent {p}" for p in parents]
    lines.append(f"author {author} {timestamp} {tz}")
    lines.append(f"committer {committer} {committer_timestamp} {tz}")
    text = "\n".join(lines) + "\n\n" + message
    return store.put("commit", text.encode("utf-8"))


def parse_commit(content: bytes) -> Commit:
    header, sep, message = content.decode("utf-8").partition("\n\n")
    tree: Optional[str] = None
    parents: list[str] = []
    author: Optional[str] = None
    committer: Optional[str] = None
    for line in header.split("\n"):
        if line.startswith(" "):
            continue  # 複数行ヘッダ（gpgsig など）の続きの行
        key, _, value = line.partition(" ")
        if key == "tree":
            tree = value
        elif key == "parent":
            parents.append(value)
        elif key == "author":
            author = value
        elif key == "committer":
            committer = value
    if tree is None or author is None or committer is None or not sep:
        raise ValueError("commit オブジェクトの形式が不正です")
    return Commit(tree, tuple(parents), author, committer, message)


def _load_commit(store: ObjectStore, sha: str) -> Commit:
    obj_type, content = store.get(sha)
    if obj_type != "commit":
        raise ValueError(f"{sha} は commit ではありません（{obj_type}）")
    return parse_commit(content)


# ---------------------------------------------------------------------------
# 演習1-4: 履歴の DAG をたどる
# ---------------------------------------------------------------------------

def _ancestors(store: ObjectStore, start: str) -> set[str]:
    """start 自身を含む、到達できるすべてのコミット（反復的な深さ優先探索）。"""
    seen: set[str] = set()
    stack = [start]
    while stack:
        sha = stack.pop()
        if sha in seen:
            continue
        seen.add(sha)
        stack.extend(_load_commit(store, sha).parents)
    return seen


def log(store: ObjectStore, head: str, first_parent: bool = False) -> list[str]:
    if first_parent:
        result = []
        sha: Optional[str] = head
        while sha is not None:
            result.append(sha)
            parents = _load_commit(store, sha).parents
            sha = parents[0] if parents else None
        return result
    commits = _ancestors(store, head)
    return sorted(commits, key=lambda s: (-_load_commit(store, s).committer_time, s))


def is_ancestor(store: ObjectStore, ancestor: str, descendant: str) -> bool:
    return ancestor in _ancestors(store, descendant)


def merge_bases(store: ObjectStore, a: str, b: str) -> list[str]:
    common = _ancestors(store, a) & _ancestors(store, b)
    # 「ほかの共通祖先の、真の祖先」であるものを除くと、最良の共通祖先が残る
    dominated: set[str] = set()
    for c in common:
        dominated |= _ancestors(store, c) - {c}
    return sorted(common - dominated)
