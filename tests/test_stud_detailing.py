"""AISC 360-22 §I8.2d stud detailing checks."""

from __future__ import annotations

from composite_beam.composite.stud_detailing import (
    MAX_SPACING_ABS_MM,
    check_stud_detailing,
    max_n_across_on_flange,
    n_studs_half_from_spacing,
    required_flange_width_mm,
)
from composite_beam.composite.cumulative_action import synthesize_uniform_stud_positions


def test_min_longitudinal_spacing_6d():
    ds = 19.0
    msgs = check_stud_detailing(
        ds_mm=ds,
        s_long_mm=5 * ds,  # too tight
        n_across=1,
        bf_mm=200.0,
        tf_mm=12.0,
        t_total_mm=150.0,
    )
    assert any("6·ds" in m or "6*ds" in m or "longitudinal" in m for m in msgs)
    ok = check_stud_detailing(
        ds_mm=ds,
        s_long_mm=6 * ds,
        n_across=1,
        bf_mm=200.0,
        tf_mm=12.0,
        t_total_mm=150.0,
    )
    assert not any("longitudinal spacing" in m and "less than" in m for m in ok)


def test_min_transverse_spacing_4d():
    ds = 19.0
    # Force equal-spaced pitch on a narrow flange → < 4d
    bf = 100.0  # with 25 mm edges → avail 50 mm for 1 gap → pitch 50 < 4*19=76
    msgs = check_stud_detailing(
        ds_mm=ds,
        s_long_mm=150.0,
        n_across=2,
        bf_mm=bf,
        tf_mm=12.0,
        t_total_mm=150.0,
    )
    assert any("transverse" in m or "flange fit" in m for m in msgs)


def test_max_spacing_8t_and_36in():
    ds = 19.0
    t_total = 50.0  # 8*t = 400 mm; 36 in ≈ 914 → max = 400
    msgs = check_stud_detailing(
        ds_mm=ds,
        s_long_mm=500.0,  # > 400
        n_across=1,
        bf_mm=200.0,
        tf_mm=12.0,
        t_total_mm=t_total,
    )
    assert any("exceeds maximum" in m for m in msgs)
    # Thick slab: capped by 36 in
    msgs2 = check_stud_detailing(
        ds_mm=ds,
        s_long_mm=MAX_SPACING_ABS_MM + 10.0,
        n_across=1,
        bf_mm=200.0,
        tf_mm=12.0,
        t_total_mm=200.0,  # 8*t = 1600 > 914
    )
    assert any("36 in" in m or "exceeds maximum" in m for m in msgs2)


def test_flange_fit_max_n_across():
    ds = 19.05
    bf = 152.0  # W18X35-ish
    max_n = max_n_across_on_flange(bf, ds, edge_clear_mm=25.0)
    assert max_n >= 1
    req = required_flange_width_mm(max_n + 1, ds, edge_clear_mm=25.0)
    assert req > bf
    msgs = check_stud_detailing(
        ds_mm=ds,
        s_long_mm=150.0,
        n_across=max_n + 1,
        bf_mm=bf,
        tf_mm=11.0,
        t_total_mm=150.0,
    )
    assert any("flange fit" in m and f"Maximum n_across that fits = {max_n}" in m for m in msgs)


def test_diameter_vs_tf():
    msgs = check_stud_detailing(
        ds_mm=25.0,
        s_long_mm=200.0,
        n_across=1,
        bf_mm=200.0,
        tf_mm=8.0,  # 2.5*8 = 20 < 25
        t_total_mm=150.0,
    )
    assert any("2.5" in m and "diameter" in m for m in msgs)


def test_n_studs_half_from_spacing():
    # L=1000, s=200 → stations at 100,300,500,700,900 → left of mid(500): 100,300,500 = 3
    n = n_studs_half_from_spacing(1000.0, 200.0, n_across=1, x_Mmax_mm=500.0)
    assert n == 3
    n2 = n_studs_half_from_spacing(1000.0, 200.0, n_across=2, x_Mmax_mm=500.0)
    assert n2 == 6


def test_synthesize_from_s_long():
    pos = synthesize_uniform_stud_positions(
        1000.0, 500.0, n_half=None, n_rows=2, s_long_mm=200.0
    )
    assert len(pos) == 10  # 5 stations × 2 rows
    assert all(p.row in (0, 1) for p in pos)
