"""Full/partial composite shear connection — ΣQn / Cf, required studs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from composite_beam.composite.slab import SlabConfig
from composite_beam.composite.studs import StudQnResult
from composite_beam.sections.w_shapes import WShape


@dataclass
class ShearConnectionResult:
    """Shear connection demand and provided capacity (AISC I3)."""

    Cf_kN: float  # concrete force = 0.85 f'c Ac  (limited)
    Cs_kN: float  # steel force = As Fy
    C_full_kN: float  # min(Cf, Cs) for full composite
    SumQn_kN: float  # provided between support and point of max moment
    ratio: float  # ΣQn / C_full  (1.0 = full)
    is_full: bool
    is_partial: bool
    n_studs_required_full: int
    n_studs_provided: int
    Qn_kN: float
    notes: list[str]


def concrete_force_Cf(slab: SlabConfig) -> float:
    """
    Cf = 0.85 f'c Ac  (AISC I3.2d / I3.1d).
    Ac = beff * t_solid for solid; for metal deck with ribs perpendicular,
    Ac is typically beff * t_solid (concrete above deck) — conservative for Cf.
    Returns kN.
    """
    Ac_mm2 = slab.beff_mm * slab.t_solid_mm
    # 0.85 * fc(MPa) * Ac(mm²) = N → /1000 = kN
    return 0.85 * slab.fc_MPa * Ac_mm2 / 1000.0


def steel_force_AsFy(shape: WShape, Fy_MPa: float) -> float:
    """As Fy in kN."""
    return shape.A_mm2 * Fy_MPa / 1000.0


def shear_connection(
    shape: WShape,
    Fy_MPa: float,
    slab: SlabConfig,
    stud_qn: StudQnResult,
    n_studs_half_span: Optional[int] = None,
    target_ratio: Optional[float] = None,
) -> ShearConnectionResult:
    """
    Compute full-composite force C = min(Cf, As Fy) and provided ΣQn.

    Partial composite: ΣQn / C  (AISC I3.2d); minimum practical ratio often 0.25–0.5
    (user-specified). Required studs from shear flow: n = C / Qn each side of max M
    for full composite (simply supported → half span).

    If target_ratio given, compute required studs for that ratio.
    If n_studs_half_span given, check provided ratio.
    """
    Cf = concrete_force_Cf(slab)
    Cs = steel_force_AsFy(shape, Fy_MPa)
    C_full = min(Cf, Cs)
    Qn = stud_qn.Qn_kN
    notes = [
        "AISC 360-22 §I3.2d: C = min(As Fy, 0.85 f'c Ac); partial ΣQn < C.",
        f"Cf = 0.85 f'c Ac = {Cf:.1f} kN; As Fy = {Cs:.1f} kN; C_full = {C_full:.1f} kN",
        f"Qn per stud = {Qn:.2f} kN",
    ]

    n_full = int((C_full / Qn) + 0.999) if Qn > 0 else 0  # ceil
    notes.append(f"Studs required each side of max M for full composite: {n_full}")

    if target_ratio is not None:
        C_target = target_ratio * C_full
        n_req = int((C_target / Qn) + 0.999) if Qn > 0 else 0
        n_prov = n_req
        SumQn = n_prov * Qn
        notes.append(f"Target ratio={target_ratio:.2f} → n≈{n_req}, ΣQn={SumQn:.1f} kN")
    elif n_studs_half_span is not None:
        n_prov = n_studs_half_span
        SumQn = n_prov * Qn
        notes.append(f"Provided n={n_prov} each side → ΣQn={SumQn:.1f} kN")
    else:
        n_prov = n_full
        SumQn = n_prov * Qn

    ratio = SumQn / C_full if C_full > 0 else 0.0
    # Cap ratio at 1.0 for classification (extra studs don't increase beyond full)
    ratio_eff = min(ratio, 1.0)
    is_full = ratio_eff >= 0.999
    is_partial = not is_full and ratio_eff > 0.0

    notes.append(f"ΣQn/C = {ratio_eff:.3f} → {'full' if is_full else 'partial'} composite")
    if is_partial:
        notes.append("Partial composite: Mn reduced; use Ieff (not full transformed I) for service.")

    return ShearConnectionResult(
        Cf_kN=Cf,
        Cs_kN=Cs,
        C_full_kN=C_full,
        SumQn_kN=min(SumQn, C_full),
        ratio=ratio_eff,
        is_full=is_full,
        is_partial=is_partial,
        n_studs_required_full=n_full,
        n_studs_provided=n_prov,
        Qn_kN=Qn,
        notes=notes,
    )
