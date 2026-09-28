"""8.3 バージョン管理とコードレビュー — 演習2: 3 方向マージ（diff3）

2 人が同じファイルを別々に変更したとき、Git は「2 人が分岐した時点の版（マージベース）」と
比べることで、どちらがどこを変えたかを判断します。これが 3 方向マージ（three-way merge）です。

    base（共通の祖先） → ours（自分の変更）
                       → theirs（相手の変更）

片方だけが変えた箇所はその変更を採用し、両方が同じ箇所を違うように変えたときだけ「衝突」にします。
この演習では、行単位の 3 方向マージを、最長共通部分列（LCS）による差分から実装します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 8.3

Git がインストールされていれば、本物の結果と比べられます:
    git merge-file -p --diff3 ours.txt base.txt theirs.txt

演習の構成:
    2-1 lcs_pairs（★★☆）: 2 つの行の列の LCS を、対応する行番号の組の列として求める
    2-2 merge3   （★★★）: diff3 のアルゴリズムで 3 方向マージを行い、衝突を diff3 形式のマーカーで表す

行はすべて改行文字を含まない文字列として扱います（例: ["a", "b", "c"]）。
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 演習2-1（★★☆）: 最長共通部分列（LCS）
# ---------------------------------------------------------------------------

def lcs_pairs(a: list[str], b: list[str]) -> list[tuple[int, int]]:
    """a と b の最長共通部分列を、対応する位置の組 (i, j)（a[i] == b[j]）の列で返す。

    - i も j も狭義に増加する列であること。組の数は LCS の長さ（最大）に等しいこと。
    - LCS が複数あるときに結果を一意にするため、次の手順で求めること:
        1. L[i][j] = a[i:] と b[j:] の LCS の長さ、を表で求める（後ろから埋める動的計画法）。
             a[i] == b[j] なら L[i][j] = L[i+1][j+1] + 1、そうでなければ max(L[i+1][j], L[i][j+1])
        2. (i, j) = (0, 0) から前向きにたどる:
             a[i] == b[j] なら (i, j) を対応として記録し、i と j を 1 進める。
             そうでなく L[i+1][j] >= L[i][j+1] なら i を進める（同点なら a 側を先に進める）。
             それ以外は j を進める。
      （等しい行はその場で対応させてよい。それを含む LCS が必ず存在するため）
    - 計算量は O(len(a) × len(b)) でよい。

    >>> lcs_pairs(["a", "b", "c", "d"], ["a", "c", "d", "e"])
    [(0, 0), (2, 1), (3, 2)]
    """
    raise NotImplementedError("演習2-1: lcs_pairs を実装してください")


# ---------------------------------------------------------------------------
# 演習2-2（★★★）: 3 方向マージ
# ---------------------------------------------------------------------------

@dataclass
class MergeResult:
    lines: list[str] = field(default_factory=list)  # マージ結果（衝突があればマーカーを含む）
    conflicts: int = 0  # 衝突した箇所の数

    @property
    def clean(self) -> bool:
        return self.conflicts == 0


def merge3(
    base: list[str],
    ours: list[str],
    theirs: list[str],
    *,
    labels: tuple[str, str, str] = ("ours", "base", "theirs"),
) -> MergeResult:
    """base を共通の祖先として、ours と theirs を 3 方向マージする（diff3 のアルゴリズム）。

    アルゴリズム（Khanna・Kunal・Pierce "A Formal Investigation of Diff3" の定式化にならう）:
      MA = lcs_pairs(base, ours) を辞書 {base の行番号: ours の行番号} にしたもの
      MB = lcs_pairs(base, theirs) を同様に辞書にしたもの
      o, a, t = 0, 0, 0   # base・ours・theirs のうち、処理し終えた行数
      繰り返し:
        1. 安定したチャンク: k = 0, 1, 2, … について MA.get(o+k) == a+k かつ MB.get(o+k) == t+k
           である間、base[o+k] は 3 つすべてで同じ行として対応している。その長さ k が 1 以上なら、
           その k 行を出力し、o・a・t をそれぞれ k 進めて繰り返しの先頭へ。
        2. 不安定なチャンク（k == 0 のとき）: j = o, o+1, … の中で、j が MA と MB の両方に含まれる
           最初の j を探す（base の行で、3 つすべてに残っている次の行）。
             見つかれば、チャンクは base[o:j]・ours[a:MA[j]]・theirs[t:MB[j]]。
             処理した後、o, a, t = j, MA[j], MB[j] として繰り返しの先頭へ。
             見つからなければ、チャンクは base[o:]・ours[a:]・theirs[t:]（最後のチャンク）で、
             処理した後に終了する。
        不安定なチャンク (B, A, T)（base, ours, theirs の部分）の処理:
           A == T         → A を出力（変更なし、または両方が同じ変更をした）
           A == B         → T を出力（相手だけが変更した）
           T == B         → A を出力（自分だけが変更した）
           それ以外       → 衝突。次の形式で出力し、conflicts を 1 増やす:
                  <<<<<<< {labels[0]}
                  （A の行）
                  ||||||| {labels[1]}
                  （B の行）
                  =======
                  （T の行）
                  >>>>>>> {labels[2]}
           （マーカーは 7 文字の記号 + 半角スペース + ラベル。"=======" の行にはラベルを付けない）

    注意: この方式では、隣り合う行をそれぞれが変更しただけでも衝突になります（Git も同様）。

    >>> merge3(["a", "b", "c"], ["a", "B", "c"], ["a", "b", "c"]).lines
    ['a', 'B', 'c']
    """
    raise NotImplementedError("演習2-2: merge3 を実装してください")
