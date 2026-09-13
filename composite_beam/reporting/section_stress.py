"""Elastic transformed-section and plastic PNA stress profiles for cross-section viewer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import numpy as np

if TYPE_CHECKING:
    from composite_beam.design_engine import DesignResult
    from composite_beam.sections.w_shapes import WShape
    from composite_beam.composite.slab import SlabConfig


# Cap plotted slab width for readability (true beff annotated when capped)
_BEFF_PLOT_CAP_MM = 1200.0


@dataclass
class ElasticStressProfile:
    """Elastic (transformed-section) stresses at a station for demand M(x)."""

    x_mm: float
    M_kNm: float
    hogging: bool
    # Geometry (mm from top of slab, positive downward)
    total_depth_mm: float
    y_NA_from_top_mm: float
    I_tr_mm4: float
    beff_mm: float
    beff_plot_mm: float
    beff_tr_mm: float
    t_solid_mm: float
    hr_mm: float
    # Stress samples along depth (steel-equivalent and material)
    y_from_top_mm: np.ndarray
    sigma_steel_eq_MPa: np.ndarray
    sigma_material_MPa: np.ndarray
    sigma_c_top_MPa: float  # material concrete (compression negative for sagging)
    sigma_s_bot_MPa: float  # steel bottom (tension positive for sagging)
    partial_ratio: float
    notes: list[str] = field(default_factory=list)


@dataclass
class PlasticBlockSchematic:
    """I3.2a plastic stress-block schematic (capacity shape) for positive M."""

    a_mm: float
    C_kN: float
    Mn_plastic_kNm: float
    M_over_Mn: float
    Y_conc_kN: float
    Y_steel_kN: float
    available: bool
    notes: list[str] = field(default_factory=list)


def moment_at_x_kNm(result: "DesignResult", x_mm: float) -> float:
    """Interpolate governing occupancy M(x) [kN·m] at station x_mm."""
    d = result.diagram
    if d is None or len(d.x_mm) == 0:
        return float(result.Mu_kNm)
    x = float(np.clip(x_mm, float(d.x_mm[0]), float(d.x_mm[-1])))
    M_kNmm = float(np.interp(x, d.x_mm, d.M_kNmm))
    return M_kNmm / 1000.0


def _shape_slab(result: "DesignResult") -> tuple["WShape", "SlabConfig", float]:
    shape = getattr(result, "shape", None)
    slab = getattr(result, "slab", None)
    Fy = float(getattr(result, "Fy_MPa", 0.0) or result.inputs_summary.get("Fy_MPa", 345.0))
    if shape is None or slab is None:
        raise ValueError("DesignResult missing shape/slab geometry for stress viewer")
    return shape, slab, Fy


def build_transformed_section(
    shape: "WShape",
    slab: "SlabConfig",
    n: float,
    SumQn_kN: float,
    C_full_kN: float,
) -> dict:
    """
    Build elastic transformed section consistent with positive_moment._elastic_Mn.

    Returns dict with I_tr, y_bar_from_bottom, beff_tr, partial_ratio, etc.
    y measured from bottom of steel upward.
    """
    beff_tr = slab.beff_mm / n if n > 0 else 0.0
    t = slab.t_solid_mm
    hr = slab.hr_mm
    ratio = min(1.0, SumQn_kN / C_full_kN) if C_full_kN > 0 else 1.0
    beff_tr *= ratio

    As = shape.A_mm2
    Ac_tr = beff_tr * t
    y_steel = shape.d_mm / 2.0
    y_conc = shape.d_mm + hr + t / 2.0
    A_tot = As + Ac_tr
    y_bar = (As * y_steel + Ac_tr * y_conc) / A_tot if A_tot > 0 else y_steel

    I_s = shape.Ix_mm4 + As * (y_steel - y_bar) ** 2
    I_c = (beff_tr * t**3 / 12.0 + Ac_tr * (y_conc - y_bar) ** 2) if Ac_tr > 0 else 0.0
    I_tr = I_s + I_c

    total_h = shape.d_mm + hr + t
    return {
        "beff_tr_mm": beff_tr,
        "partial_ratio": ratio,
        "t_solid_mm": t,
        "hr_mm": hr,
        "y_bar_from_bottom_mm": y_bar,
        "I_tr_mm4": I_tr,
        "total_depth_mm": total_h,
        "As_mm2": As,
        "Ac_tr_mm2": Ac_tr,
    }


def elastic_stress_profile(result: "DesignResult", x_mm: float) -> ElasticStressProfile:
    """
    Elastic transformed-section stresses for governing M(x).

    Sign: positive = tension, negative = compression (fiber stress).
    Sagging (+M): concrete top compression (−), steel bottom tension (+).
    Hogging (−M): steel-only note; concrete ignored (cracked); reverse curvature.
    """
    shape, slab, _Fy = _shape_slab(result)
    M_kNm = moment_at_x_kNm(result, x_mm)
    notes: list[str] = []
    hogging = M_kNm < -1e-9

    tr = build_transformed_section(
        shape,
        slab,
        result.n,
        result.shear.SumQn_kN,
        result.shear.C_full_kN,
    )
    t = tr["t_solid_mm"]
    hr = tr["hr_mm"]
    total_h = tr["total_depth_mm"]
    beff_plot = min(slab.beff_mm, max(_BEFF_PLOT_CAP_MM, 3.0 * shape.bf_mm))

    if hogging:
        # Steel-only elastic section about steel centroid
        notes.append(
            "Hogging M(x) < 0: cracked-slab / steel-only elastic stresses "
            "(composite concrete ignored in tension)."
        )
        I = shape.Ix_mm4
        y_bar_bot = shape.d_mm / 2.0  # from bottom of steel
        # Coordinate: top of slab still y=0 for plot alignment; steel starts at t+hr
        slab_depth = t + hr
        # Sample through steel only for stress; zeros in slab
        n_pts = 81
        y_from_top = np.linspace(0.0, total_h, n_pts)
        sigma_eq = np.zeros(n_pts)
        sigma_mat = np.zeros(n_pts)
        M_Nmm = M_kNm * 1e6  # kN·m → N·mm
        for i, y_top in enumerate(y_from_top):
            if y_top < slab_depth - 1e-9:
                continue
            y_from_steel_bot = total_h - y_top  # from bottom of steel
            y_from_NA = y_from_steel_bot - y_bar_bot
            # Hogging: top of steel in tension, bottom in compression
            # σ = M * y / I with y from NA; use steel-only; M negative
            # With M<0 and y_from_NA positive above NA (toward top of steel):
            # We want top fiber tension (+) for hogging.
            # Using σ = −M * (y_from_centroid_up) / I with standard beam:
            # Better: distance from NA, positive toward bottom; σ = M * y_bot_dir / I
            # For sagging M>0, bottom tension: σ = M * (y_bar - y_from_bot) / I ... 
            # y measured from NA positive downward (toward tension for sagging):
            y_down_from_NA = y_bar_bot - y_from_steel_bot
            sig = (M_Nmm * y_down_from_NA / I) if I > 0 else 0.0  # N/mm² = MPa
            sigma_eq[i] = sig
            sigma_mat[i] = sig
        y_NA_from_top = slab_depth + (shape.d_mm - y_bar_bot)
        # Top of steel / bottom of steel
        sigma_c_top = 0.0
        sigma_s_bot = float(sigma_mat[-1])
        return ElasticStressProfile(
            x_mm=float(x_mm),
            M_kNm=M_kNm,
            hogging=True,
            total_depth_mm=total_h,
            y_NA_from_top_mm=y_NA_from_top,
            I_tr_mm4=I,
            beff_mm=slab.beff_mm,
            beff_plot_mm=beff_plot,
            beff_tr_mm=0.0,
            t_solid_mm=t,
            hr_mm=hr,
            y_from_top_mm=y_from_top,
            sigma_steel_eq_MPa=sigma_eq,
            sigma_material_MPa=sigma_mat,
            sigma_c_top_MPa=sigma_c_top,
            sigma_s_bot_MPa=sigma_s_bot,
            partial_ratio=tr["partial_ratio"],
            notes=notes,
        )

    # Positive / zero moment — composite transformed section
    notes.append("AISC 360-22 §I3.2b elastic transformed-section stresses at M(x).")
    notes.append(
        f"n={result.n:.3f}; partial ΣQn/C={tr['partial_ratio']:.3f}; "
        f"beff/n (eff)={tr['beff_tr_mm']:.1f} mm"
    )
    if slab.beff_mm > beff_plot + 1.0:
        notes.append(
            f"Plotting width capped at {beff_plot:.0f} mm "
            f"(true beff={slab.beff_mm:.0f} mm)."
        )

    I_tr = tr["I_tr_mm4"]
    y_bar_bot = tr["y_bar_from_bottom_mm"]
    y_NA_from_top = total_h - y_bar_bot
    M_Nmm = M_kNm * 1e6

    n_pts = 121
    y_from_top = np.linspace(0.0, total_h, n_pts)
    sigma_eq = np.zeros(n_pts)
    sigma_mat = np.zeros(n_pts)
    n_mod = result.n if result.n > 0 else 1.0

    for i, y_top in enumerate(y_from_top):
        y_from_bot = total_h - y_top
        y_down_from_NA = y_bar_bot - y_from_bot  # + below NA (tension for +M)
        sig_eq = (M_Nmm * y_down_from_NA / I_tr) if I_tr > 0 else 0.0
        sigma_eq[i] = sig_eq
        # Material stress: in concrete region (slab solid), σ_c = σ_steel_eq / n
        # (transformed width already uses beff/n; My/I gives steel-equivalent)
        if y_top <= t + 1e-9:
            sigma_mat[i] = sig_eq / n_mod
        elif y_top < t + hr - 1e-9:
            # Deck haunch / rib zone — no solid concrete in simplified model
            sigma_mat[i] = 0.0
            sigma_eq[i] = 0.0
        else:
            sigma_mat[i] = sig_eq

    sigma_c_top = float(sigma_mat[0])
    sigma_s_bot = float(sigma_mat[-1])
    notes.append(
        f"σc,top={sigma_c_top:.2f} MPa; σs,bot={sigma_s_bot:.2f} MPa; "
        f"NA at {y_NA_from_top:.1f} mm from top"
    )

    return ElasticStressProfile(
        x_mm=float(x_mm),
        M_kNm=M_kNm,
        hogging=False,
        total_depth_mm=total_h,
        y_NA_from_top_mm=y_NA_from_top,
        I_tr_mm4=I_tr,
        beff_mm=slab.beff_mm,
        beff_plot_mm=beff_plot,
        beff_tr_mm=tr["beff_tr_mm"],
        t_solid_mm=t,
        hr_mm=hr,
        y_from_top_mm=y_from_top,
        sigma_steel_eq_MPa=sigma_eq,
        sigma_material_MPa=sigma_mat,
        sigma_c_top_MPa=sigma_c_top,
        sigma_s_bot_MPa=sigma_s_bot,
        partial_ratio=tr["partial_ratio"],
        notes=notes,
    )


def plastic_block_schematic(result: "DesignResult", x_mm: float) -> PlasticBlockSchematic:
    """I3.2a plastic stress-block schematic; available only for positive M(x)."""
    M = moment_at_x_kNm(result, x_mm)
    pos = result.positive_moment
    Mn = pos.Mn_plastic_kNm
    ratio = (M / Mn) if Mn > 1e-9 else 0.0
    if M <= 0:
        return PlasticBlockSchematic(
            a_mm=pos.a_mm,
            C_kN=pos.Y_conc_kN,
            Mn_plastic_kNm=Mn,
            M_over_Mn=ratio,
            Y_conc_kN=pos.Y_conc_kN,
            Y_steel_kN=pos.Y_steel_kN,
            available=False,
            notes=["Plastic I3.2a blocks shown only for positive (sagging) M(x)."],
        )
    return PlasticBlockSchematic(
        a_mm=pos.a_mm,
        C_kN=pos.Y_conc_kN,
        Mn_plastic_kNm=Mn,
        M_over_Mn=ratio,
        Y_conc_kN=pos.Y_conc_kN,
        Y_steel_kN=pos.Y_steel_kN,
        available=True,
        notes=[
            "AISC 360-22 §I3.2a plastic stress distribution (capacity schematic).",
            f"Demand M/Mn,pl = {ratio:.3f} at this station.",
        ],
    )


def section_geometry_for_plot(result: "DesignResult") -> dict:
    """Return dimensions needed to draw the cross-section outline."""
    shape, slab, Fy = _shape_slab(result)
    beff_plot = min(slab.beff_mm, max(_BEFF_PLOT_CAP_MM, 3.0 * shape.bf_mm))
    return {
        "shape": shape,
        "slab": slab,
        "Fy_MPa": Fy,
        "beff_mm": slab.beff_mm,
        "beff_plot_mm": beff_plot,
        "t_solid_mm": slab.t_solid_mm,
        "hr_mm": slab.hr_mm,
        "d_mm": shape.d_mm,
        "bf_mm": shape.bf_mm,
        "tf_mm": shape.tf_mm,
        "tw_mm": shape.tw_mm,
        "total_depth_mm": shape.d_mm + slab.t_solid_mm + slab.hr_mm,
    }
