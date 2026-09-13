"""Serviceability: deflections, Ieff, camber — AISC I3 / common practice."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from composite_beam.analysis.simple_beam import (
    deflection_point_general,
    deflection_udl_simply_supported,
)
from composite_beam.composite.shear_connection import ShearConnectionResult
from composite_beam.composite.slab import SlabConfig
from composite_beam.loads.load_cases import PointLoad
from composite_beam.sections.w_shapes import WShape
from composite_beam.units import ES_MPA


@dataclass
class DeflectionLimits:
    LL_ratio: float = 360.0  # L/360
    total_ratio: float = 240.0  # L/240
    custom_ratio: Optional[float] = None


@dataclass
class DeflectionResult:
    """Service deflection summary with shored vs unshored paths."""

    delta_LL_mm: float
    delta_DL_composite_mm: float
    delta_DL_construction_mm: float  # steel alone (unshored wet)
    delta_total_mm: float
    delta_LL_limit_mm: float
    delta_total_limit_mm: float
    LL_OK: bool
    total_OK: bool
    I_eff_mm4: float
    I_full_mm4: float
    I_s_mm4: float
    shored: bool
    camber_mm: float
    camber_suggested_mm: float
    camber_warn: bool
    notes: list[str]


def transformed_I_full(
    shape: WShape,
    slab: SlabConfig,
    n: float,
) -> tuple[float, float]:
    """
    Full composite transformed moment of inertia (mm⁴) and y_bar from bottom of steel.
    Concrete width = beff/n; solid thickness only (ribs neglected in I — common).
    """
    beff_tr = slab.beff_mm / n
    t = slab.t_solid_mm
    hr = slab.hr_mm
    As = shape.A_mm2
    Ac_tr = beff_tr * t
    y_s = shape.d_mm / 2.0
    y_c = shape.d_mm + hr + t / 2.0
    A = As + Ac_tr
    y_bar = (As * y_s + Ac_tr * y_c) / A if A > 0 else y_s
    I = (
        shape.Ix_mm4
        + As * (y_s - y_bar) ** 2
        + beff_tr * t**3 / 12.0
        + Ac_tr * (y_c - y_bar) ** 2
    )
    return I, y_bar


def Ieff_partial(I_full_mm4: float, I_s_mm4: float, ratio: float) -> float:
    """
    Effective I for partial composite — AISC 360-22 Eq. I3-1:
      Ieff = Is + √(ΣQn/Cf) * (Ifull − Is)
    where ratio = ΣQn/C (C = Cf in the equation nomenclature when concrete governs,
    but Spec uses ΣQn/C' with C' = min...). Use provided shear.ratio.
    """
    r = max(0.0, min(1.0, ratio))
    return I_s_mm4 + (r**0.5) * (I_full_mm4 - I_s_mm4)


def _EI_kNmm2(I_mm4: float, E_MPa: float = ES_MPA) -> float:
    """EI in kN·mm². E [MPa=N/mm²]·I [mm⁴] = N·mm²; ÷1000 → kN·mm².

    Paired with deflection_* helpers that convert back via EI_Nmm2 = EI_kNmm2 * 1000
    and take w in kN/m as N/mm (1 kN/m ≡ 1 N/mm) — do not divide w by 1000.
    """
    return E_MPa * I_mm4 / 1000.0


def compute_deflections(
    L_mm: float,
    shape: WShape,
    slab: SlabConfig,
    n: float,
    shear: ShearConnectionResult,
    w_LL_kNpm: float,
    w_DL_service_kNpm: float,
    w_DL_construction_kNpm: float,
    points_LL: Optional[list[PointLoad]] = None,
    points_DL: Optional[list[PointLoad]] = None,
    shored: bool = False,
    limits: Optional[DeflectionLimits] = None,
    camber_mm: float = 0.0,
    E_MPa: float = ES_MPA,
) -> DeflectionResult:
    """
    Serviceability paths:
      - Unshored: construction DL (wet) on steel alone Is; superimposed + LL on Ieff.
      - Shored: all DL + LL on Ieff (shores remove construction steel-alone deflection).
    Camber: manual input; suggest 80% of DL Δ; warn if camber > 100% DL Δ (non-blocking).
    """
    limits = limits or DeflectionLimits()
    points_LL = points_LL or []
    points_DL = points_DL or []
    notes = [
        "Construction vs service deflection paths kept separate.",
        "AISC 360-22 Eq. I3-1 for Ieff under partial composite.",
    ]

    I_full, _ = transformed_I_full(shape, slab, n)
    I_s = shape.Ix_mm4
    I_eff = Ieff_partial(I_full, I_s, shear.ratio)
    notes.append(
        f"I_s={I_s:.3e} mm⁴; I_full={I_full:.3e}; Ieff={I_eff:.3e} (√(ΣQn/C)={shear.ratio**0.5:.3f})"
    )
    if shear.is_partial:
        notes.append("Partial composite → Ieff used (not full I).")

    EI_s = _EI_kNmm2(I_s, E_MPa)
    EI_eff = _EI_kNmm2(I_eff, E_MPa)

    # Live load deflection on Ieff
    d_LL = deflection_udl_simply_supported(w_LL_kNpm, L_mm, EI_eff)
    for p in points_LL:
        a = p.location * L_mm if p.spec.value == "ratio" else p.location
        d_LL += deflection_point_general(p.P_kN, a, L_mm, EI_eff)

    # Construction DL on steel alone (unshored)
    d_DL_const = deflection_udl_simply_supported(w_DL_construction_kNpm, L_mm, EI_s)
    for p in points_DL:
        a = p.location * L_mm if p.spec.value == "ratio" else p.location
        d_DL_const += deflection_point_general(p.P_kN, a, L_mm, EI_s)

    # Service DL on composite (superimposed dead after composite action)
    d_DL_comp = deflection_udl_simply_supported(w_DL_service_kNpm, L_mm, EI_eff)

    if shored:
        # All dead on Ieff; no steel-alone construction deflection in total service
        d_DL_for_total = deflection_udl_simply_supported(
            w_DL_construction_kNpm + w_DL_service_kNpm, L_mm, EI_eff
        )
        notes.append("Shored: total DL deflection computed on Ieff.")
        d_DL_construction_report = 0.0
    else:
        d_DL_for_total = d_DL_const + d_DL_comp
        d_DL_construction_report = d_DL_const
        notes.append("Unshored: wet DL on Is + superimposed DL on Ieff.")

    d_total = d_DL_for_total + d_LL

    lim_LL = L_mm / limits.LL_ratio
    lim_tot = L_mm / limits.total_ratio
    if limits.custom_ratio:
        notes.append(f"Custom limit L/{limits.custom_ratio:.0f} noted (not replacing LL/total).")

    # Camber suggestion: 80% of DL deflection (pre-composite path for unshored)
    dl_for_camber = d_DL_const if not shored else d_DL_for_total
    suggested = 0.80 * dl_for_camber
    warn = camber_mm > 1.00 * dl_for_camber + 1e-9
    notes.append(
        f"Camber suggested ≈ 80% DL Δ = {suggested:.1f} mm; "
        f"user camber={camber_mm:.1f} mm"
        + ("; WARN camber > 100% DL Δ (non-blocking)" if warn else "")
    )

    return DeflectionResult(
        delta_LL_mm=d_LL,
        delta_DL_composite_mm=d_DL_comp,
        delta_DL_construction_mm=d_DL_construction_report,
        delta_total_mm=d_total,
        delta_LL_limit_mm=lim_LL,
        delta_total_limit_mm=lim_tot,
        LL_OK=d_LL <= lim_LL + 1e-6,
        total_OK=d_total <= lim_tot + 1e-6,
        I_eff_mm4=I_eff,
        I_full_mm4=I_full,
        I_s_mm4=I_s,
        shored=shored,
        camber_mm=camber_mm,
        camber_suggested_mm=suggested,
        camber_warn=warn,
        notes=notes,
    )
