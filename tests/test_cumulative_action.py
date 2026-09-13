"""Cumulative composite action along span (AISC I3.2d / I8 detailing plot)."""

from __future__ import annotations

import numpy as np
import pytest

from composite_beam.composite.cumulative_action import (
    cumulative_composite_action,
    synthesize_uniform_stud_positions,
)
from composite_beam.composite.effective_width import AISCEdition, BeamLocation, effective_width
from composite_beam.composite.slab import DeckOrientation, SlabConfig
from composite_beam.design_engine import DesignEngine, DesignInputs
from composite_beam.materials.concrete import ConcreteMaterial, EcCode
from composite_beam.materials.steel import SteelMaterial
from composite_beam.units import in_to_mm, ksi_to_mpa


def test_synthesize_uniform_half_span_counts():
    L = 10_000.0
    x_max = 5_000.0
    pos = synthesize_uniform_stud_positions(L, x_max, n_half=10, n_rows=1)
    assert len(pos) == 20
    assert sum(1 for p in pos if p.x_mm <= x_max + 1e-6) == 10
    assert all(0 < p.x_mm < L for p in pos)


def test_ss_full_composite_cumulative_midspan(wdb):
    """
    Simply-supported full-composite: at support ΣQn≈0; at midspan ΣQn≈C_full
    (within stud discretisation); monotonic increase toward midspan for uniform studs.
    """
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
    res = eng.design(inp, search_passing=False)
    assert res.cumulative is not None
    cum = res.cumulative
    assert cum.C_full_kN == pytest.approx(res.shear.C_full_kN)
    assert abs(cum.x_maxM_mm - L_mm / 2.0) < L_mm * 0.05  # near midspan for UDL

    # At left support ≈ 0
    assert float(cum.SumQn_prov_kN[0]) == pytest.approx(0.0, abs=1e-9)
    assert float(cum.alpha[0]) == pytest.approx(0.0, abs=1e-9)

    # At max +M / midspan ≈ C_full (ceil discretisation → within one Qn)
    i_mid = int(np.argmin(np.abs(cum.x_mm - cum.x_maxM_mm)))
    sum_mid = float(cum.SumQn_prov_kN[i_mid])
    Qn = res.stud_qn.Qn_kN
    assert sum_mid == pytest.approx(cum.C_full_kN, abs=Qn * 1.01)
    assert float(cum.alpha[i_mid]) == pytest.approx(1.0, abs=Qn / cum.C_full_kN + 0.02)

    # Left half monotonic non-decreasing toward midspan
    left = cum.x_mm <= cum.x_maxM_mm + 1e-6
    sq_left = cum.SumQn_prov_kN[left]
    assert np.all(np.diff(sq_left) >= -1e-9)

    # F_req at support ~0, at max M ~ C_full
    assert float(cum.F_req_kN[0]) == pytest.approx(0.0, abs=1e-6)
    assert float(cum.F_req_kN[i_mid]) == pytest.approx(cum.C_full_kN, rel=0.02)

    # Notes cite I3.2d / I8
    assert any("I3.2d" in n for n in cum.notes)
    assert any("I8" in n for n in cum.notes)


def test_moment_proportional_with_point_load():
    """F_req follows M(x)/M_max (not triangular x/x_max) under a point load."""
    L = 8000.0
    x = np.linspace(0.0, L, 81)
    # Simply supported midspan point load: triangle moment peaking at mid
    P, a = 40.0, L / 2.0
    R_L = P * (L - a) / L
    M = np.where(x <= a, R_L * x, R_L * a - (P - R_L) * (x - a))  # kN·mm if x in mm... 
    # Use consistent units: treat M as kN·mm with x in mm → scale: R_L[kN]*x[mm]
    M_kNmm = np.where(x <= a, R_L * x, R_L * a - (P - R_L) * (x - a))
    C = 500.0
    Qn = 50.0
    n_half = int(np.ceil(C / Qn))
    res = cumulative_composite_action(
        L,
        C,
        Qn,
        x_mm_diag=x,
        M_kNmm=M_kNmm,
        x_maxM_mm=a,
        n_studs_half_span=n_half,
    )
    # Quarter-span: M = R_L * L/4 = 20*2000 = 40000; M_max = 20*4000 = 80000 → ratio 0.5
    i_q = int(np.argmin(np.abs(res.x_mm - L / 4.0)))
    assert float(res.F_req_kN[i_q]) == pytest.approx(0.5 * C, rel=0.03)
    # At support F_req=0
    assert float(res.F_req_kN[0]) == pytest.approx(0.0, abs=1e-9)
