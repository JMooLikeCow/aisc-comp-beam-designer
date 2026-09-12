"""P1 feature tests: continuous analysis, H interaction, box, punching, four-zone studs."""

from __future__ import annotations

import math

import pytest

from composite_beam.analysis.continuous import SupportType, analyze_span, elastic_end_moments_kNm
from composite_beam.composite.punching import punching_one_stud, punching_with_group
from composite_beam.composite.stud_layout import default_four_zones, layout_studs
from composite_beam.loads.load_cases import PointLoad, PointLoadSpec
from composite_beam.sections.box_sections import box_properties
from composite_beam.strength.interaction import chapter_h_interaction, compressive_strength_E3


def test_fixed_fixed_udl_end_moments():
    """Elastic FF UDL: ML=MR=−wL²/12; midspan sagging wL²/24."""
    L_mm = 10_000.0
    w = 10.0  # kN/m
    ML, MR = elastic_end_moments_kNm(L_mm, w, [], SupportType.FIXED_FIXED)
    assert ML == pytest.approx(-w * 10.0**2 / 12.0, rel=1e-9)
    assert MR == pytest.approx(ML)
    diag = analyze_span(L_mm, w, support=SupportType.FIXED_FIXED)
    assert diag.M_left_kNm == pytest.approx(-w * 100.0 / 12.0, rel=1e-6)
    assert diag.M_right_kNm == pytest.approx(-w * 100.0 / 12.0, rel=1e-6)
    assert diag.M_max_kNm == pytest.approx(w * 100.0 / 24.0, rel=0.03)
    assert diag.R_left_kN == pytest.approx(w * 10.0 / 2.0, rel=1e-6)
    assert diag.V_max_kN == pytest.approx(w * 10.0 / 2.0, rel=0.02)


def test_fixed_pinned_udl_and_variable_end_moment():
    """FP UDL: ML=−wL²/8, RL=3wL/8, RR=5wL/8; override changes ML."""
    L_mm = 10_000.0
    w = 10.0
    diag = analyze_span(L_mm, w, support=SupportType.FIXED_PINNED)
    assert diag.M_left_kNm == pytest.approx(-w * 100.0 / 8.0, rel=1e-6)
    assert diag.M_right_kNm == pytest.approx(0.0, abs=1e-9)
    assert diag.R_left_kN == pytest.approx(3.0 * w * 10.0 / 8.0, rel=1e-6)
    assert diag.R_right_kN == pytest.approx(5.0 * w * 10.0 / 8.0, rel=1e-6)

    # Variable fixed-end moment: half the FEM
    ov = -w * 100.0 / 16.0
    d2 = analyze_span(L_mm, w, support=SupportType.FIXED_PINNED, M_left_override_kNm=ov)
    assert d2.M_left_kNm == pytest.approx(ov)
    assert abs(d2.M_left_kNm) < abs(diag.M_left_kNm)


def test_fixed_fixed_point_load_midspan():
    """FF midspan point load: ends −PL/8, mid +PL/8."""
    L_mm = 8000.0
    P = 40.0
    pts = [PointLoad(P_kN=P, location=0.5, spec=PointLoadSpec.RATIO)]
    diag = analyze_span(L_mm, 0.0, pts, support=SupportType.FIXED_FIXED)
    PL = P * 8.0
    assert diag.M_left_kNm == pytest.approx(-PL / 8.0, rel=1e-6)
    assert diag.M_max_kNm == pytest.approx(PL / 8.0, rel=0.04)


def test_h_interaction_smoke():
    """H1-1a / H1-1b smoke: zero axial reduces to Mr/Mc; 0.3+8/9*0.5."""
    r0 = chapter_h_interaction(Pr_kN=0.0, Pc_kN=1000.0, Mrx_kNm=100.0, Mcx_kNm=200.0)
    assert r0.equation == "H1-1b"
    assert r0.DCR == pytest.approx(100.0 / 200.0)
    assert r0.passes is True

    r1 = chapter_h_interaction(Pr_kN=300.0, Pc_kN=1000.0, Mrx_kNm=100.0, Mcx_kNm=200.0)
    assert r1.equation == "H1-1a"
    assert r1.DCR == pytest.approx(0.3 + (8.0 / 9.0) * 0.5)
    assert r1.passes is True

    r_fail = chapter_h_interaction(Pr_kN=800.0, Pc_kN=1000.0, Mrx_kNm=180.0, Mcx_kNm=200.0)
    assert r_fail.equation == "H1-1a"
    assert r_fail.DCR > 1.0
    assert r_fail.passes is False


