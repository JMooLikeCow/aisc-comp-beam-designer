"""
Acceptance fixtures for AISC composite beam design tool.

Each test docstring states the AISC / ASCE edition locked for that check.
"""

from __future__ import annotations

import math

import pytest

from composite_beam.composite.effective_width import (
    AISCEdition,
    BeamLocation,
    effective_width,
)
from composite_beam.composite.shear_connection import shear_connection
from composite_beam.composite.slab import DeckOrientation, SlabConfig
from composite_beam.composite.studs import StudConfig, StudGoverning, stud_Qn
from composite_beam.design_engine import DesignEngine, DesignInputs
from composite_beam.materials.concrete import ConcreteMaterial, EcCode
from composite_beam.materials.steel import SteelMaterial
from composite_beam.sections.classification import Compactness, classify_flexure
from composite_beam.strength.ltb import construction_LTB
from composite_beam.strength.positive_moment import positive_flexural_strength
from composite_beam.units import ksi_to_mpa, in_to_mm


# ---------------------------------------------------------------------------
# (a) full composite compact W + solid slab
# ---------------------------------------------------------------------------
def test_a_full_composite_compact_solid_slab(wdb):
    """
    Edition: AISC 360-22 §I3.2a / Table B4.1b; ASCE 7-22 gravity.
    Full composite compact W-shape with solid slab — plastic Mn governs design;
    elastic Mn reported but not mixed into φMn.
    """
    shape = wdb.get("W18X35")
    steel = SteelMaterial.from_grade("A992", tf_mm=shape.tf_mm)
    assert steel.Fy_MPa == pytest.approx(ksi_to_mpa(50.0), rel=1e-3)

    cls = classify_flexure(shape, steel.Fy_MPa)
    assert cls.overall == Compactness.COMPACT

    L_mm = in_to_mm(30 * 12)  # 30 ft
    beff = effective_width(
        L_mm, in_to_mm(10 * 12), in_to_mm(10 * 12), BeamLocation.INTERIOR, AISCEdition.AISC360_22
    )
    slab = SlabConfig(
        t_solid_mm=in_to_mm(4.0),
        hr_mm=0.0,
        orientation=DeckOrientation.NONE,
        fc_MPa=ksi_to_mpa(4.0),
        beff_mm=beff.beff_mm,
    )
    conc = ConcreteMaterial(fc_MPa=slab.fc_MPa, Ec_code=EcCode.ACI318)
    stud = StudConfig(diameter_mm=in_to_mm(0.75), Fu_stud_MPa=ksi_to_mpa(65.0))
    qn = stud_Qn(stud, slab, shape.tf_mm, conc.Ec_MPa)
    shear = shear_connection(shape, steel.Fy_MPa, slab, qn, target_ratio=1.0)

    assert shear.is_full
    assert shear.ratio == pytest.approx(1.0, abs=0.01)

    n = steel.Es_MPa / conc.Ec_MPa
    pos = positive_flexural_strength(shape, steel.Fy_MPa, slab, shear, cls, n)

    assert pos.compact is True
    assert pos.used_method == "I3.2a_plastic"
    assert pos.Mn_plastic_kNm > 0
    assert pos.Mn_elastic_kNm > 0
    # Must not silently use elastic when compact
    assert pos.Mn_design_kNm == pytest.approx(pos.Mn_plastic_kNm)
    assert pos.phiMn_kNm == pytest.approx(0.90 * pos.Mn_plastic_kNm)

    # End-to-end engine
    eng = DesignEngine(wdb)
    inp = DesignInputs(
        L_mm=L_mm,
        shape=shape,
        steel=steel,
        concrete=conc,
        slab=slab,
        spacing_left_mm=in_to_mm(10 * 12),
        spacing_right_mm=in_to_mm(10 * 12),
        target_composite_ratio=1.0,
        w_SDL_kNpm=2.0,
        w_LL_kNpm=8.0,
        w_construction_kNpm=1.5,
        deck_braces_construction=True,
        shored=False,
    )
    res = eng.design(inp, search_passing=False)
    assert res.shear.is_full
    assert res.positive_moment.used_method == "I3.2a_plastic"
    assert res.classification.is_compact


