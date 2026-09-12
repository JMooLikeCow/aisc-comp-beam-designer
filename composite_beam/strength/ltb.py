"""Lateral-torsional buckling for steel alone (construction) — AISC Chapter F."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import math

from composite_beam.sections.w_shapes import WShape
from composite_beam.units import ES_MPA


@dataclass
class LTBResult:
    """Construction-stage flexural strength (steel alone), AISC F2."""

    Mn_kNm: float
    phiMn_kNm: float
    Mp_kNm: float
    Mr_kNm: float
    Fcr_MPa: float
    Lb_mm: float
    Lp_mm: float
    Lr_mm: float
    Cb: float
    braced_by_deck: bool
    limit_state: str
    passes: bool
    Mu_kNm: float
    DCR: float
    notes: list[str]


def _Lp_mm(ry_mm: float, Fy_MPa: float, E_MPa: float = ES_MPA) -> float:
    """Lp = 1.76 ry √(E/Fy) — AISC F2-5."""
    return 1.76 * ry_mm * (E_MPa / Fy_MPa) ** 0.5


def _Lr_mm(
    shape: WShape,
    Fy_MPa: float,
    E_MPa: float = ES_MPA,
    G_MPa: float = 77_200.0,
) -> float:
    """
    Lr per AISC F2-6:
      Lr = 1.95 rts (E/(0.7 Fy)) √( (J c)/(Sx ho) + √( ((J c)/(Sx ho))^2 + 6.76 (0.7 Fy/E)^2 ) )
    c = 1 for doubly symmetric I-shapes.
    """
    rts = shape.rts_mm
    J = shape.J_mm4
    Sx = shape.Sx_mm3
    ho = shape.ho_mm
    c = 1.0
    jc_sxho = (J * c) / (Sx * ho) if Sx * ho > 0 else 0.0
    inner = jc_sxho**2 + 6.76 * (0.7 * Fy_MPa / E_MPa) ** 2
    return (
        1.95
        * rts
        * (E_MPa / (0.7 * Fy_MPa))
        * math.sqrt(jc_sxho + math.sqrt(inner))
    )


def construction_LTB(
    shape: WShape,
    Fy_MPa: float,
    Lb_mm: float,
    Mu_kNm: float,
    Cb: float = 1.0,
    braced_by_deck: bool = False,
    phi_b: float = 0.90,
    E_MPa: float = ES_MPA,
) -> LTBResult:
    """
    Available flexural strength of steel beam alone under construction loads.

    If braced_by_deck: assume continuous top flange lateral brace → Lb = 0 for LTB
    (deck provides lateral restraint to compression flange when attached).
    Toggle is user-controlled.

    AISC 360-22 §F2 (doubly symmetric compact I-shapes bent about major axis).
    For noncompact, still use F2 as approximation with note (P0 scope).
    """
    notes = [
        "AISC 360-22 Chapter F §F2 — LTB of doubly symmetric compact I-shapes.",
        "Construction combo ≠ occupancy combo (wet concrete + construction live).",
    ]
    Mp = Fy_MPa * shape.Zx_mm3 / 1e6  # kN·m
    # BFY limit Mn ≤ 1.6 My for compact — F2.2; My = Fy Sx
    My = Fy_MPa * shape.Sx_mm3 / 1e6
    Mp = min(Mp, 1.6 * My)

    if braced_by_deck:
        Lb_eff = 0.0
        notes.append("Deck brace toggle ON: compression flange assumed continuously braced (Lb→0).")
    else:
        Lb_eff = Lb_mm
        notes.append(f"Deck brace toggle OFF: unbraced length Lb = {Lb_mm:.0f} mm")

    Lp = _Lp_mm(shape.ry_mm, Fy_MPa, E_MPa)
    Lr = _Lr_mm(shape, Fy_MPa, E_MPa)
    notes.append(f"Lp={Lp:.0f} mm; Lr={Lr:.0f} mm (F2-5, F2-6)")

    # Mr = 0.7 Fy Sx
    Mr = 0.7 * Fy_MPa * shape.Sx_mm3 / 1e6

    if Lb_eff <= Lp:
        Mn = Mp
        Fcr = Fy_MPa
        limit = "yielding_F2-1"
        notes.append("Lb ≤ Lp → Mn = Mp (plastic yielding)")
    elif Lb_eff <= Lr:
        # F2-2 inelastic LTB
        Mn = Cb * (Mp - (Mp - 0.7 * Fy_MPa * shape.Sx_mm3 / 1e6) * (Lb_eff - Lp) / (Lr - Lp))
        Mn = min(Mn, Mp)
        Fcr = Mn * 1e6 / shape.Sx_mm3
        limit = "inelastic_LTB_F2-2"
        notes.append(f"Lp < Lb ≤ Lr → inelastic LTB (Cb={Cb}); Mn={Mn:.1f} kN·m")
    else:
        # F2-3 elastic LTB
        # Fcr = Cb π² E / (Lb/rts)² * √(1 + 0.078 (J c)/(Sx ho) (Lb/rts)²)
        rts = shape.rts_mm
        jterm = (shape.J_mm4 * 1.0) / (shape.Sx_mm3 * shape.ho_mm)
        Lb_rts = Lb_eff / rts if rts > 0 else 0.0
        Fcr = (
            Cb
            * (math.pi**2)
            * E_MPa
            / (Lb_rts**2)
            * math.sqrt(1.0 + 0.078 * jterm * (Lb_rts**2))
        )
        Fcr = min(Fcr, Fy_MPa)
        Mn = Fcr * shape.Sx_mm3 / 1e6
        Mn = min(Mn, Mp)
        limit = "elastic_LTB_F2-3"
        notes.append(f"Lb > Lr → elastic LTB; Fcr={Fcr:.1f} MPa; Mn={Mn:.1f} kN·m")

    phiMn = phi_b * Mn
    DCR = Mu_kNm / phiMn if phiMn > 0 else float("inf")
    passes = DCR <= 1.0
    notes.append(f"φMn={phiMn:.1f} kN·m; Mu={Mu_kNm:.1f} kN·m; DCR={DCR:.3f} → {'PASS' if passes else 'FAIL'}")

    return LTBResult(
        Mn_kNm=Mn,
        phiMn_kNm=phiMn,
        Mp_kNm=Mp,
        Mr_kNm=Mr,
        Fcr_MPa=Fcr if Lb_eff > Lr else (Mn * 1e6 / shape.Sx_mm3),
        Lb_mm=Lb_eff,
        Lp_mm=Lp,
        Lr_mm=Lr,
        Cb=Cb,
        braced_by_deck=braced_by_deck,
        limit_state=limit,
        passes=passes,
        Mu_kNm=Mu_kNm,
        DCR=DCR,
        notes=notes,
    )
