"""Four independent stud-spacing zones along the beam.

Zones are contiguous, non-overlapping intervals of the span. Each zone has
its own center-to-center spacing and optional number of studs across the
flange (rows). Positions are generated from the zone start + spacing/2 so
zone boundaries are not double-counted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StudZone:
    """One spacing zone along the span."""

    name: str
    start_ratio: float  # 0–1 from left support
    end_ratio: float
    spacing_mm: float
    n_rows: int = 1

    def length_mm(self, L_mm: float) -> float:
        return max(0.0, (self.end_ratio - self.start_ratio) * L_mm)


@dataclass
class StudPosition:
    x_mm: float
    zone_name: str
    row: int


@dataclass
class StudLayoutResult:
    """Resolved four-zone layout and counts used for ΣQn and graphics."""

    zones: list[StudZone]
    positions: list[StudPosition]
    n_total: int
    n_left_of_max_M: int
    n_hogging: int
    notes: list[str] = field(default_factory=list)

    def count_between(self, x0_mm: float, x1_mm: float) -> int:
        lo, hi = (x0_mm, x1_mm) if x0_mm <= x1_mm else (x1_mm, x0_mm)
        return sum(1 for p in self.positions if lo - 1e-6 <= p.x_mm <= hi + 1e-6)


def default_four_zones(
    spacing_mm: float = 305.0,
    n_rows: int = 1,
    end_spacing_mm: Optional[float] = None,
) -> list[StudZone]:
    """Four equal-length quarters; optional tighter spacing in the two end zones."""
    end_s = end_spacing_mm if end_spacing_mm is not None else spacing_mm
    mid_s = spacing_mm
    return [
        StudZone("Z1 left end", 0.00, 0.25, end_s, n_rows),
        StudZone("Z2 left mid", 0.25, 0.50, mid_s, n_rows),
        StudZone("Z3 right mid", 0.50, 0.75, mid_s, n_rows),
        StudZone("Z4 right end", 0.75, 1.00, end_s, n_rows),
    ]


def layout_studs(
    L_mm: float,
    zones: list[StudZone],
    x_Mmax_mm: Optional[float] = None,
    hogging_mask_x_mm: Optional[list[float]] = None,
    hogging_mask: Optional[list[bool]] = None,
) -> StudLayoutResult:
    """
    Place studs in four (or N) zones and count those that contribute to ΣQn
    between the left support and the point of maximum sagging moment
    (simply-supported / positive-moment shear connection).
    """
    if len(zones) != 4:
        raise ValueError(f"Expected four stud spacing zones, got {len(zones)}")
    notes = [
        "Four independent stud-spacing zones (user spacing per zone).",
        "Positions at start + s/2, then every s while x < zone end (no double-count at joints).",
    ]
    positions: list[StudPosition] = []
    for z in zones:
        if z.end_ratio <= z.start_ratio or z.spacing_mm <= 0 or z.n_rows < 1:
            notes.append(f"{z.name}: skipped (non-positive length/spacing/rows).")
            continue
        x0 = z.start_ratio * L_mm
        x1 = z.end_ratio * L_mm
        x = x0 + z.spacing_mm / 2.0
        n_zone = 0
        while x < x1 - 1e-6:
            for row in range(z.n_rows):
                positions.append(StudPosition(x_mm=x, zone_name=z.name, row=row))
                n_zone += 1
            x += z.spacing_mm
        notes.append(
            f"{z.name}: {z.start_ratio:.2f}L–{z.end_ratio:.2f}L, s={z.spacing_mm:.0f} mm, "
            f"{z.n_rows} row(s) → {n_zone} studs"
        )

    x_max = x_Mmax_mm if x_Mmax_mm is not None else L_mm / 2.0
    n_left = sum(1 for p in positions if p.x_mm <= x_max + 1e-6)

    n_hog = 0
    if hogging_mask_x_mm is not None and hogging_mask is not None and hogging_mask_x_mm:
        # interpolate nearest station
        xs = hogging_mask_x_mm
        mask = hogging_mask
        for p in positions:
            # nearest
            j = min(range(len(xs)), key=lambda i: abs(xs[i] - p.x_mm))
            if mask[j]:
                n_hog += 1
        notes.append(f"Studs in hogging stations (M<0): {n_hog}")

    notes.append(f"Total studs on span: {len(positions)}; left of max M (x≤{x_max:.0f} mm): {n_left}")
    return StudLayoutResult(
        zones=list(zones),
        positions=positions,
        n_total=len(positions),
        n_left_of_max_M=n_left,
        n_hogging=n_hog,
        notes=notes,
    )
