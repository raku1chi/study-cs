"""7.2 レプリケーションと一貫性 — 演習: Merkle 木によるレプリカ間の差分検出（アンチエントロピー）

2 台のレプリカが持つ数百万件のキーのうち、食い違っているのはどれか。全件を送り合って比べるのは
高くつきます。Dynamo や Cassandra は、キーの範囲ごとのハッシュを木にまとめた **Merkle 木**
（ハッシュ木）を交換し、ハッシュが一致する部分木は丸ごと飛ばすことで、比較量を劇的に減らします。

この演習の木の形:
    - キーを SHA-256 でハッシュし、先頭 8 バイトを 64 ビットの「トークン」とする（key_token）
    - トークンの上位 depth ビットをバケツ番号とする（key_bucket）。バケツ = トークンの範囲
    - 葉（level = depth）はバケツ。葉のハッシュは、そのバケツの (key, value) をキー順に並べて
      正規化した JSON にし、SHA-256 をとったもの（leaf_digest）
    - 内部ノードのハッシュは sha256(左の子のダイジェスト + 右の子のダイジェスト)（生のバイト列を連結）
    - level 0 がルート。level L には 2^L 個のノードがあり、(L, i) の子は (L+1, 2i) と (L+1, 2i+1)

      level 0:                 [ root ]
      level 1:        [ 0 ]                [ 1 ]
      level 2:   [ 0 ]     [ 1 ]      [ 2 ]     [ 3 ]    ← depth = 2 なら、これが葉（バケツ）

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 7.2
このディレクトリで、この演習だけを実行することもできます:
    python3 -m unittest -v test_merkle
"""
from __future__ import annotations

import hashlib  # noqa: F401  SHA-256 に使います
import json  # noqa: F401  leaf_digest の正規化に使います
from typing import Mapping

MAX_DEPTH = 20

# ---------------------------------------------------------------------------
# 演習3（★★☆）: Merkle 木と差分検出
# ---------------------------------------------------------------------------


def key_token(key: str) -> int:
    """key を UTF-8 で符号化して SHA-256 をとり、先頭 8 バイトをビッグエンディアンの整数にしたもの。

    ヒント: int.from_bytes(hashlib.sha256(...).digest()[:8], "big")
    """
    raise NotImplementedError("演習3: key_token を実装してください")


def key_bucket(key: str, depth: int) -> int:
    """key_token(key) の上位 depth ビット（0 <= 値 < 2^depth）。depth == 0 なら常に 0。

    depth が 0〜MAX_DEPTH の範囲外なら ValueError。
    """
    raise NotImplementedError("演習3: key_bucket を実装してください")


def leaf_digest(items: list[tuple[str, str]]) -> bytes:
    """バケツの中身から葉のダイジェスト（32 バイト）を計算する。

    items をキー順（(key, value) のタプルの昇順）に並べ、
        json.dumps(並べたリスト, ensure_ascii=False, separators=(",", ":"))
    を UTF-8 で符号化したバイト列の SHA-256 ダイジェストを返す。
    例: [("b", "2"), ("a", "1")] → '[["a","1"],["b","2"]]' のハッシュ。空なら '[]' のハッシュ。

    なぜ正規化が必要か: 2 台のレプリカが「同じデータなら必ず同じバイト列」を作れないと、
    データが同じでもハッシュが一致せず、比較の意味がなくなる。
    """
    raise NotImplementedError("演習3: leaf_digest を実装してください")


class MerkleTree:
    """data（key → value、どちらも str）から作る深さ depth の Merkle 木。

    - depth が 0〜MAX_DEPTH の範囲外なら ValueError。キーや値が str でなければ TypeError。
    - root（プロパティ）: ルートのハッシュ（16 進文字列）。
    - node_hash(level, index): ノード (level, index) のハッシュ（16 進文字列）。
      存在しないノード（level が 0〜depth の範囲外、index が 0〜2^level - 1 の範囲外）なら IndexError。
    - bucket_items(index): index 番のバケツの (key, value) をキー順に並べたリスト（コピー）。範囲外なら IndexError。

    ヒント: 葉のダイジェストのリストを作り、隣どうしを連結してハッシュする操作を、要素が 1 つになるまで
    繰り返すと、下から上へ全レベルが求まる。
    """

    def __init__(self, data: Mapping[str, str], depth: int = 8) -> None:
        raise NotImplementedError("演習3: MerkleTree.__init__ を実装してください")

    @property
    def root(self) -> str:
        raise NotImplementedError("演習3: MerkleTree.root を実装してください")

    def node_hash(self, level: int, index: int) -> str:
        raise NotImplementedError("演習3: MerkleTree.node_hash を実装してください")

    def bucket_items(self, index: int) -> list[tuple[str, str]]:
        raise NotImplementedError("演習3: MerkleTree.bucket_items を実装してください")


def diff_buckets(a: MerkleTree, b: MerkleTree) -> tuple[list[int], int]:
    """2 つの木を上から比べ、ハッシュが異なる葉（バケツ）の番号の昇順リストと、比較回数を返す。

    比較の手順（比較回数がテストで検査されるので、この通りに数えること）:
        1. ルートを比べる（1 回）。一致すれば終わり。
        2. 異なるノードが内部ノードなら、その 2 つの子を **両方** 比べる（2 回）。
           一致した子の部分木には降りない。異なる子にだけ降りる。
        3. 異なるノードが葉なら、そのバケツ番号を結果に加える。

    例: 1 つのキーだけが異なり depth = 10 なら、比較回数は 1 + 2 × 10 = 21。
    深さが異なる木どうしなら ValueError。
    """
    raise NotImplementedError("演習3: diff_buckets を実装してください")


def find_differences(
    a_data: Mapping[str, str], b_data: Mapping[str, str], depth: int = 8
) -> tuple[list[str], int]:
    """2 つのレプリカのデータから、値が異なる（片方にしかない場合を含む）キーの昇順リストと比較回数を返す。

    それぞれの MerkleTree を作って diff_buckets で異なるバケツを見つけ、
    **そのバケツの中身だけ** を突き合わせてキーを特定すること（全件を比べない）。
    比較回数は diff_buckets が返した値をそのまま返す。
    """
    raise NotImplementedError("演習3: find_differences を実装してください")
