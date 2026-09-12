"""AISC Chapter H interaction (flexure + axial) with Chapter I composite notes.

H1-1a / H1-1b are numerically the same in AISC 360-16 and 360-22.
Composite members subject to axial + flexure are covered by Chapter I
(I1, I2 encased/filled, I5/I6 combined forces). This tool applies H1 to the
*steel section* (or to the available flexural strengths already computed) and
flags that a full I5/I6 composite beam-column is not implemented.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from composite_beam.sections.w_shapes import WShape
from composite_beam.units import ES_MPA


@dataclass
class InteractionResult:
    """Chapter H1 interaction check."""

    Pr_kN: float
    Pc_kN: float
    Pn_kN: float
    Mrx_kNm: float
    Mcx_kNm: float
    Mry_kNm: float
    Mcy_kNm: float
    ratio_P: float
    ratio_Mx: float
    ratio_My: float
    DCR: float
    equation: str  # H1-1a or H1-1b
    passes: bool
    KL_r: float
    Fcr_MPa: float
    notes: list[str] = field(default_factory=list)


def compressive_strength_E3(
    shape: WShape,
    Fy_MPa: float,
    L_mm: float,
    K: float = 1.0,
    phi_c: float = 0.90,
    E_MPa: float = ES_MPA,
    r_mm: Optional[float] = None,
) -> tuple[float, float, float, float, list[str]]:
    """
    Available compressive strength φc Pn — AISC E3 flexural buckling.

    Uses the governing (minimum) radius of gyration unless r_mm is supplied.
    Returns Pn_kN, Pc=φcPn_kN, Fcr_MPa, KL/r, notes.
    """
    notes = [
        "AISC 360-22 §E3 (360-16 §E3 identical form) flexural buckling of the steel section.",
    ]
    r = r_mm if r_mm is not None else min(shape.rx_mm, shape.ry_mm)
    KL = K * L_mm
    slenderness = KL / r if r > 0 else 1e6
    notes.append(f"KL/r = {K:.2f}×{L_mm:.0f}/{r:.1f} = {slenderness:.1f}")
    limit = 4.71 * (E_MPa / Fy_MPa) ** 0.5
    Fe = (math.pi**2) * E_MPa / (slenderness**2) if slenderness > 0 else Fy_MPa
    if slenderness <= limit:
        Fcr = (0.658 ** (Fy_MPa / Fe)) * Fy_MPa if Fe > 0 else Fy_MPa
        notes.append(f"KL/r ≤ 4.71√(E/Fy)={limit:.1f} → inelastic E3-2; Fe={Fe:.1f} MPa")
    else:
        Fcr = 0.877 * Fe
        notes.append(f"KL/r > 4.71√(E/Fy) → elastic E3-3; Fe={Fe:.1f} MPa")
    Pn = Fcr * shape.A_mm2 / 1000.0  # kN
    Pc = phi_c * Pn
    notes.append(f"Fcr={Fcr:.1f} MPa; Pn={Pn:.1f} kN; φc Pn={Pc:.1f} kN (φc={phi_c})")
    return Pn, Pc, Fcr, slenderness, notes


def chapter_h_interaction(
    Pr_kN: float,
    Pc_kN: float,
    Mrx_kNm: float,
    Mcx_kNm: float,
    Mry_kNm: float = 0.0,
    Mcy_kNm: float = 1.0,
    Pn_kN: float = 0.0,
    KL_r: float = 0.0,
    Fcr_MPa: float = 0.0,
    extra_notes: Optional[list[str]] = None,
) -> InteractionResult:
    """
    AISC H1-1a / H1-1b.

      If Pr/Pc ≥ 0.2:  Pr/Pc + (8/9)(Mrx/Mcx + Mry/Mcy) ≤ 1.0   (H1-1a)
      If Pr/Pc <  0.2:  Pr/(2 Pc) + (Mrx/Mcx + Mry/Mcy) ≤ 1.0   (H1-1b)

    Use absolute values of required moments. Mcx/Mcy are available strengths.
    """
    notes = [
        "AISC 360-22 §H1.1 (360-16 §H1.1 — interaction equations unchanged).",
        "Chapter I note: composite *beam-columns* (encased I2 / filled I2 / I5–I6) "
        "are not designed here. H1 is applied to the steel available strengths "
        "(φc Pn from E3, φb Mn from I3 sagging and/or F hogging). Conservative "
        "for incidental axial in a floor beam; not a substitute for I5/I6.",
    ]
    if extra_notes:
        notes.extend(extra_notes)

    Pc_eff = Pc_kN if Pc_kN > 1e-9 else 1e-9
    Mcx_eff = Mcx_kNm if abs(Mcx_kNm) > 1e-9 else 1e-9
    Mcy_eff = Mcy_kNm if abs(Mcy_kNm) > 1e-9 else 1e-9
    ratio_P = abs(Pr_kN) / Pc_eff
    ratio_Mx = abs(Mrx_kNm) / abs(Mcx_eff)
    ratio_My = abs(Mry_kNm) / abs(Mcy_eff)

    if ratio_P >= 0.2:
        DCR = ratio_P + (8.0 / 9.0) * (ratio_Mx + ratio_My)
        eq = "H1-1a"
        notes.append(
            f"Pr/Pc={ratio_P:.3f} ≥ 0.2 → H1-1a: "
            f"{ratio_P:.3f} + (8/9)({ratio_Mx:.3f}+{ratio_My:.3f}) = {DCR:.3f}"
        )
    else:
        DCR = ratio_P / 2.0 + (ratio_Mx + ratio_My)
        eq = "H1-1b"
        notes.append(
            f"Pr/Pc={ratio_P:.3f} < 0.2 → H1-1b: "
            f"{ratio_P:.3f}/2 + ({ratio_Mx:.3f}+{ratio_My:.3f}) = {DCR:.3f}"
        )

    return InteractionResult(
        Pr_kN=Pr_kN,
        Pc_kN=Pc_kN,
        Pn_kN=Pn_kN,
        Mrx_kNm=Mrx_kNm,
        Mcx_kNm=Mcx_kNm,
        Mry_kNm=Mry_kNm,
        Mcy_kNm=Mcy_kNm,
        ratio_P=ratio_P,
        ratio_Mx=ratio_Mx,
        ratio_My=ratio_My,
        DCR=DCR,
        equation=eq,
        passes=DCR <= 1.0 + 1e-9,
        KL_r=KL_r,
        Fcr_MPa=Fcr_MPa,
        notes=notes,
    )
