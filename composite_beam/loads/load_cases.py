"""Load case data structures for gravity, lateral, and thermal loads."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LoadCaseType(str, Enum):
    """User-listed load case categories (model all; not all need values)."""

    SELF_WEIGHT = "SW"
    ADDITIONAL_SELF_WEIGHT = "add_SW"
    SUPERIMPOSED_DEAD = "SDL"
    MISC_DEAD_1 = "misc_D1"
    MISC_DEAD_2 = "misc_D2"
    MISC_DEAD_3 = "misc_D3"
    LIVE_REDUCIBLE = "L_reducible"
    LIVE_NON_REDUCIBLE = "L_nonreducible"
    MISC_LIVE_1 = "misc_L1"
    MISC_LIVE_2 = "misc_L2"
    MISC_LIVE_3 = "misc_L3"
    SEISMIC_1 = "E1"
    SEISMIC_2 = "E2"
    SEISMIC_3 = "E3"
    SEISMIC_4 = "E4"
    WIND_1 = "W1"
    WIND_2 = "W2"
    WIND_3 = "W3"
    WIND_4 = "W4"
    THERMAL = "T"
    CONSTRUCTION = "C"  # construction live / temporary


class PointLoadSpec(str, Enum):
    RATIO = "ratio"  # fraction of span from left support
    ABSOLUTE = "absolute"  # mm from left support


@dataclass
class PointLoad:
    """Concentrated force (and optional axial) on the beam."""

    P_kN: float
    location: float  # ratio 0–1 or absolute mm
    spec: PointLoadSpec = PointLoadSpec.RATIO
    axial_kN: float = 0.0
    label: str = ""


@dataclass
class UDL:
    """Uniformly distributed load."""

    w_kNpm: float  # kN per m of beam length
    axial_kNpm: float = 0.0
    label: str = ""


@dataclass
class LoadCase:
    """Single named load case with UDL and/or point loads."""

    name: str
    case_type: LoadCaseType
    udl: Optional[UDL] = None
    points: list[PointLoad] = field(default_factory=list)
    is_dead: bool = False
    is_live: bool = False
    is_construction: bool = False
    reducible: bool = False

    def total_udl_kNpm(self) -> float:
        return self.udl.w_kNpm if self.udl else 0.0


@dataclass
class LoadSet:
    """Collection of load cases for a design run."""

    cases: list[LoadCase] = field(default_factory=list)

    def by_type(self, t: LoadCaseType) -> list[LoadCase]:
        return [c for c in self.cases if c.case_type == t]

    def dead_cases(self) -> list[LoadCase]:
        return [c for c in self.cases if c.is_dead]

    def live_cases(self) -> list[LoadCase]:
        return [c for c in self.cases if c.is_live]

    def add(self, case: LoadCase) -> None:
        self.cases.append(case)


def default_empty_load_set() -> LoadSet:
    """Scaffold all required load-case slots (zero magnitude)."""
    specs = [
        ("Self weight", LoadCaseType.SELF_WEIGHT, True, False, False, False),
        ("Additional SW", LoadCaseType.ADDITIONAL_SELF_WEIGHT, True, False, False, False),
        ("SDL", LoadCaseType.SUPERIMPOSED_DEAD, True, False, False, False),
        ("Misc D1", LoadCaseType.MISC_DEAD_1, True, False, False, False),
        ("Misc D2", LoadCaseType.MISC_DEAD_2, True, False, False, False),
        ("Misc D3", LoadCaseType.MISC_DEAD_3, True, False, False, False),
        ("Live (reducible)", LoadCaseType.LIVE_REDUCIBLE, False, True, False, True),
        ("Live (non-red.)", LoadCaseType.LIVE_NON_REDUCIBLE, False, True, False, False),
        ("Misc L1", LoadCaseType.MISC_LIVE_1, False, True, False, False),
        ("Misc L2", LoadCaseType.MISC_LIVE_2, False, True, False, False),
        ("Misc L3", LoadCaseType.MISC_LIVE_3, False, True, False, False),
        ("Seismic E1", LoadCaseType.SEISMIC_1, False, False, False, False),
        ("Seismic E2", LoadCaseType.SEISMIC_2, False, False, False, False),
        ("Seismic E3", LoadCaseType.SEISMIC_3, False, False, False, False),
        ("Seismic E4", LoadCaseType.SEISMIC_4, False, False, False, False),
        ("Wind W1", LoadCaseType.WIND_1, False, False, False, False),
        ("Wind W2", LoadCaseType.WIND_2, False, False, False, False),
        ("Wind W3", LoadCaseType.WIND_3, False, False, False, False),
        ("Wind W4", LoadCaseType.WIND_4, False, False, False, False),
        ("Thermal", LoadCaseType.THERMAL, False, False, False, False),
        ("Construction", LoadCaseType.CONSTRUCTION, False, False, True, False),
    ]
    ls = LoadSet()
    for name, t, dead, live, constr, red in specs:
        ls.add(
            LoadCase(
                name=name,
                case_type=t,
                is_dead=dead,
                is_live=live,
                is_construction=constr,
                reducible=red,
            )
        )
    return ls