# ---------------------------------------------------------------------------
# (b) partial ~50% with deck perpendicular
# ---------------------------------------------------------------------------
def test_b_partial_50pct_deck_perpendicular(wdb):
    """
    Edition: AISC 360-22 §I3.2d / §I8 / Eq. I3-1; deck ribs perpendicular.
    Partial composite ≈50%: Mn reduced vs full; Ieff < I_full; Rg/Rp for perp deck.
    """
    shape = wdb.get("W16X26")
    steel = SteelMaterial.from_grade("A992", tf_mm=shape.tf_mm)
    L_mm = in_to_mm(28 * 12)
    beff = effective_width(
        L_mm, in_to_mm(8 * 12), in_to_mm(8 * 12), BeamLocation.INTERIOR, AISCEdition.AISC360_22
    )
    # 2" deck + 3.25" solid → hr=2 in > 1.5 → Rg=0.85 for 1 stud/rib
    slab = SlabConfig(
        t_solid_mm=in_to_mm(3.25),
        hr_mm=in_to_mm(2.0),
        wr_mm=in_to_mm(6.0),
        orientation=DeckOrientation.PERPENDICULAR,
        fc_MPa=ksi_to_mpa(4.0),
        beff_mm=beff.beff_mm,
    )
    conc = ConcreteMaterial(fc_MPa=slab.fc_MPa)
    stud = StudConfig(diameter_mm=in_to_mm(0.75), Fu_stud_MPa=ksi_to_mpa(65.0))
    qn = stud_Qn(stud, slab, shape.tf_mm, conc.Ec_MPa, n_studs_per_rib=1)
    assert qn.Rg == pytest.approx(0.85)
    assert qn.Rp == pytest.approx(0.75)

    shear_full = shear_connection(shape, steel.Fy_MPa, slab, qn, target_ratio=1.0)
    shear_part = shear_connection(shape, steel.Fy_MPa, slab, qn, target_ratio=0.50)
    assert shear_part.is_partial
    assert shear_part.ratio == pytest.approx(0.50, abs=0.05)

    cls = classify_flexure(shape, steel.Fy_MPa)
    n = steel.Es_MPa / conc.Ec_MPa
    pos_full = positive_flexural_strength(shape, steel.Fy_MPa, slab, shear_full, cls, n)
    pos_part = positive_flexural_strength(shape, steel.Fy_MPa, slab, shear_part, cls, n)
    assert pos_part.Mn_plastic_kNm < pos_full.Mn_plastic_kNm

    from composite_beam.serviceability.deflection import Ieff_partial, transformed_I_full

    I_full, _ = transformed_I_full(shape, slab, n)
    Ieff = Ieff_partial(I_full, shape.Ix_mm4, shear_part.ratio)
    assert Ieff < I_full
    assert Ieff > shape.Ix_mm4


# ---------------------------------------------------------------------------
# (c) edge beam beff
# ---------------------------------------------------------------------------
def test_c_edge_beam_beff():
    """
    Edition: AISC 360-22 §I2.1a (edge beam).
    Edge beff = interior half-spacing side + exterior overhang (not half overhang);
    smaller than equivalent interior with symmetric spacing = 2×overhang.
    """
    L = 9000.0  # mm
    s_adj = 3000.0
    overhang = 1000.0

    edge = effective_width(
        L, s_adj, overhang, BeamLocation.EDGE, AISCEdition.AISC360_22
    )
    # Interior with spacing 2*overhang on "right" would use overhang (half of 2*overhang)
    interior = effective_width(
        L, s_adj, 2.0 * overhang, BeamLocation.INTERIOR, AISCEdition.AISC360_22
    )

    L8 = L / 8.0
    expected_L = min(L8, s_adj / 2.0)
    expected_R = min(L8, overhang)
    assert edge.beff_left_mm == pytest.approx(expected_L)
    assert edge.beff_right_mm == pytest.approx(expected_R)
    assert edge.beff_mm == pytest.approx(expected_L + expected_R)

    # Edge with overhang=1000 equals interior with s_right=2000 for the right side contrib
    assert edge.beff_right_mm == pytest.approx(interior.beff_right_mm)
    # Flag notes mention edition
    assert any("I2.1a" in n for n in edge.notes)
    assert any("360-22" in n for n in edge.notes)

    # Manual override
    ov = effective_width(L, s_adj, overhang, BeamLocation.EDGE, beff_override_mm=2500.0)
    assert ov.beff_mm == pytest.approx(2500.0)
    assert ov.manual_override is True


