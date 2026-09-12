"""Continuous-span elastic analysis: fixed-fixed and fixed-pinned (no cantilevers).

Superposition: simply-supported M,V plus linearly interpolated end moments.
End moments default to elastic fixed-end moments (FEM); the user may override
them (frame moments, patterned live load, etc.).

Sign convention (same as simply-supported helper):
  - Positive moment = sagging (compression in top flange / slab)
  - Hogging end moments are negative
  - Shear positive when the left face is upward
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

import numpy as np

from composite_beam.analysis.simple_beam import BeamDiagram, analyze_simply_supported, _point_x_mm
from composite_beam.loads.load_cases import PointLoad


class SupportType(str, Enum):
    """Supported end conditions. Cantilevers are out of scope."""

    SIMPLY_SUPPORTED = "simply_supported"
    FIXED_FIXED = "fixed_fixed"
    FIXED_PINNED = "fixed_pinned"  # left fixed, right pinned


def elastic_end_moments_kNm(
    L_mm: float,
    w_kNpm: float,
    points: Optional[list[PointLoad]],
    support: SupportType,
) -> tuple[float, float]:
    """
    Elastic fixed-end moments (kN·m), hogging negative.

    Fixed-fixed UDL: ML = MR = −w L² / 12
    Fixed-fixed point load at a (b = L−a): ML = −P a b² / L², MR = −P a² b / L²
    Fixed-pinned (left fixed) UDL: ML = −w L² / 8, MR = 0
    Fixed-pinned point load: ML = −P a b (L+b) / (2 L²), MR = 0
    Superposition applies for UDL + any number of point loads.
    """
    if support == SupportType.SIMPLY_SUPPORTED:
        return 0.0, 0.0

    L_m = L_mm / 1000.0
    points = points or []
    ML = 0.0
    MR = 0.0

    if support == SupportType.FIXED_FIXED:
        ML += -w_kNpm * L_m**2 / 12.0
        MR += -w_kNpm * L_m**2 / 12.0
        for p in points:
            a = _point_x_mm(p, L_mm) / 1000.0
            b = L_m - a
            if L_m <= 0:
                continue
            ML += -p.P_kN * a * b**2 / (L_m**2)
            MR += -p.P_kN * (a**2) * b / (L_m**2)
        return ML, MR

    # Fixed-pinned: left fixed, right pinned
    ML += -w_kNpm * L_m**2 / 8.0
    for p in points:
        a = _point_x_mm(p, L_mm) / 1000.0
        b = L_m - a
        if L_m <= 0:
            continue
        ML += -p.P_kN * a * b * (L_m + b) / (2.0 * L_m**2)
    return ML, 0.0


def analyze_span(
    L_mm: float,
    w_kNpm: float = 0.0,
    points: Optional[list[PointLoad]] = None,
    support: SupportType = SupportType.SIMPLY_SUPPORTED,
    M_left_override_kNm: Optional[float] = None,
    M_right_override_kNm: Optional[float] = None,
    n_stations: int = 101,
) -> BeamDiagram:
    """
    Elastic M(x), V(x) for simply-supported, fixed-fixed, or fixed-pinned spans.

    M(x) = M_ss(x) + ML (1 − x/L) + MR (x/L)
    V(x) = V_ss(x) + (ML − MR) / L
    with ML, MR the (possibly overridden) end moments in kN·m.
    """
    points = points or []
    ss = analyze_simply_supported(L_mm, w_kNpm, points, n_stations=n_stations)

    if support == SupportType.SIMPLY_SUPPORTED and M_left_override_kNm is None and M_right_override_kNm is None:
        i_min = int(np.argmin(ss.M_kNmm))
        ss.M_min_kNmm = float(ss.M_kNmm[i_min])
        ss.M_min_x_mm = float(ss.x_mm[i_min])
        ss.M_left_kNm = 0.0
        ss.M_right_kNm = 0.0
        ss.support = support.value
        return ss

    ML_fem, MR_fem = elastic_end_moments_kNm(L_mm, w_kNpm, points, support)
    ML = M_left_override_kNm if M_left_override_kNm is not None else ML_fem
    MR = M_right_override_kNm if M_right_override_kNm is not None else MR_fem
    if support == SupportType.FIXED_PINNED and M_right_override_kNm is None:
        MR = 0.0

    L_m = L_mm / 1000.0
    x = ss.x_mm
    xi = x / L_mm
    M = ss.M_kNmm + ML * 1000.0 * (1.0 - xi) + MR * 1000.0 * xi
    dV = (ML - MR) / L_m if L_m > 0 else 0.0
    V = ss.V_kN + dV

    i_max = int(np.argmax(M))
    i_min = int(np.argmin(M))
    return BeamDiagram(
        x_mm=x,
        V_kN=V,
        M_kNmm=M,
        R_left_kN=ss.R_left_kN + dV,
        R_right_kN=ss.R_right_kN - dV,
        M_max_kNmm=float(M[i_max]),
        M_max_x_mm=float(x[i_max]),
        V_max_kN=float(np.max(np.abs(V))),
        M_min_kNmm=float(M[i_min]),
        M_min_x_mm=float(x[i_min]),
        M_left_kNm=float(ML),
        M_right_kNm=float(MR),
        support=support.value,
    )


def midspan_deflection_from_moment_mm(
    x_mm: np.ndarray,
    M_kNmm: np.ndarray,
    EI_kNmm2: float,
) -> float:
    """
    Midspan deflection (mm) from M(x) by double integration with δ(0)=δ(L)=0.

    Valid for simply-supported and for continuous spans whose moment already
    includes the restraining end moments (slope at a fixed end is then ~0).
    EI in kN·mm²; M in kN·mm.
    """
    if EI_kNmm2 <= 0 or len(x_mm) < 3:
        return 0.0
    # κ = M/EI ; M_kNmm / EI_kNmm2 = 1/mm
    kappa = M_kNmm / EI_kNmm2
    # θ(x) = θ0 + ∫ κ dx ; choose θ0 so δ(L)=0
    # trapezoidal integration
    dx = np.diff(x_mm)
    # cumulative ∫_0^x κ
    integ = np.concatenate([[0.0], np.cumsum((kappa[:-1] + kappa[1:]) * 0.5 * dx)])
    # δ*(x) = ∫_0^x integ ; δ(x) = δ*(x) + θ0 x ; δ(L)=0 → θ0 = −δ*(L)/L
    dxi = dx
    delta_star = np.concatenate([[0.0], np.cumsum((integ[:-1] + integ[1:]) * 0.5 * dxi)])
    L = float(x_mm[-1] - x_mm[0])
    if L <= 0:
        return 0.0
    theta0 = -float(delta_star[-1]) / L
    delta = delta_star + theta0 * (x_mm - x_mm[0])
    # report value at midspan station
    imid = int(np.argmin(np.abs(x_mm - 0.5 * (x_mm[0] + x_mm[-1]))))
    return float(abs(delta[imid]))


def cb_from_segment(
    x_mm: np.ndarray,
    M_kNmm: np.ndarray,
    x0_mm: float,
    x1_mm: float,
) -> float:
    """AISC F1-1 Cb on an unbraced segment [x0, x1]. Conservative floor 1.0, cap 2.3."""
    mask = (x_mm >= min(x0_mm, x1_mm) - 1e-6) & (x_mm <= max(x0_mm, x1_mm) + 1e-6)
    if not np.any(mask):
        return 1.0
    xs = x_mm[mask]
    Ms = np.abs(M_kNmm[mask])
    if xs.size < 4 or float(np.max(Ms)) < 1e-9:
        return 1.0
    Mmax = float(np.max(Ms))
    Lseg = float(xs[-1] - xs[0])
    if Lseg <= 0:
        return 1.0

    def _at_frac(frac: float) -> float:
        target = xs[0] + frac * Lseg
        return float(np.interp(target, xs, Ms))

    MA = _at_frac(0.25)
    MB = _at_frac(0.50)
    MC = _at_frac(0.75)
    denom = 2.5 * Mmax + 3.0 * MA + 4.0 * MB + 3.0 * MC
    if denom <= 0:
        return 1.0
    Cb = 12.5 * Mmax / denom
    return float(min(2.3, max(1.0, Cb)))
