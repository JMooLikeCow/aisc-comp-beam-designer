"""Concrete punching shear around headed studs — ACI 318 two-way shear.

AISC 360 does not provide a slab punching check around shear connectors.
This module applies ACI 318-19 / 318M-19 §22.6 (two-way shear) to a single
stud and a simple group perimeter when studs are closer than 4d.

SI (ACI 318M): vc = 0.33 λ √f'c  (MPa)  — equivalent to 4 λ √f'c (psi).
φ = 0.75 (ACI 21.2.1, shear).
Critical section taken at d/2 from the stud shank: b0 = π (ds + d).
Effective depth d = solid slab thickness above deck (ribs neglected).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PunchingResult:
    """Punching shear around headed studs."""

    b0_mm: float
    d_mm: float
    vc_MPa: float
    Vc_kN: float
    phi: float
    phiVc_kN: float
    Vu_kN: float
    DCR: float
    passes: bool
    group_phiVc_kN: float
    group_Vu_kN: float
    group_DCR: float
    notes: list[str] = field(default_factory=list)


def punching_one_stud(
    ds_mm: float,
    t_solid_mm: float,
    fc_MPa: float,
    Vu_kN: float,
    lambda_nwc: float = 1.0,
    phi: float = 0.75,
    beta: float = 1.0,
    alpha_s: float = 40.0,
) -> PunchingResult:
    """
    Single-stud punching — ACI 318-19 §22.6.5.2 (ACI 318M SI coefficients).

    vc = min(
        0.33 λ √f'c,
        0.17 (1 + 2/β) λ √f'c,
        0.083 (2 + αs d / b0) λ √f'c,
    )
    Vc = vc * b0 * d
    Interior stud: αs = 40; circular β = 1.

    FLAG: ACI 318-14 used the same 4√f'c / 0.33√f'c two-way baseline;
    ACI 318-19 reorganized §22.6 but the interior two-way coefficients match.
    """
    notes = [
        "Punching around studs is an ACI 318 slab check (not AISC 360 I8).",
        "ACI 318-19 / 318M-19 §22.6.5.2; φ=0.75 (ACI 21.2.1). "
        "ACI 318-14 §22.6 used the same 4λ√f'c (psi) / 0.33λ√f'c (MPa) interior cap.",
        "d taken as solid thickness above deck; rib concrete neglected (conservative).",
    ]
    d = max(t_solid_mm, 1e-6)
    b0 = math.pi * (ds_mm + d)
    root = math.sqrt(max(fc_MPa, 0.0))
    vc1 = 0.33 * lambda_nwc * root
    vc2 = 0.17 * (1.0 + 2.0 / max(beta, 0.1)) * lambda_nwc * root
    vc3 = 0.083 * (2.0 + alpha_s * d / b0) * lambda_nwc * root
    vc = min(vc1, vc2, vc3)
    Vc_N = vc * b0 * d  # N
    Vc = Vc_N / 1000.0
    phiVc = phi * Vc
    DCR = Vu_kN / phiVc if phiVc > 0 else float("inf")
    notes.append(
        f"b0=π(ds+d)={b0:.1f} mm; d={d:.1f} mm; "
        f"vc=min({vc1:.3f},{vc2:.3f},{vc3:.3f})={vc:.3f} MPa"
    )
    notes.append(
        f"φVc={phiVc:.2f} kN; Vu (stud force)={Vu_kN:.2f} kN; DCR={DCR:.3f} "
        f"→ {'PASS' if DCR <= 1.0 else 'FAIL'}"
    )
    return PunchingResult(
        b0_mm=b0,
        d_mm=d,
        vc_MPa=vc,
        Vc_kN=Vc,
        phi=phi,
        phiVc_kN=phiVc,
        Vu_kN=Vu_kN,
        DCR=DCR,
        passes=DCR <= 1.0,
        group_phiVc_kN=phiVc,
        group_Vu_kN=Vu_kN,
        group_DCR=DCR,
        notes=notes,
    )


def punching_with_group(
    ds_mm: float,
    t_solid_mm: float,
    fc_MPa: float,
    Qn_kN: float,
    min_spacing_mm: float,
    n_rows: int = 1,
    lambda_nwc: float = 1.0,
) -> PunchingResult:
    """
    Single-stud punching plus a group check when s < 4d.

    Group critical section: rectangle around n_rows × 2 studs (or the cluster)
    with perimeter 2*(s + d) + 2*((n_rows-1)*pitch + d) — simplified as
    a pair of adjacent studs along the beam when spacing is tight.
    Vu,group = 2 Qn (two closest studs).
    """
    one = punching_one_stud(ds_mm, t_solid_mm, fc_MPa, Vu_kN=Qn_kN, lambda_nwc=lambda_nwc)
    d = one.d_mm
    notes = list(one.notes)
    group_phi = one.phiVc_kN
    group_Vu = Qn_kN
    group_DCR = one.DCR
    if min_spacing_mm < 4.0 * d and min_spacing_mm > 0:
        # Two-stud group along the beam: perimeter ≈ 2(s + d) + 2(ds + d)
        b0_g = 2.0 * (min_spacing_mm + d) + 2.0 * (ds_mm + d)
        vc = one.vc_MPa
        Vc_g = vc * b0_g * d / 1000.0
        group_phi = one.phi * Vc_g
        group_Vu = 2.0 * Qn_kN
        group_DCR = group_Vu / group_phi if group_phi > 0 else float("inf")
        notes.append(
            f"Group punching (s={min_spacing_mm:.0f} < 4d={4*d:.0f} mm): "
            f"b0,g={b0_g:.0f} mm; φVc,g={group_phi:.1f} kN; "
            f"Vu,g=2 Qn={group_Vu:.1f} kN; DCR,g={group_DCR:.3f}"
        )
    else:
        notes.append(
            f"Group punching not engaged (s={min_spacing_mm:.0f} mm ≥ 4d={4*d:.0f} mm)."
        )
    one.group_phiVc_kN = group_phi
    one.group_Vu_kN = group_Vu
    one.group_DCR = group_DCR
    one.notes = notes
    one.passes = one.DCR <= 1.0 and group_DCR <= 1.0
    return one
