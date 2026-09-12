"""Steel material grades and properties (AISC / ASTM)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from composite_beam.units import ES_MPA, ksi_to_mpa, mm_to_in

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@dataclass
class SteelGrade:
    """Steel grade with optional flange-thickness-dependent Fy/Fu."""

    key: str
    name: str
    Fy_ksi: float
    Fu_ksi: float
    notes: str = ""

    @property
    def Fy_MPa(self) -> float:
        return ksi_to_mpa(self.Fy_ksi)

    @property
    def Fu_MPa(self) -> float:
        return ksi_to_mpa(self.Fu_ksi)


def load_steel_grades(path: Optional[Path] = None) -> dict[str, dict]:
    """Load steel grade catalog from JSON."""
    p = path or (DATA_DIR / "steel_grades.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def resolve_steel_grade(
    grade_key: str,
    tf_mm: Optional[float] = None,
    Fy_override_MPa: Optional[float] = None,
    Fu_override_MPa: Optional[float] = None,
    catalog: Optional[dict] = None,
) -> SteelGrade:
    """
    Resolve Fy/Fu for a grade, applying flange-thickness rules where applicable
    (e.g. A36 plates > 8 in). Manual overrides take precedence.
    """
    catalog = catalog or load_steel_grades()
    if grade_key not in catalog and Fy_override_MPa is None:
        raise KeyError(f"Unknown steel grade: {grade_key}")

    if Fy_override_MPa is not None:
        Fu = Fu_override_MPa if Fu_override_MPa is not None else Fy_override_MPa * 1.3
        return SteelGrade(
            key="custom",
            name="Custom",
            Fy_ksi=Fy_override_MPa / 6.894757293168,
            Fu_ksi=Fu / 6.894757293168,
            notes="User override",
        )

    entry = catalog[grade_key]
    Fy_ksi = float(entry["Fy_default_ksi"])
    Fu_ksi = float(entry["Fu_default_ksi"])
    rules = entry.get("flange_thickness_rules") or []
    if rules and tf_mm is not None:
        tf_in = mm_to_in(tf_mm)
        for rule in rules:
            tmax = rule.get("tf_max_in")
            if tmax is None or tf_in <= tmax:
                Fy_ksi = float(rule["Fy_ksi"])
                Fu_ksi = float(rule["Fu_ksi"])
                break

    if Fu_override_MPa is not None:
        Fu_ksi = Fu_override_MPa / 6.894757293168

    return SteelGrade(
        key=grade_key,
        name=entry["name"],
        Fy_ksi=Fy_ksi,
        Fu_ksi=Fu_ksi,
        notes=entry.get("notes", ""),
    )


@dataclass
class SteelMaterial:
    """Steel material for design (SI primary)."""

    Fy_MPa: float
    Fu_MPa: float
    Es_MPa: float = ES_MPA
    grade: str = "A992"

    @classmethod
    def from_grade(
        cls,
        grade_key: str,
        tf_mm: Optional[float] = None,
        Fy_override_MPa: Optional[float] = None,
        Fu_override_MPa: Optional[float] = None,
    ) -> "SteelMaterial":
        g = resolve_steel_grade(grade_key, tf_mm, Fy_override_MPa, Fu_override_MPa)
        return cls(Fy_MPa=g.Fy_MPa, Fu_MPa=g.Fu_MPa, grade=g.key)
