"""Deflection unit fix + AISC Chapter G web shear."""

from __future__ import annotations

import math

import pytest

from composite_beam.analysis.simple_beam import (
    deflection_point_general,
    deflection_point_midspan,
    deflection_udl_simply_supported,
)
from composite_beam.analysis.continuous import midspan_deflection_from_moment_mm, analyze_span
from composite_beam.design_engine import DesignEngine, DesignInputs
from composite_beam.materials.concrete import ConcreteMaterial, EcCode
from composite_beam.materials.steel import SteelMaterial
from composite_beam.composite.slab import DeckOrientation, SlabConfig
from composite_beam.serviceability.deflection import _EI_kNmm2, compute_deflections, transformed_I_full, Ieff_partial
from composite_beam.composite.shear_connection import shear_connection
from composite_beam.composite.studs import StudConfig, stud_Qn
from composite_beam.strength.shear import web_shear_strength
from composite_beam.units import ES_MPA, ksi_to_mpa, in_to_mm


def test_udl_deflection_unit_hand_calc():
    """
    Δ = 5 w L^4 / (384 EI) with consistent N–mm units.
    1 kN/m = 1 N/mm (not /1000). Hand calc for steel-alone W18×35.
    """
    # Synthetic EI so the hand number is exact
    # Choose L=9000 mm, w=10 kN/m, EI_kNmm2 such that delta is clean
    L = 9000.0
    w = 10.0  # kN/m = 10 N/mm
    # Pick I and E → EI_kNmm2
    I = 2.0e8  # mm^4
    E = ES_MPA
    EI_kNmm2 = _EI_kNmm2(I, E)  # E*I/1000
    # Hand: w_Nmm=w, EI_Nmm2=E*I
    delta_hand = 5.0 * w * (L**4) / (384.0 * (E * I))
    delta = deflection_udl_simply_supported(w, L, EI_kNmm2)
    assert delta == pytest.approx(delta_hand, rel=1e-12)
    assert delta > 1.0  # must not be near-zero from /1000 bug


def test_ss_w18x35_ll_deflection_tens_of_mm(wdb):
    """Dummy SS W18×35, L=9144 mm, w_LL=7 kN/m on Ieff → ΔLL on order of tens of mm."""
    shape = wdb.get("W18X35")
    steel = SteelMaterial.from_grade("A992", tf_mm=shape.tf_mm)
    conc = ConcreteMaterial(fc_MPa=ksi_to_mpa(4.0), Ec_code=EcCode.ACI318)
    L_mm = 9144.0
    beff = L_mm / 4.0  # interior beff often L/4 governing vs spacing
    slab = SlabConfig(
        t_solid_mm=in_to_mm(3.25),
        hr_mm=in_to_mm(2.0),
        wr_mm=in_to_mm(6.0),
        orientation=DeckOrientation.PERPENDICULAR,
        fc_MPa=conc.fc_MPa,
        beff_mm=beff,
    )
    n = steel.Es_MPa / conc.Ec_MPa
    stud = StudConfig(diameter_mm=in_to_mm(0.75), Fu_stud_MPa=ksi_to_mpa(65.0))
    qn = stud_Qn(stud, slab, shape.tf_mm, conc.Ec_MPa)
    shear = shear_connection(shape, steel.Fy_MPa, slab, qn, target_ratio=1.0)
    I_full, _ = transformed_I_full(shape, slab, n)
    I_eff = Ieff_partial(I_full, shape.Ix_mm4, shear.ratio)
    EI_eff = _EI_kNmm2(I_eff, steel.Es_MPa)
    w_LL = 7.0
    delta = deflection_udl_simply_supported(w_LL, L_mm, EI_eff)
    # Bug was /1000 → ~0.004 mm; fixed value is several mm on Ieff (tens on Is).
    delta_steel = deflection_udl_simply_supported(w_LL, L_mm, _EI_kNmm2(shape.Ix_mm4, steel.Es_MPa))
    assert delta_steel == pytest.approx(15.0, rel=0.05)  # order of tens of mm on Is
    assert delta > 1.0, f"ΔLL on Ieff={delta:.3f} mm must not be near-zero"
    assert delta < delta_steel  # composite stiffer
    # Hand calc check (N–mm): w_Nmm = w_kNpm
    hand = 5.0 * w_LL * (L_mm**4) / (384.0 * steel.Es_MPa * I_eff)
    assert delta == pytest.approx(hand, rel=1e-9)

    # Engine path should match
    eng = DesignEngine(wdb)
    inp = DesignInputs(
        L_mm=L_mm,
        shape=shape,
        steel=steel,
        concrete=conc,
        slab=slab,
        spacing_left_mm=beff,
        spacing_right_mm=beff,
        target_composite_ratio=1.0,
        w_SDL_kNpm=1.0,
        w_LL_kNpm=w_LL,
        w_construction_kNpm=1.0,
        deck_braces_construction=True,
        shored=True,  # LL on Ieff clearly
        include_beam_self_weight=False,
        include_slab_self_weight=False,
    )
    res = eng.design(inp, search_passing=False)
    assert res.deflection.delta_LL_mm == pytest.approx(delta, rel=1e-3)
    assert res.deflection.delta_LL_mm > 1.0


