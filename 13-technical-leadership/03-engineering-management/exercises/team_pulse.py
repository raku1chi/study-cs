"""13.3 エンジニアリングマネジメントの基礎 — 演習: チームのサーベイ結果の分析

定期的なエンゲージメントサーベイ（パルスサーベイ）の結果を集計する小さなツールを作ります。
eNPS の計算、低スコアの設問の抽出、期ごとの推移、そして「回答者を特定させない」ための
小さなグループの秘匿（二次秘匿を含む）を実装します。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 13.3          # 合格数を表示
    python3 tools/check.py -v 13.3       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v

データの形:
    - eNPS の設問: 「この職場を友人に勧める可能性は？」を 0〜10 の 11 段階で回答
    - その他の設問: 1〜5 の 5 段階（5 = とてもそう思う）
    - 期（period）は "2026-Q3" のように、文字列の昇順が時系列の順になる形式とする

制約:
    - 標準ライブラリのみを使ってください。
"""
from __future__ import annotations

from dataclasses import dataclass, field

ENTIRE_ORG = "全体"


@dataclass(frozen=True)
class Response:
    """1 人分の回答。

    team  : チーム名
    period: 期（例: "2026-Q3"）
    enps  : eNPS の設問への回答（0〜10）。未回答なら None
    items : 設問名 → 回答（1〜5）。未回答の設問は含めない
    """

    team: str
    period: str
    enps: int | None = None
    items: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class TeamSummary:
    """チーム（または組織全体）の集計結果。

    n         : 回答者数（その期の Response の数）
    enps      : eNPS（eNPS の設問に答えた人が 0 人なら None）
    item_means: 設問名 → 平均値（回答のあった設問のみ）
    """

    n: int
    enps: float | None
    item_means: dict[str, float]


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: eNPS と好意的回答率
# ---------------------------------------------------------------------------

def enps(scores: list[int]) -> float:
    """eNPS（従業員ネットプロモータースコア）を返す。範囲は -100〜100。

    eNPS = 推奨者（9〜10）の割合(%) − 批判者（0〜6）の割合(%)
    7〜8 は「中立」で、どちらにも数えない（ただし分母には含める）。

    - scores が空、または 0〜10 の整数でない値（小数や bool を含む）がある → ValueError

    >>> enps([10, 10, 10, 10, 7, 7, 7, 3, 3, 3])
    10.0
    >>> enps([9, 8, 6])
    0.0

    ヒント: (推奨者の人数 − 批判者の人数) × 100 / 回答数 の順に計算すると、
    0.3 * 100 = 30.000000000000004 のような浮動小数点の誤差を避けられる。
    """
    raise NotImplementedError("演習1: enps を実装してください")


def favorability(scores: list[int]) -> float:
    """5 段階の設問の「好意的回答率」（4 または 5 と答えた人の割合、%）を返す。

    - scores が空、または 1〜5 の整数でない値がある → ValueError

    >>> favorability([5, 4, 3, 2, 1])
    40.0
    """
    raise NotImplementedError("演習1: favorability を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★☆☆）: 設問ごとの平均・低スコアの設問・期ごとの推移
# ---------------------------------------------------------------------------

def item_means(responses: list[Response]) -> dict[str, float]:
    """設問ごとの平均値を返す（キーは設問名の昇順）。

    - 平均の分母は、その設問に回答した人数（未回答の人は含めない）
    - 1〜5 の整数でない回答がある → ValueError
    - responses が空なら空の dict

    >>> rs = [Response("A", "2026-Q3", items={"成長実感": 4, "心理的安全性": 5}),
    ...       Response("A", "2026-Q3", items={"成長実感": 2})]
    >>> item_means(rs)
    {'心理的安全性': 5.0, '成長実感': 3.0}
    """
    raise NotImplementedError("演習2: item_means を実装してください")


def low_scoring_items(responses: list[Response], threshold: float = 3.5) -> list[tuple[str, float]]:
    """平均値が threshold 未満の設問を (設問名, 平均値) のリストで返す。

    並び順は平均値の昇順（最も低い設問が先頭）。平均値が同じなら設問名の昇順。
    """
    raise NotImplementedError("演習2: low_scoring_items を実装してください")


def period_trend(responses: list[Response], metric: str = "enps") -> list[tuple[str, float, float | None]]:
    """期ごとの値と前期からの変化を (期, 値, 前期からの差) のリストで返す（期の昇順）。

    - metric == "enps" なら、その期の eNPS（enps が None の回答は除く）
    - それ以外なら、metric という名前の設問の、その期の平均値
    - 該当するデータが 1 件もない期は結果に含めない
    - 最初の期の「前期からの差」は None

    >>> rs = [Response("A", "2026-Q2", enps=10), Response("A", "2026-Q1", enps=5),
    ...       Response("A", "2026-Q2", enps=6)]
    >>> period_trend(rs)
    [('2026-Q1', -100.0, None), ('2026-Q2', 0.0, 100.0)]
    """
    raise NotImplementedError("演習2: period_trend を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: 匿名性を守る集計（小さなグループの秘匿と二次秘匿）
# ---------------------------------------------------------------------------

def suppress_small_groups(counts: dict[str, int], min_responses: int = 5) -> set[str]:
    """結果を公開しない（秘匿する）グループ名の集合を返す。

    counts はグループ名 → 回答数。組織全体の集計は別に公開されている前提とする。

    1. 一次秘匿: 回答数が 1 以上 min_responses 未満のグループを秘匿する
       （回答数 0 のグループは公開する情報がないので対象外）
    2. 二次秘匿: 全体の数値が公開されていると、「全体 − 公開したグループ」で
       秘匿したグループの合計が逆算できてしまう。そこで、秘匿したグループの回答数の合計が
       min_responses 未満である間は、公開予定のグループのうち回答数が最も少ないもの
       （同数なら名前の昇順で先のもの）を秘匿に加える。加えられるグループがなくなったら終わり。
       秘匿するグループが 1 つもなければ、二次秘匿は行わない。

    - min_responses が 1 未満、または負の回答数がある → ValueError

    >>> sorted(suppress_small_groups({"A": 12, "B": 3, "C": 8}))
    ['B', 'C']
    >>> sorted(suppress_small_groups({"A": 12, "B": 3, "C": 4}))
    ['B', 'C']
    >>> suppress_small_groups({"A": 5, "B": 7})
    set()
    """
    raise NotImplementedError("演習3: suppress_small_groups を実装してください")


def team_report(
    responses: list[Response], period: str, min_responses: int = 5
) -> dict[str, TeamSummary | None]:
    """指定した期の、チームごとと組織全体の集計を返す。

    - 対象は period が一致する回答だけ
    - キーはチーム名（昇順）と、最後に ENTIRE_ORG（"全体"）
    - suppress_small_groups で秘匿対象になったチームの値は None
    - 組織全体の回答数が min_responses 未満なら、"全体" の値も None
    - チーム名に "全体" が使われていたら ValueError

    ヒント: チームごとに Response を分けてから、TeamSummary(n, enps, item_means) を作る。
    """
    raise NotImplementedError("演習3: team_report を実装してください")
