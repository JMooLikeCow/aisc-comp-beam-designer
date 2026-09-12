"""Simply supported beam analysis: UDL + point loads → M, V envelopes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from composite_beam.loads.load_cases import PointLoad, PointLoadSpec, UDL


@dataclass
class BeamDiagram:
    """Shear and moment along the span (SI: x in mm, V in kN, M in kN·mm)."""

    x_mm: np.ndarray
    V_kN: np.ndarray
    M_kNmm: np.ndarray
    R_left_kN: float
    R_right_kN: float
    M_max_kNmm: float
    M_max_x_mm: float
    V_max_kN: float
    M_min_kNmm: float = 0.0
    M_min_x_mm: float = 0.0
    M_left_kNm: float = 0.0
    M_right_kNm: float = 0.0
    support: str = "simply_supported"

    @property
    def M_max_kNm(self) -> float:
        return self.M_max_kNmm / 1000.0

    @property
    def M_min_kNm(self) -> float:
        """Most negative (hogging) moment along the span, kN·m."""
        return self.M_min_kNmm / 1000.0


@dataclass
class SpanLoads:
    """Aggregated UDL (kN/m) and point loads for one analysis case."""

    L_mm: float
    w_kNpm: float = 0.0
    points: list[PointLoad] = field(default_factory=list)


def _point_x_mm(p: PointLoad, L_mm: float) -> float:
    if p.spec == PointLoadSpec.RATIO:
        return float(np.clip(p.location, 0.0, 1.0) * L_mm)
    return float(np.clip(p.location, 0.0, L_mm))


def analyze_simply_supported(
    L_mm: float,
    w_kNpm: float = 0.0,
    points: Optional[list[PointLoad]] = None,
    n_stations: int = 101,
) -> BeamDiagram:
    """
    Elastic analysis of a simply supported beam with UDL + concentrated loads.

    Sign convention: positive moment sagging (compression on top);
    shear positive when left face upward.
    Reactions from equilibrium; M(x), V(x) by sections.
    """
    points = points or []
    L_m = L_mm / 1000.0
    # Reactions
    # UDL: each support wL/2
    R_L = w_kNpm * L_m / 2.0
    R_R = w_kNpm * L_m / 2.0
    for p in points:
        a = _point_x_mm(p, L_mm) / 1000.0  # m from left
        b = L_m - a
        R_L += p.P_kN * b / L_m
        R_R += p.P_kN * a / L_m

    x = np.linspace(0.0, L_mm, n_stations)
    V = np.zeros_like(x)
    M = np.zeros_like(x)

    for i, xi in enumerate(x):
        xi_m = xi / 1000.0
        # Shear: R_L - w*xi - sum of points to the left
        Vi = R_L - w_kNpm * xi_m
        Mi = R_L * xi_m - w_kNpm * xi_m * xi_m / 2.0
        for p in points:
            a_mm = _point_x_mm(p, L_mm)
            if a_mm < xi - 1e-9:
                Vi -= p.P_kN
                Mi -= p.P_kN * (xi_m - a_mm / 1000.0)
            elif abs(a_mm - xi) <= 1e-9:
                # At point load: report average / left face
                pass
        V[i] = Vi
        M[i] = Mi * 1000.0  # kN·m → kN·mm

    i_max = int(np.argmax(M))
    i_min = int(np.argmin(M))
    return BeamDiagram(
        x_mm=x,
        V_kN=V,
        M_kNmm=M,
        R_left_kN=R_L,
        R_right_kN=R_R,
        M_max_kNmm=float(M[i_max]),
        M_max_x_mm=float(x[i_max]),
        V_max_kN=float(np.max(np.abs(V))),
        M_min_kNmm=float(M[i_min]),
        M_min_x_mm=float(x[i_min]),
        M_left_kNm=0.0,
        M_right_kNm=0.0,
        support="simply_supported",
    )


def deflection_udl_simply_supported(w_kNpm: float, L_mm: float, EI_kNmm2: float) -> float:
    """Δ_mid = 5 w L^4 / (384 EI). Returns mm. w in kN/m, L in mm, EI in kN·mm²."""
    L_m = L_mm / 1000.0
    # Work in N, mm: w_N_per_mm = w_kNpm / 1000  (kN/m = N/mm)
    w_Nmm = w_kNpm / 1000.0  # N/mm
    # EI_kNmm2 = EI in kN·mm²; convert to N·mm² = *1000
    EI = EI_kNmm2 * 1000.0
    delta = 5.0 * w_Nmm * (L_mm**4) / (384.0 * EI)
    return delta  # mm


def deflection_point_midspan(P_kN: float, L_mm: float, EI_kNmm2: float) -> float:
    """Δ_mid for midspan point load = P L^3 / (48 EI). mm."""
    P_N = P_kN * 1000.0
    EI = EI_kNmm2 * 1000.0
    return P_N * (L_mm**3) / (48.0 * EI)


def deflection_point_general(P_kN: float, a_mm: float, L_mm: float, EI_kNmm2: float) -> float:
    """
    Midspan deflection due to point load at distance a from left.
    For simply supported: δ(x) = P b x (L² - b² - x²) / (6 E I L) for x <= a...
    Evaluate at midspan x = L/2.
    """
    a = a_mm
    b = L_mm - a
    L = L_mm
    x = L / 2.0
    P_N = P_kN * 1000.0
    EI = EI_kNmm2 * 1000.0
    if x <= a:
        delta = P_N * b * x * (L**2 - b**2 - x**2) / (6.0 * EI * L)
    else:
        # symmetric formula from right
        delta = P_N * a * (L - x) * (L**2 - a**2 - (L - x) ** 2) / (6.0 * EI * L)
    return delta
