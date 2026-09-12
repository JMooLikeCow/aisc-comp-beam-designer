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
KNM_PER_KIPFT = 1.0 / KIPFT_PER_KNM

# Line load: 1 plf = 1 lbf/ft = N_PER_LBF / M_PER_FT N/m
KNPM_PER_PLF = (N_PER_LBF / M_PER_FT) / 1000.0  # ≈ 0.0145939 kN/m per plf
PLF_PER_KNPM = 1.0 / KNPM_PER_PLF

# Density / weight
KNM3_PER_PCF = 0.1570875  # kN/m³ per pcf
PCF_PER_KNM3 = 1.0 / KNM3_PER_PCF
KG_PER_LB = 0.45359237
LB_PER_FT_PER_KG_PER_M = 1.0 / (KG_PER_LB / M_PER_FT)  # plf per (kg/m)

# Steel modulus defaults
ES_MPA = 200_000.0  # AISC F1 / E = 29,000 ksi ≈ 200 GPa
ES_KSI = 29_000.0

# Concrete density default (normal weight)
GAMMA_C_KNM3 = 23.6  # ≈ 150 pcf


def mm_to_in(mm: float) -> float:
    return mm * IN_PER_MM


def in_to_mm(inches: float) -> float:
    return inches * MM_PER_IN


def m_to_ft(m: float) -> float:
    return m * FT_PER_M


def kn_to_kip(kn: float) -> float:
    return kn * KIP_PER_KN


def kip_to_kn(kip: float) -> float:
    return kip * KN_PER_KIP


def mpa_to_ksi(mpa: float) -> float:
    return mpa * KSI_PER_MPA


def ksi_to_mpa(ksi: float) -> float:
    return ksi * MPA_PER_KSI


def knm_to_kipft(knm: float) -> float:
    return knm * KIPFT_PER_KNM


def kipft_to_knm(kipft: float) -> float:
    return kipft * KNM_PER_KIPFT


def knpm_to_plf(knpm: float) -> float:
    return knpm * PLF_PER_KNPM


def plf_to_knpm(plf: float) -> float:
    return plf * KNPM_PER_PLF


def format_dual(
    value_si: float,
    unit_si: str,
    value_us: float,
    unit_us: str,
    precision: int = 2,
    precision_us: int | None = None,
) -> str:
    """Format SI value with US customary in brackets for UI/reports."""
    pu = precision if precision_us is None else precision_us
    return f"{value_si:.{precision}f} {unit_si} [{value_us:.{pu}f} {unit_us}]"


def dual_length_mm(mm: float, precision: int = 0, precision_us: int = 1) -> str:
    return format_dual(mm, "mm", mm_to_in(mm), "in", precision, precision_us)


def dual_length_m(m: float, precision: int = 2, precision_us: int = 2) -> str:
    return format_dual(m, "m", m_to_ft(m), "ft", precision, precision_us)


def dual_force_kN(kn: float, precision: int = 2, precision_us: int = 2) -> str:
    return format_dual(kn, "kN", kn_to_kip(kn), "kip", precision, precision_us)


def dual_moment_kNm(knm: float, precision: int = 1, precision_us: int = 1) -> str:
    return format_dual(knm, "kN·m", knm_to_kipft(knm), "kip·ft", precision, precision_us)


def dual_stress_MPa(mpa: float, precision: int = 1, precision_us: int = 1) -> str:
    return format_dual(mpa, "MPa", mpa_to_ksi(mpa), "ksi", precision, precision_us)


def dual_line_load_kNpm(knpm: float, precision: int = 2, precision_us: int = 1) -> str:
    return format_dual(knpm, "kN/m", knpm_to_plf(knpm), "plf", precision, precision_us)


def dual_density_kgm3(kg_m3: float, precision: int = 0, precision_us: int = 1) -> str:
    """Mass density kg/m³ with US lb/ft³ in brackets."""
    lb_per_ft3 = kg_m3 / KG_PER_LB * (M_PER_FT**3)
    return format_dual(kg_m3, "kg/m³", lb_per_ft3, "lb/ft³", precision, precision_us)