def test_point_load_deflection_units_consistent():
    """Point-load formulas already use P_N = P_kN*1000; sanity vs midspan closed form."""
    L = 8000.0
    P = 50.0  # kN
    I = 1.5e8
    EI = _EI_kNmm2(I, ES_MPA)
    d_mid = deflection_point_midspan(P, L, EI)
    d_gen = deflection_point_general(P, L / 2.0, L, EI)
    assert d_mid == pytest.approx(d_gen, rel=1e-9)
    # Hand: P L^3 / (48 EI) with N, mm
    hand = (P * 1000.0) * (L**3) / (48.0 * ES_MPA * I)
    assert d_mid == pytest.approx(hand, rel=1e-12)


def test_mei_integration_matches_ss_udl():
    """Continuous M/EI path should agree with 5wL^4/384 EI for SS UDL (no /1000 bug)."""
    L = 9144.0
    w = 7.0
    I = 3.0e8
    EI = _EI_kNmm2(I, ES_MPA)
    diag = analyze_span(L, w_kNpm=w)
    d_int = midspan_deflection_from_moment_mm(diag.x_mm, diag.M_kNmm, EI)
    d_closed = deflection_udl_simply_supported(w, L, EI)
    assert d_int == pytest.approx(d_closed, rel=2e-3)


def test_chapter_g_web_shear_rolled_w(wdb):
    """AISC G2.1 for rolled W: Aw=d·tw, Vn=0.6 Fy Aw Cv1, φ/Ω per case."""
    shape = wdb.get("W18X35")
    Fy = ksi_to_mpa(50.0)
    Vu = 100.0  # kN demand
    r = web_shear_strength(shape, Fy, Vu, method="LRFD", E_MPa=ES_MPA)
    Aw = shape.d_mm * shape.tw_mm
    assert r.Aw_mm2 == pytest.approx(Aw)
    assert r.Cv1 == pytest.approx(1.0)  # W18×35 still Cv1=1 under G2.1(b)
    assert r.Vn_kN == pytest.approx(0.60 * Fy * Aw / 1000.0, rel=1e-9)
    # W18×35 h/tw approx exceeds 2.24√(E/Fy) → G2.1(b) φv=0.90
    h_tw = (shape.d_mm - 2.0 * shape.tf_mm) / shape.tw_mm
    lim_a = 2.24 * math.sqrt(ES_MPA / Fy)
    if h_tw <= lim_a:
        assert r.section_ref == "G2.1(a)"
        assert r.phiVn_kN == pytest.approx(1.00 * r.Vn_kN)
    else:
        assert r.section_ref == "G2.1(b)"
        assert r.phiVn_kN == pytest.approx(0.90 * r.Vn_kN)
    assert r.DCR == pytest.approx(Vu / r.phiVn_kN)
    assert r.passes is True

    r_asd = web_shear_strength(shape, Fy, Vu, method="ASD", E_MPa=ES_MPA)
    assert r_asd.phiVn_kN == pytest.approx(r_asd.Vn_kN / r_asd.Omega)


def test_engine_reports_shear_dcr(wdb):
    """DesignResult stores shear_strength and Summary/overall include Ch.G."""
    shape = wdb.get("W18X35")
    steel = SteelMaterial.from_grade("A992", tf_mm=shape.tf_mm)
    conc = ConcreteMaterial(fc_MPa=ksi_to_mpa(4.0), Ec_code=EcCode.ACI318)
    L_mm = 9144.0
    slab = SlabConfig(
        t_solid_mm=in_to_mm(4.0),
        hr_mm=0.0,
        orientation=DeckOrientation.NONE,
        fc_MPa=conc.fc_MPa,
        beff_mm=L_mm / 4.0,
    )
    eng = DesignEngine(wdb)
    inp = DesignInputs(
        L_mm=L_mm,
        shape=shape,
        steel=steel,
        concrete=conc,
        slab=slab,
        spacing_left_mm=3000.0,
        spacing_right_mm=3000.0,
        target_composite_ratio=1.0,
        w_SDL_kNpm=2.0,
        w_LL_kNpm=7.0,
        w_construction_kNpm=1.5,
        deck_braces_construction=True,
    )
    res = eng.design(inp, search_passing=False)
    assert res.shear_strength is not None
    assert res.shear_strength.Vu_kN == pytest.approx(res.Vu_kN)
    assert res.shear_strength.phiVn_kN > 0
    assert res.pass_shear == res.shear_strength.passes
    from composite_beam.reporting.summary import summary_lines
    text = "\n".join(summary_lines(res))
    assert "Shear Ch.G" in text
    assert "φVn=" in text
    assert "DCR=" in text
