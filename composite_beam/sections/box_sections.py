"""Custom welded box (closed rectangular) section properties.

Thin-walled welded box: two flanges (width B, thickness tf) and two webs
(clear height H−2 tf, thickness tw). Compatible with WShape so existing
flexure / LTB / classification paths can consume it via section_kind='BOX'.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from composite_beam.sections.w_shapes import WShape
from composite_beam.units import IN_PER_MM


STEEL_GAMMA_KNM3 = 77.0  # ≈ 490 pcf


@dataclass
class WeldedBoxDims:
    """User dimensions for a welded box (overall, mm)."""

    H_mm: float
    B_mm: float
    tf_mm: float
    tw_mm: float
    designation: str = "BOX"


def box_properties(
    H_mm: float,
    B_mm: float,
    tf_mm: float,
    tw_mm: float,
    designation: str = "BOX",
    W_kNm: Optional[float] = None,
) -> WShape:
    """
    Elastic and plastic properties of a doubly-symmetric welded box.

    A  = 2 B tf + 2 (H − 2 tf) tw
    Ix, Iy from parallel-axis plate idealization
    Zx = B tf (H − tf) + tw (H − 2 tf)² / 2
    Closed Saint-Venant J = 4 Am² / ∮ ds/t   (Bredt)
    Cw ≈ 0 for a closed section (warping restraint not required)
    """
    if H_mm <= 2.0 * tf_mm or B_mm <= 2.0 * tw_mm:
        raise ValueError("Box clear height/width must be positive (H>2 tf, B>2 tw).")

    hw = H_mm - 2.0 * tf_mm
    A = 2.0 * B_mm * tf_mm + 2.0 * hw * tw_mm

    # Ix about major (horizontal) axis through centroid
    Ix_fl = 2.0 * (
        B_mm * tf_mm**3 / 12.0 + B_mm * tf_mm * (H_mm / 2.0 - tf_mm / 2.0) ** 2
    )
    Ix_web = 2.0 * (tw_mm * hw**3 / 12.0)
    Ix = Ix_fl + Ix_web

    # Iy about minor (vertical) axis
    Iy_fl = 2.0 * (tf_mm * B_mm**3 / 12.0)
    Iy_web = 2.0 * (
        hw * tw_mm**3 / 12.0 + hw * tw_mm * (B_mm / 2.0 - tw_mm / 2.0) ** 2
    )
    Iy = Iy_fl + Iy_web

    Sx = Ix / (H_mm / 2.0)
    Sy = Iy / (B_mm / 2.0)
    # Plastic moduli (doubly symmetric)
    Zx = B_mm * tf_mm * (H_mm - tf_mm) + tw_mm * hw**2 / 2.0
    Zy = tf_mm * B_mm**2 / 2.0 + hw * tw_mm * (B_mm - tw_mm)

    # Bredt torsion: median-line rectangle
    bm = B_mm - tw_mm
    hm = H_mm - tf_mm
    Am = bm * hm
    oint = 2.0 * bm / tf_mm + 2.0 * hm / tw_mm
    J = 4.0 * Am**2 / oint if oint > 0 else 0.0

    Cw = 0.0  # closed
    rx = (Ix / A) ** 0.5
    ry = (Iy / A) ** 0.5
    ho = H_mm - tf_mm
    # rts unused for F7 but keep a positive placeholder
    rts = ry

    if W_kNm is None:
        W_kNm = A * 1e-6 * STEEL_GAMMA_KNM3

    return WShape(
        designation=designation,
        W_kNm=W_kNm,
        A_mm2=A,
        d_mm=H_mm,
        tw_mm=tw_mm,
        bf_mm=B_mm,
        tf_mm=tf_mm,
        Ix_mm4=Ix,
        Sx_mm3=Sx,
        rx_mm=rx,
        Zx_mm3=Zx,
        Iy_mm4=Iy,
        Sy_mm3=Sy,
        ry_mm=ry,
        Zy_mm3=Zy,
        J_mm4=J,
        Cw_mm6=Cw,
        rts_mm=rts,
        ho_mm=ho,
        custom=True,
        section_kind="BOX",
        W_lb_ft=W_kNm / 0.0145939,
        A_in2=A / (25.4**2),
        d_in=H_mm * IN_PER_MM,
        tw_in=tw_mm * IN_PER_MM,
        bf_in=B_mm * IN_PER_MM,
        tf_in=tf_mm * IN_PER_MM,
        Ix_in4=Ix / (25.4**4),
        Sx_in3=Sx / (25.4**3),
        Zx_in3=Zx / (25.4**3),
        Iy_in4=Iy / (25.4**4),
        ry_in=ry * IN_PER_MM,
        J_in4=J / (25.4**4),
        Cw_in6=0.0,
        rts_in=rts * IN_PER_MM,
        ho_in=ho * IN_PER_MM,
    )
