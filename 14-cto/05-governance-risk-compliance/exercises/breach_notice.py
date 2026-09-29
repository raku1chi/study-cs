"""14.5 ガバナンス・リスク・コンプライアンスと法務 — 演習（breach_notice.py）

【教育用・簡略化】個人データの漏えい等が起きたときに、日本の個人情報保護法（APPI）と
EU の GDPR の報告・通知の義務と期限の「目安」を整理する判定ツールを作ります。

!!! これは法的助言ではありません !!!
制度を学ぶための簡略化したモデルです。実際のインシデントでは、個人情報保護委員会の
ガイドライン・Q&A、各国の監督機関の資料などの一次資料を確認し、弁護士に相談してください。
記述は 2026 年時点の制度に基づきます。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。
データ構造と validate は完成しています。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 14.5
    python3 -m unittest -v test_breach_notice   # このディレクトリで直接

このモデルが扱う制度の要点（本文 3.4 節・3.5 節）:
    APPI（個人情報保護法。2022 年 4 月施行の改正で義務化）
      - 報告対象: ①要配慮個人情報 ②財産的被害のおそれ ③不正の目的によるおそれ
                  ④本人の数が 1,000 人を超える（いずれも「おそれ」を含む）
      - 高度な暗号化などの措置が講じられていれば報告対象にならない
      - 速報: 速やかに（目安は知った時点から概ね 3〜5 日以内）
      - 確報: 知った日を 1 日目として 30 日以内（③は 60 日以内）。末日が土日・祝日・
              年末年始（12/29〜1/3）なら翌開庁日（ガイドラインの文言は「その翌日」。このモデルは
              翌日も閉庁日ならさらに後ろにずらすものとして簡略化している）
      - 本人への通知: 状況に応じて速やかに
    GDPR
      - 管理者（controller）: 侵害を記録する。リスクがあれば監督機関へ、可能なら認識から
        72 時間以内に通知。高いリスクがあれば本人へ不当な遅滞なく通知
        （暗号化などでデータが理解できない状態なら本人への通知は不要）
      - 処理者（processor）: 管理者へ不当な遅滞なく通知
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone  # noqa: F401  time は assess で使えます
from typing import Collection

JST = timezone(timedelta(hours=9), "JST")
GDPR_ROLES = ("controller", "processor")
GDPR_RISKS = ("unlikely", "risk", "high")


@dataclass(frozen=True)
class Incident:
    """インシデントの属性（この型は完成しています）。"""

    aware_at: datetime                 # 事業者（いずれかの部署）が事態を知った日時。タイムゾーン付き
    affected_people: int               # 影響を受けた（おそれを含む）本人の数
    sensitive: bool = False            # 要配慮個人情報を含む
    financial_risk: bool = False       # 不正利用で財産的被害が生じるおそれ（クレジットカード番号など）
    malicious: bool = False            # 不正の目的をもって行われたおそれ（不正アクセス、内部不正など）
    high_grade_encryption: bool = False  # 高度な暗号化等の措置あり（鍵は漏えいしていない）
    appi_applies: bool = True          # 日本の個人情報保護法の対象となる個人データを含む
    eu_data_subjects: bool = False     # GDPR の対象となる EU の本人のデータを含む
    gdpr_role: str = "controller"      # GDPR 上の立場: "controller"（管理者）/ "processor"（処理者）
    gdpr_risk: str = "risk"            # 管理者によるリスク評価: "unlikely" / "risk" / "high"


@dataclass(frozen=True)
class Obligation:
    """1 つの義務（この型は完成しています）。"""

    regime: str              # "APPI" / "GDPR"
    action: str              # 何をするか
    due: datetime | None     # 期限（目安を含む）。「速やかに」など日時で定まらないものは None
    note: str                # 補足


def validate(incident: Incident) -> None:
    """入力を検証する（完成しています）。不正なら ValueError。"""
    if incident.aware_at.tzinfo is None or incident.aware_at.utcoffset() is None:
        raise ValueError("aware_at はタイムゾーン付きの datetime にしてください")
    if incident.affected_people < 0:
        raise ValueError("affected_people は 0 以上です")
    if incident.gdpr_role not in GDPR_ROLES:
        raise ValueError(f"gdpr_role は {GDPR_ROLES} のいずれかです: {incident.gdpr_role!r}")
    if incident.gdpr_risk not in GDPR_RISKS:
        raise ValueError(f"gdpr_risk は {GDPR_RISKS} のいずれかです: {incident.gdpr_risk!r}")


# ---------------------------------------------------------------------------
# 演習1（★★☆）: 個人情報保護法の報告対象の判定と、確報の期限
# ---------------------------------------------------------------------------

def appi_triggers(incident: Incident) -> list[str]:
    """個人情報保護委員会への報告対象に当たる類型のラベルを、次の順で返す。

        "要配慮個人情報"（sensitive）
        "財産的被害のおそれ"（financial_risk）
        "不正の目的によるおそれ"（malicious）
        "1,000人超"（affected_people が 1,000 を「超える」とき。1,000 ちょうどは含まない）

    - appi_applies が False、または high_grade_encryption が True なら空リスト。
    - 最初に validate(incident) を呼ぶこと（不正な入力は ValueError）。

    >>> appi_triggers(Incident(datetime(2026, 4, 1, tzinfo=JST), 1000))
    []
    >>> appi_triggers(Incident(datetime(2026, 4, 1, tzinfo=JST), 1001, malicious=True))
    ['不正の目的によるおそれ', '1,000人超']
    """
    raise NotImplementedError("演習1: appi_triggers を実装してください")


def is_closed_day(day: date, holidays: Collection[date] = ()) -> bool:
    """行政機関の閉庁日かどうか（簡略化）: 土曜・日曜、holidays に含まれる日、
    年末年始（12 月 29 日〜1 月 3 日）なら True。

    祝日のカレンダーは年によって変わるので、この関数は持たず、呼び出し側が holidays で渡す。

    >>> is_closed_day(date(2026, 1, 3)), is_closed_day(date(2026, 1, 5))
    (True, False)
    """
    raise NotImplementedError("演習1: is_closed_day を実装してください")


def appi_final_report_due(aware_date: date, malicious: bool, holidays: Collection[date] = ()) -> date:
    """確報の期限日を返す。

    - 知った日（aware_date）を 1 日目として、30 日目（malicious なら 60 日目）が期限。
      つまり aware_date の 29 日後（または 59 日後）。
    - その日が閉庁日（is_closed_day）なら、閉庁日でない日まで 1 日ずつ後ろにずらす。

    >>> appi_final_report_due(date(2026, 4, 1), malicious=False)
    datetime.date(2026, 4, 30)
    >>> appi_final_report_due(date(2026, 4, 1), malicious=True)   # 60 日目は 5/30（土）→ 6/1（月）
    datetime.date(2026, 6, 1)
    """
    raise NotImplementedError("演習1: appi_final_report_due を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: GDPR の義務と、全体の整理
# ---------------------------------------------------------------------------

def gdpr_obligations(incident: Incident) -> list[Obligation]:
    """GDPR 上の義務を、次の順で返す（regime はすべて "GDPR"）。

    - eu_data_subjects が False なら空リスト。
    - gdpr_role が "processor" なら、action が "管理者（controller）へ通知"・due が None の
      義務 1 つだけ。
    - gdpr_role が "controller" なら:
        1. "侵害を記録する"（due None）… リスク評価にかかわらず常に
        2. "監督機関へ通知"（due = aware_at + 72 時間）… gdpr_risk が "risk" か "high" のとき
        3. "本人へ通知"（due None）… gdpr_risk が "high" で、high_grade_encryption が False のとき
    - note は自由（条文や補足を書く）。最初に validate(incident) を呼ぶこと。
    """
    raise NotImplementedError("演習2: gdpr_obligations を実装してください")


def assess(incident: Incident, holidays: Collection[date] = ()) -> list[Obligation]:
    """APPI と GDPR の義務をまとめて返す。順序は APPI の義務 → GDPR の義務。

    APPI（appi_triggers が空でないときだけ。regime は "APPI"）:
        1. "個人情報保護委員会へ速報": due = aware_at を日本時間（JST）に直した日時 + 5 日（目安の上限）
           note には該当した類型のラベルを含める
        2. "個人情報保護委員会へ確報": due = appi_final_report_due(JST での aware_at の日付, malicious,
           holidays) の 23:59:59（JST のタイムゾーン付き）
        3. "本人へ通知": due None
    GDPR: gdpr_obligations(incident) をそのまま続ける。

    日本の制度の日数は日本時間の日付で数える。aware_at が UTC などで与えられても、
    JST に変換してから日付を取り出すこと（例: 2026-03-31 16:00 UTC は JST では 4 月 1 日）。
    """
    raise NotImplementedError("演習2: assess を実装してください")
