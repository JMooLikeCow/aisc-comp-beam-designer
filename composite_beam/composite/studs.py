"""Shear stud strength Qn per AISC 360-22 §I8 (Rg, Rp, deck orientation, diam ≤ 2.5 tf)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from composite_beam.composite.slab import DeckOrientation, SlabConfig
from composite_beam.units import MM_PER_IN


class StudGoverning(str, Enum):
    STEEL_SHEAR = "steel_shear"
    CONCRETE_CRUSHING = "concrete_crushing"


@dataclass
class StudConfig:
    """Headed stud geometry."""

    diameter_mm: float = 19.05  # 3/4 in
    Fu_stud_MPa: float = 448.0  # ~65 ksi typical
    length_mm: float = 101.6  # 4 in after weld (typical)
    Rg: Optional[float] = None  # override
    Rp: Optional[float] = None


@dataclass
class StudQnResult:
    """Nominal stud strength and governing limit state — AISC I8."""

    Qn_kN: float
    Qn_steel_kN: float
    Qn_concrete_kN: float
    governing: StudGoverning
    Rg: float
    Rp: float
    Asc_mm2: float
    diameter_ok: bool  # I8: ds ≤ 2.5 tf
    notes: list[str]


def default_Rg_Rp(
    orientation: DeckOrientation,
    hr_mm: float,
    n_studs_per_rib: int = 1,
) -> tuple[float, float]:
    """
    AISC 360-22 Table I8.1 — Rg and Rp.

    No deck (solid): Rg = 1.0, Rp = 1.0
    Deck parallel: Rg = 1.0, Rp = 0.75
    Deck perpendicular:
      hr ≤ 1.5 in: Rg = 1.0
      hr > 1.5 in: Rg = 0.85 / 0.70 / 0.60 for 1 / 2 / ≥3 studs per rib
      Rp = 0.75 typical (e_mid-ht ≥ 2 in); 0.60 if e_mid-ht < 2 in (not auto-detected)
    """
    hr_in = hr_mm / MM_PER_IN
    if orientation == DeckOrientation.NONE:
        return 1.0, 1.0
    if orientation == DeckOrientation.PARALLEL:
        return 1.0, 0.75
    # Perpendicular
    if hr_in <= 1.5:
        Rg = 1.0
    else:
        if n_studs_per_rib <= 1:
            Rg = 0.85
        elif n_studs_per_rib == 2:
            Rg = 0.70
        else:
            Rg = 0.60
    Rp = 0.75
    return Rg, Rp


def stud_Qn(
    stud: StudConfig,
    slab: SlabConfig,
    tf_mm: float,
    Ec_MPa: float,
    n_studs_per_rib: int = 1,
) -> StudQnResult:
    """
    Nominal shear strength of one stud — AISC 360-22 §I8.2a Eq. I8-1:

      Qn = 0.5 * Asc * √(f'c * Ec)  ≤  Rg * Rp * Asc * Fu

    Also check I8: stud diameter shall not exceed 2.5 × flange thickness.
    """
    notes: list[str] = [
        "AISC 360-22 §I8.2a Eq. I8-1: Qn = min(0.5 Asc √(f'c Ec), Rg Rp Asc Fu)",
        "AISC 360-22 §I8: stud diameter ≤ 2.5 tf when welded to flange.",
    ]
    Asc = 0.25 * math.pi * stud.diameter_mm**2
    Rg, Rp = default_Rg_Rp(slab.orientation, slab.hr_mm, n_studs_per_rib)
    if stud.Rg is not None:
        Rg = stud.Rg
        notes.append(f"Rg override = {Rg}")
    if stud.Rp is not None:
        Rp = stud.Rp
        notes.append(f"Rp override = {Rp}")

    Qn_conc_N = 0.5 * Asc * (slab.fc_MPa * Ec_MPa) ** 0.5
    Qn_steel_N = Rg * Rp * Asc * stud.Fu_stud_MPa

    Qn_conc_kN = Qn_conc_N / 1000.0
    Qn_steel_kN = Qn_steel_N / 1000.0

    if Qn_steel_kN <= Qn_conc_kN:
        governing = StudGoverning.STEEL_SHEAR
        Qn = Qn_steel_kN
    else:
        governing = StudGoverning.CONCRETE_CRUSHING
        Qn = Qn_conc_kN

    diam_ok = stud.diameter_mm <= 2.5 * tf_mm
    notes.append(f"Asc = {Asc:.1f} mm²; Rg={Rg}, Rp={Rp}")
    notes.append(
        f"Qn,conc={Qn_conc_kN:.2f} kN; Qn,steel={Qn_steel_kN:.2f} kN → governing: {governing.value}"
    )
    notes.append(
        f"ds={stud.diameter_mm:.2f} mm vs 2.5 tf={2.5 * tf_mm:.2f} mm → "
        f"{'OK' if diam_ok else 'NG (I8 diameter limit)'}"
    )
    notes.append(f"Deck orientation: {slab.orientation.value}")

    return StudQnResult(
        Qn_kN=Qn,
        Qn_steel_kN=Qn_steel_kN,
        Qn_concrete_kN=Qn_conc_kN,
        governing=governing,
        Rg=Rg,
        Rp=Rp,
        Asc_mm2=Asc,
        diameter_ok=diam_ok,
        notes=notes,
    )
