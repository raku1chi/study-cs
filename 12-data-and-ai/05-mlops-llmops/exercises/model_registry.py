"""12.5 AIシステムの本番運用 — 演習2: モデルレジストリ（★★☆）

学習したモデルの「版」を管理し、本番への昇格を統制する仕組みを作ります。

    - 版ごとに、成果物の場所・評価指標・学習に使ったデータの版・コードの版・設定・作成者を記録する
      （「データ ＋ コード ＋ 設定 ＋ モデル」がそろって初めて再現できる）
    - ステージの遷移: None → Staging → Production → Archived（許可された遷移だけ）
    - 本番への昇格の条件（ゲート）: 指標の閾値、承認の数（作成者本人の承認は数えない）、
      現行の本番モデル（チャンピオン）より悪化していないこと
    - 本番は常に 1 つ。障害時には、1 つ前の本番の版へすぐにロールバックできる
    - すべての操作を監査ログに記録する（時計は注入できる）

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 12.5
このディレクトリで直接実行する場合:
    python3 -m unittest -v test_model_registry

参考: MLflow などの実際のレジストリにも同様の仕組みがあります（製品によってはステージの代わりに
別名（エイリアス）やタグで管理する方式に移行しています。2026 年時点の各製品のドキュメントを確認してください）。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Callable

NONE, STAGING, PRODUCTION, ARCHIVED = "None", "Staging", "Production", "Archived"
STAGES = (NONE, STAGING, PRODUCTION, ARCHIVED)
# 許可される遷移（これ以外は TransitionError）。Archived からは transition では戻せない（rollback は別）
ALLOWED_TRANSITIONS = {
    (NONE, STAGING),
    (NONE, ARCHIVED),
    (STAGING, PRODUCTION),
    (STAGING, ARCHIVED),
    (PRODUCTION, ARCHIVED),
}


class RegistryError(Exception):
    """レジストリの操作の誤り（実装済み）。"""


class TransitionError(RegistryError):
    """許可されていないステージの遷移（実装済み）。"""


class GateError(RegistryError):
    """本番への昇格の条件を満たさない（実装済み）。reasons に満たさなかった理由のリストを持つ。"""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("昇格の条件を満たしていません: " + " / ".join(reasons))
        self.reasons = reasons


# ---------------------------------------------------------------------------
# 演習2a（★☆☆）: 昇格の条件
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetricGate:
    """指標の閾値。例: MetricGate("auc", ">=", 0.80)、MetricGate("latency_p99_ms", "<=", 50)"""

    metric: str
    op: str  # ">=" または "<="
    threshold: float

    def __post_init__(self) -> None:
        """op が ">=" でも "<=" でもなければ ValueError（実装済み）。"""
        if self.op not in (">=", "<="):
            raise ValueError(f"op は '>=' か '<=': {self.op!r}")

    def check(self, metrics: dict[str, float]) -> str | None:
        """満たせば None、満たさなければ理由の文字列（指標名を含める）。指標が記録されていなければ不合格。"""
        raise NotImplementedError("演習2a: MetricGate.check を実装してください")


@dataclass(frozen=True)
class ChampionCheck:
    """現行の本番モデルとの比較（実装済み）。

    higher_is_better=True なら (本番の値 - 候補の値)、False なら (候補の値 - 本番の値) が
    「悪化の量」で、それが tolerance を超えたら不合格。
    """

    metric: str
    higher_is_better: bool = True
    tolerance: float = 0.0


@dataclass(frozen=True)
class PromotionPolicy:
    """モデル（名前）ごとの昇格の方針（実装済み）。"""

    gates: tuple[MetricGate, ...] = ()
    required_approvals: int = 1
    champion_checks: tuple[ChampionCheck, ...] = ()


@dataclass
class ModelVersion:
    """登録されたモデルの 1 つの版（実装済み）。"""

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
    """監査ログの 1 件（実装済み）。"""

    at: dt.datetime
    actor: str
    action: str  # "register" / "approve" / "transition" / "archive" / "promotion_rejected" / "rollback"
    name: str
    version: int | None
    detail: str = ""


# ---------------------------------------------------------------------------
# 演習2b（★★☆）: レジストリ
# ---------------------------------------------------------------------------

class ModelRegistry:
    """モデルレジストリ。clock は現在時刻を返す関数（テストでは偽の時計を渡す）。"""

    def __init__(self, *, clock: Callable[[], dt.datetime] | None = None) -> None:
        self._clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))
        self._models: dict[str, list[ModelVersion]] = {}
        self._policies: dict[str, PromotionPolicy] = {}
        self._previous_production: dict[str, list[int]] = {}  # ロールバック先の版番号（新しいものが末尾）
        self.audit_log: list[AuditEvent] = []

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
        """新しい版を登録して返す。

        - 版番号はモデル名ごとに 1, 2, 3, …。ステージは "None"、created_at は clock() の値。
        - name・artifact_uri・data_version・code_version・created_by のどれかが空なら ValueError
          （学習に使ったデータとコードの版が分からないモデルは、再現も監査もできない）。
        - metrics と params はコピーして保存する（呼び出し元の辞書の変更に影響されない）。
        - 監査ログに action="register" を記録する（actor は created_by）。
        """
        raise NotImplementedError("演習2b: register を実装してください")

    def get(self, name: str, version: int) -> ModelVersion:
        """版を返す。存在しなければ RegistryError。"""
        raise NotImplementedError("演習2b: get を実装してください")

    def versions(self, name: str) -> list[ModelVersion]:
        """そのモデルの全版（版番号の順）。なければ空のリスト。"""
        raise NotImplementedError("演習2b: versions を実装してください")

    def production(self, name: str) -> ModelVersion | None:
        """現在 Production の版（なければ None）。"""
        raise NotImplementedError("演習2b: production を実装してください")

    def set_policy(self, name: str, policy: PromotionPolicy) -> None:
        """昇格の方針を設定する（未設定なら PromotionPolicy() の既定値）。required_approvals < 0 は ValueError。"""
        raise NotImplementedError("演習2b: set_policy を実装してください")

    def approve(self, name: str, version: int, *, approver: str) -> None:
        """承認を記録する（同じ人の承認は 1 件と数える）。

        - approver が作成者（created_by）と同じなら RegistryError（職務の分離）。
        - ステージが None か Staging でなければ RegistryError。
        - 監査ログに action="approve" を記録する。
        """
        raise NotImplementedError("演習2b: approve を実装してください")

    def transition(self, name: str, version: int, to_stage: str, *, actor: str) -> ModelVersion:
        """ステージを遷移させ、その版を返す。

        1. to_stage が STAGES にない、または (現在のステージ, to_stage) が ALLOWED_TRANSITIONS にないなら TransitionError。
        2. to_stage が Production なら、次の条件をすべて確かめ、満たさないものの理由をまとめて GateError にする
           （監査ログに action="promotion_rejected" を記録し、状態は変えない）:
           - 方針のすべての MetricGate
           - 承認の数 >= required_approvals
           - 現在の本番の版があれば、各 ChampionCheck（どちらかの版に指標がなければ不合格。
             理由に本番の版番号を "v1" のように含める）
           条件を満たしたら、現在の本番の版を Archived にし、その版番号をロールバック先として覚え、
           監査ログに action="archive" を記録する。
        3. ステージを変え、監査ログに action="transition"、detail="Staging → Production" のような文字列を記録する。
        """
        raise NotImplementedError("演習2b: transition を実装してください")

    def rollback(self, name: str, *, actor: str) -> ModelVersion:
        """直前の本番の版（最後に覚えたロールバック先）を Production に戻し、その版を返す。

        - ロールバック先がなければ RegistryError。
        - 現在の本番の版は Archived にする（問題のあった版なので、ロールバック先には加えない）。
          こうすると、ロールバックを繰り返すと v3 → v2 → v1 と順にさかのぼれる。
        - 障害対応では速さが重要で、戻す先は以前に本番で使われていた版なので、昇格の条件は再確認しない。
        - 監査ログに action="rollback" を記録する。
        """
        raise NotImplementedError("演習2b: rollback を実装してください")
