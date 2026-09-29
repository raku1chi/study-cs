"""12.5 AIシステムの本番運用 — 演習2: モデルレジストリ（解答例）

演習の仕様は exercises/model_registry.py の docstring を参照してください。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Callable

NONE, STAGING, PRODUCTION, ARCHIVED = "None", "Staging", "Production", "Archived"
STAGES = (NONE, STAGING, PRODUCTION, ARCHIVED)
ALLOWED_TRANSITIONS = {
    (NONE, STAGING),
    (NONE, ARCHIVED),
    (STAGING, PRODUCTION),
    (STAGING, ARCHIVED),
    (PRODUCTION, ARCHIVED),
}


class RegistryError(Exception):
    pass


class TransitionError(RegistryError):
    pass


class GateError(RegistryError):
    def __init__(self, reasons: list[str]) -> None:
        super().__init__("昇格の条件を満たしていません: " + " / ".join(reasons))
        self.reasons = reasons


@dataclass(frozen=True)
class MetricGate:
    metric: str
    op: str
    threshold: float

    def __post_init__(self) -> None:
        if self.op not in (">=", "<="):
            raise ValueError(f"op は '>=' か '<=': {self.op!r}")

    def check(self, metrics: dict[str, float]) -> str | None:
        if self.metric not in metrics:
            return f"{self.metric} が記録されていません"
        value = metrics[self.metric]
        ok = value >= self.threshold if self.op == ">=" else value <= self.threshold
        return None if ok else f"{self.metric}={value} は {self.op} {self.threshold} を満たしません"


@dataclass(frozen=True)
class ChampionCheck:
    metric: str
    higher_is_better: bool = True
    tolerance: float = 0.0


@dataclass(frozen=True)
class PromotionPolicy:
    gates: tuple[MetricGate, ...] = ()
    required_approvals: int = 1
    champion_checks: tuple[ChampionCheck, ...] = ()


@dataclass
class ModelVersion:
    name: str
    version: int
    artifact_uri: str
    metrics: dict[str, float]
    params: dict[str, object]
    data_version: str
    code_version: str
    created_by: str
    created_at: dt.datetime
    stage: str = NONE
    approvals: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class AuditEvent:
    at: dt.datetime
    actor: str
    action: str
    name: str
    version: int | None
    detail: str = ""


class ModelRegistry:
    def __init__(self, *, clock: Callable[[], dt.datetime] | None = None) -> None:
        self._clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))
        self._models: dict[str, list[ModelVersion]] = {}
        self._policies: dict[str, PromotionPolicy] = {}
        # 本番から外された版の履歴（ロールバック先）。新しいものほど末尾
        self._previous_production: dict[str, list[int]] = {}
        self.audit_log: list[AuditEvent] = []

    def _audit(self, actor: str, action: str, name: str, version: int | None, detail: str = "") -> None:
        self.audit_log.append(AuditEvent(self._clock(), actor, action, name, version, detail))

    # --- 登録と参照 -------------------------------------------------------------
    def register(
        self,
        name: str,
        artifact_uri: str,
        *,
        metrics: dict[str, float],
        data_version: str,
        code_version: str,
        created_by: str,
        params: dict[str, object] | None = None,
    ) -> ModelVersion:
        # 再現性のために「データ・コード・モデル・設定」の版を必ず記録させる
        for label, value in (("name", name), ("artifact_uri", artifact_uri), ("data_version", data_version),
                             ("code_version", code_version), ("created_by", created_by)):
            if not value:
                raise ValueError(f"{label} は必須です")
        versions = self._models.setdefault(name, [])
        mv = ModelVersion(
            name=name,
            version=len(versions) + 1,
            artifact_uri=artifact_uri,
            metrics=dict(metrics),
            params=dict(params or {}),
            data_version=data_version,
            code_version=code_version,
            created_by=created_by,
            created_at=self._clock(),
        )
        versions.append(mv)
        self._audit(created_by, "register", name, mv.version, artifact_uri)
        return mv

    def get(self, name: str, version: int) -> ModelVersion:
        versions = self._models.get(name, [])
        if not 1 <= version <= len(versions):
            raise RegistryError(f"{name} の版 {version} はありません")
        return versions[version - 1]

    def versions(self, name: str) -> list[ModelVersion]:
        return list(self._models.get(name, []))

    def production(self, name: str) -> ModelVersion | None:
        for mv in self._models.get(name, []):
            if mv.stage == PRODUCTION:
                return mv
        return None

    # --- 昇格の方針と承認 ---------------------------------------------------------
    def set_policy(self, name: str, policy: PromotionPolicy) -> None:
        if policy.required_approvals < 0:
            raise ValueError("required_approvals は 0 以上")
        self._policies[name] = policy

    def approve(self, name: str, version: int, *, approver: str) -> None:
        mv = self.get(name, version)
        if approver == mv.created_by:
            # 作った本人の承認は数えない（職務の分離、いわゆる 4 つの目の原則）
            raise RegistryError("自分が登録した版は承認できません")
        if mv.stage not in (NONE, STAGING):
            raise RegistryError(f"{mv.stage} の版は承認できません")
        mv.approvals.add(approver)
        self._audit(approver, "approve", name, version)

    def _promotion_failures(self, mv: ModelVersion) -> list[str]:
        policy = self._policies.get(mv.name, PromotionPolicy())
        reasons = [r for r in (g.check(mv.metrics) for g in policy.gates) if r]
        if len(mv.approvals) < policy.required_approvals:
            reasons.append(f"承認が {len(mv.approvals)} 件（必要なのは {policy.required_approvals} 件）")
        champion = self.production(mv.name)
        if champion is not None:
            for check in policy.champion_checks:
                if check.metric not in mv.metrics or check.metric not in champion.metrics:
                    reasons.append(f"{check.metric} を現行の本番と比較できません")
                    continue
                new, old = mv.metrics[check.metric], champion.metrics[check.metric]
                worse_by = (old - new) if check.higher_is_better else (new - old)
                if worse_by > check.tolerance:
                    reasons.append(
                        f"{check.metric} が現行の本番（v{champion.version}: {old}）より悪化しています（{new}）"
                    )
        return reasons

    # --- 状態の遷移とロールバック ----------------------------------------------------
    def transition(self, name: str, version: int, to_stage: str, *, actor: str) -> ModelVersion:
        mv = self.get(name, version)
        if to_stage not in STAGES:
            raise TransitionError(f"未知のステージです: {to_stage}")
        if (mv.stage, to_stage) not in ALLOWED_TRANSITIONS:
            raise TransitionError(f"{mv.stage} → {to_stage} は許可されていません")
        if to_stage == PRODUCTION:
            reasons = self._promotion_failures(mv)
            if reasons:
                self._audit(actor, "promotion_rejected", name, version, " / ".join(reasons))
                raise GateError(reasons)
            current = self.production(name)
            if current is not None:
                # 本番は常に 1 つ。入れ替えた版はロールバック先として覚えておく
                current.stage = ARCHIVED
                self._previous_production.setdefault(name, []).append(current.version)
                self._audit(actor, "archive", name, current.version, f"v{version} の昇格に伴う")
        previous_stage = mv.stage
        mv.stage = to_stage
        self._audit(actor, "transition", name, version, f"{previous_stage} → {to_stage}")
        return mv

    def rollback(self, name: str, *, actor: str) -> ModelVersion:
        history = self._previous_production.get(name, [])
        if not history:
            raise RegistryError(f"{name} にはロールバック先がありません")
        target = self.get(name, history.pop())
        current = self.production(name)
        if current is not None:
            current.stage = ARCHIVED  # 問題のあった版。ロールバック先の履歴には戻さない
        # 障害対応では速さが重要。以前に本番で使われていた版なので、昇格の条件は再確認しない
        target.stage = PRODUCTION
        detail = f"v{current.version} → v{target.version}" if current else f"→ v{target.version}"
        self._audit(actor, "rollback", name, target.version, detail)
        return target
