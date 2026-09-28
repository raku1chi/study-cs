"""14.5 ガバナンス・リスク・コンプライアンスと法務 — 解答例（breach_notice.py）

【教育用・簡略化】個人データの漏えい等が起きたときに、日本の個人情報保護法（APPI）と
EU の GDPR の報告・通知の義務と期限の「目安」を整理する判定ツールです。
法的助言ではありません。実際の判断は、個人情報保護委員会のガイドライン・Q&A などの
一次資料を確認し、弁護士に相談してください（2026 年時点の制度に基づく簡略化です）。

演習の仕様は exercises/breach_notice.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Collection

JST = timezone(timedelta(hours=9), "JST")
GDPR_ROLES = ("controller", "processor")
GDPR_RISKS = ("unlikely", "risk", "high")


@dataclass(frozen=True)
class Incident:
    aware_at: datetime
    affected_people: int
    sensitive: bool = False
    financial_risk: bool = False
    malicious: bool = False
    high_grade_encryption: bool = False
    appi_applies: bool = True
    eu_data_subjects: bool = False
    gdpr_role: str = "controller"
    gdpr_risk: str = "risk"


@dataclass(frozen=True)
class Obligation:
    regime: str
    action: str
    due: datetime | None
    note: str


def validate(incident: Incident) -> None:
    if incident.aware_at.tzinfo is None or incident.aware_at.utcoffset() is None:
        raise ValueError("aware_at はタイムゾーン付きの datetime にしてください")
    if incident.affected_people < 0:
        raise ValueError("affected_people は 0 以上です")
    if incident.gdpr_role not in GDPR_ROLES:
        raise ValueError(f"gdpr_role は {GDPR_ROLES} のいずれかです: {incident.gdpr_role!r}")
    if incident.gdpr_risk not in GDPR_RISKS:
        raise ValueError(f"gdpr_risk は {GDPR_RISKS} のいずれかです: {incident.gdpr_risk!r}")


# ---------------------------------------------------------------------------
# 演習1: 個人情報保護法の報告対象の判定と、確報の期限
# ---------------------------------------------------------------------------

def appi_triggers(incident: Incident) -> list[str]:
    validate(incident)
    # 高度な暗号化などの措置が講じられていれば、そもそも報告対象の事態に当たらない
    if not incident.appi_applies or incident.high_grade_encryption:
        return []
    triggers = []
    if incident.sensitive:
        triggers.append("要配慮個人情報")
    if incident.financial_risk:
        triggers.append("財産的被害のおそれ")
    if incident.malicious:
        triggers.append("不正の目的によるおそれ")
    if incident.affected_people > 1000:  # 「1,000 人を超える」なので 1,000 人ちょうどは含まない
        triggers.append("1,000人超")
    return triggers


def is_closed_day(day: date, holidays: Collection[date] = ()) -> bool:
    year_end = (day.month == 12 and day.day >= 29) or (day.month == 1 and day.day <= 3)
    return day.weekday() >= 5 or day in holidays or year_end


def appi_final_report_due(aware_date: date, malicious: bool, holidays: Collection[date] = ()) -> date:
    days = 60 if malicious else 30
    # 知った日を 1 日目として数えるので、30 日目は 29 日後
    due = aware_date + timedelta(days=days - 1)
    # 末日が閉庁日（土日・祝日・年末年始）なら、次の開庁日まで延ばす
    while is_closed_day(due, holidays):
        due += timedelta(days=1)
    return due


# ---------------------------------------------------------------------------
# 演習2: GDPR の義務と、全体の整理
# ---------------------------------------------------------------------------

def gdpr_obligations(incident: Incident) -> list[Obligation]:
    validate(incident)
    if not incident.eu_data_subjects:
        return []
    if incident.gdpr_role == "processor":
        return [Obligation("GDPR", "管理者（controller）へ通知", None,
                           "不当な遅滞なく（第33条2項）。処理委託契約でより短い期限を定めることが多い")]
    obligations = [Obligation("GDPR", "侵害を記録する", None,
                              "事実・影響・対応を文書化する（第33条5項）。通知が不要な場合も必要")]
    if incident.gdpr_risk in ("risk", "high"):
        obligations.append(Obligation("GDPR", "監督機関へ通知", incident.aware_at + timedelta(hours=72),
                                      "不当な遅滞なく、可能なら認識から72時間以内（第33条）。遅れた場合は理由を添える"))
    if incident.gdpr_risk == "high" and not incident.high_grade_encryption:
        obligations.append(Obligation("GDPR", "本人へ通知", None,
                                      "高いリスクがある場合、不当な遅滞なく（第34条）"))
    return obligations


def assess(incident: Incident, holidays: Collection[date] = ()) -> list[Obligation]:
    obligations: list[Obligation] = []
    triggers = appi_triggers(incident)
    if triggers:
        aware_jst = incident.aware_at.astimezone(JST)  # 日本の制度の日付は日本時間で数える
        label = "・".join(triggers)
        obligations.append(Obligation(
            "APPI", "個人情報保護委員会へ速報", aware_jst + timedelta(days=5),
            f"該当: {label}。速やかに（目安: 知った時点から概ね3〜5日以内）。"
            "業種によっては権限の委任を受けた省庁が報告先になる"))
        due = appi_final_report_due(aware_jst.date(), incident.malicious, holidays)
        obligations.append(Obligation(
            "APPI", "個人情報保護委員会へ確報", datetime.combine(due, time(23, 59, 59), tzinfo=JST),
            "知った日を1日目として30日以内（不正の目的のおそれがある場合は60日以内）。"
            "末日が土日・祝日・年末年始なら翌開庁日"))
        obligations.append(Obligation(
            "APPI", "本人へ通知", None,
            "当該事態の状況に応じて速やかに。困難な場合は公表などの代替措置"))
    obligations.extend(gdpr_obligations(incident))
    return obligations


if __name__ == "__main__":
    # 本文 3.4 節の例: 不正アクセスで会員 2,300 人分のデータ（EU の会員を含む）が漏えいしたおそれ
    incident = Incident(
        aware_at=datetime(2026, 3, 5, 18, 30, tzinfo=JST),
        affected_people=2300,
        malicious=True,
        eu_data_subjects=True,
        gdpr_risk="high",
    )
    golden_week = {date(2026, 4, 29), date(2026, 5, 3), date(2026, 5, 4), date(2026, 5, 5), date(2026, 5, 6)}
    print("【教育用・簡略化。法的助言ではありません】")
    for ob in assess(incident, holidays=golden_week):
        due = ob.due.strftime("%Y-%m-%d %H:%M %Z") if ob.due else "期限は日時で定まらない"
        print(f"[{ob.regime}] {ob.action} — {due}\n    {ob.note}")
