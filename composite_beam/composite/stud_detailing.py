"""AISC 360-22 §I8.2d headed-stud spacing / detailing checks (pure helpers)."""

from __future__ import annotations

from typing import Optional

from composite_beam.units import MM_PER_IN

# Documented flange-edge clearance assumption (clear to flange edge).
# AISC does not prescribe a single SI edge distance here; 25 mm (~1 in) is used.
DEFAULT_EDGE_CLEAR_MM = 25.0
MAX_SPACING_ABS_MM = 36.0 * MM_PER_IN  # 36 in = 914.4 mm


def max_n_across_on_flange(
    bf_mm: float,
    ds_mm: float,
    *,
    edge_clear_mm: float = DEFAULT_EDGE_CLEAR_MM,
) -> int:
    """
    Maximum transverse stud count that fits on bf with edge clearance and
    transverse pitch ≥ 4 × ds (AISC I8.2d).
    """
    if ds_mm <= 0 or bf_mm <= 0:
        return 0
    min_pitch = 4.0 * ds_mm
    if bf_mm < 2.0 * edge_clear_mm:
        return 0
    # n=1 needs only edge clears; additional studs need (n-1) gaps ≥ 4d
    avail = bf_mm - 2.0 * edge_clear_mm
    return 1 + int(avail // min_pitch)


def required_flange_width_mm(
    n_across: int,
    ds_mm: float,
    *,
    edge_clear_mm: float = DEFAULT_EDGE_CLEAR_MM,
    s_trans_mm: Optional[float] = None,
) -> float:
    """Minimum bf to place n_across studs with edge clear and pitch ≥ 4d."""
    n = max(1, int(n_across))
    pitch = 4.0 * ds_mm if s_trans_mm is None else max(float(s_trans_mm), 4.0 * ds_mm)
    if n <= 1:
        return 2.0 * edge_clear_mm
    return 2.0 * edge_clear_mm + (n - 1) * pitch


def transverse_pitch_equal_spaced_mm(
    bf_mm: float,
    n_across: int,
    *,
    edge_clear_mm: float = DEFAULT_EDGE_CLEAR_MM,
) -> Optional[float]:
    """Center-to-center pitch if n_across studs are equally spaced with edge clears."""
    n = int(n_across)
    if n <= 1:
        return None
    avail = bf_mm - 2.0 * edge_clear_mm
    if avail <= 0:
        return 0.0
    return avail / (n - 1)


def check_stud_detailing(
    *,
    ds_mm: float,
    s_long_mm: float,
    n_across: int,
    bf_mm: float,
    tf_mm: float,
    t_total_mm: float,
    s_trans_mm: Optional[float] = None,
    edge_clear_mm: float = DEFAULT_EDGE_CLEAR_MM,
) -> list[str]:
    """
    Return human-readable AISC 360-22 §I8.2d (and §I8 diameter) violations.

    Parameters
    ----------
    ds_mm :
        Stud diameter.
    s_long_mm :
        Longitudinal center-to-center spacing along the beam.
    n_across :
        Number of studs across the flange (transverse rows).
    bf_mm, tf_mm :
        Steel flange width and thickness.
    t_total_mm :
        Total slab thickness (solid + deck rib depth) for the max-spacing limit.
    s_trans_mm :
        Optional explicit transverse pitch. If omitted, equal-spaced pitch on bf
        is used when n_across > 1; fit check still assumes pitch ≥ 4d.
    edge_clear_mm :
        Assumed clear distance from stud centerline to flange edge (default 25 mm ≈ 1 in).
    """
    violations: list[str] = []
    n = max(1, int(n_across))
    ds = float(ds_mm)
    s_long = float(s_long_mm)
    bf = float(bf_mm)
    tf = float(tf_mm)
    t_tot = float(t_total_mm)

    # I8: ds ≤ 2.5 tf
    limit_d = 2.5 * tf
    if ds > limit_d + 1e-9:
        violations.append(
            f"AISC 360-22 §I8: stud diameter ds={ds:.1f} mm exceeds 2.5·tf="
            f"{limit_d:.1f} mm (tf={tf:.1f} mm)."
        )

    # I8.2d: min longitudinal spacing ≥ 6d
    min_long = 6.0 * ds
    if s_long + 1e-9 < min_long:
        violations.append(
            f"AISC 360-22 §I8.2d: longitudinal spacing s={s_long:.0f} mm is less than "
            f"minimum 6·ds={min_long:.1f} mm."
        )

    # I8.2d: max center-to-center ≤ min(8 × total slab thickness, 36 in)
    max_s = min(8.0 * t_tot, MAX_SPACING_ABS_MM) if t_tot > 0 else MAX_SPACING_ABS_MM
    if s_long > max_s + 1e-9:
        violations.append(
            f"AISC 360-22 §I8.2d: longitudinal spacing s={s_long:.0f} mm exceeds maximum "
            f"min(8·t_total={8.0 * t_tot:.0f} mm, 36 in={MAX_SPACING_ABS_MM:.0f} mm) "
            f"= {max_s:.0f} mm."
        )

    # Transverse spacing ≥ 4d
    min_trans = 4.0 * ds
    pitch = s_trans_mm
    if pitch is None and n > 1:
        pitch = transverse_pitch_equal_spaced_mm(bf, n, edge_clear_mm=edge_clear_mm)
    if n > 1 and pitch is not None and pitch + 1e-9 < min_trans:
        violations.append(
            f"AISC 360-22 §I8.2d: transverse spacing s_trans={pitch:.1f} mm is less than "
            f"minimum 4·ds={min_trans:.1f} mm (n_across={n})."
        )

    # Flange fit with edge clearance + pitch ≥ 4d
    max_n = max_n_across_on_flange(bf, ds, edge_clear_mm=edge_clear_mm)
    req_bf = required_flange_width_mm(
        n, ds, edge_clear_mm=edge_clear_mm, s_trans_mm=s_trans_mm
    )
    if n > max_n or req_bf > bf + 1e-9:
        violations.append(
            f"AISC 360-22 §I8.2d flange fit: n_across={n} cannot fit on bf={bf:.1f} mm "
            f"with ≥{edge_clear_mm:.0f} mm edge clearance and transverse pitch ≥ 4·ds="
            f"{min_trans:.1f} mm (requires bf≥{req_bf:.1f} mm). "
            f"Maximum n_across that fits = {max_n}."
        )

    return violations


def n_studs_half_from_spacing(
    L_mm: float,
    s_long_mm: float,
    n_across: int = 1,
    x_Mmax_mm: Optional[float] = None,
) -> int:
    """
    Count studs from support to max M for uniform longitudinal spacing.

    Placement matches ``layout_studs``: first stud at s/2, then every s while x < L.
    Each longitudinal station contributes ``n_across`` studs.
    """
    if L_mm <= 0 or s_long_mm <= 0 or n_across < 1:
        return 0
    x_max = float(x_Mmax_mm) if x_Mmax_mm is not None else 0.5 * L_mm
    n_stations = 0
    x = 0.5 * s_long_mm
    while x < L_mm - 1e-6:
        if x <= x_max + 1e-6:
            n_stations += 1
        x += s_long_mm
    return n_stations * int(n_across)
