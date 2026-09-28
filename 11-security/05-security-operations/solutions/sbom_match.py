"""11.5 セキュリティ運用とサプライチェーン — 解答例（sbom_match）

演習の仕様は exercises/sbom_match.py の docstring を参照してください。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_VERSION_RE = re.compile(
    r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-.]?(alpha|beta|rc|pre|dev)\.?(\d*))?",
    re.IGNORECASE,
)
_STAGE_ORDER = {"alpha": 0, "dev": 0, "pre": 0, "beta": 1, "rc": 2}
_CONSTRAINT_RE = re.compile(r"\s*(>=|<=|==|!=|>|<)\s*(.+)")


# ---------------------------------------------------------------------------
# 演習1: バージョンの比較
# ---------------------------------------------------------------------------

def parse_version(text: str) -> tuple[int, int, int, tuple[int, int, int]]:
    m = _VERSION_RE.fullmatch(text.strip())
    if not m:
        raise ValueError(f"バージョンとして解釈できません: {text!r}")
    major = int(m.group(1))
    minor = int(m.group(2) or 0)
    patch = int(m.group(3) or 0)
    stage = m.group(4)
    if stage:
        # プレリリース（1.0.0-rc1 など）は同じ番号の正式版より小さい
        pre = (0, _STAGE_ORDER[stage.lower()], int(m.group(5)) if m.group(5) else 0)
    else:
        pre = (1, 0, 0)
    return (major, minor, patch, pre)


def compare_versions(a: str, b: str) -> int:
    va, vb = parse_version(a), parse_version(b)
    return (va > vb) - (va < vb)


def satisfies(version: str, constraint: str) -> bool:
    """version が constraint（">=1.0.0,<1.4.2" のようにカンマ区切りの AND）を満たすか。"""
    if not constraint.strip():
        return True
    for part in constraint.split(","):
        m = _CONSTRAINT_RE.fullmatch(part)
        if not m:
            raise ValueError(f"制約の構文が不正です: {part!r}")
        op, target = m.group(1), m.group(2).strip()
        c = compare_versions(version, target)
        ok = {
            ">=": c >= 0, "<=": c <= 0, ">": c > 0,
            "<": c < 0, "==": c == 0, "!=": c != 0,
        }[op]
        if not ok:
            return False
    return True


# ---------------------------------------------------------------------------
# 演習2: CycloneDX SBOM と脆弱性の突き合わせ
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Component:
    name: str
    version: str
    purl: str = ""


@dataclass(frozen=True)
class Advisory:
    id: str
    package: str
    affected: str  # 影響を受けるバージョンの制約
    fixed: str  # 修正されたバージョン（なければ ""）
    severity: str


@dataclass(frozen=True)
class Finding:
    component: str
    version: str
    advisory_id: str
    severity: str
    fixed: str


def parse_cyclonedx(data: str | dict) -> list[Component]:
    """CycloneDX（簡略版）の JSON からコンポーネントの一覧を取り出す。"""
    doc = json.loads(data) if isinstance(data, str) else data
    if doc.get("bomFormat") != "CycloneDX":
        raise ValueError("CycloneDX 形式ではありません")
    components: list[Component] = []
    for c in doc.get("components", []):
        name, version = c.get("name"), c.get("version")
        if not name or not version:
            raise ValueError(f"name か version が欠けています: {c!r}")
        components.append(Component(name, str(version), c.get("purl", "")))
    return components


def load_advisories(rows: list[dict]) -> list[Advisory]:
    return [
        Advisory(r["id"], r["package"], r.get("affected", ""), r.get("fixed", ""), r.get("severity", "unknown"))
        for r in rows
    ]


def match(components: list[Component], advisories: list[Advisory]) -> list[Finding]:
    """各コンポーネントに該当する脆弱性を見つける。

    脆弱性 ID → コンポーネント名 の順で安定にソートして返す。
    """
    findings: list[Finding] = []
    by_package: dict[str, list[Advisory]] = {}
    for adv in advisories:
        by_package.setdefault(adv.package, []).append(adv)
    for comp in components:
        for adv in by_package.get(comp.name, []):
            if satisfies(comp.version, adv.affected):
                findings.append(Finding(comp.name, comp.version, adv.id, adv.severity, adv.fixed))
    findings.sort(key=lambda f: (f.advisory_id, f.component))
    return findings


def scan_sbom_file(path: str | Path, advisories: list[Advisory]) -> list[Finding]:
    text = Path(path).read_text(encoding="utf-8")
    return match(parse_cyclonedx(text), advisories)
