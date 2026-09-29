"""4.5 仮想化とコンテナ — 解答例: コンテンツアドレスのレイヤとビルドキャッシュ

演習の仕様は exercises/image_layers.py の docstring を参照してください。
"""
from __future__ import annotations

import hashlib
from typing import Mapping, NamedTuple, Sequence


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Step(NamedTuple):
    instruction: str  # 例: "RUN pip install -r requirements.txt"
    sources: tuple[str, ...] = ()  # COPY/ADD がビルドコンテキストから取り込むパス


class Layer(NamedTuple):
    digest: str
    size: int


class Usage(NamedTuple):
    logical: int  # 各イメージの大きさの合計（共有を考えない場合）
    physical: int  # 異なるレイヤの大きさの合計（実際に必要な保存容量）
    shared: int  # 2 つ以上のイメージが使うレイヤの大きさの合計
    unique: dict[str, int]  # イメージ名 -> そのイメージだけが使うレイヤの大きさの合計


# ---------------------------------------------------------------------------
# 演習4: ビルドキャッシュのキー
# ---------------------------------------------------------------------------

def select_files(context: Mapping[str, bytes], source: str) -> list[str]:
    if source in (".", "./"):
        return sorted(context)  # ビルドコンテキストのすべて
    if source in context:
        return [source]  # ファイルそのもの
    prefix = source.rstrip("/") + "/"
    matched = sorted(p for p in context if p.startswith(prefix))  # ディレクトリ以下のすべて
    if not matched:
        raise FileNotFoundError(f"ビルドコンテキストにありません: {source}")
    return matched


def content_digest(context: Mapping[str, bytes], sources: Sequence[str]) -> str:
    paths = sorted({p for s in sources for p in select_files(context, s)})
    h = hashlib.sha256()
    for path in paths:
        # パスと中身のハッシュの組を順に混ぜる。中身が 1 バイトでも変われば、ダイジェストが変わる
        h.update(path.encode() + b"\0" + sha256_hex(context[path]).encode() + b"\n")
    return h.hexdigest()


def cache_keys(base: str, steps: Sequence[Step], context: Mapping[str, bytes]) -> list[str]:
    keys: list[str] = []
    parent = sha256_hex(base.encode())
    for step in steps:
        material = parent + "\n" + step.instruction
        if step.sources:
            # COPY/ADD は、取り込むファイルの中身もキーに含める
            material += "\n" + content_digest(context, step.sources)
        # RUN はコマンドの文字列だけでキーが決まる（外の世界の変化はキーに入らない）
        parent = sha256_hex(material.encode())
        keys.append(parent)  # 親のキーを含むので、1 つ変わるとそれ以降がすべて変わる
    return keys


def build(base: str, steps: Sequence[Step], context: Mapping[str, bytes], cache: set[str]) -> list[bool]:
    keys = cache_keys(base, steps, context)
    rebuilt = [key not in cache for key in keys]
    cache.update(keys)
    return rebuilt


# ---------------------------------------------------------------------------
# 演習5: レイヤの共有と保存容量
# ---------------------------------------------------------------------------

def _sizes(images: Mapping[str, Sequence[Layer]]) -> dict[str, int]:
    sizes: dict[str, int] = {}
    for name, layers in images.items():
        for layer in layers:
            if layer.size < 0:
                raise ValueError(f"{name}: 大きさが負のレイヤ {layer}")
            if sizes.setdefault(layer.digest, layer.size) != layer.size:
                # 同じダイジェスト = 同じ中身。大きさが違うなら、どこかが壊れている
                raise ValueError(f"同じダイジェストで大きさが異なります: {layer.digest}")
    return sizes


def storage_usage(images: Mapping[str, Sequence[Layer]]) -> Usage:
    sizes = _sizes(images)
    users: dict[str, set[str]] = {}
    for name, layers in images.items():
        for layer in layers:
            users.setdefault(layer.digest, set()).add(name)
    logical = sum(sum(sizes[d] for d in {layer.digest for layer in layers}) for layers in images.values())
    physical = sum(sizes.values())
    shared = sum(sizes[d] for d, u in users.items() if len(u) >= 2)
    unique = {name: 0 for name in images}
    for d, u in users.items():
        if len(u) == 1:
            unique[next(iter(u))] += sizes[d]
    return Usage(logical, physical, shared, unique)


def pull_bytes(layers: Sequence[Layer], present: set[str]) -> int:
    _sizes({"image": layers})
    missing = {layer.digest: layer.size for layer in layers if layer.digest not in present}
    return sum(missing.values())
