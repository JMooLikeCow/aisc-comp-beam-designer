"""Cumulative composite action along the span (detailing / development plot).

Reports how horizontal shear transfer builds from each end (or from points of
zero moment / contraflexure) toward the point of maximum positive moment.

This is a detailing aid per AISC I3.2d / I8 concepts — not a substitute for the
discrete half-span stud count check (ΣQn vs C between support and max M).

Method (moment-proportional, preferred with point loads):
  F_req(x) = C_full * M(x) / M_max   on the positive-moment side, clipped to
  [0, C_full], measured from the left origin for x ≤ x_maxM and from the right
  origin for x ≥ x_maxM. Origins are supports for simply-supported spans, or
  inflection (M = 0) points for continuous spans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from composite_beam.composite.stud_layout import StudLayoutResult, StudPosition


@dataclass
class CumulativeCompositeResult:
    """Stations along the span for the cumulative composite-action plot."""

    x_mm: np.ndarray
    F_req_kN: np.ndarray  # governing envelope (from nearer origin)
    SumQn_prov_kN: np.ndarray
    alpha: np.ndarray  # ΣQn_prov / C_full
    F_req_from_left_kN: np.ndarray
    F_req_from_right_kN: np.ndarray
    alpha_vs_req: np.ndarray  # ΣQn_prov / F_req (inf where F_req≈0)
    shortfall_kN: np.ndarray
    ok: np.ndarray  # bool: SumQn_prov >= F_req − tol
    C_full_kN: float
    x_maxM_mm: float
    origin_left_mm: float
    origin_right_mm: float
    notes: list[str] = field(default_factory=list)

    def station_rows(self) -> list[dict]:
        """Table rows for Detailed / Excel / HTML."""
        rows = []
        for i, x in enumerate(self.x_mm):
            fr = float(self.F_req_kN[i])
            sp = float(self.SumQn_prov_kN[i])
            al = float(self.alpha[i])
            sf = float(self.shortfall_kN[i])
            rows.append(
                {
                    "x_mm": float(x),
                    "F_req_kN": fr,
                    "SumQn_prov_kN": sp,
                    "alpha": al,
                    "shortfall_kN": sf,
                    "status": "OK" if bool(self.ok[i]) else "SHORT",
                }
            )
        return rows


def _inflection_points(x_mm: np.ndarray, M_kNmm: np.ndarray) -> list[float]:
    """Zero-moment crossings (linear interpolate), excluding endpoints."""
    out: list[float] = []
    for i in range(len(x_mm) - 1):
        m0, m1 = float(M_kNmm[i]), float(M_kNmm[i + 1])
        if m0 == 0.0:
            xi = float(x_mm[i])
            if 1e-3 < xi < float(x_mm[-1]) - 1e-3:
                out.append(xi)
            continue
        if m0 * m1 < 0.0:
            t = abs(m0) / (abs(m0) + abs(m1))
            xi = float(x_mm[i] + t * (x_mm[i + 1] - x_mm[i]))
            if 1e-3 < xi < float(x_mm[-1]) - 1e-3:
                out.append(xi)
    return out


def _positive_segment_origins(
    L_mm: float,
    x_maxM_mm: float,
    x_mm: np.ndarray,
    M_kNmm: np.ndarray,
) -> tuple[float, float, list[str]]:
    """
    Origins for cumulative build-up toward max positive moment.

    Simply supported (M ≥ 0 on whole span): left support and right support.
    Continuous: nearest inflection (or support) on each side of x_maxM.
    """
    notes: list[str] = []
    M_max = float(np.max(M_kNmm))
    if M_max <= 0:
        notes.append("No positive moment on span — cumulative F_req = 0.")
        return 0.0, L_mm, notes

    inflections = _inflection_points(x_mm, M_kNmm)
    # Default SS: supports
    origin_L, origin_R = 0.0, L_mm

    # If moment is negative near a support, use inflection as origin
    left_of = [z for z in inflections if z < x_maxM_mm]
    right_of = [z for z in inflections if z > x_maxM_mm]
    if left_of:
        origin_L = max(left_of)
    elif float(M_kNmm[0]) < -1e-6:
        # hogging at left but no crossing found — stay at 0
        pass
    if right_of:
        origin_R = min(right_of)
    elif float(M_kNmm[-1]) < -1e-6:
        pass

    if origin_L > 1e-3 or origin_R < L_mm - 1e-3:
        notes.append(
            f"Continuous/segment origins at inflection: "
            f"left={origin_L:.0f} mm, right={origin_R:.0f} mm "
            f"(between contraflexure and max +M)."
        )
    else:
        notes.append(
            "Simply-supported origins: left support (0) and right support (L)."
        )
    return origin_L, origin_R, notes


def synthesize_uniform_stud_positions(
    L_mm: float,
    x_maxM_mm: float,
    n_half: int,
    n_rows: int = 1,
) -> list[StudPosition]:
    """
    Place n_half studs uniformly on each side of max M when no four-zone layout
    is provided (matches the discrete half-span n used in shear_connection).
    """
    positions: list[StudPosition] = []
    n_half = max(0, int(n_half))
    n_rows = max(1, int(n_rows))
    if n_half == 0:
        return positions

    # Left segment (origin 0 → x_maxM): n_half locations
    L_left = max(x_maxM_mm, 1e-6)
    if n_half == 1:
        xs_left = [0.5 * L_left]
    else:
        s = L_left / n_half
        xs_left = [s * (i + 0.5) for i in range(n_half)]

    L_right = max(L_mm - x_maxM_mm, 1e-6)
    if n_half == 1:
        xs_right = [x_maxM_mm + 0.5 * L_right]
    else:
        s = L_right / n_half
        xs_right = [x_maxM_mm + s * (i + 0.5) for i in range(n_half)]

    for x in xs_left:
        for row in range(n_rows):
            positions.append(StudPosition(x_mm=float(x), zone_name="uniform L", row=row))
    for x in xs_right:
        for row in range(n_rows):
            positions.append(StudPosition(x_mm=float(x), zone_name="uniform R", row=row))
    return positions


def _build_stations(
    L_mm: float,
    x_maxM_mm: float,
    origin_L: float,
    origin_R: float,
    stud_xs: Sequence[float],
    diagram_x: Optional[np.ndarray],
    n_even: int = 31,
) -> np.ndarray:
    pts = {0.0, L_mm, x_maxM_mm, origin_L, origin_R}
    for x in stud_xs:
        pts.add(float(x))
    # Evenly spaced detailing stations
    for i in range(n_even):
        pts.add(L_mm * i / (n_even - 1) if n_even > 1 else 0.0)
    if diagram_x is not None and len(diagram_x) > 0:
        # subsample diagram (~ every few stations) for moment fidelity
        step = max(1, len(diagram_x) // 40)
        for xi in diagram_x[::step]:
            pts.add(float(xi))
    xs = np.array(sorted(p for p in pts if 0.0 - 1e-9 <= p <= L_mm + 1e-9), dtype=float)
    # dedupe close points
    if len(xs) < 2:
        return np.array([0.0, L_mm], dtype=float)
    keep = [xs[0]]
    for x in xs[1:]:
        if x - keep[-1] > 0.5:  # ≥ 0.5 mm apart
            keep.append(x)
    return np.array(keep, dtype=float)


def cumulative_composite_action(
    L_mm: float,
    C_full_kN: float,
    Qn_kN: float,
    *,
    x_mm_diag: np.ndarray,
    M_kNmm: np.ndarray,
    x_maxM_mm: Optional[float] = None,
    stud_layout: Optional[StudLayoutResult] = None,
    n_studs_half_span: Optional[int] = None,
    n_rows: int = 1,
    n_even_stations: int = 31,
    tol_kN: float = 0.05,
) -> CumulativeCompositeResult:
    """
    Build cumulative provided ΣQn and moment-proportional required force along span.

    Parameters
    ----------
    C_full_kN :
        Full-composite force min(As Fy, 0.85 f'c Ac).
    Qn_kN :
        Nominal strength per stud.
    x_mm_diag, M_kNmm :
        Governing occupancy moment diagram (sagging positive).
    stud_layout :
        Four-zone (or N-zone) layout if available; else uniform half-span synthesis.
    n_studs_half_span :
        Used when stud_layout is None (same n as shear_connection half-span check).
    """
    notes = [
        "Cumulative composite action (detailing/development plot) — AISC I3.2d / I8.",
        "F_req(x) = C_full · M(x)/M_max (moment-proportional), clipped to [0, C_full].",
        "ΣQn_prov(x) = sum of Qn for studs between the nearer origin "
        "(support or inflection) and x, toward max +M.",
        "α(x) = ΣQn_prov(x) / C_full. Not a substitute for the discrete half-span "
        "stud count check already implemented.",
    ]

    if x_maxM_mm is None:
        i_max = int(np.argmax(M_kNmm))
        x_maxM_mm = float(x_mm_diag[i_max])
    M_max = float(np.max(M_kNmm))
    if M_max < 1e-9:
        M_max = 1e-9

    origin_L, origin_R, o_notes = _positive_segment_origins(
        L_mm, x_maxM_mm, x_mm_diag, M_kNmm
    )
    notes.extend(o_notes)

    # Stud positions
    if stud_layout is not None and stud_layout.positions:
        positions = list(stud_layout.positions)
        notes.append(
            f"Stud positions from layout: {len(positions)} studs on span."
        )
    else:
        n_half = int(n_studs_half_span or 0)
        positions = synthesize_uniform_stud_positions(
            L_mm, x_maxM_mm, n_half, n_rows=n_rows
        )
        notes.append(
            f"Uniform stud synthesis: {n_half} each side of max M "
            f"→ {len(positions)} positions (n_rows={n_rows})."
        )

    stud_xs = [p.x_mm for p in positions]
    # Each position is one stud; Qn per position
    stud_Qn = [(p.x_mm, Qn_kN) for p in positions]

    stations = _build_stations(
        L_mm,
        x_maxM_mm,
        origin_L,
        origin_R,
        stud_xs,
        x_mm_diag,
        n_even=n_even_stations,
    )

    M_at = np.interp(stations, x_mm_diag, M_kNmm)
    M_pos = np.maximum(M_at, 0.0)
    ratio_M = np.clip(M_pos / M_max, 0.0, 1.0)
    F_env = C_full_kN * ratio_M  # same shape both sides for SS

    # Left-origin curve: meaningful on [origin_L, x_maxM]; 0 elsewhere for display
    F_left = np.where(
        (stations >= origin_L - 1e-9) & (stations <= x_maxM_mm + 1e-9),
        F_env,
        0.0,
    )
    # Right-origin curve: meaningful on [x_maxM, origin_R]
    F_right = np.where(
        (stations >= x_maxM_mm - 1e-9) & (stations <= origin_R + 1e-9),
        F_env,
        0.0,
    )
    # Governing envelope along span (piecewise from nearer origin)
    F_req = np.where(stations <= x_maxM_mm, F_left, F_right)
    # Outside positive segment → 0
    F_req = np.where(
        (stations < origin_L - 1e-9) | (stations > origin_R + 1e-9),
        0.0,
        F_req,
    )
    F_req = np.clip(F_req, 0.0, C_full_kN)

    # Provided cumulative ΣQn from nearer origin
    SumQn = np.zeros_like(stations)
    for i, x in enumerate(stations):
        if x <= x_maxM_mm:
            # from origin_L to x (inclusive)
            SumQn[i] = sum(
                q for sx, q in stud_Qn if origin_L - 1e-6 <= sx <= x + 1e-6
            )
        else:
            # from x to origin_R (inclusive) — accumulate from right
            SumQn[i] = sum(
                q for sx, q in stud_Qn if x - 1e-6 <= sx <= origin_R + 1e-6
            )

    C = max(C_full_kN, 1e-12)
    alpha = SumQn / C
    with np.errstate(divide="ignore", invalid="ignore"):
        alpha_vs = np.where(F_req > tol_kN, SumQn / F_req, np.inf)
    shortfall = np.maximum(F_req - SumQn, 0.0)
    ok = SumQn + tol_kN >= F_req

    notes.append(
        f"C_full = {C_full_kN:.1f} kN; x_maxM = {x_maxM_mm:.0f} mm; "
        f"Qn = {Qn_kN:.2f} kN/stud; stations = {len(stations)}."
    )
    # Midspan / max-M check note
    i_mid = int(np.argmin(np.abs(stations - x_maxM_mm)))
    notes.append(
        f"At max +M: ΣQn_prov = {SumQn[i_mid]:.1f} kN "
        f"({100.0 * alpha[i_mid]:.0f}% of C_full); F_req = {F_req[i_mid]:.1f} kN."
    )

    return CumulativeCompositeResult(
        x_mm=stations,
        F_req_kN=F_req,
        SumQn_prov_kN=SumQn,
        alpha=alpha,
        F_req_from_left_kN=F_left,
        F_req_from_right_kN=F_right,
        alpha_vs_req=alpha_vs,
        shortfall_kN=shortfall,
        ok=ok,
        C_full_kN=C_full_kN,
        x_maxM_mm=x_maxM_mm,
        origin_left_mm=origin_L,
        origin_right_mm=origin_R,
        notes=notes,
    )