def test_e3_compressive_strength_smoke(wdb):
    shape = wdb.get("W12X50")
    Pn, Pc, Fcr, slend, notes = compressive_strength_E3(shape, 345.0, 4000.0, K=1.0)
    assert Pn > 0 and Pc == pytest.approx(0.90 * Pn)
    assert Fcr > 0 and slend > 0
    assert any("E3" in n for n in notes)


def test_box_section_properties():
    """Welded box A, Ix, closed J; J much larger than an open I of similar plates."""
    H, B, tf, tw = 400.0, 300.0, 16.0, 12.0
    box = box_properties(H, B, tf, tw, designation="BOX-TEST")
    hw = H - 2.0 * tf
    A_expect = 2.0 * B * tf + 2.0 * hw * tw
    assert box.A_mm2 == pytest.approx(A_expect)
    assert box.section_kind == "BOX"
    assert box.Ix_mm4 > 0 and box.Iy_mm4 > 0
    assert box.Sx_mm3 == pytest.approx(box.Ix_mm4 / (H / 2.0))
    assert box.Zx_mm3 > box.Sx_mm3
    # Closed Bredt J
    bm, hm = B - tw, H - tf
    Am = bm * hm
    oint = 2.0 * bm / tf + 2.0 * hm / tw
    J_expect = 4.0 * Am**2 / oint
    assert box.J_mm4 == pytest.approx(J_expect, rel=1e-9)
    # Open I (one web) J is orders of magnitude smaller
    from composite_beam.sections.w_shapes import custom_w_shape

    open_i = custom_w_shape("I", H, B, tf, tw)
    assert box.J_mm4 > 20.0 * open_i.J_mm4


def test_punching_formula_smoke():
    """φVc > 0 and scales with √f'c and d (ACI 318M 0.33λ√f'c b0 d)."""
    r = punching_one_stud(ds_mm=19.05, t_solid_mm=100.0, fc_MPa=27.6, Vu_kN=20.0)
    assert r.phiVc_kN > 0
    assert r.b0_mm == pytest.approx(math.pi * (19.05 + 100.0))
    r2 = punching_one_stud(ds_mm=19.05, t_solid_mm=100.0, fc_MPa=27.6 * 4.0, Vu_kN=20.0)
    assert r2.phiVc_kN == pytest.approx(2.0 * r.phiVc_kN, rel=0.08)
    r3 = punching_one_stud(ds_mm=19.05, t_solid_mm=200.0, fc_MPa=27.6, Vu_kN=20.0)
    assert r3.phiVc_kN > r.phiVc_kN
    g = punching_with_group(19.05, 100.0, 27.6, 40.0, min_spacing_mm=80.0)
    assert g.group_DCR >= g.DCR * 0.5  # group engaged when s < 4d


def test_four_zone_stud_count():
    """Four equal 2 m zones, s=200 mm → 10 studs/zone (at 100,300,…,1900), 40 total."""
    L = 8000.0
    zones = default_four_zones(spacing_mm=200.0, n_rows=1)
    assert len(zones) == 4
    lay = layout_studs(L, zones, x_Mmax_mm=4000.0)
    assert lay.n_total == 40
    assert lay.n_left_of_max_M == 20
    # Independent spacing in end zones
    zones2 = default_four_zones(spacing_mm=200.0, end_spacing_mm=100.0)
    lay2 = layout_studs(L, zones2, x_Mmax_mm=4000.0)
    # End zones 2000/100 = 20 each; mid zones 10 each → 60
    assert lay2.n_total == 60
    assert lay2.zones[0].spacing_mm == 100.0
    assert lay2.zones[1].spacing_mm == 200.0
