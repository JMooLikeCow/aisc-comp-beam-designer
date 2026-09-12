"""Effective slab width per AISC 360-22 §I2.1a (and 360-16 notes)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class BeamLocation(str, Enum):
    INTERIOR = "interior"
    EDGE = "edge"


class AISCEdition(str, Enum):
    AISC360_16 = "AISC360-16"
    AISC360_22 = "AISC360-22"


@dataclass
class EffectiveWidthResult:
    """Effective width beff (mm) with code citations and edition flags."""

    beff_mm: float
    beff_left_mm: float
    beff_right_mm: float
    L_mm: float
    s_left_mm: float
    s_right_mm: float
    location: BeamLocation
    edition: AISCEdition
    manual_override: bool
    notes: list[str]


def effective_width(
    L_mm: float,
    spacing_left_mm: float,
    spacing_right_mm: float,
    location: BeamLocation = BeamLocation.INTERIOR,
    edition: AISCEdition = AISCEdition.AISC360_22,
    beff_override_mm: Optional[float] = None,
) -> EffectiveWidthResult:
    """
    AISC 360-22 §I2.1a — Effective Width of Concrete Slab.

    The effective width of the concrete slab shall not exceed:
      Interior: sum of
        - L/8 each side of beam centerline
        - one-half the distance to the adjacent beam centerline each side
        - distance to edge of slab each side
      Edge beam: similarly limited on the exterior side by the actual overhang.

    Implementation model:
      For each side i: beff,i = min(L/8, s_i/2) for interior adjacent spacing s_i;
      for an exterior (edge) free side: beff,ext = min(L/8, overhang).
      Total beff = beff,left + beff,right (beam web thickness neglected — standard).

    360-16 vs 360-22: wording cleaned up in 360-22 I2.1a but numerical limits
    for building beams are the same (L/8 and half spacing). Flag both editions.
    """
    notes: list[str] = [
        f"Locked AISC edition: {edition.value}",
        "AISC 360-22 §I2.1a (Effective Width of Concrete Slab).",
    ]
    if edition == AISCEdition.AISC360_16:
        notes.append(
            "FLAG: AISC 360-16 §I2.1a — same L/8 and half-spacing limits; "
            "360-22 clarifies edge-beam overhang language."
        )
    else:
        notes.append(
            "FLAG: Using AISC 360-22 §I2.1a; numerically equivalent to 360-16 for "
            "interior L/8 & s/2 limits."
        )

    if beff_override_mm is not None:
        notes.append(f"Manual override: beff = {beff_override_mm:.1f} mm")
        half = beff_override_mm / 2.0
        return EffectiveWidthResult(
            beff_mm=beff_override_mm,
            beff_left_mm=half,
            beff_right_mm=half,
            L_mm=L_mm,
            s_left_mm=spacing_left_mm,
            s_right_mm=spacing_right_mm,
            location=location,
            edition=edition,
            manual_override=True,
            notes=notes,
        )

    L8 = L_mm / 8.0

    if location == BeamLocation.INTERIOR:
        beff_L = min(L8, spacing_left_mm / 2.0)
        beff_R = min(L8, spacing_right_mm / 2.0)
        notes.append(
            f"Interior: beff,L = min(L/8={L8:.1f}, sL/2={spacing_left_mm/2:.1f}) = {beff_L:.1f} mm"
        )
        notes.append(
            f"Interior: beff,R = min(L/8={L8:.1f}, sR/2={spacing_right_mm/2:.1f}) = {beff_R:.1f} mm"
        )
    else:
        # Edge: left = interior side (half spacing), right = overhang (spacing_right as overhang)
        # Convention: spacing_left = distance to adjacent interior beam;
        # spacing_right = overhang to free edge.
        beff_L = min(L8, spacing_left_mm / 2.0)
        beff_R = min(L8, spacing_right_mm)  # overhang, not half
        notes.append(
            f"Edge: interior side beff = min(L/8, s_adj/2) = {beff_L:.1f} mm"
        )
        notes.append(
            f"Edge: exterior overhang beff = min(L/8, overhang={spacing_right_mm:.1f}) = {beff_R:.1f} mm"
        )

    beff = beff_L + beff_R
    notes.append(f"Total beff = {beff:.1f} mm")
    return EffectiveWidthResult(
        beff_mm=beff,
        beff_left_mm=beff_L,
        beff_right_mm=beff_R,
        L_mm=L_mm,
        s_left_mm=spacing_left_mm,
        s_right_mm=spacing_right_mm,
        location=location,
        edition=edition,
        manual_override=False,
        notes=notes,
    )
