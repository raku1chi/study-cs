"""7.2 レプリケーションと一貫性 — 演習: Merkle 木によるレプリカ間の差分検出（解答例）

演習の仕様は exercises/merkle.py の docstring を参照してください。
"""
from __future__ import annotations

import hashlib
import json
from typing import Mapping

MAX_DEPTH = 20


def key_token(key: str) -> int:
    # キーを 64 ビットの「トークン」（ハッシュ空間上の位置）に写す
    return int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")


def key_bucket(key: str, depth: int) -> int:
    if not 0 <= depth <= MAX_DEPTH:
        raise ValueError(f"depth は 0〜{MAX_DEPTH} です: {depth}")
    # 上位 depth ビット = トークンの範囲を 2^depth 等分したときの番号（範囲ごとのバケツ）
    return key_token(key) >> (64 - depth)


def leaf_digest(items: list[tuple[str, str]]) -> bytes:
    # 両方のレプリカが同じバイト列を作れるよう、正規化した直列化（キー順・区切り固定）でハッシュする
    payload = json.dumps(sorted(items), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).digest()


class MerkleTree:
    def __init__(self, data: Mapping[str, str], depth: int = 8) -> None:
        if not 0 <= depth <= MAX_DEPTH:
            raise ValueError(f"depth は 0〜{MAX_DEPTH} です: {depth}")
        self.depth = depth
        buckets: list[list[tuple[str, str]]] = [[] for _ in range(1 << depth)]
        for key, value in data.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError("キーと値は文字列です")
            buckets[key_bucket(key, depth)].append((key, value))
        self._buckets = [sorted(b) for b in buckets]
        # levels[0] がルート、levels[depth] が葉。下から順に親を計算する
        level = [leaf_digest(b) for b in self._buckets]
        levels = [level]
        while len(level) > 1:
            level = [hashlib.sha256(level[i] + level[i + 1]).digest() for i in range(0, len(level), 2)]
            levels.append(level)
        levels.reverse()
        self._levels = levels

    @property
    def root(self) -> str:
        return self._levels[0][0].hex()

    def node_hash(self, level: int, index: int) -> str:
        if not 0 <= level <= self.depth or not 0 <= index < (1 << level):
            raise IndexError(f"ノードが存在しません: level={level}, index={index}")
        return self._levels[level][index].hex()

    def bucket_items(self, index: int) -> list[tuple[str, str]]:
        if not 0 <= index < (1 << self.depth):
            raise IndexError(f"バケツが存在しません: {index}")
        return list(self._buckets[index])


def diff_buckets(a: MerkleTree, b: MerkleTree) -> tuple[list[int], int]:
    if a.depth != b.depth:
        raise ValueError(f"深さが違う木は比べられません: {a.depth} と {b.depth}")
    differing: list[int] = []
    comparisons = 0
    stack = [(0, 0)]
    while stack:
        level, index = stack.pop()
        comparisons += 1
        if a.node_hash(level, index) == b.node_hash(level, index):
            continue  # この部分木はまるごと一致。中を見る必要はない
        if level == a.depth:
            differing.append(index)
        else:
            stack.append((level + 1, 2 * index + 1))
            stack.append((level + 1, 2 * index))
    return sorted(differing), comparisons


def find_differences(
    a_data: Mapping[str, str], b_data: Mapping[str, str], depth: int = 8
) -> tuple[list[str], int]:
    a, b = MerkleTree(a_data, depth), MerkleTree(b_data, depth)
    buckets, comparisons = diff_buckets(a, b)
    keys: set[str] = set()
    for index in buckets:
        # 異なるバケツの中身だけを実際に突き合わせる
        left = dict(a.bucket_items(index))
        right = dict(b.bucket_items(index))
        for key in left.keys() | right.keys():
            if left.get(key) != right.get(key):
                keys.add(key)
    return sorted(keys), comparisons
