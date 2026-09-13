"""Slab / metal deck geometry for composite beams."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from composite_beam.units import MM_PER_IN

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class DeckOrientation(str, Enum):
    NONE = "none"  # solid slab
    PERPENDICULAR = "perpendicular"
    PARALLEL = "parallel"


@dataclass
class SlabConfig:
    """
    Concrete slab on metal deck or solid.

    t_solid_mm: solid thickness above deck (haunch/cover) — for solid slab this is total t.
    hr_mm: rib height of deck
    wr_mm: average rib width (for concrete crushing / Rg)
    orientation: deck ribs relative to beam
    """

    t_solid_mm: float
    hr_mm: float = 0.0
    wr_mm: float = 0.0
    orientation: DeckOrientation = DeckOrientation.NONE
    fc_MPa: float = 27.6  # ~4 ksi
    beff_mm: float = 0.0
    catalog_key: str = "solid"
    weight_kNpm2: float = 0.0  # deck self-weight if any

    @property
    def total_depth_mm(self) -> float:
        """Overall slab depth from top of steel to top of concrete."""
        return self.t_solid_mm + self.hr_mm

    @property
    def y_conc_from_steel_top_mm(self) -> float:
        """Centroid of concrete compression block measured from top of steel flange (approx mid solid)."""
        # For solid: t/2 above steel; for deck: solid part above ribs
        return self.hr_mm + self.t_solid_mm / 2.0


def load_deck_catalog(path: Optional[Path] = None) -> dict:
    p = path or (DATA_DIR / "deck_catalog.json")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def catalog_hr_wr_mm(entry: dict) -> tuple[float, float]:
    """Prefer SI catalog fields; fall back to legacy inch keys."""
    if "hr_mm" in entry:
        hr_mm = float(entry["hr_mm"])
    else:
        hr_mm = float(entry.get("hr_in", 0.0)) * MM_PER_IN
    if "wr_mm" in entry:
        wr_mm = float(entry["wr_mm"])
    else:
        wr_mm = float(entry.get("wr_in", 0.0)) * MM_PER_IN
    return hr_mm, wr_mm


def catalog_weight_kNpm2(entry: dict) -> float:
    if "weight_kNpm2" in entry:
        return float(entry.get("weight_kNpm2") or 0.0)
    # Legacy psf → kPa ≈ kN/m²
    return float(entry.get("weight_psf", 0.0)) * 0.04788025898


def slab_from_catalog(
    key: str,
    t_solid_mm: float,
    fc_MPa: float,
    beff_mm: float = 0.0,
    orientation_override: Optional[DeckOrientation] = None,
    hr_mm_override: Optional[float] = None,
    wr_mm_override: Optional[float] = None,
) -> SlabConfig:
    cat = load_deck_catalog()
    if key not in cat:
        raise KeyError(f"Deck catalog key not found: {key}")
    e = cat[key]
    orient = orientation_override or DeckOrientation(e.get("orientation", "none"))
    hr_mm, wr_mm = catalog_hr_wr_mm(e)
    if hr_mm_override is not None:
        hr_mm = float(hr_mm_override)
    if wr_mm_override is not None:
        wr_mm = float(wr_mm_override)
    return SlabConfig(
        t_solid_mm=t_solid_mm,
        hr_mm=hr_mm,
        wr_mm=wr_mm,
        orientation=orient,
        fc_MPa=fc_MPa,
        beff_mm=beff_mm,
        catalog_key=key,
        weight_kNpm2=catalog_weight_kNpm2(e),
    )
