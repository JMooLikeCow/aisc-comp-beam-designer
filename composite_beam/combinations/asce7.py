"""ASCE 7-16 / 7-22 gravity load combinations as factor dictionaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ASCEEdition(str, Enum):
    ASCE7_16 = "ASCE7-16"
    ASCE7_22 = "ASCE7-22"


@dataclass
class Combination:
    """Load combination as factor dict keyed by load-case role."""

    name: str
    factors: dict[str, float]  # keys: D, L, Lr, S, R, W, E, C, ...
    method: str = "LRFD"  # LRFD or ASD
    edition: str = "ASCE7-22"
    notes: str = ""

    def factor(self, key: str) -> float:
        return self.factors.get(key, 0.0)


# Role keys used across the engine
ROLE_D = "D"
ROLE_L = "L"
ROLE_LR = "Lr"
ROLE_S = "S"
ROLE_R = "R"
ROLE_W = "W"
ROLE_E = "E"
ROLE_C = "C"  # construction live
ROLE_SDL = "SDL"


def lrfd_gravity_combinations(edition: ASCEEdition = ASCEEdition.ASCE7_22) -> list[Combination]:
    """
    ASCE 7 LRFD basic gravity combinations (simplified set for composite beams).

    ASCE 7-16 §2.3.1 / ASCE 7-22 §2.3.1 (same for basic D+L gravity):
      1.4 D
      1.2 D + 1.6 L + 0.5(Lr or S or R)
      1.2 D + 1.6(Lr or S or R) + (L or 0.5W)
    Construction (wet concrete) is NOT an occupancy combo — keep separate.
    """
    ed = edition.value
    # Note: 7-16 vs 7-22 basic gravity factors for D and L are the same.
    # Divergence flags are surfaced where wind/seismic differ; gravity happy-path shared.
    combos = [
        Combination("1.4D", {ROLE_D: 1.4}, "LRFD", ed, "ASCE 7 §2.3.1"),
        Combination(
            "1.2D+1.6L",
            {ROLE_D: 1.2, ROLE_L: 1.6},
            "LRFD",
            ed,
            "ASCE 7 §2.3.1 (Lr/S/R omitted if zero)",
        ),
        Combination(
            "1.2D+1.6L+0.5Lr",
            {ROLE_D: 1.2, ROLE_L: 1.6, ROLE_LR: 0.5},
            "LRFD",
            ed,
            "ASCE 7 §2.3.1",
        ),
        Combination(
            "1.2D+1.6Lr+0.5L",
            {ROLE_D: 1.2, ROLE_LR: 1.6, ROLE_L: 0.5},
            "LRFD",
            ed,
            "ASCE 7 §2.3.1",
        ),
    ]
    return combos


def asd_gravity_combinations(edition: ASCEEdition = ASCEEdition.ASCE7_22) -> list[Combination]:
    """ASCE 7 ASD basic gravity combinations §2.4.1."""
    ed = edition.value
    return [
        Combination("D", {ROLE_D: 1.0}, "ASD", ed, "ASCE 7 §2.4.1"),
        Combination("D+L", {ROLE_D: 1.0, ROLE_L: 1.0}, "ASD", ed, "ASCE 7 §2.4.1"),
        Combination(
            "D+0.75L+0.75Lr",
            {ROLE_D: 1.0, ROLE_L: 0.75, ROLE_LR: 0.75},
            "ASD",
            ed,
            "ASCE 7 §2.4.1",
        ),
    ]


def construction_combinations(edition: ASCEEdition = ASCEEdition.ASCE7_22) -> list[Combination]:
    """
    Construction (unshored) combinations — separate from occupancy.

    Typical practice / AISC Design Guide 5 guidance:
      LRFD: 1.2 D_wet + 1.6 C  (C = construction live)
      ASD:  D_wet + C
    These MUST NOT be mixed with occupancy 1.2D+1.6L in tests or reporting.
    """
    ed = edition.value
    return [
        Combination(
            "1.2Dwet+1.6C",
            {ROLE_D: 1.2, ROLE_C: 1.6},
            "LRFD",
            ed,
            "Construction unshored (not an occupancy combo)",
        ),
        Combination(
            "Dwet+C",
            {ROLE_D: 1.0, ROLE_C: 1.0},
            "ASD",
            ed,
            "Construction unshored ASD",
        ),
    ]


@dataclass
class CombinationSet:
    """Built-in + up to 5 custom combinations."""

    edition: ASCEEdition = ASCEEdition.ASCE7_22
    method: str = "LRFD"
    include_construction: bool = True
    custom: list[Combination] = field(default_factory=list)

    def all(self) -> list[Combination]:
        if self.method.upper() == "ASD":
            base = asd_gravity_combinations(self.edition)
        else:
            base = lrfd_gravity_combinations(self.edition)
        out = list(base)
        if self.include_construction:
            out.extend(
                c
                for c in construction_combinations(self.edition)
                if c.method == self.method.upper() or True
            )
        # Cap custom at 5
        out.extend(self.custom[:5])
        return out

    def add_custom(self, name: str, factors: dict[str, float], method: str = "LRFD") -> None:
        if len(self.custom) >= 5:
            raise ValueError("At most 5 custom combinations allowed")
        self.custom.append(
            Combination(name=name, factors=factors, method=method, edition=self.edition.value)
        )


def edition_flags(edition: ASCEEdition) -> list[str]:
    """Surface ASCE 7-16 vs 7-22 divergence notes for detailed calcs."""
    flags = [
        f"Locked ASCE edition: {edition.value}",
        "Basic LRFD gravity factors for D and L are identical in ASCE 7-16 and 7-22 §2.3.1.",
    ]
    if edition == ASCEEdition.ASCE7_22:
        flags.append(
            "ASCE 7-22: wind/seismic combination details differ from 7-16 in Ch. 2 "
            "and risk-category tables; gravity happy-path unaffected."
        )
    else:
        flags.append(
            "ASCE 7-16: using 7-16 combination numbering; confirm W/E factors if lateral used."
        )
    return flags
