"""Unit conversions: primary SI (kN, mm, kPa, MPa); US customary helpers."""

from __future__ import annotations

# Length
MM_PER_IN = 25.4
IN_PER_MM = 1.0 / MM_PER_IN
M_PER_FT = 0.3048
FT_PER_M = 1.0 / M_PER_FT

# Force
KN_PER_KIP = 4.4482216152605
KIP_PER_KN = 1.0 / KN_PER_KIP
N_PER_LBF = 4.4482216152605

# Stress / pressure
MPA_PER_KSI = 6.894757293168
KSI_PER_MPA = 1.0 / MPA_PER_KSI
KPA_PER_PSF = 0.04788025898
PSF_PER_KPA = 1.0 / KPA_PER_PSF

# Moment
KNMM_PER_KIPIN = KN_PER_KIP * MM_PER_IN  # kN·mm per kip·in
KIPIN_PER_KNMM = 1.0 / KNMM_PER_KIPIN
KIPFT_PER_KNM = KIP_PER_KN * FT_PER_M  # approximately 0.73756
KNM_PER_KIPFT = 1.0 / KIPFT_PER_M if (KIPFT_PER_M := KIP_PER_KN * FT_PER_M) else 1.0

# Density / weight
KNM3_PER_PCF = 0.1570875  # kN/m³ per pcf
PCF_PER_KNM3 = 1.0 / KNM3_PER_PCF

# Steel modulus defaults
ES_MPA = 200_000.0  # AISC F1 / E = 29,000 ksi ≈ 200 GPa
ES_KSI = 29_000.0

# Concrete density default (normal weight)
GAMMA_C_KNM3 = 23.6  # ≈ 150 pcf


def mm_to_in(mm: float) -> float:
    return mm * IN_PER_MM


def in_to_mm(inches: float) -> float:
    return inches * MM_PER_IN


def kn_to_kip(kn: float) -> float:
    return kn * KIP_PER_KN


def kip_to_kn(kip: float) -> float:
    return kip * KN_PER_KIP


def mpa_to_ksi(mpa: float) -> float:
    return mpa * KSI_PER_MPA


def ksi_to_mpa(ksi: float) -> float:
    return ksi * MPA_PER_KSI


def knm_to_kipft(knm: float) -> float:
    return knm * KIPFT_PER_M


def kipft_to_knm(kipft: float) -> float:
    return kipft * KNM_PER_KIPFT


def format_dual(value_si: float, unit_si: str, value_us: float, unit_us: str, precision: int = 2) -> str:
    """Format SI value with US customary in brackets for UI/reports."""
    return f"{value_si:.{precision}f} {unit_si} [{value_us:.{precision}f} {unit_us}]"
