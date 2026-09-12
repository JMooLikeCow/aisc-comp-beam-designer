"""W-shape database loader and section property model (AISC Manual)."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

from composite_beam.units import IN_PER_MM, MM_PER_IN, MPA_PER_KSI

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@dataclass
class WShape:
    """
    Wide-flange section properties.

    Stored in SI (mm, mm², mm⁴, mm³) with original imperial retained for reference.
    """

    designation: str
    W_kNm: float  # self-weight kN/m (from lb/ft)
    A_mm2: float
    d_mm: float
    tw_mm: float
    bf_mm: float
    tf_mm: float
    Ix_mm4: float
    Sx_mm3: float
    rx_mm: float
    Zx_mm3: float
    Iy_mm4: float
    Sy_mm3: float
    ry_mm: float
    Zy_mm3: float
    J_mm4: float
    Cw_mm6: float
    rts_mm: float
    ho_mm: float
    custom: bool = False
    section_kind: str = "W"  # "W" rolled/plate-girder I; "BOX" welded box
    # imperial originals
    W_lb_ft: float = 0.0
    A_in2: float = 0.0
    d_in: float = 0.0
    tw_in: float = 0.0
    bf_in: float = 0.0
    tf_in: float = 0.0
    Ix_in4: float = 0.0
    Sx_in3: float = 0.0
    Zx_in3: float = 0.0
    Iy_in4: float = 0.0
    ry_in: float = 0.0
    J_in4: float = 0.0
    Cw_in6: float = 0.0
    rts_in: float = 0.0
    ho_in: float = 0.0

    @property
    def h_c_tw(self) -> float:
        """Approximate clear distance between flanges less corner radii ≈ (d - 2*tf)/tw.
        Conservative for classification; actual h uses filleted clear distance.
        AISC Table B4.1b uses h/tw where h is clear distance between flanges
        less the fillet or corner radius for rolled shapes. Approximation:
        h ≈ d - 2*tf (slightly conservative for λ_w).
        """
        return (self.d_mm - 2.0 * self.tf_mm) / self.tw_mm

    @property
    def bf_2tf(self) -> float:
        """Flange slenderness λ_f.

        I-shape (Table B4.1b case 10): bf/(2 tf)
        Box (case 12): clear flange width / tf = (B − 2 tw)/tf
        """
        if self.section_kind == "BOX":
            b_clear = self.bf_mm - 2.0 * self.tw_mm
            return b_clear / self.tf_mm if self.tf_mm > 0 else 0.0
        return self.bf_mm / (2.0 * self.tf_mm)


def _in_to_mm(v: float) -> float:
    return v * MM_PER_IN


def _in2_to_mm2(v: float) -> float:
    return v * (MM_PER_IN ** 2)


def _in3_to_mm3(v: float) -> float:
    return v * (MM_PER_IN ** 3)


def _in4_to_mm4(v: float) -> float:
    return v * (MM_PER_IN ** 4)


def _in6_to_mm6(v: float) -> float:
    return v * (MM_PER_IN ** 6)


def _lbft_to_kNm(v: float) -> float:
    # 1 lb/ft = 14.5939 N/m = 0.0145939 kN/m
    return v * 0.0145939


def shape_from_row(row: dict) -> WShape:
    """Build WShape from CSV row (imperial columns)."""
    d_in = float(row["d_in"])
    tw_in = float(row["tw_in"])
    bf_in = float(row["bf_in"])
    tf_in = float(row["tf_in"])
    return WShape(
        designation=row["designation"],
        W_kNm=_lbft_to_kNm(float(row["W_lb_ft"])),
        A_mm2=_in2_to_mm2(float(row["A_in2"])),
        d_mm=_in_to_mm(d_in),
        tw_mm=_in_to_mm(tw_in),
        bf_mm=_in_to_mm(bf_in),
        tf_mm=_in_to_mm(tf_in),
        Ix_mm4=_in4_to_mm4(float(row["Ix_in4"])),
        Sx_mm3=_in3_to_mm3(float(row["Sx_in3"])),
        rx_mm=_in_to_mm(float(row["rx_in"])),
        Zx_mm3=_in3_to_mm3(float(row["Zx_in3"])),
        Iy_mm4=_in4_to_mm4(float(row["Iy_in4"])),
        Sy_mm3=_in3_to_mm3(float(row["Sy_in3"])),
        ry_mm=_in_to_mm(float(row["ry_in"])),
        Zy_mm3=_in3_to_mm3(float(row["Zy_in3"])),
        J_mm4=_in4_to_mm4(float(row["J_in4"])),
        Cw_mm6=_in6_to_mm6(float(row["Cw_in6"])),
        rts_mm=_in_to_mm(float(row["rts_in"])),
        ho_mm=_in_to_mm(float(row["ho_in"])),
        W_lb_ft=float(row["W_lb_ft"]),
        A_in2=float(row["A_in2"]),
        d_in=d_in,
        tw_in=tw_in,
        bf_in=bf_in,
        tf_in=tf_in,
        Ix_in4=float(row["Ix_in4"]),
        Sx_in3=float(row["Sx_in3"]),
        Zx_in3=float(row["Zx_in3"]),
        Iy_in4=float(row["Iy_in4"]),
        ry_in=float(row["ry_in"]),
        J_in4=float(row["J_in4"]),
        Cw_in6=float(row["Cw_in6"]),
        rts_in=float(row["rts_in"]),
        ho_in=float(row["ho_in"]),
    )


def custom_w_shape(
    designation: str,
    d_mm: float,
    bf_mm: float,
    tf_mm: float,
    tw_mm: float,
    A_mm2: Optional[float] = None,
    Ix_mm4: Optional[float] = None,
    Zx_mm3: Optional[float] = None,
    Sx_mm3: Optional[float] = None,
    Iy_mm4: Optional[float] = None,
    ry_mm: Optional[float] = None,
    J_mm4: Optional[float] = None,
    Cw_mm6: Optional[float] = None,
    rts_mm: Optional[float] = None,
    ho_mm: Optional[float] = None,
    W_kNm: float = 0.0,
) -> WShape:
    """
    Build a custom I-section from plate dimensions (approximate rolled properties).
    Missing properties estimated from rectangular plate idealization.
    """
    if A_mm2 is None:
        A_mm2 = 2.0 * bf_mm * tf_mm + (d_mm - 2.0 * tf_mm) * tw_mm
    hw = d_mm - 2.0 * tf_mm
    if Ix_mm4 is None:
        # Parallel axis: 2*(bf*tf^3/12 + bf*tf*(d/2 - tf/2)^2) + tw*hw^3/12
        Ix_flange = 2.0 * (
            bf_mm * tf_mm**3 / 12.0 + bf_mm * tf_mm * ((d_mm / 2.0) - (tf_mm / 2.0)) ** 2
        )
        Ix_web = tw_mm * hw**3 / 12.0
        Ix_mm4 = Ix_flange + Ix_web
    if Sx_mm3 is None:
        Sx_mm3 = Ix_mm4 / (d_mm / 2.0)
    if Zx_mm3 is None:
        # Plastic modulus approx for doubly symmetric I
        Zx_mm3 = bf_mm * tf_mm * (d_mm - tf_mm) + 0.25 * tw_mm * hw**2
    if Iy_mm4 is None:
        Iy_mm4 = 2.0 * (tf_mm * bf_mm**3 / 12.0) + hw * tw_mm**3 / 12.0
    if ry_mm is None:
        ry_mm = (Iy_mm4 / A_mm2) ** 0.5
    if J_mm4 is None:
        # Approximate Saint-Venant torsion for open thin-walled
        J_mm4 = (2.0 * bf_mm * tf_mm**3 + hw * tw_mm**3) / 3.0
    if Cw_mm6 is None:
        # Approx Cw ≈ (tf*bf^3/12)*((d-tf)^2)/2  for doubly symmetric
        Cw_mm6 = (tf_mm * bf_mm**3 / 12.0) * ((d_mm - tf_mm) ** 2) / 2.0
    if rts_mm is None:
        # rts² ≈ sqrt(Iy*Cw)/Sx  per AISC commentary approx; use sqrt(sqrt(Iy*Cw)/Sx)
        rts_mm = ((Iy_mm4 * Cw_mm6) ** 0.5 / Sx_mm3) ** 0.5 if Sx_mm3 > 0 else ry_mm
    if ho_mm is None:
        ho_mm = d_mm - tf_mm

    return WShape(
        designation=designation,
        W_kNm=W_kNm,
        A_mm2=A_mm2,
        d_mm=d_mm,
        tw_mm=tw_mm,
        bf_mm=bf_mm,
        tf_mm=tf_mm,
        Ix_mm4=Ix_mm4,
        Sx_mm3=Sx_mm3,
        rx_mm=(Ix_mm4 / A_mm2) ** 0.5,
        Zx_mm3=Zx_mm3,
        Iy_mm4=Iy_mm4,
        Sy_mm3=Iy_mm4 / (bf_mm / 2.0) if bf_mm > 0 else 0.0,
        ry_mm=ry_mm,
        Zy_mm3=0.5 * bf_mm**2 * tf_mm + 0.25 * tw_mm**2 * hw,  # rough
        J_mm4=J_mm4,
        Cw_mm6=Cw_mm6,
        rts_mm=rts_mm,
        ho_mm=ho_mm,
        custom=True,
        d_in=d_mm * IN_PER_MM,
        bf_in=bf_mm * IN_PER_MM,
        tf_in=tf_mm * IN_PER_MM,
        tw_in=tw_mm * IN_PER_MM,
    )


class WShapeDatabase:
    """CSV-backed W-shape catalog."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or (DATA_DIR / "w_shapes.csv")
        self._shapes: dict[str, WShape] = {}
        self._load()

    def _load(self) -> None:
        with open(self.path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                s = shape_from_row(row)
                self._shapes[s.designation.upper()] = s

    def get(self, designation: str) -> WShape:
        key = designation.strip().upper().replace(" ", "")
        # normalize W21X44 vs W21x44
        key = key.replace("X", "X")
        if key not in self._shapes:
            # try alternate
            for k, v in self._shapes.items():
                if k.replace("X", "X") == key:
                    return v
            raise KeyError(f"W-shape not found: {designation}")
        return self._shapes[key]

    def __iter__(self) -> Iterator[WShape]:
        return iter(sorted(self._shapes.values(), key=lambda s: (s.d_mm, s.W_kNm)))

    def __len__(self) -> int:
        return len(self._shapes)

    def lightest_first(self) -> list[WShape]:
        return sorted(self._shapes.values(), key=lambda s: (s.W_kNm, s.d_mm))
