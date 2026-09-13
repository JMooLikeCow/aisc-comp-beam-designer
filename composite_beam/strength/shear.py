"""Steel beam web shear strength — AISC 360 Chapter G (rolled I / W)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from composite_beam.sections.w_shapes import WShape
from composite_beam.units import ES_MPA


@dataclass
class ShearStrengthResult:
    """AISC Chapter G web shear check (steel beam; not stud / punching shear)."""

    Vu_kN: float
    Vn_kN: float
    phi: float  # φv (LRFD) or 1/Ωv (ASD) applied to Vn → available
    phiVn_kN: float  # available shear strength (φVn or Vn/Ω)
    Omega: float
    DCR: float
    passes: bool
    Aw_mm2: float
    Cv1: float
    h_tw: float
    kv: float
    method: str  # "LRFD" or "ASD"
    section_ref: str
    notes: list[str]


def web_shear_strength(
    shape: WShape,
    Fy_MPa: float,
    Vu_kN: float,
    *,
    method: str = "LRFD",
    E_MPa: float = ES_MPA,
    a_h: float | None = None,
) -> ShearStrengthResult:
    """
    Nominal and available web shear strength per AISC 360-22 §G2.

    Rolled I / W (and similar doubly-symmetric I):
      Aw = d · tw                                           (G2.1)
      Vn = 0.60 Fy Aw Cv1                                   (Eq. G2-1)

    G2.1(a) — webs of rolled I-shaped members with h/tw ≤ 2.24 √(E/Fy):
      φv = 1.00 (LRFD), Ωv = 1.50 (ASD); Cv1 = 1.0

    G2.1(b) — other doubly symmetric / singly symmetric I and channels
    without tension field (unstiffened web: a/h > 3 or unknown → kv = 5):
      φv = 0.90 (LRFD), Ωv = 1.67 (ASD)
      Cv1 = 1.0 when h/tw ≤ 1.10 √(kv E/Fy)
      Cv1 = 1.10 √(kv E/Fy) / (h/tw) when h/tw > 1.10 √(kv E/Fy)

    h/tw approximated as (d − 2 tf)/tw (fillet neglected → slightly conservative).
    Longitudinal / stud shear connection remains separate (Chapter I); punching is ACI.
    """
    notes: list[str] = [
        "AISC 360-22 Chapter G steel web shear (not stud longitudinal shear; not ACI punching).",
    ]
    method_u = method.upper()
    d = shape.d_mm
    tw = shape.tw_mm
    # Clear web depth approx. (fillets neglected — conservative for h/tw)
    h = max(d - 2.0 * shape.tf_mm, 1e-9)
    h_tw = h / tw if tw > 0 else float("inf")
    Aw = d * tw  # G2.1 rolled I: Aw = d tw
    notes.append(f"Aw = d·tw = {d:.2f}·{tw:.3f} = {Aw:.1f} mm² (AISC G2.1)")
    notes.append(
        f"h/tw ≈ (d−2tf)/tw = {h_tw:.2f} (fillet neglected; Manual h/tw may be slightly smaller)"
    )

    limit_a = 2.24 * math.sqrt(E_MPa / Fy_MPa) if Fy_MPa > 0 else 0.0
    use_g21a = (
        getattr(shape, "section_kind", "W") != "BOX"
        and h_tw <= limit_a + 1e-9
    )

    if use_g21a:
        Cv1 = 1.0
        kv = 5.0  # unused under G2.1(a)
        phi_v = 1.00
        Omega_v = 1.50
        section_ref = "G2.1(a)"
        notes.append(
            f"G2.1(a): h/tw={h_tw:.2f} ≤ 2.24√(E/Fy)={limit_a:.2f} → Cv1=1.0; "
            f"φv=1.00 (LRFD), Ωv=1.50 (ASD)"
        )
    else:
        # Unstiffened: a/h unknown or > 3 → kv = 5 (G2.1(b) / User Note)
        if a_h is not None and a_h <= 3.0 and a_h > 0:
            kv = 5.0 + 5.0 / (a_h**2)
        else:
            kv = 5.0
        threshold = 1.10 * math.sqrt(kv * E_MPa / Fy_MPa) if Fy_MPa > 0 else 0.0
        if h_tw <= threshold + 1e-9:
            Cv1 = 1.0
            notes.append(
                f"G2.1(b): h/tw={h_tw:.2f} ≤ 1.10√(kv E/Fy)={threshold:.2f} (kv={kv:.2f}) → Cv1=1.0"
            )
        else:
            Cv1 = threshold / h_tw
            notes.append(
                f"G2.1(b): h/tw={h_tw:.2f} > 1.10√(kv E/Fy)={threshold:.2f} (kv={kv:.2f}) → "
                f"Cv1={Cv1:.4f}"
            )
        phi_v = 0.90
        Omega_v = 1.67
        section_ref = "G2.1(b)"
        notes.append(f"G2.1(b): φv=0.90 (LRFD), Ωv=1.67 (ASD)")
        if getattr(shape, "section_kind", "W") == "BOX":
            notes.append("Box section: treated under G2.1(b) with Aw=d·tw (web pair not doubled).")

    # Eq. G2-1: Vn = 0.60 Fy Aw Cv1 ; Fy MPa=N/mm², Aw mm² → N → /1000 = kN
    Vn = 0.60 * Fy_MPa * Aw * Cv1 / 1000.0
    notes.append(f"Vn = 0.60 Fy Aw Cv1 = {Vn:.2f} kN (Eq. G2-1)")

    if method_u == "ASD":
        avail_factor = 1.0 / Omega_v
        phiVn = Vn / Omega_v
        notes.append(f"ASD: Vn/Ωv = {Vn:.2f}/{Omega_v:.2f} = {phiVn:.2f} kN")
    else:
        avail_factor = phi_v
        phiVn = phi_v * Vn
        notes.append(f"LRFD: φv Vn = {phi_v:.2f}·{Vn:.2f} = {phiVn:.2f} kN")

    DCR = Vu_kN / phiVn if phiVn > 0 else float("inf")
    passes = DCR <= 1.0 + 1e-9
    notes.append(
        f"Vu={Vu_kN:.2f} kN; available={phiVn:.2f} kN; DCR={DCR:.3f} "
        f"{'PASS' if passes else 'FAIL'} ({section_ref})"
    )

    return ShearStrengthResult(
        Vu_kN=Vu_kN,
        Vn_kN=Vn,
        phi=avail_factor,
        phiVn_kN=phiVn,
        Omega=Omega_v,
        DCR=DCR,
        passes=passes,
        Aw_mm2=Aw,
        Cv1=Cv1,
        h_tw=h_tw,
        kv=kv,
        method=method_u,
        section_ref=section_ref,
        notes=notes,
    )
