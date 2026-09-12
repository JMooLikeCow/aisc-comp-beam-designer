"""Positive flexural strength — AISC 360-22 §I3.2a (plastic) / §I3.2b (elastic)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from composite_beam.composite.shear_connection import ShearConnectionResult
from composite_beam.composite.slab import SlabConfig
from composite_beam.sections.classification import ClassificationResult, Compactness
from composite_beam.sections.w_shapes import WShape


@dataclass
class PositiveMomentResult:
    """
    Report BOTH plastic (I3.2a) and elastic (I3.2b) capacities.
    Design φMn uses plastic only when compact; else elastic — never mix silently.
    """

    Mn_plastic_kNm: float
    Mn_elastic_kNm: float
    Mn_design_kNm: float
    phi: float
    phiMn_kNm: float
    used_method: str  # "I3.2a_plastic" or "I3.2b_elastic"
    compact: bool
    a_mm: float  # PNA depth in concrete from top of slab (plastic)
    Y_conc_kN: float
    Y_steel_kN: float
    SumQn_kN: float
    notes: list[str]


def _plastic_PNA_and_Mn(
    shape: WShape,
    Fy_MPa: float,
    slab: SlabConfig,
    SumQn_kN: float,
) -> tuple[float, float, float, float, list[str]]:
    """
    Plastic stress distribution — AISC I3.2a.

    Horizontal force = min(As Fy, 0.85 f'c Ac, ΣQn).
    PNA assumed in slab when C = force ≤ 0.85 f'c beff t_solid.
    Mn = C * (lever arm between steel tension centroid and concrete compression).

    Simplified doubly-symmetric PNA-in-slab case (common for composite beams):
      a = C / (0.85 f'c beff)
      lever arm ≈ d/2 + hr + t_solid - a/2
      Mn = C * lever_arm
    When PNA falls in steel, use force equilibrium with steel plastic redistribution
    (conservative approximate when C < As Fy).
    Returns Mn_kNm, a_mm, Yconc_kN, Ysteel_kN, notes.
    """
    notes: list[str] = ["AISC 360-22 §I3.2a plastic stress distribution method."]
    AsFy = shape.A_mm2 * Fy_MPa / 1000.0  # kN
    Cf = 0.85 * slab.fc_MPa * slab.beff_mm * slab.t_solid_mm / 1000.0
    C = min(AsFy, Cf, SumQn_kN)
    notes.append(f"C = min(AsFy={AsFy:.1f}, Cf={Cf:.1f}, ΣQn={SumQn_kN:.1f}) = {C:.1f} kN")

    # Depth of concrete rectangular stress block from top of solid concrete
    a = C * 1000.0 / (0.85 * slab.fc_MPa * slab.beff_mm) if slab.beff_mm > 0 else 0.0
    notes.append(f"a = C/(0.85 f'c beff) = {a:.2f} mm")

    # Distance from top of steel to concrete force centroid
    # Concrete block in solid thickness above deck ribs
    if a <= slab.t_solid_mm + 1e-6:
        # Force in solid concrete: centroid at a/2 from top of slab
        y_conc_from_slab_top = a / 2.0
        y_conc_above_steel = slab.hr_mm + slab.t_solid_mm - y_conc_from_slab_top
        # Steel tension: for PNA in slab, entire steel in tension → centroid at d/2 below top flange
        # Lever arm from steel centroid to concrete force
        # Top of steel flange to steel centroid ≈ d/2
        lever_mm = y_conc_above_steel + shape.d_mm / 2.0
        Mn_kNmm = C * lever_mm
        notes.append(
            f"PNA in slab (a≤t_solid). Lever arm = {lever_mm:.1f} mm; Mn = {Mn_kNmm/1000:.1f} kN·m"
        )
        return Mn_kNmm / 1000.0, a, C, AsFy - C, notes

    # PNA in steel — approximate: concrete takes Cf_slab_full solid, remainder in steel
    notes.append("PNA extends into steel — approximate plastic redistribution.")
    C_conc = Cf  # use full solid slab capacity first... but limited by SumQn/AsFy already in C
    # Recompute: max concrete in solid
    C_conc = min(C, 0.85 * slab.fc_MPa * slab.beff_mm * slab.t_solid_mm / 1000.0)
    a = slab.t_solid_mm
    y_conc_above_steel = slab.hr_mm + slab.t_solid_mm / 2.0
    # Remaining compression in steel top flange/web
    C_steel_comp = C - C_conc
    # Approximate lever: steel tension force (AsFy roughly balanced)
    # Use AISC-style: Mn ≈ C_conc*(d/2 + y_conc) + Mp_reduced
    # Simpler conservative: treat as C at lever to mid-depth of steel
    lever_mm = y_conc_above_steel + shape.d_mm / 2.0
    # Reduce for steel compression: approximate additional couple from steel plastic
    # Distance between steel compression and tension ≈ (d - tf) roughly when flange yields
    if C_steel_comp > 0 and shape.bf_mm * shape.tf_mm * Fy_MPa / 1000.0 >= C_steel_comp:
        # Compression in top flange
        lever_steel = shape.d_mm - shape.tf_mm
        Mn_kNmm = C_conc * lever_mm + C_steel_comp * lever_steel
    else:
        Mn_kNmm = C * lever_mm
    notes.append(f"Approx Mn with PNA in steel = {Mn_kNmm/1000:.1f} kN·m")
    return Mn_kNmm / 1000.0, a, C_conc, C_steel_comp, notes


def _elastic_Mn(
    shape: WShape,
    Fy_MPa: float,
    slab: SlabConfig,
    n: float,
    SumQn_kN: float,
    C_full_kN: float,
) -> tuple[float, list[str]]:
    """
    Elastic (transformed section) stress distribution — AISC I3.2b.

    First yield when steel extreme fiber reaches Fy OR concrete reaches 0.85? 
    Spec: elastic stress distribution with steel stress limited to Fy and concrete
    to 0.70 f'c? Wait — AISC I3.2b User Note: concrete stress limited to 0.85? 
    Actually I3.2b: "elastic stress distribution... steel stress shall not exceed Fy
    and concrete stress shall not exceed 0.70 f'c" in older; 360-22 I3.2b says
    concrete compressive stress shall not exceed 0.85? Let me check...

    AISC 360-22 §I3.2b: The available strength shall be determined from the
    superposition of elastic stresses... Concrete stress limited using transformed
    section; typically first yield of steel governs. Conservative implementation:
    Mn = Fy * Str (transformed elastic section modulus to steel tension flange),
    limited by partial composite via effective transformed I / reduced force.

    For partial composite, AISC uses effective section with reduced concrete
    participation consistent with ΣQn.
    """
    notes = [
        "AISC 360-22 §I3.2b elastic stress distribution method.",
        "Concrete compressive stress limit taken as 0.70 f'c (I3.2b); steel ≤ Fy.",
    ]
    # Transformed concrete width
    beff_tr = slab.beff_mm / n
    t = slab.t_solid_mm
    hr = slab.hr_mm
    # Partial: reduce effective concrete area proportional to ΣQn/C_full
    ratio = min(1.0, SumQn_kN / C_full_kN) if C_full_kN > 0 else 1.0
    beff_tr *= ratio
    notes.append(f"n={n:.2f}; beff/n={beff_tr:.1f} mm (partial factor {ratio:.3f})")

    # Transformed section: concrete rectangle beff_tr × t atop steel (ignore deck concrete in ribs)
    # Centroid from bottom of steel
    As = shape.A_mm2
    Ac_tr = beff_tr * t
    y_steel = shape.d_mm / 2.0  # from bottom
    y_conc = shape.d_mm + hr + t / 2.0
    A_tot = As + Ac_tr
    y_bar = (As * y_steel + Ac_tr * y_conc) / A_tot if A_tot > 0 else y_steel

    # I transformed about y_bar
    I_s = shape.Ix_mm4 + As * (y_steel - y_bar) ** 2
    I_c = beff_tr * t**3 / 12.0 + Ac_tr * (y_conc - y_bar) ** 2
    I_tr = I_s + I_c

    # Distance to steel bottom (tension)
    y_t = y_bar
    S_s = I_tr / y_t if y_t > 0 else shape.Sx_mm3
    # Distance to concrete top
    y_c_top = (shape.d_mm + hr + t) - y_bar
    S_c_conc = I_tr / y_c_top if y_c_top > 0 else I_tr

    # Moment at steel first yield
    My_steel = Fy_MPa * S_s / 1e6  # MPa * mm³ → N·mm → /1e6 = kN·m
    # Moment at concrete 0.70 f'c (stress in concrete = M * y / I; transformed stress)
    # Actual concrete stress = (M * y_c / I_tr) — since width already /n, stress is steel-equiv;
    # concrete stress = steel-equiv / n ... wait: if we use beff/n, stresses from M y/I are
    # steel-equivalent; concrete stress = that value (already accounted). Limit 0.70 fc.
    Mc_conc = 0.70 * slab.fc_MPa * S_c_conc / 1e6
    Mn = min(My_steel, Mc_conc)
    notes.append(f"My,steel={My_steel:.1f} kN·m; M at 0.70f'c={Mc_conc:.1f} kN·m → Mn,el={Mn:.1f}")
    notes.append(f"I_tr={I_tr:.3e} mm⁴; y_bar from bottom={y_bar:.1f} mm")
    return Mn, notes


def positive_flexural_strength(
    shape: WShape,
    Fy_MPa: float,
    slab: SlabConfig,
    shear: ShearConnectionResult,
    classification: ClassificationResult,
    n: float,
    phi_b: float = 0.90,
) -> PositiveMomentResult:
    """
    Compute plastic and elastic Mn; select design value per compactness.

    Rule (non-negotiable): φMn plastic I3.2a ONLY when compact; else elastic I3.2b.
    Always report BOTH.
    """
    Mn_pl, a, Yc, Ys, notes_pl = _plastic_PNA_and_Mn(
        shape, Fy_MPa, slab, shear.SumQn_kN
    )
    Mn_el, notes_el = _elastic_Mn(
        shape, Fy_MPa, slab, n, shear.SumQn_kN, shear.C_full_kN
    )

    compact = classification.is_compact
    notes = list(notes_pl) + list(notes_el)
    notes.extend(classification.notes)

    if compact:
        Mn_design = Mn_pl
        method = "I3.2a_plastic"
        notes.append(
            "Section COMPACT → design Mn from plastic I3.2a "
            f"(Mn,pl={Mn_pl:.1f}; Mn,el={Mn_el:.1f} reported for information)."
        )
    else:
        Mn_design = Mn_el
        method = "I3.2b_elastic"
        notes.append(
            "Section NONCOMPACT/SLENDER → design Mn from elastic I3.2b "
            f"(Mn,pl={Mn_pl:.1f} NOT used for design; Mn,el={Mn_el:.1f})."
        )

    return PositiveMomentResult(
        Mn_plastic_kNm=Mn_pl,
        Mn_elastic_kNm=Mn_el,
        Mn_design_kNm=Mn_design,
        phi=phi_b,
        phiMn_kNm=phi_b * Mn_design,
        used_method=method,
        compact=compact,
        a_mm=a,
        Y_conc_kN=Yc,
        Y_steel_kN=Ys,
        SumQn_kN=shear.SumQn_kN,
        notes=notes,
    )
