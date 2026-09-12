"""Negative (hogging) flexural strength — default steel-only AISC Chapter F.

AISC 360-16 / 360-22 §I3 addresses *positive* flexure of composite beams with a
plastic or elastic stress distribution. Negative-moment composite action
(hogging PNA including the slab) is *not* permitted by this tool unless the
engineer supplies the I3 provisions that are out of scope here
(longitudinal slab reinforcement, I3.2 negative-flexure PNA, etc.).

Default: steel section alone, Chapter F (LTB + FLB + WLB).
Optional toggle: a residual concrete *tensile* couple limited by studs in the
hogging region — documented as a non-spec residual model, not I3 hogging PNA.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from composite_beam.sections.classification import ClassificationResult, Compactness
from composite_beam.sections.w_shapes import WShape
from composite_beam.strength.ltb import box_LTB_Mn, construction_LTB
from composite_beam.units import ES_MPA


@dataclass
class NegativeMomentResult:
    """Hogging available strength (steel Chapter F, optional residual tension)."""

    Mn_steel_kNm: float
    Mn_residual_kNm: float
    Mn_design_kNm: float
    phi: float
    phiMn_kNm: float
    limit_state: str
    used_residual_concrete: bool
    DCR: float
    Mu_kNm: float
    passes: bool
    notes: list[str] = field(default_factory=list)


def _flb_Mn_kNm(shape: WShape, Fy_MPa: float, E_MPa: float, classification: ClassificationResult) -> tuple[float, str]:
    """Flange local buckling Mn — AISC F3 (I-shape) / F7.2 (box)."""
    Mp = min(Fy_MPa * shape.Zx_mm3 / 1e6, 1.6 * Fy_MPa * shape.Sx_mm3 / 1e6)
    My = Fy_MPa * shape.Sx_mm3 / 1e6
    lam = classification.lambda_f
    lp = classification.lambda_pf
    lr = classification.lambda_rf
    if classification.flange == Compactness.COMPACT:
        return Mp, "FLB compact (no reduction)"
    if classification.flange == Compactness.NONCOMPACT:
        # F3-1 / F7-2 style interpolation
        Mn = Mp - (Mp - 0.7 * My) * (lam - lp) / (lr - lp) if lr > lp else Mp
        return min(Mn, Mp), "FLB noncompact F3-1/F7-2"
    # slender flange F3-2: Fcr = 0.9 E kc / λ² ; kc = 4/√(h/tw) in [0.35, 0.76]
    htw = max(shape.h_c_tw, 1e-6)
    kc = min(0.76, max(0.35, 4.0 / (htw ** 0.5)))
    Fcr = 0.9 * E_MPa * kc / (lam**2) if lam > 0 else Fy_MPa
    Mn = min(Fcr * shape.Sx_mm3 / 1e6, Mp)
    return Mn, "FLB slender F3-2"


def _wlb_factor(classification: ClassificationResult, shape: WShape, Fy_MPa: float, E_MPa: float) -> tuple[float, str]:
    """
    Web local buckling reduction on Mn.

    Compact web: 1.0
    Noncompact web (F4 Rpc): interpolate Mp/Myc → 1.0
    Slender web (F5 Rpg): Rpg = 1 − aw/(1200+300 aw) (hc/tw − λrw) ≤ 1
    """
    if classification.web == Compactness.COMPACT:
        return 1.0, "WLB compact (no reduction)"
    Myc = Fy_MPa * shape.Sx_mm3 / 1e6
    Mp = min(Fy_MPa * shape.Zx_mm3 / 1e6, 1.6 * Myc)
    if classification.web == Compactness.NONCOMPACT:
        ratio = Mp / Myc if Myc > 0 else 1.0
        lam = classification.lambda_w
        lp, lr = classification.lambda_pw, classification.lambda_rw
        Rpc = ratio - (ratio - 1.0) * (lam - lp) / (lr - lp) if lr > lp else 1.0
        Rpc = min(max(Rpc, 1.0), ratio)
        factor = (Rpc * Myc / Mp) if Mp > 0 else 1.0
        return float(min(1.0, factor)), f"WLB noncompact F4 Rpc={Rpc:.3f}"
    # F5 slender
    hc_tw = classification.lambda_w
    aw = (shape.d_mm - 2.0 * shape.tf_mm) * shape.tw_mm / max(shape.bf_mm * shape.tf_mm, 1e-6)
    Rpg = 1.0 - (aw / (1200.0 + 300.0 * aw)) * (hc_tw - classification.lambda_rw)
    Rpg = min(1.0, max(Rpg, 0.5))
    return float(Rpg), f"WLB slender F5 Rpg={Rpg:.3f}"


def negative_flexural_strength(
    shape: WShape,
    Fy_MPa: float,
    classification: ClassificationResult,
    Mu_kNm: float,
    Lb_mm: float,
    Cb: float = 1.0,
    phi_b: float = 0.90,
    E_MPa: float = ES_MPA,
    include_residual_concrete: bool = False,
    residual_T_kN: float = 0.0,
    residual_lever_mm: float = 0.0,
) -> NegativeMomentResult:
    """
    Hogging φMn.

    Steel-only Chapter F (default):
      Mn = min(LTB, FLB) × WLB factor.
      Compression flange in hogging is the *bottom* flange — deck brace of the
      top flange does **not** restrain LTB of the hogging region.

    Residual concrete tension (optional, off by default):
      Adds φ * T_res * lever. T_res is supplied by the engine from studs in
      hogging regions, capped conservatively. This is **not** AISC I3 hogging PNA.
    """
    notes = [
        "AISC 360-22 Chapter F (360-16 Chapter F equivalent) — steel-only hogging.",
        "FLAG: AISC I3 plastic/elastic composite PNA is for *positive* flexure.",
        "Do NOT assume a full-composite hogging PNA without I3 longitudinal slab reinforcement.",
        "Compression flange in hogging = bottom flange (deck does not brace it).",
    ]
    if getattr(shape, "section_kind", "W") == "BOX":
        Mn_ltb, _lp, _lr, ltb_note = box_LTB_Mn(shape, Fy_MPa, Lb_mm, Cb, E_MPa)
        notes.append("Box / rectangular HSS: LTB per §F7.4 (high J, rarely governs).")
    else:
        ltb = construction_LTB(
            shape,
            Fy_MPa,
            Lb_mm,
            Mu_kNm=0.0,
            Cb=Cb,
            braced_by_deck=False,
            phi_b=1.0,
            E_MPa=E_MPa,
        )
        Mn_ltb = ltb.Mn_kNm
        ltb_note = f"I-shape LTB §F2 {ltb.limit_state}; Cb={Cb:.2f}"
        notes.extend(n for n in ltb.notes if "Construction combo" not in n)

    Mn_flb, flb_note = _flb_Mn_kNm(shape, Fy_MPa, E_MPa, classification)
    wlb_fac, wlb_note = _wlb_factor(classification, shape, Fy_MPa, E_MPa)
    notes.append(ltb_note)
    notes.append(flb_note)
    notes.append(wlb_note)

    Mn_steel = min(Mn_ltb, Mn_flb) * wlb_fac
    governing = "LTB" if Mn_ltb <= Mn_flb else "FLB"
    if wlb_fac < 0.999:
        governing = f"{governing}+WLB"

    Mn_res = 0.0
    if include_residual_concrete and residual_T_kN > 0 and residual_lever_mm > 0:
        Mn_res = residual_T_kN * residual_lever_mm / 1000.0
        notes.append(
            f"OPTIONAL residual concrete tension: T={residual_T_kN:.1f} kN × "
            f"lever={residual_lever_mm:.1f} mm → M_res={Mn_res:.1f} kN·m. "
            "This is a residual (cracked-slab) couple limited by hogging-zone studs; "
            "it is NOT AISC I3.2 negative-flexure PNA and must not be treated as full composite."
        )
    elif include_residual_concrete:
        notes.append("Residual-concrete toggle ON but T_res=0 (no hogging-zone studs or zero lever).")

    Mn = Mn_steel + Mn_res
    phiMn = phi_b * Mn
    DCR = abs(Mu_kNm) / phiMn if phiMn > 0 else float("inf")
    notes.append(
        f"Mn,steel={Mn_steel:.1f}; Mn,res={Mn_res:.1f}; φMn={phiMn:.1f} kN·m; "
        f"|Mu,neg|={abs(Mu_kNm):.1f}; DCR={DCR:.3f}"
    )
    return NegativeMomentResult(
        Mn_steel_kNm=Mn_steel,
        Mn_residual_kNm=Mn_res,
        Mn_design_kNm=Mn,
        phi=phi_b,
        phiMn_kNm=phiMn,
        limit_state=governing,
        used_residual_concrete=bool(include_residual_concrete and Mn_res > 0),
        DCR=DCR,
        Mu_kNm=Mu_kNm,
        passes=DCR <= 1.0,
        notes=notes,
    )
