"""12.3 深層学習とTransformer — 演習3: 注意機構（アテンション）を行列演算から作る（★★☆）

Transformer（Vaswani ほか, 2017）の中核である scaled dot-product attention と multi-head attention を、
純粋な Python の行列演算で実装します。行列は「リストのリスト」で、X[i] が i 番目のトークンの
ベクトル（行ベクトル）です。

    Attention(Q, K, V) = softmax(Q Kᵀ / √d_k) V

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 12.3
このディレクトリで直接実行する場合:
    python3 -m unittest -v test_attention
"""
from __future__ import annotations

import math  # noqa: F401
from typing import Sequence

Matrix = list[list[float]]
Mask = Sequence[Sequence[bool]]


# ---------------------------------------------------------------------------
# 演習3a（★☆☆）: 行列演算と softmax
# ---------------------------------------------------------------------------

def matmul(A: Sequence[Sequence[float]], B: Sequence[Sequence[float]]) -> Matrix:
    """行列の積 A @ B（A: n×k, B: k×m → n×m）。

    空の行列、行の長さがそろっていない行列、形が合わない場合は ValueError。
    """
    raise NotImplementedError("演習3a: matmul を実装してください")


def transpose(A: Sequence[Sequence[float]]) -> Matrix:
    """転置行列。"""
    raise NotImplementedError("演習3a: transpose を実装してください")


def softmax(xs: Sequence[float]) -> list[float]:
    """数値的に安定な softmax: exp(x_i - max) / Σ exp(x_j - max)。

    - 最大値を引いても結果は変わらず、exp のオーバーフロー（math.exp(1000) は OverflowError）を防げる。
    - -inf の要素は確率 0 になる（マスクに使う）。
    - 空のベクトル、またはすべてが -inf なら ValueError。

    >>> softmax([0.0, float("-inf"), 0.0])
    [0.5, 0.0, 0.5]
    """
    raise NotImplementedError("演習3a: softmax を実装してください")


def causal_mask(n: int) -> list[list[bool]]:
    """n×n の因果マスク。mask[i][j] は「位置 i が位置 j を見てよいか」で、j <= i なら True。

    >>> causal_mask(3)
    [[True, False, False], [True, True, False], [True, True, True]]
    """
    raise NotImplementedError("演習3a: causal_mask を実装してください")


def layer_norm(x: Sequence[float], eps: float = 1e-5) -> list[float]:
    """層正規化（学習可能なパラメータなし）: (x - 平均) / √(分散 + eps)。分散は n で割る。空なら ValueError。"""
    raise NotImplementedError("演習3a: layer_norm を実装してください")


# ---------------------------------------------------------------------------
# 演習3b（★★☆）: scaled dot-product attention
# ---------------------------------------------------------------------------

def scaled_dot_product_attention(
    Q: Sequence[Sequence[float]],
    K: Sequence[Sequence[float]],
    V: Sequence[Sequence[float]],
    mask: Mask | None = None,
) -> tuple[Matrix, Matrix]:
    """(出力, 注意の重み) を返す。Q: n_q×d_k、K: n_k×d_k、V: n_k×d_v。

    1. scores = Q Kᵀ / √d_k   （n_q × n_k）
    2. mask があれば、mask[i][j] が False の位置のスコアを -inf にする。
    3. weights = 各行に softmax   （各行の和が 1）
    4. 出力 = weights V          （n_q × d_v。値ベクトルの重み付き平均）

    ValueError にする場合: Q と K の列数が違う、K と V の行数が違う、mask の形が n_q × n_k でない。
    n_q と n_k は違ってよい（クロスアテンション）。
    """
    raise NotImplementedError("演習3b: scaled_dot_product_attention を実装してください")


# ---------------------------------------------------------------------------
# 演習3c（★★☆）: multi-head attention
# ---------------------------------------------------------------------------

def split_heads(X: Sequence[Sequence[float]], n_heads: int) -> list[Matrix]:
    """n×d_model の行列を、列方向に n_heads 等分して n×(d_model/n_heads) の行列のリストにする。

    ヘッド h は列 [h·d_head, (h+1)·d_head) を受け持つ。d_model が n_heads で割り切れない
    （または n_heads < 1）なら ValueError。
    """
    raise NotImplementedError("演習3c: split_heads を実装してください")


def merge_heads(heads: Sequence[Sequence[Sequence[float]]]) -> Matrix:
    """split_heads の逆: 各行について、ヘッドの順に列を連結する。空や行数の不一致は ValueError。"""
    raise NotImplementedError("演習3c: merge_heads を実装してください")


def multi_head_attention(
    X: Sequence[Sequence[float]],
    W_q: Sequence[Sequence[float]],
    W_k: Sequence[Sequence[float]],
    W_v: Sequence[Sequence[float]],
    W_o: Sequence[Sequence[float]],
    n_heads: int,
    *,
    causal: bool = False,
) -> Matrix:
    """自己注意（self-attention）の multi-head 版。

    1. Q = X W_q、K = X W_k、V = X W_v（すべて d_model × d_model の重み）
    2. Q, K, V をそれぞれ split_heads し、ヘッドごとに scaled_dot_product_attention
       （causal=True なら causal_mask を渡す）
    3. 各ヘッドの出力を merge_heads で連結し、W_o を掛ける
    """
    raise NotImplementedError("演習3c: multi_head_attention を実装してください")


# ---------------------------------------------------------------------------
# 演習3d（★★☆）: 位置エンコーディングと KV キャッシュ
# ---------------------------------------------------------------------------

def sinusoidal_positional_encoding(n_positions: int, d_model: int) -> Matrix:
    """Transformer の論文の正弦波の位置エンコーディング（n_positions × d_model）。

    PE[pos][2i]   = sin(pos / 10000^(2i/d_model))
    PE[pos][2i+1] = cos(pos / 10000^(2i/d_model))
    つまり列 j の角度は pos / 10000^(2·(j//2)/d_model) で、j が偶数なら sin、奇数なら cos。
    n_positions < 1 または d_model < 1 なら ValueError。
    """
    raise NotImplementedError("演習3d: sinusoidal_positional_encoding を実装してください")


class KVCache:
    """自己回帰の生成（1 トークンずつ出力する）で、過去のトークンの K と V を保存して再利用する。

    因果的な注意では、位置 i の出力は位置 0〜i の K, V だけに依存する。そこで新しいトークンが来るたびに
    その K, V を append し、そのトークンのクエリ q だけで attend すれば、過去の K, V を計算し直さずに済む。
    （1 ヘッド分。テストでは、これが因果マスク付きの全体計算の各行と一致することを確かめる）
    """

    def __init__(self) -> None:
        self.keys: Matrix = []
        self.values: Matrix = []

    def __len__(self) -> int:
        return len(self.keys)

    def append(self, k: Sequence[float], v: Sequence[float]) -> None:
        """k, v を追加する。既存のエントリと次元が違えば ValueError。"""
        raise NotImplementedError("演習3d: KVCache.append を実装してください")

    def attend(self, q: Sequence[float]) -> tuple[list[float], list[float]]:
        """クエリ q で、保存済みのすべての K, V に注意を向け、(出力ベクトル, 重みのリスト) を返す。

        空なら ValueError。ヒント: scaled_dot_product_attention([q], keys, values) の 1 行目。
        """
        raise NotImplementedError("演習3d: KVCache.attend を実装してください")
