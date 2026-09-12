"""Concrete material properties and Ec formulas."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from composite_beam.units import ES_MPA, GAMMA_C_KNM3, MPA_PER_KSI


class EcCode(str, Enum):
    """Code basis for modulus of elasticity Ec."""

    ACI318 = "ACI318"  # default
    EUROCODE2 = "Eurocode2"
    NZS3101 = "NZS3101"


@dataclass
class ConcreteMaterial:
    """
    Concrete material (SI: f'c in MPa, Ec in MPa, density in kN/m³).

    Ec defaults to ACI 318 (normal-weight): Ec = w_c^1.5 * 0.043 * sqrt(f'c)
    with w_c in kg/m³, f'c in MPa — equivalently Ec ≈ 4700*sqrt(f'c) for
    normal-weight (≈145–150 pcf). Eurocode 2 and NZS 3101 stubs provided.
    """

    fc_MPa: float
    density_kNm3: float = GAMMA_C_KNM3
    Ec_code: EcCode = EcCode.ACI318
    Ec_override_MPa: Optional[float] = None

    @property
    def Ec_MPa(self) -> float:
        if self.Ec_override_MPa is not None:
            return self.Ec_override_MPa
        return compute_Ec(self.fc_MPa, self.density_kNm3, self.Ec_code)

    @property
    def n(self) -> float:
        """Modular ratio Es/Ec (Es = 200 GPa)."""
        return ES_MPA / self.Ec_MPa


def compute_Ec(
    fc_MPa: float,
    density_kNm3: float = GAMMA_C_KNM3,
    code: EcCode = EcCode.ACI318,
) -> float:
    """
    Compute Ec (MPa).

    ACI 318-19 §19.2.2.1: Ec = w_c^1.5 * 0.043 * sqrt(f'c)
    with w_c in kg/m³ (≈ density_kN/m³ * 1000/9.81), f'c in MPa.
    For normal weight, simplified Ec = 4700*sqrt(f'c) is commonly used.

    Eurocode 2 EN 1992-1-1: Ecm = 22 * (fcm/10)^0.3  (GPa), fcm ≈ fc + 8 MPa.
    NZS 3101 stub: Ec = 3320*sqrt(fc) + 6900 (MPa) for normal density.
    """
    if code == EcCode.ACI318:
        # Use simplified normal-weight formula when density ~23.6 kN/m³;
        # otherwise use full ACI formula.
        wc_kgm3 = density_kNm3 * 1000.0 / 9.80665
        if 2200 <= wc_kgm3 <= 2500:
            return 4700.0 * (fc_MPa ** 0.5)
        return (wc_kgm3 ** 1.5) * 0.043 * (fc_MPa ** 0.5)

    if code == EcCode.EUROCODE2:
        # Stub: Ecm in GPa → MPa; fcm = fck + 8
        fcm = fc_MPa + 8.0
        Ecm_GPa = 22.0 * ((fcm / 10.0) ** 0.3)
        return Ecm_GPa * 1000.0

    if code == EcCode.NZS3101:
        # Stub per NZS 3101 Table 5.1 approximate
        return 3320.0 * (fc_MPa ** 0.5) + 6900.0

    raise ValueError(f"Unknown Ec code: {code}")


def modular_ratio(Es_MPa: float, Ec_MPa: float, override: Optional[float] = None) -> float:
    """n = Es/Ec with optional manual override."""
    if override is not None:
        return override
    if Ec_MPa <= 0:
        raise ValueError("Ec must be positive")
    return Es_MPa / Ec_MPa