# ---------------------------------------------------------------------------
# (d) unshored construction LTB pass/fail
# ---------------------------------------------------------------------------
def test_d_unshored_construction_ltb(wdb):
    """
    Edition: AISC 360-22 §F2; construction combo ≠ occupancy (1.2Dwet+1.6C).
    Unshored steel-alone LTB: braced-by-deck passes; long unbraced fails for light shape.
    """
    shape = wdb.get("W12X19")
    Fy = ksi_to_mpa(50.0)
    L = in_to_mm(40 * 12)  # long span

    # Small construction moment → should pass when continuously braced
    Mu_small = 20.0  # kN·m
    braced = construction_LTB(
        shape, Fy, Lb_mm=L, Mu_kNm=Mu_small, braced_by_deck=True, Cb=1.14
    )
    assert braced.passes is True
    assert braced.Lb_mm == pytest.approx(0.0)
    assert braced.limit_state == "yielding_F2-1"

    # Same shape, unbraced full span, large Mu → fail
    Mu_large = braced.phiMn_kNm * 0.95  # near capacity when braced... need unbraced Mn
    unbraced = construction_LTB(
        shape, Fy, Lb_mm=L, Mu_kNm=Mu_large, braced_by_deck=False, Cb=1.0
    )
    # Unbraced Mn should be much lower than braced Mp path
    assert unbraced.Mn_kNm < braced.Mn_kNm
    # Force a fail
    fail = construction_LTB(
        shape, Fy, Lb_mm=L, Mu_kNm=unbraced.phiMn_kNm * 1.25, braced_by_deck=False, Cb=1.0
    )
    assert fail.passes is False
    assert fail.DCR > 1.0

    # Occupancy vs construction: ensure construction notes present
    assert any("Construction combo" in n or "construction" in n.lower() for n in fail.notes)


# ---------------------------------------------------------------------------
# (e) stud governing by concrete vs steel
# ---------------------------------------------------------------------------
def test_e_stud_governing_concrete_vs_steel(wdb):
    """
    Edition: AISC 360-22 §I8.2a Eq. I8-1.
    Low f'c / Ec → concrete crushing governs; high f'c + low Rp*Rg → steel shear governs.
    """
    shape = wdb.get("W14X22")
    stud = StudConfig(diameter_mm=in_to_mm(0.75), Fu_stud_MPa=ksi_to_mpa(65.0))

    # Concrete governs: weak concrete
    slab_weak = SlabConfig(
        t_solid_mm=in_to_mm(3.0),
        hr_mm=0.0,
        orientation=DeckOrientation.NONE,
        fc_MPa=ksi_to_mpa(2.5),  # low
        beff_mm=2000.0,
    )
    Ec_weak = 4700.0 * math.sqrt(slab_weak.fc_MPa)
    qn_weak = stud_Qn(stud, slab_weak, shape.tf_mm, Ec_weak)
    assert qn_weak.governing == StudGoverning.CONCRETE_CRUSHING
    assert qn_weak.Qn_kN == pytest.approx(qn_weak.Qn_concrete_kN)
    assert qn_weak.Qn_concrete_kN < qn_weak.Qn_steel_kN

    # Steel governs: strong concrete + deck perp reducing Rg*Rp
    slab_strong = SlabConfig(
        t_solid_mm=in_to_mm(4.0),
        hr_mm=in_to_mm(3.0),
        orientation=DeckOrientation.PERPENDICULAR,
        fc_MPa=ksi_to_mpa(8.0),
        beff_mm=2000.0,
    )
    Ec_strong = 4700.0 * math.sqrt(slab_strong.fc_MPa)
    qn_strong = stud_Qn(stud, slab_strong, shape.tf_mm, Ec_strong, n_studs_per_rib=1)
    # With high fc, concrete term large; Rg*Rp < 1 reduces steel term → steel governs
    assert qn_strong.Qn_steel_kN < qn_strong.Qn_concrete_kN
    assert qn_strong.governing == StudGoverning.STEEL_SHEAR
    assert qn_strong.diameter_ok is True  # 0.75" vs tf of W14x22
