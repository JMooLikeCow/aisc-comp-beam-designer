"""Section classification per AISC 360-22 Table B4.1b (flexure)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from composite_beam.sections.w_shapes import WShape


class Compactness(str, Enum):
    COMPACT = "compact"
    NONCOMPACT = "noncompact"
    SLENDER = "slender"


@dataclass
class ClassificationResult:
    """Flange and web compactness for flexure (Table B4.1b)."""

    flange: Compactness
    web: Compactness
    lambda_f: float
    lambda_pf: float
    lambda_rf: float
    lambda_w: float
    lambda_pw: float
    lambda_rw: float
    overall: Compactness
    notes: list[str]

    @property
    def is_compact(self) -> bool:
        return self.overall == Compactness.COMPACT


def classify_flexure(shape: "WShape", Fy_MPa: float, E_MPa: float = 200_000.0) -> ClassificationResult:
    """
    Classify rolled I-shaped member flanges and web for flexure.

    AISC 360-22 Table B4.1b:
      Flange (case 10): λ = bf/(2 tf)
        λpf = 0.38√(E/Fy)
        λrf = 1.0√(E/Fy)
      Web (case 15): λ = h/tw
        λpw = 3.76√(E/Fy)
        λrw = 5.70√(E/Fy)

    Overall compact only if both flange and web are compact.
    Plastic Mn (I3.2a) requires compact; otherwise use elastic I3.2b.
    """
    root = (E_MPa / Fy_MPa) ** 0.5
    lambda_pf = 0.38 * root
    lambda_rf = 1.0 * root
    lambda_pw = 3.76 * root
    lambda_rw = 5.70 * root

    lambda_f = shape.bf_2tf
    lambda_w = shape.h_c_tw

    def _cls(lam: float, lp: float, lr: float) -> Compactness:
        if lam <= lp:
            return Compactness.COMPACT
        if lam <= lr:
            return Compactness.NONCOMPACT
        return Compactness.SLENDER

    flange = _cls(lambda_f, lambda_pf, lambda_rf)
    web = _cls(lambda_w, lambda_pw, lambda_rw)

    notes = [
        "AISC 360-22 Table B4.1b cases 10 (flange) and 15 (web) for flexure.",
        f"λf={lambda_f:.3f} vs λpf={lambda_pf:.3f}, λrf={lambda_rf:.3f} → {flange.value}",
        f"λw={lambda_w:.3f} vs λpw={lambda_pw:.3f}, λrw={lambda_rw:.3f} → {web.value}",
        "h/tw approximated as (d−2tf)/tw (slightly conservative vs filleted clear distance).",
    ]

    if flange == Compactness.COMPACT and web == Compactness.COMPACT:
        overall = Compactness.COMPACT
    elif Compactness.SLENDER in (flange, web):
        overall = Compactness.SLENDER
    else:
        overall = Compactness.NONCOMPACT

    notes.append(f"Overall for plastic composite Mn eligibility: {overall.value}")
    return ClassificationResult(
        flange=flange,
        web=web,
        lambda_f=lambda_f,
        lambda_pf=lambda_pf,
        lambda_rf=lambda_rf,
        lambda_w=lambda_w,
        lambda_pw=lambda_pw,
        lambda_rw=lambda_rw,
        overall=overall,
        notes=notes,
    )
