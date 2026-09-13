"""Cross-section stress viewer: elastic profile signs and no-crash at supports."""

from __future__ import annotations

import pytest

from composite_beam.composite.effective_width import AISCEdition, BeamLocation, effective_width
from composite_beam.composite.slab import DeckOrientation, SlabConfig
from composite_beam.design_engine import DesignEngine, DesignInputs
from composite_beam.materials.concrete import ConcreteMaterial, EcCode
from composite_beam.materials.steel import SteelMaterial
from composite_beam.reporting.charts import cross_section_stress_figure
from composite_beam.reporting.section_stress import (
    elastic_stress_profile,
    moment_at_x_kNm,
    plastic_block_schematic,
)
from composite_beam.units import in_to_mm, ksi_to_mpa


@pytest.fixture
def ss_positive_result(wdb):
    """Simply-supported beam with positive sagging moment under UDL."""
    shape = wdb.get("W18X35")
    steel = SteelMaterial.from_grade("A992", tf_mm=shape.tf_mm)
    L_mm = in_to_mm(30 * 12)
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
    return eng.design(inp, search_passing=False)


def test_midspan_elastic_compression_top_tension_bottom(ss_positive_result):
    res = ss_positive_result
    assert res.shape is not None and res.slab is not None
    x_mid = res.inputs_summary["L_mm"] / 2.0
    M = moment_at_x_kNm(res, x_mid)
    assert M > 0  # sagging

    prof = elastic_stress_profile(res, x_mid)
    assert not prof.hogging
    # Concrete top in compression (negative), steel bottom in tension (positive)
    assert prof.sigma_c_top_MPa < 0
    assert prof.sigma_s_bot_MPa > 0
    # Neutral axis between top of slab and bottom of steel
    assert 0 < prof.y_NA_from_top_mm < prof.total_depth_mm


def test_x0_no_crash(ss_positive_result):
    res = ss_positive_result
    prof = elastic_stress_profile(res, 0.0)
    assert prof.x_mm == 0.0
    # Near support, M ≈ 0 for SS → stresses near zero
    assert abs(prof.M_kNm) < 1.0
    fig = cross_section_stress_figure(res, 0.0, show_plastic_blocks=False)
    assert fig is not None
    assert len(fig.data) >= 1


def test_plastic_toggle_positive(ss_positive_result):
    res = ss_positive_result
    x_mid = res.inputs_summary["L_mm"] / 2.0
    plas = plastic_block_schematic(res, x_mid)
    assert plas.available
    assert plas.M_over_Mn > 0
    fig = cross_section_stress_figure(res, x_mid, show_plastic_blocks=True)
    assert fig is not None
    assert len(fig.layout.annotations) >= 1 or len(fig.data) >= 3


def test_html_includes_cross_section(ss_positive_result):
    from composite_beam.reporting.html_report import result_to_html

    html = result_to_html(ss_positive_result)
    assert "Cross-section stress" in html
